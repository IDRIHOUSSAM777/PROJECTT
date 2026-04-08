import math
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload
from data import models
from search.nlp_service import NLPParser, REGEX_IP, REGEX_MAC, normalize_text, split_words, clean_noise_terms
from search.ranking_service import RankingEngine, CANCELLED_STATUSES

class SmartSearchEngine:
    def __init__(self):
        print("⚡ Chargement du Moteur de Recherche (Architecture Micro-services)...")
        self.nlp = NLPParser()

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
        user_x: float = 0.0,
        user_y: float = 0.0,
        user_etage: int = None,
    ):
        raw_query = (query or "").strip()

        if raw_query:
            if REGEX_IP.match(raw_query):
                return db.query(models.Objet).filter(models.Objet.ip_adress == raw_query).all()
            if REGEX_MAC.match(raw_query):
                return db.query(models.Objet).filter(models.Objet.mac_adresse == raw_query).all()

        tokens = self.nlp.extract_tokens(raw_query)
        available_types = self.nlp.load_available_types(db)
        available_marques = self.nlp.load_available_marques(db)
        available_fonctions = self.nlp.load_available_fonctions(db)
        available_salles = self.nlp.load_available_salles(db)

        nlp_filters, cleaned_terms = self.nlp.extract_filters(
            raw_query, tokens, available_types, available_marques, available_fonctions, available_salles
        )
        vocabulary = self.nlp.load_domain_vocabulary(db)

        corrected_terms, _ = self.nlp.autocorrect_terms(cleaned_terms, vocabulary)
        expanded_terms = self.nlp.expand_terms(corrected_terms)

        normalized_query = normalize_text(raw_query)
        if not expanded_terms and normalized_query:
            expanded_terms = self.nlp.expand_terms(clean_noise_terms(split_words(normalized_query)))

        if not filtre_type and not nlp_filters.get("type_objet"):
            inferred_type = self.nlp.infer_type_from_terms(expanded_terms or tokens, available_types, normalized_query)
            if inferred_type:
                nlp_filters["type_objet"] = inferred_type

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
                if v == target_type: terms_to_exclude.extend(k.split())
        if target_marque: terms_to_exclude.extend(normalize_text(target_marque).split())
        if target_fonction: terms_to_exclude.extend(normalize_text(target_fonction).split())
        
        from search.nlp_service import STATUS_KEYWORDS
        for kws in STATUS_KEYWORDS.values():
            terms_to_exclude.extend(kws)
        
        filtered_terms = [t for t in expanded_terms if t not in terms_to_exclude]
        query_clean = " ".join([term for term in filtered_terms if len(term) >= 2]).strip()

        sql = db.query(models.Objet).options(joinedload(models.Objet.salle), joinedload(models.Objet.fonctionnalites))

        target_etage = filtre_etage_id if filtre_etage_id is not None else nlp_filters.get("num_etage")
        target_statut = filtre_statut if filtre_statut is not None else nlp_filters.get("statut")
        target_salle_text = nlp_filters.get("salle_text")

        joined_salle = False

        if target_etage is not None or filtre_salle_id is not None or sort_by_distance or max_distance is not None or target_salle_text:
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

        if query_clean:
            if not joined_salle:
                sql = sql.join(models.Salle)
                joined_salle = True
            
            # PostgreSQL FTS
            document = func.concat_ws(" ",
                func.coalesce(models.Objet.nom_model, ""),
                func.coalesce(models.Objet.type_objet, ""),
                func.coalesce(models.Objet.nom_marque, ""),
                func.coalesce(models.Objet.description, ""),
                func.coalesce(models.Salle.nom_salle, "")
            )
            fts_condition = document.op('@@')(func.plainto_tsquery('simple', query_clean))
            
            fallback_conditions = []
            for term in expanded_terms:
                if len(term) >= 2:
                    like_term = f"%{term}%"
                    fallback_conditions.extend([
                        models.Objet.nom_model.ilike(like_term),
                        models.Objet.type_objet.ilike(like_term),
                        models.Objet.nom_marque.ilike(like_term),
                        models.Objet.description.ilike(like_term),
                        models.Salle.nom_salle.ilike(like_term)
                    ])

            if fallback_conditions:
                sql = sql.filter(or_(fts_condition, *fallback_conditions))
            else:
                sql = sql.filter(fts_condition)

        # ── COMPOSITE SCORE IN SQL (Scalability: sort + limit in DB) ──
        from sqlalchemy import case, literal
        from sqlalchemy.sql import functions as sqlfunc

        text_rank_col = RankingEngine.sql_text_rank(query_clean)
        avail_col = RankingEngine.sql_availability_score()
        pop_col = RankingEngine.sql_popularity_score()
        wait_col = RankingEngine.sql_waiting_score()

        # Clamp popularity bonus: min(pop * 2, 30)
        pop_bonus = case(
            (pop_col * 2 > 30, 30.0),
            else_=pop_col * 2.0
        )
        # Clamp waiting penalty: min(wait * 5, 40)
        wait_penalty = case(
            (wait_col * 5 > 40, 40.0),
            else_=wait_col * 5.0
        )

        composite_score = (text_rank_col * 100.0 + avail_col + pop_bonus - wait_penalty)

        sql = sql.add_columns(
            text_rank_col.label("text_rank"),
            avail_col.label("availability_score"),
            pop_col.label("pop_count"),
            wait_col.label("wait_count"),
            composite_score.label("sql_score")
        )

        # Apply ORDER BY + LIMIT at SQL level (avoid loading 10K+ rows in RAM)
        if sort_by == 'distance' or sort_by_distance:
            # Distance requires Python (user coords), but pre-limit to top 200 by score
            sql = sql.order_by(composite_score.desc()).limit(200)
        elif sort_by == 'popularity':
            sql = sql.order_by(pop_col.desc(), composite_score.desc()).limit(50)
        else:
            sql = sql.order_by(composite_score.desc()).limit(50)

        all_objs = sql.all()
        if not all_objs: return []

        scored_results = []
        for row in all_objs:
            obj = row.Objet
            score = float(row.sql_score or 0.0)

            # Python-side bonus: exact match + term overlap (lightweight on ≤50 rows)
            if query_clean:
                haystack = RankingEngine.build_haystack(obj)
                if normalized_query and normalized_query in haystack:
                    score += 80.0
                matched_terms = sum(1 for term in expanded_terms if len(term) >= 2 and term in haystack)
                score += matched_terms * 15.0
                if expanded_terms:
                    score += (matched_terms / len(expanded_terms)) * 20.0

            dist = RankingEngine.distance_from_user(obj, user_x, user_y, user_etage)
            if sort_by_distance:
                score += RankingEngine.distance_score(dist)

            # Filter by max distance if requested
            if max_distance is not None and not sort_by_distance:
                if dist > max_distance:
                    continue

            obj.relevance_score = score
            obj.distance_m = dist
            scored_results.append((obj, dist))

        # Final sort in Python (on the small ≤50/200 result set)
        if sort_by == 'distance' or sort_by_distance:
            def distance_key(x):
                obj, d = x[0], x[1]
                # Priority 1: Floor difference (so same floor is ALWAYS first)
                etage_diff = 0
                if user_etage is not None and obj.salle and obj.salle.num_etage is not None:
                    etage_diff = abs(obj.salle.num_etage - user_etage)
                
                # Priority 2: Physical Distance
                dt = d if math.isfinite(d) else float('inf')
                
                # Priority 3: Relevance fallback
                return (etage_diff, dt, -getattr(obj, 'relevance_score', 0.0))
                
            scored_results.sort(key=distance_key)
        else:
            scored_results.sort(key=lambda x: getattr(x[0], 'relevance_score', 0.0), reverse=True)

        final_objects = [item[0] for item in scored_results][:50]
        return final_objects

    def suggest(self, db: Session, query: str, limit: int = 8):
        query = (query or "").strip().lower()
        if len(query) < 2: return []
        
        vocab = self.nlp.load_domain_vocabulary(db)
        suggestions = []
        
        for v in vocab:
            if v.startswith(query): suggestions.append({"label": v, "score": 100})
            elif query in v: suggestions.append({"label": v, "score": 80})
        
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
