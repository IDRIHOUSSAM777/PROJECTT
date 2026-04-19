import logging
import math
from typing import Optional
from sqlalchemy import func, or_, case, literal
from sqlalchemy.orm import Session, joinedload
from data import models
from search.nlp_service import (
    NLPParser,
    REGEX_IP,
    REGEX_MAC,
    normalize_text,
    split_words,
    clean_noise_terms,
    detect_language,
)
from search.ranking_service import RankingEngine, MATCH_TIER_BONUS
from search.bm25 import bm25_scorer
from search.semantic_service import semantic_service

logger = logging.getLogger(__name__)

# Poids du score BM25 dans le score final. Un BM25 « solide » (pertinence forte,
# plusieurs tokens en commun) atteint ~10 ; on l'amplifie à ~250 points pour
# rivaliser avec les bonus de palier (exact=500, synonym=250) et dominer quand
# la correspondance textuelle est réelle.
BM25_WEIGHT = 25.0

# Poids sémantique : le score de similarité cosinus [0.0–1.0] est multiplié par
# ce facteur. Max ~150 pts — suffisant pour faire remonter un « bon » match
# sémantique sans jamais écraser un match exact (tier_bonus=500).
SEMANTIC_WEIGHT = 150.0


class SmartSearchEngine:
    """
    Pipeline:
      1. NLP parse (tokenize + filter extraction + intent inference)
      2. Multilingual normalization/translation -> canonical FR terms
      3. Autocorrect typos against domain vocabulary
      4. Query expansion (synonyms + cross-language + feature variants)
      5. SQL retrieval: FTS + ILIKE (entity filters + text match)
      6. Composite scoring in SQL (text_rank, availability, popularity, waiting)
      7. Tiered Python bonus (exact > synonym > fuzzy) + distance / floor boost
      8. pg_trgm fallback when retrieval is empty
    """

    def __init__(self):
        logger.info("⚡ Chargement du Moteur de Recherche (Architecture Multilingue + Tiered Ranking)")
        self.nlp = NLPParser()

    # ─────────────────────────────────────────────────────────────────
    # Tier classification
    # ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _classify_tier(haystack: str, original_terms, synonym_terms, fuzzy_terms) -> str:
        if not haystack:
            return "trigram"
        for t in original_terms:
            if t and len(t) >= 2 and t in haystack:
                return "exact"
        for t in synonym_terms:
            if t and len(t) >= 2 and t in haystack:
                return "synonym"
        for t in fuzzy_terms:
            if t and len(t) >= 2 and t in haystack:
                return "fuzzy"
        return "trigram"

    # ─────────────────────────────────────────────────────────────────
    # Scoring a row set (shared by main query and trigram fallback)
    # ─────────────────────────────────────────────────────────────────
    def _score_rows(
        self,
        rows,
        *,
        raw_query: str = "",
        query_clean: str,
        normalized_query: str,
        expanded_terms,
        original_terms,
        synonym_terms,
        fuzzy_terms,
        sort_by_distance: bool,
        max_distance,
        user_x,
        user_y,
        user_etage,
        debug: bool = False,
    ):
        scored = []

        # Tokens utilisés pour BM25 : on retient les termes étendus de longueur ≥ 2,
        # dédupliqués. C'est aussi ce qui pondère la pertinence textuelle.
        bm25_tokens = list({t for t in (expanded_terms or []) if t and len(t) >= 2})

        for row in rows:
            obj = row.Objet if hasattr(row, "Objet") else row
            sql_score = float(getattr(row, "sql_score", 0.0) or 0.0)

            haystack = RankingEngine.build_haystack(obj) if query_clean else ""

            # ─── Pertinence textuelle : BM25 (Okapi) — re-ranking chirurgical ───
            bm25_raw = bm25_scorer.score(bm25_tokens, obj) if bm25_tokens else 0.0
            bm25_contrib = bm25_raw * BM25_WEIGHT

            # ─── Bonus de phrase entière littérale (les 3 mots collés dans le haystack) ───
            phrase_bonus = 80.0 if (query_clean and normalized_query and normalized_query in haystack) else 0.0

            # ─── Palier de correspondance (exact > synonym > fuzzy > trigram) ───
            tier = (
                self._classify_tier(haystack, original_terms, synonym_terms, fuzzy_terms)
                if query_clean
                else "exact"
            )
            tier_bonus = MATCH_TIER_BONUS.get(tier, 0.0)

            # ─── Bonus contextuel : même étage que l'utilisateur ───
            floor_bonus = 0.0
            if user_etage is not None and obj.salle and obj.salle.num_etage is not None:
                if obj.salle.num_etage == user_etage:
                    floor_bonus = 25.0

            dist = RankingEngine.distance_from_user(obj, user_x, user_y, user_etage)
            distance_bonus = RankingEngine.distance_score(dist) if sort_by_distance else 0.0

            # Filtre max_distance : n'est appliqué que si la distance est
            # calculable. dist=inf signifie "position user inconnue" — dans ce
            # cas on garde l'objet plutôt que de tout masquer silencieusement.
            if (
                max_distance is not None
                and not sort_by_distance
                and math.isfinite(dist)
                and dist > max_distance
            ):
                continue

            # ─── Score sémantique (similarité cosinus via sentence-transformers) ───
            # Active uniquement quand la requête brute est fournie et que les embeddings
            # sont disponibles ; sinon 0.0 (pas d'impact sur le score).
            semantic_sim = semantic_service.score(raw_query, obj) if raw_query else 0.0
            semantic_contrib = semantic_sim * SEMANTIC_WEIGHT

            score = (
                sql_score
                + bm25_contrib
                + phrase_bonus
                + tier_bonus
                + floor_bonus
                + distance_bonus
                + semantic_contrib
            )

            obj.relevance_score = score
            obj.match_tier = tier
            # inf = distance inconnue (coords manquantes ou user non localisé) →
            # on renvoie None pour que le frontend affiche "—" au lieu de "inf m".
            obj.distance_m = dist if math.isfinite(dist) else None

            if debug:
                obj._score_breakdown = {
                    "sql_composite": round(sql_score, 2),
                    "bm25_raw": round(bm25_raw, 3),
                    "bm25_weighted": round(bm25_contrib, 2),
                    "phrase_bonus": phrase_bonus,
                    "tier": tier,
                    "tier_bonus": tier_bonus,
                    "floor_bonus": floor_bonus,
                    "distance_bonus": round(distance_bonus, 2),
                    "distance_m": None if not math.isfinite(dist) else round(dist, 2),
                    "semantic_similarity": round(semantic_sim, 4),
                    "semantic_contrib": round(semantic_contrib, 2),
                    "total": round(score, 2),
                }

            scored.append((obj, dist))
        return scored

    # ─────────────────────────────────────────────────────────────────
    # Trigram (pg_trgm) fallback — runs when main SQL returns nothing
    # ─────────────────────────────────────────────────────────────────
    def _trigram_fallback(self, db: Session, query_clean: str, normalized_query: str):
        if not query_clean:
            return []
        try:
            sim = RankingEngine.sql_trgm_similarity(query_clean).label("trgm_sim")
            # Score: availability + similarity*300 so a decent near-miss doesn't outrank a real match.
            avail = RankingEngine.sql_availability_score()
            composite = (avail + sim * 300.0).label("sql_score")
            rows = (
                db.query(models.Objet, sim, composite.label("sql_score"))
                .options(joinedload(models.Objet.salle), joinedload(models.Objet.fonctionnalites))
                .outerjoin(models.Salle)
                .filter(sim > 0.18)
                .order_by(sim.desc())
                .limit(20)
                .all()
            )
            return rows
        except Exception as e:
            logger.warning(f"Trigram fallback unavailable (pg_trgm?): {e}")
            return []

    # ─────────────────────────────────────────────────────────────────
    # Main entry point — identical signature to previous implementation
    # ─────────────────────────────────────────────────────────────────
    def search(
        self,
        db: Session,
        query: str = None,
        filtre_etage_id: int = None,
        filtre_salle_id: int = None,
        filtre_type: str = None,
        filtre_marque: str = None,
        filtre_statut: str = None,
        filtre_fonction: str = None,
        sort_by_distance: bool = False,
        max_distance: float = None,
        sort_by: str = None,
        user_x: Optional[float] = None,
        user_y: Optional[float] = None,
        user_etage: Optional[int] = None,
        debug: bool = False,
    ):
        raw_query = (query or "").strip()
        lang = detect_language(raw_query) if raw_query else "latin"

        # Fast-path: IP / MAC address shortcuts
        if raw_query:
            if REGEX_IP.match(raw_query):
                return db.query(models.Objet).filter(models.Objet.ip_adress == raw_query).all()
            if REGEX_MAC.match(raw_query):
                return db.query(models.Objet).filter(models.Objet.mac_adresse == raw_query).all()

        # ── 1. NLP pipeline ───────────────────────────────────────────
        tokens = self.nlp.extract_tokens(raw_query)
        available_types = self.nlp.load_available_types(db)
        available_marques = self.nlp.load_available_marques(db)
        available_fonctions = self.nlp.load_available_fonctions(db)
        available_salles = self.nlp.load_available_salles(db)

        nlp_filters, cleaned_terms = self.nlp.extract_filters(
            raw_query, tokens, available_types, available_marques, available_fonctions, available_salles
        )
        vocabulary = self.nlp.load_domain_vocabulary(db)

        # Track the raw (user-typed, normalized) terms BEFORE correction/translation — used for tier=exact.
        original_terms = list(cleaned_terms)

        corrected_terms, corrections = self.nlp.autocorrect_terms(cleaned_terms, vocabulary)
        expanded_terms = self.nlp.expand_terms(corrected_terms)

        normalized_query = normalize_text(raw_query)
        if not expanded_terms and normalized_query:
            fallback_terms = clean_noise_terms(split_words(normalized_query))
            original_terms = fallback_terms
            expanded_terms = self.nlp.expand_terms(fallback_terms)

        # Split expansion into tiers for later scoring:
        #   synonym_terms = terms added by expansion OR translation (i.e. not the user's literal word but known synonyms)
        #   fuzzy_terms   = corrected typos (the user wrote X, we matched against Y)
        original_set = set(original_terms)
        corrected_set = set(corrected_terms)
        synonym_terms = [t for t in expanded_terms if t not in original_set and t not in corrected_set]
        fuzzy_terms = list((corrected_set - original_set) | set(corrections.values()))

        # Type inference fallback (when no explicit filter)
        if not filtre_type and not nlp_filters.get("type_objet"):
            inferred = self.nlp.infer_type_from_terms(
                expanded_terms or tokens, available_types, normalized_query
            )
            if inferred:
                nlp_filters["type_objet"] = inferred

        # Remove filter words from text-search so they're not double-counted
        terms_to_exclude = []
        if nlp_filters.get("salle_text_raw"):
            terms_to_exclude.extend(normalize_text(nlp_filters.get("salle_text_raw")).split())
        if nlp_filters.get("etage_text_raw"):
            terms_to_exclude.extend(normalize_text(nlp_filters.get("etage_text_raw")).split())

        target_type = filtre_type if filtre_type else nlp_filters.get("type_objet")
        target_marque = filtre_marque if filtre_marque else nlp_filters.get("nom_marque")
        target_fonction = filtre_fonction if filtre_fonction else nlp_filters.get("fonction")

        if target_type:
            terms_to_exclude.append(normalize_text(target_type))
            for k, v in self.nlp.type_alias_to_canonical.items():
                if v == target_type:
                    terms_to_exclude.extend(k.split())
        if target_marque:
            terms_to_exclude.extend(normalize_text(target_marque).split())
        if target_fonction:
            terms_to_exclude.extend(normalize_text(target_fonction).split())

        from search.nlp_service import STATUS_KEYWORDS
        for kws in STATUS_KEYWORDS.values():
            terms_to_exclude.extend(kws)

        filtered_terms = [t for t in expanded_terms if t not in terms_to_exclude]
        query_clean = " ".join(t for t in filtered_terms if len(t) >= 2).strip()

        # ── 2. Build SQL query ────────────────────────────────────────
        sql = db.query(models.Objet).options(
            joinedload(models.Objet.salle),
            joinedload(models.Objet.fonctionnalites),
        )

        target_etage = filtre_etage_id if filtre_etage_id is not None else nlp_filters.get("num_etage")
        target_statut = filtre_statut if filtre_statut is not None else nlp_filters.get("statut")
        target_salle_text = nlp_filters.get("salle_text")

        joined_salle = False
        if (
            target_etage is not None
            or filtre_salle_id is not None
            or sort_by_distance
            or max_distance is not None
            or target_salle_text
        ):
            sql = sql.join(models.Salle)
            joined_salle = True

        if target_fonction:
            sql = sql.join(models.Objet.fonctionnalites)

        if target_etage is not None:
            sql = sql.filter(models.Salle.num_etage == target_etage)
        if target_salle_text:
            sql = sql.filter(models.Salle.nom_salle == target_salle_text)
        if filtre_salle_id is not None:
            sql = sql.filter(models.Salle.id_salle == filtre_salle_id)
        if target_type:
            sql = sql.filter(models.Objet.type_objet.ilike(f"%{target_type}%"))
        if target_marque:
            sql = sql.filter(models.Objet.nom_marque.ilike(f"%{target_marque}%"))
        if target_statut:
            sql = sql.filter(models.Objet.statut.ilike(f"%{target_statut}%"))
        if target_fonction:
            sql = sql.filter(models.Fonctionnalite.nom.ilike(f"%{target_fonction}%"))

        has_entity_filters = any([
            target_etage is not None,
            target_salle_text,
            filtre_salle_id is not None,
            target_type,
            target_marque,
            target_statut,
            target_fonction,
        ])

        if query_clean:
            if not joined_salle:
                sql = sql.join(models.Salle)
                joined_salle = True

            document = func.concat_ws(
                " ",
                func.coalesce(models.Objet.nom_model, ""),
                func.coalesce(models.Objet.type_objet, ""),
                func.coalesce(models.Objet.nom_marque, ""),
                func.coalesce(models.Objet.description, ""),
                func.coalesce(models.Salle.nom_salle, ""),
            )
            fts_condition = document.op("@@")(func.plainto_tsquery("simple", query_clean))

            fallback_conditions = []
            for term in expanded_terms:
                if len(term) >= 2:
                    like_term = f"%{term}%"
                    fallback_conditions.extend([
                        models.Objet.nom_model.ilike(like_term),
                        models.Objet.type_objet.ilike(like_term),
                        models.Objet.nom_marque.ilike(like_term),
                        models.Objet.description.ilike(like_term),
                        models.Salle.nom_salle.ilike(like_term),
                    ])

            if not has_entity_filters:
                if fallback_conditions:
                    sql = sql.filter(or_(fts_condition, *fallback_conditions))
                else:
                    sql = sql.filter(fts_condition)

        # ── 3. Composite scoring in SQL ───────────────────────────────
        text_rank_col = RankingEngine.sql_text_rank(query_clean)
        avail_col = RankingEngine.sql_availability_score()
        pop_col = RankingEngine.sql_popularity_score()
        wait_col = RankingEngine.sql_waiting_score()

        pop_bonus = case((pop_col * 2 > 30, 30.0), else_=pop_col * 2.0)
        wait_penalty = case((wait_col * 5 > 40, 40.0), else_=wait_col * 5.0)

        composite_score = text_rank_col * 100.0 + avail_col + pop_bonus - wait_penalty

        sql = sql.add_columns(
            text_rank_col.label("text_rank"),
            avail_col.label("availability_score"),
            pop_col.label("pop_count"),
            wait_col.label("wait_count"),
            composite_score.label("sql_score"),
        )

        if sort_by == "distance" or sort_by_distance:
            sql = sql.order_by(composite_score.desc()).limit(200)
        elif sort_by == "popularity":
            sql = sql.order_by(pop_col.desc(), composite_score.desc()).limit(50)
        else:
            sql = sql.order_by(composite_score.desc()).limit(50)

        rows = sql.all()

        # ── 4. pg_trgm fallback when retrieval is empty ───────────────
        used_fallback = False
        if not rows and query_clean and not has_entity_filters:
            logger.info(f"[Search] No FTS/ILIKE hit for '{raw_query}' (lang={lang}) — trying pg_trgm fallback")
            rows = self._trigram_fallback(db, query_clean, normalized_query)
            used_fallback = True

        if not rows:
            return []

        # ── 5. BM25 + Semantic stats (lazy build, cached 1 h dans Redis + 120 s RAM) ──
        if query_clean:
            bm25_scorer.build(db)
            semantic_service.build(db)  # builds corpus embeddings if not cached

        # ── 6. Python-side scoring : BM25 + semantic + palier + contexte ────
        scored_results = self._score_rows(
            rows,
            raw_query=raw_query,
            query_clean=query_clean,
            normalized_query=normalized_query,
            expanded_terms=expanded_terms,
            original_terms=original_terms,
            synonym_terms=synonym_terms,
            fuzzy_terms=fuzzy_terms,
            sort_by_distance=sort_by_distance,
            max_distance=max_distance,
            user_x=user_x,
            user_y=user_y,
            user_etage=user_etage,
            debug=debug,
        )

        if used_fallback:
            # Penalise trigram-only hits so they sort below any real match that follows.
            for obj, _ in scored_results:
                obj.match_tier = "trigram"

        # ── 6. Final sort ─────────────────────────────────────────────
        if sort_by == "distance" or sort_by_distance:
            def distance_key(x):
                obj, d = x[0], x[1]
                etage_diff = 0
                if user_etage is not None and obj.salle and obj.salle.num_etage is not None:
                    etage_diff = abs(obj.salle.num_etage - user_etage)
                dt = d if math.isfinite(d) else float("inf")
                return (etage_diff, dt, -getattr(obj, "relevance_score", 0.0))

            scored_results.sort(key=distance_key)
        else:
            scored_results.sort(key=lambda x: getattr(x[0], "relevance_score", 0.0), reverse=True)

        return [item[0] for item in scored_results][:50]

    def suggest(self, db: Session, query: str, limit: int = 8):
        query = (query or "").strip().lower()
        if len(query) < 2:
            return []

        vocab = self.nlp.load_domain_vocabulary(db)
        suggestions = []

        for v in vocab:
            if v.startswith(query):
                suggestions.append({"label": v, "score": 100})
            elif query in v:
                suggestions.append({"label": v, "score": 80})

        from search.nlp_service import fuzz, process
        best_match = process.extractOne(query, vocab, scorer=fuzz.WRatio, score_cutoff=70)
        if best_match:
            suggestions.append({"label": best_match[0], "score": best_match[1]})
        for v in vocab:
            score = fuzz.WRatio(query, v)
            if score >= 70 and not any(s["label"] == v for s in suggestions):
                suggestions.append({"label": v, "score": score})

        seen, final = set(), []
        for s in sorted(suggestions, key=lambda x: x["score"], reverse=True):
            if s["label"] not in seen:
                seen.add(s["label"])
                final.append(s["label"])

        return final[:limit]


engine = SmartSearchEngine()
