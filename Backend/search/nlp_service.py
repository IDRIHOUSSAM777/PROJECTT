import re
import time
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

try:
    import spacy
except Exception:
    spacy = None

try:
    from rapidfuzz import fuzz, process
except Exception:

    class _FuzzFallback:
        @classmethod
        def _ratio(cls, a: str, b: str) -> float:
            if not a or not b:
                return 0.0
            return SequenceMatcher(None, a, b).ratio() * 100

        @classmethod
        def token_set_ratio(cls, a: str, b: str) -> float:
            from itertools import product
            parts_a = set(a.split())
            parts_b = set(b.split())
            if not parts_a or not parts_b:
                return 0.0
            return max(cls._ratio(i, j) for i, j in product(parts_a, parts_b))

        @classmethod
        def partial_ratio(cls, a: str, b: str) -> float:
            if not a or not b:
                return 0.0
            if len(a) <= len(b):
                short, long = a, b
            else:
                short, long = b, a
            best = 0.0
            for i in range(len(long) - len(short) + 1):
                sub = long[i : i + len(short)]
                best = max(best, cls._ratio(short, sub))
            return best

        @classmethod
        def WRatio(cls, a: str, b: str) -> float:
            return max(cls._ratio(a, b), cls.partial_ratio(a, b), cls.token_set_ratio(a, b))

    class _ProcessFallback:
        @classmethod
        def extractOne(cls, query: str, choices: List[str], scorer=None, score_cutoff: float = 0.0) -> Optional[Tuple[str, float]]:
            if not choices or not query:
                return None
            scorer_func = scorer if scorer else _FuzzFallback.WRatio
            best_match = None
            best_score = -1.0
            for choice in choices:
                score = scorer_func(query, choice)
                if score > best_score and score >= score_cutoff:
                    best_score = score
                    best_match = choice
            return (best_match, best_score, 0) if best_match else None

    fuzz = _FuzzFallback()
    process = _ProcessFallback()


import json
import os
from sqlalchemy.orm import Session
from data import models

# Load NLP settings from external config file
NLP_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nlp_rules.json")

try:
    with open(NLP_RULES_PATH, "r", encoding="utf-8") as f:
        nlp_rules = json.load(f)
except FileNotFoundError:
    print(f"⚠️ NLP RULES FILE NOT FOUND AT {NLP_RULES_PATH}. USING EMPTY DEFAULTS.")
    nlp_rules = {"TYPE_KEYWORDS": {}, "TYPE_INTENT_PATTERNS": {}, "NOISE_TERMS": []}

TYPE_KEYWORDS = {k: set(v) for k, v in nlp_rules.get("TYPE_KEYWORDS", {}).items()}
TYPE_INTENT_PATTERNS = {
    k: [re.compile(pattern, re.IGNORECASE) for pattern in v]
    for k, v in nlp_rules.get("TYPE_INTENT_PATTERNS", {}).items()
}
NOISE_TERMS = set(nlp_rules.get("NOISE_TERMS", []))

STATUS_KEYWORDS = {
    "Disponible": {"disponible", "dispo", "libre", "available", "free", "ready", "متاح", "فارغ"},
    "Occupé": {"occupe", "occupé", "busy", "reserved", "reserve", "used", "محجوز", "مشغول"},
    "Panne": {"panne", "hs", "error", "critical", "broken", "down", "معطل", "عطل"},
}

REGEX_FLOOR_1 = re.compile(r"(?:etage|étage|niveau|floor|طابق|الطابق)\s*(\d+)", re.IGNORECASE)
REGEX_FLOOR_2 = re.compile(r"(\d+)\s*(?:er|e|eme)?\s*(?:etage|étage|niveau|floor)", re.IGNORECASE)
REGEX_ROOM = re.compile(r"(?:salle|room|قاعة|غرفة)\s*([\w\-]+)", re.IGNORECASE)
REGEX_IP = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
REGEX_MAC = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


def normalize_text(value: Optional[str]) -> str:
    if not value: return ""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(c))
    return stripped.lower().strip()

def split_words(value: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9؀-ۿ]+", normalize_text(value), flags=re.UNICODE) if w]

def clean_noise_terms(terms: List[str]) -> List[str]:
    cleaned = []
    seen = set()
    for term in terms:
        norm = normalize_text(term)
        if not norm or norm in NOISE_TERMS or (len(norm) < 2 and not norm.isdigit()) or norm in seen:
            continue
        seen.add(norm)
        cleaned.append(norm)
    return cleaned


class NLPParser:
    def __init__(self):
        self.nlp = None
        if spacy is not None:
            try:
                self.nlp = spacy.load("fr_core_news_sm")
            except Exception:
                pass

        self.type_alias_to_canonical: Dict[str, str] = {}
        for canonical, aliases in TYPE_KEYWORDS.items():
            self.type_alias_to_canonical[normalize_text(canonical)] = canonical
            for alias in aliases:
                self.type_alias_to_canonical[normalize_text(alias)] = canonical

        self.intent_patterns = TYPE_INTENT_PATTERNS
        self._vocab_cache_at = 0.0
        self._vocab_cache_terms: List[str] = []
        
        # Use centralized Redis for vocab cache
        from data.redis_client import redis_client
        self.redis_client = redis_client
        import logging
        self.logger = logging.getLogger(__name__)

    def extract_tokens(self, query: str) -> List[str]:
        query = (query or "").strip()
        if not query: return []

        if self.nlp:
            doc = self.nlp(query)
            terms = []
            for token in doc:
                if token.is_space or token.is_punct or token.is_stop: continue
                if token.like_num:
                    terms.append(token.text.lower())
                    continue
                lemma = (token.lemma_ or token.text).lower().strip()
                if not lemma: continue
                chunks = split_words(lemma)
                if chunks: terms.extend(chunks)
                else: terms.append(normalize_text(lemma))
            if terms: return terms
        return split_words(query)

    def load_available_types(self, db: Session) -> List[str]:
        rows = db.query(models.Objet.type_objet).filter(models.Objet.type_objet.isnot(None)).distinct().all()
        return [str(row[0]).strip() for row in rows if row and row[0]]

    def load_available_marques(self, db: Session) -> List[str]:
        rows = db.query(models.Objet.nom_marque).filter(models.Objet.nom_marque.isnot(None)).distinct().all()
        return [str(row[0]).strip() for row in rows if row and row[0]]

    def load_available_fonctions(self, db: Session) -> List[str]:
        rows = db.query(models.Fonctionnalite.nom).filter(models.Fonctionnalite.nom.isnot(None)).distinct().all()
        return [str(row[0]).strip() for row in rows if row and row[0]]

    def load_available_salles(self, db: Session) -> List[str]:
        rows = db.query(models.Salle.nom_salle).filter(models.Salle.nom_salle.isnot(None)).distinct().all()
        return [str(row[0]).strip() for row in rows if row and row[0]]

    def load_domain_vocabulary(self, db: Session) -> List[str]:
        cache_key = "nlp_domain_vocabulary"
        
        # 1. Check Redis Cache First
        if self.redis_client:
            try:
                cached_vocab = self.redis_client.get(cache_key)
                if cached_vocab:
                    return json.loads(cached_vocab)
            except Exception as e:
                self.logger.error(f"⚠️ Redis GET error for NLP vocabulary: {e}")

        # 2. Check InMemory Cache (Fallback)
        now = time.time()
        if self._vocab_cache_terms and (now - self._vocab_cache_at) < 45: 
            return self._vocab_cache_terms
            
        # 3. Build from Database
        terms: Set[str] = set()
        def add_term(val):
            norm = normalize_text(val)
            if not norm: return
            if len(norm) >= 2: terms.add(norm)
            for chunk in split_words(norm):
                if len(chunk) >= 3: terms.add(chunk)

        for col in [models.Objet.type_objet, models.Objet.nom_marque, models.Objet.nom_model, models.Objet.description]:
            for r in db.query(col).filter(col.isnot(None)).distinct().limit(400).all(): add_term(r[0] if r else None)
        for r in db.query(models.Salle.nom_salle).filter(models.Salle.nom_salle.isnot(None)).distinct().limit(200).all(): add_term(r[0] if r else None)
        for r in db.query(models.Fonctionnalite.nom).filter(models.Fonctionnalite.nom.isnot(None)).distinct().limit(200).all(): add_term(r[0] if r else None)
        for alias in self.type_alias_to_canonical.keys():
            if alias and len(alias) >= 3: terms.add(alias)
        
        self._vocab_cache_terms = sorted(terms)
        self._vocab_cache_at = now
        
        # 4. Save to Redis
        if self.redis_client:
            try:
                self.redis_client.set(cache_key, json.dumps(self._vocab_cache_terms), ex=3600) # Cache for 1 hour
            except Exception as e:
                self.logger.error(f"⚠️ Redis SET error for NLP vocabulary: {e}")

        return self._vocab_cache_terms

    def resolve_to_available_type(self, canonical_type: str, available_types: List[str]) -> str:
        if not canonical_type or not available_types: return canonical_type
        target = normalize_text(canonical_type)
        norm_map = {normalize_text(t): t for t in available_types}
        if target in norm_map: return norm_map[target]
        for v_norm, v_orig in norm_map.items():
            if target and (target in v_norm or v_norm in target): return v_orig
        best = process.extractOne(target, list(norm_map.keys()), scorer=fuzz.WRatio, score_cutoff=80)
        return norm_map[best[0]] if best else canonical_type

    def infer_type_from_intent(self, norm_query: str, available_types: List[str]) -> Optional[str]:
        if not norm_query: return None
        for canonical, patterns in self.intent_patterns.items():
            if patterns and any(p.search(norm_query) for p in patterns):
                return self.resolve_to_available_type(canonical, available_types)
        return None

    def infer_type_from_terms(self, terms: List[str], available_types: List[str], norm_query: str) -> Optional[str]:
        for alias, canonical in self.type_alias_to_canonical.items():
            if alias and alias in norm_query: return self.resolve_to_available_type(canonical, available_types)
            
        norm_map = {normalize_text(t): t for t in available_types}
        all_keys = list(norm_map.keys()) + list(self.type_alias_to_canonical.keys())
        best_type, best_score = None, 0.0
        
        for term in terms:
            n_term = normalize_text(term)
            if not n_term or n_term in NOISE_TERMS: continue
            if n_term in self.type_alias_to_canonical: return self.resolve_to_available_type(self.type_alias_to_canonical[n_term], available_types)
            if n_term in norm_map: return norm_map[n_term]
            
            best = process.extractOne(n_term, all_keys, scorer=fuzz.WRatio, score_cutoff=83)
            if best and float(best[1]) > best_score:
                best_score = float(best[1])
                matched_key = best[0]
                if matched_key in norm_map:
                    best_type = norm_map[matched_key]
                else:
                    best_type = self.resolve_to_available_type(self.type_alias_to_canonical[matched_key], available_types)
        return best_type

    def best_value_from_query(self, terms: List[str], norm_query: str, values: List[str], score_cutoff: float = 88.0) -> Optional[str]:
        if not values: return None
        norm_map = {normalize_text(v): v for v in values if normalize_text(v)}
        if not norm_map: return None
        for v_norm, v_orig in norm_map.items():
            if len(v_norm) >= 3 and v_norm in norm_query: return v_orig
        best_value, best_score = None, 0.0
        for term in terms:
            n_term = normalize_text(term)
            if not n_term or n_term in NOISE_TERMS: continue
            if n_term in norm_map: return norm_map[n_term]
            if n_term.isdigit() or len(n_term) < 3: continue
            best = process.extractOne(n_term, list(norm_map.keys()), scorer=fuzz.WRatio, score_cutoff=score_cutoff)
            if best and float(best[1]) > best_score:
                best_score = float(best[1])
                best_value = norm_map.get(best[0])
        return best_value

    def resolve_salle_name(self, raw_val: str, avail_salles: List[str]) -> str:
        if not raw_val: return "NON_EXISTENT_SALLE"
        norm_val = normalize_text(raw_val)
        norm_map = {normalize_text(v): v for v in avail_salles}
        
        if norm_val in norm_map: return norm_map[norm_val]
        if "salle " + norm_val in norm_map: return norm_map["salle " + norm_val]
        if "salle" + norm_val in norm_map: return norm_map["salle" + norm_val]
        
        for v_norm, v_orig in norm_map.items():
            if norm_val in v_norm.split() or norm_val in v_norm.split("-"):
                return v_orig
                
        if len(norm_val) >= 3:
            best = process.extractOne(norm_val, list(norm_map.keys()), scorer=fuzz.WRatio, score_cutoff=85)
            if best: return norm_map[best[0]]
            
        return "NON_EXISTENT_SALLE"

    def extract_filters(self, query: str, tokens: List[str], avail_types: List[str], avail_marques: List[str], avail_fonctions: List[str], avail_salles: List[str] = []) -> Tuple[Dict, List[str]]:
        filters = {}
        norm_query = normalize_text(query)
        norm_tokens = [normalize_text(t) for t in tokens if normalize_text(t)]
        token_set = set(norm_tokens)

        for status, kws in STATUS_KEYWORDS.items():
            if any(kw in norm_query for kw in kws) or any(kw in token_set for kw in kws):
                filters["statut"] = status
                break
        
        m_floor = REGEX_FLOOR_1.search(query) or REGEX_FLOOR_2.search(query)
        if m_floor:
            try: 
                filters["num_etage"] = int(m_floor.group(1))
                filters["etage_text_raw"] = m_floor.group(0)
            except: pass
        m_room = REGEX_ROOM.search(query)
        if m_room and m_room.group(1): 
            exact_salle = self.resolve_salle_name(m_room.group(1).strip(), avail_salles)
            filters["salle_text"] = exact_salle
            filters["salle_text_raw"] = m_room.group(0)

        cleaned_terms = clean_noise_terms(norm_tokens)

        if not filters.get("salle_text"):
            inferred_salle = self.best_value_from_query(cleaned_terms or norm_tokens, norm_query, avail_salles, 85)
            if inferred_salle:
                filters["salle_text"] = inferred_salle
                filters["salle_text_raw"] = inferred_salle
        
        inferred_type = self.infer_type_from_intent(norm_query, avail_types)
        if not inferred_type: inferred_type = self.infer_type_from_terms(cleaned_terms or norm_tokens, avail_types, norm_query)
        if inferred_type: filters["type_objet"] = inferred_type

        inferred_marque = self.best_value_from_query(cleaned_terms or norm_tokens, norm_query, avail_marques, 90)
        if inferred_marque: filters["nom_marque"] = inferred_marque

        inferred_fonction = self.best_value_from_query(cleaned_terms or norm_tokens, norm_query, avail_fonctions, 90)
        if inferred_fonction: filters["fonction"] = inferred_fonction

        return filters, cleaned_terms

    def is_safe_autocorrect(self, source: str, candidate: str, score: float) -> bool:
        if not source or not candidate: return False
        if source == candidate: return True
        if len(source) < 3 or len(candidate) < 3 or source[0] != candidate[0]: return False
        len_diff = abs(len(source) - len(candidate))
        if len(source) <= 4: min_score, max_diff = 88.0, 1
        elif len(source) <= 6: min_score, max_diff = 82.0, 2
        else: min_score, max_diff = 78.0, 4
        if score < min_score or len_diff > max_diff: return False
        return SequenceMatcher(None, source, candidate).ratio() >= 0.62

    def autocorrect_terms(self, terms: List[str], vocabulary: List[str]) -> Tuple[List[str], Dict[str, str]]:
        if not terms or not vocabulary: return terms, {}
        corrected = []
        corrections = {}
        for term in terms:
            norm = normalize_text(term)
            if not norm: continue
            if norm in NOISE_TERMS or norm.isdigit() or len(norm) < 3 or norm in vocabulary:
                corrected.append(norm)
                continue
            best = process.extractOne(norm, vocabulary, scorer=fuzz.WRatio, score_cutoff=82)
            if best:
                candidate = normalize_text(best[0])
                if self.is_safe_autocorrect(norm, candidate, float(best[1] or 0.0)):
                    corrections[norm] = candidate
                    corrected.append(candidate)
                    continue
            corrected.append(norm)
        return corrected, corrections

    def expand_terms(self, terms: List[str]) -> List[str]:
        expanded = []
        seen = set()
        def push(val):
            n = normalize_text(val)
            if n and n not in seen:
                seen.add(n)
                expanded.append(n)
        for term in terms:
            push(term)
            if canonical := self.type_alias_to_canonical.get(normalize_text(term)): push(canonical)
        return expanded
