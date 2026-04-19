"""
Tests Unitaires — SmartFind Search Engine
==========================================
Vérifie le bon fonctionnement des 3 micro-services :
  1. NLP Service   (Tokenization, Noise Removal, Autocorrect, Query Expansion)
  2. Ranking Engine (Scores de disponibilité, distance, haystack)
  3. Search Engine  (Pipeline complet : NLP → SQL → Scoring → Résultats)
"""

import pytest
import math
import sys
import os

# ── Setup path so we can import from Backend root ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from search.nlp_service import (
    normalize_text,
    normalize_arabic,
    detect_language,
    split_words,
    clean_noise_terms,
    NLPParser,
    STATUS_KEYWORDS,
    REGEX_IP,
    REGEX_MAC,
)
from search.ranking_service import RankingEngine, MATCH_TIER_BONUS
from search.phonetic import phonetic_key, phonetic_match
from search.bm25 import BM25Scorer, FIELD_WEIGHTS


# ═══════════════════════════════════════════════════
#  1. NLP SERVICE — Tests
# ═══════════════════════════════════════════════════

class TestNormalizeText:
    def test_basic(self):
        assert normalize_text("Imprimante") == "imprimante"

    def test_accents_removed(self):
        assert normalize_text("Écran Réseau") == "ecran reseau"

    def test_empty_and_none(self):
        assert normalize_text("") == ""
        assert normalize_text(None) == ""

    def test_unicode_arabic(self):
        # Ta marbouta (ة) normalised to ha (ه) so all ta-marbouta spellings collapse to one form.
        result = normalize_text("طابعة")
        assert result == "طابعه"


class TestSplitWords:
    def test_basic_split(self):
        assert split_words("imprimante hp wifi") == ["imprimante", "hp", "wifi"]

    def test_punctuation_removed(self):
        result = split_words("imprimante, en panne!")
        assert "imprimante" in result
        assert "panne" in result

    def test_empty(self):
        assert split_words("") == []


class TestCleanNoiseTerms:
    def test_removes_noise(self):
        terms = ["je", "veux", "une", "imprimante", "hp"]
        cleaned = clean_noise_terms(terms)
        assert "je" not in cleaned
        assert "veux" not in cleaned
        assert "imprimante" in cleaned
        assert "hp" in cleaned

    def test_removes_duplicates(self):
        terms = ["imprimante", "imprimante", "hp"]
        cleaned = clean_noise_terms(terms)
        assert cleaned.count("imprimante") == 1

    def test_removes_short_non_digit(self):
        terms = ["a", "b", "hp", "42"]
        cleaned = clean_noise_terms(terms)
        assert "a" not in cleaned
        assert "hp" in cleaned
        assert "42" in cleaned


class TestNLPParser:
    @pytest.fixture
    def parser(self):
        return NLPParser()

    def test_extract_tokens_basic(self, parser):
        tokens = parser.extract_tokens("imprimante HP LaserJet")
        assert len(tokens) > 0
        lower_tokens = [t.lower() for t in tokens]
        assert any("imprimante" in t for t in lower_tokens)

    def test_extract_tokens_empty(self, parser):
        assert parser.extract_tokens("") == []
        assert parser.extract_tokens(None) == []

    def test_expand_terms_includes_canonical(self, parser):
        expanded = parser.expand_terms(["printer"])
        # "printer" is an alias for "Imprimante" in nlp_rules.json
        lower_expanded = [e.lower() for e in expanded]
        assert "printer" in lower_expanded
        assert "imprimante" in lower_expanded

    def test_expand_terms_no_duplicates(self, parser):
        expanded = parser.expand_terms(["imprimante", "imprimante"])
        assert expanded.count("imprimante") == 1

    def test_autocorrect_exact_match(self, parser):
        vocab = ["imprimante", "scanner", "routeur"]
        corrected, corrections = parser.autocorrect_terms(["imprimante"], vocab)
        assert "imprimante" in corrected
        assert len(corrections) == 0

    def test_autocorrect_typo(self, parser):
        vocab = ["imprimante", "scanner", "routeur"]
        corrected, corrections = parser.autocorrect_terms(["imprimente"], vocab)
        assert "imprimante" in corrected


class TestArabicNormalization:
    def test_alif_variants(self):
        assert normalize_arabic("أحمد") == "احمد"
        assert normalize_arabic("إمام") == "امام"
        assert normalize_arabic("آية") == "ايه"

    def test_ya_variant(self):
        assert normalize_arabic("مصطفى") == "مصطفي"

    def test_ta_marbouta(self):
        assert normalize_arabic("طابعة") == "طابعه"

    def test_diacritics_stripped(self):
        assert normalize_arabic("كَتَبَ") == "كتب"

    def test_tatweel_stripped(self):
        assert normalize_arabic("طـابـعـة") == "طابعه"


class TestLanguageDetection:
    def test_latin(self):
        assert detect_language("imprimante HP") == "latin"

    def test_arabic(self):
        assert detect_language("طابعة") == "ar"

    def test_mixed(self):
        assert detect_language("imprimante طابعة") == "mixed"

    def test_empty(self):
        assert detect_language("") == "latin"


class TestMultilingualExpansion:
    @pytest.fixture
    def parser(self):
        return NLPParser()

    def test_english_to_french(self, parser):
        canonical = parser.translate_to_canonical("printer")
        assert canonical == "imprimante"

    def test_arabic_to_french(self, parser):
        canonical = parser.translate_to_canonical("طابعة")
        assert canonical == "imprimante"

    def test_expand_english_includes_arabic(self, parser):
        expanded = parser.expand_terms(["printer"])
        normalized_expansions = [normalize_text(e) for e in expanded]
        assert "imprimante" in normalized_expansions
        assert any("طابع" in normalize_text(e) for e in expanded)

    def test_expand_arabic_includes_french(self, parser):
        expanded = parser.expand_terms(["طابعة"])
        normalized = [normalize_text(e) for e in expanded]
        assert "imprimante" in normalized

    def test_feature_synonyms_expand(self, parser):
        expanded = parser.expand_terms(["recto-verso"])
        flat = " ".join(expanded)
        assert "duplex" in flat or "double" in flat


class TestTypoCorrection:
    @pytest.fixture
    def parser(self):
        return NLPParser()

    def test_fr_typo(self, parser):
        vocab = ["imprimante", "scanner", "routeur"]
        corrected, _ = parser.autocorrect_terms(["emprimante"], vocab)
        assert "imprimante" in corrected

    def test_heavy_typo(self, parser):
        vocab = ["imprimante", "scanner", "routeur"]
        corrected, _ = parser.autocorrect_terms(["imprimat"], vocab)
        assert "imprimante" in corrected

    def test_cross_language_normalization(self, parser):
        # Even with an empty domain vocab, a known translation should resolve
        corrected, corrections = parser.autocorrect_terms(["printer"], ["imprimante"])
        assert "imprimante" in corrected


class TestPhonetic:
    def test_projecteur_typo(self):
        assert phonetic_match("projecteur", "projeckteur")

    def test_scanner_variants(self):
        assert phonetic_match("scanner", "skanner")

    def test_videoprojecteur(self):
        assert phonetic_match("videoprojecteur", "vidioprojecteur")

    def test_distinct_words(self):
        assert not phonetic_match("imprimante", "ordinateur")

    def test_empty_returns_empty(self):
        assert phonetic_key("") == ""
        assert phonetic_key(None) == ""


class TestFuzzyMultiAlgo:
    @pytest.fixture
    def parser(self):
        return NLPParser()

    def test_severe_typo_phonetic_rescue(self, parser):
        # 'projeckteur' has 2 edits from 'projecteur' → WRatio might pass, but
        # test ensures phonetic path exists and returns consistent results.
        vocab = ["projecteur", "imprimante", "scanner"]
        corrected, _ = parser.autocorrect_terms(["projeckteur"], vocab)
        assert "projecteur" in corrected

    def test_fuzzy_score_returns_bounded(self, parser):
        score = parser.fuzzy_score("imprimante", "imprimante")
        assert 99.0 <= score <= 112.0  # up to 100 + phonetic bonus 12

    def test_fuzzy_score_zero_on_empty(self, parser):
        assert parser.fuzzy_score("", "anything") == 0.0


class TestBM25:
    class _FakeSalle:
        def __init__(self, nom="A-101"):
            self.nom_salle = nom

    class _FakeFonc:
        def __init__(self, nom):
            self.nom = nom

    class _FakeObj:
        def __init__(self, id_, nom_model, type_objet, marque, desc, salle=None, fonctions=None):
            self.id_objet = id_
            self.nom_model = nom_model
            self.type_objet = type_objet
            self.nom_marque = marque
            self.description = desc
            self.salle = salle
            self.fonctionnalites = fonctions or []

    @pytest.fixture
    def scorer(self):
        s = BM25Scorer()
        # Manually seed stats to avoid touching the DB.
        s.N = 10
        s.avgdl = 20.0
        s.doc_freq = {
            "imprimante": 2, "scanner": 2, "hp": 3, "laserjet": 1,
            "couleur": 4, "recto": 3, "verso": 3, "a4": 5,
        }
        s._built_at = 1e18  # prevent rebuild
        return s

    def test_score_nonzero_on_match(self, scorer):
        obj = self._FakeObj(
            1, "LaserJet Pro", "Imprimante", "HP",
            "Imprimante couleur recto-verso A4",
            salle=self._FakeSalle(),
            fonctions=[self._FakeFonc("recto-verso"), self._FakeFonc("couleur")],
        )
        score = scorer.score(["imprimante", "hp"], obj)
        assert score > 0

    def test_score_zero_on_no_overlap(self, scorer):
        obj = self._FakeObj(2, "Router X500", "Routeur", "Cisco", "WiFi 6 access point")
        score = scorer.score(["imprimante", "laserjet"], obj)
        assert score == 0.0

    def test_rare_term_ranks_higher(self, scorer):
        """IDF: 'laserjet' (df=1) must dominate 'a4' (df=5) for the same tf."""
        obj_rare = self._FakeObj(3, "LaserJet", "Imprimante", "HP", "document")
        obj_common = self._FakeObj(4, "model", "Imprimante", "HP", "a4")
        rare_score = scorer.score(["laserjet"], obj_rare)
        common_score = scorer.score(["a4"], obj_common)
        assert rare_score > common_score

    def test_field_weighting_applied(self, scorer):
        """A match in nom_model (weight 3) must outscore a match only in description (weight 1)."""
        obj_in_name = self._FakeObj(5, "Imprimante Pro", "Tableau", "Acme", "random text")
        obj_in_desc = self._FakeObj(6, "Pro Model", "Tableau", "Acme", "imprimante")
        s1 = scorer.score(["imprimante"], obj_in_name)
        s2 = scorer.score(["imprimante"], obj_in_desc)
        assert s1 > s2

    def test_field_weights_configured(self):
        assert FIELD_WEIGHTS["nom_model"] >= FIELD_WEIGHTS["description"]
        assert FIELD_WEIGHTS["type_objet"] >= FIELD_WEIGHTS["description"]


class TestMatchTiers:
    def test_tier_ordering(self):
        assert MATCH_TIER_BONUS["exact"] > MATCH_TIER_BONUS["synonym"]
        assert MATCH_TIER_BONUS["synonym"] > MATCH_TIER_BONUS["fuzzy"]
        assert MATCH_TIER_BONUS["fuzzy"] > MATCH_TIER_BONUS["trigram"]


class TestRegexPatterns:
    def test_ip_valid(self):
        assert REGEX_IP.match("192.168.1.1")
        assert REGEX_IP.match("10.0.0.1")

    def test_ip_invalid(self):
        assert not REGEX_IP.match("imprimante")
        assert not REGEX_IP.match("192.168")

    def test_mac_valid(self):
        assert REGEX_MAC.match("AA:BB:CC:DD:EE:FF")
        assert REGEX_MAC.match("aa:bb:cc:dd:ee:ff")

    def test_mac_invalid(self):
        assert not REGEX_MAC.match("imprimante")
        assert not REGEX_MAC.match("AA:BB:CC")


class TestStatusKeywords:
    def test_disponible_keywords(self):
        keywords = STATUS_KEYWORDS["Disponible"]
        assert "disponible" in keywords
        assert "dispo" in keywords
        assert "libre" in keywords
        assert "متاح" in keywords

    def test_panne_keywords(self):
        keywords = STATUS_KEYWORDS["Panne"]
        assert "panne" in keywords
        assert "hs" in keywords
        assert "معطل" in keywords


# ═══════════════════════════════════════════════════
#  2. RANKING ENGINE — Tests
# ═══════════════════════════════════════════════════

class TestRankingEngine:
    def test_availability_score_disponible(self):
        assert RankingEngine.availability_score("Disponible") == 100.0

    def test_availability_score_occupe(self):
        assert RankingEngine.availability_score("Occupé") == 45.0

    def test_availability_score_panne(self):
        assert RankingEngine.availability_score("Panne") == 10.0

    def test_availability_score_unknown(self):
        assert RankingEngine.availability_score("Inconnu") == 30.0

    def test_availability_score_none(self):
        assert RankingEngine.availability_score(None) == 30.0

    def test_distance_score_zero(self):
        assert RankingEngine.distance_score(0.0) == 100.0

    def test_distance_score_far(self):
        score = RankingEngine.distance_score(5000.0)
        assert score == 0.0

    def test_distance_score_mid(self):
        score = RankingEngine.distance_score(2500.0)
        assert 0 < score < 100

    def test_distance_score_infinite(self):
        assert RankingEngine.distance_score(float("inf")) == 0.0

    def test_distance_from_user_no_salle(self):
        class FakeObj:
            salle = None
        assert RankingEngine.distance_from_user(FakeObj()) == float("inf")

    def test_distance_from_user_with_coords(self):
        class FakeSalle:
            coord_x = 3.0
            coord_y = 4.0
        class FakeObj:
            salle = FakeSalle()
        dist = RankingEngine.distance_from_user(FakeObj())
        assert abs(dist - 5.0) < 0.001  # 3² + 4² = 25, √25 = 5

    def test_distance_from_user_custom_coords(self):
        class FakeSalle:
            coord_x = 6.0
            coord_y = 8.0
        class FakeObj:
            salle = FakeSalle()
        dist = RankingEngine.distance_from_user(FakeObj(), user_x=3.0, user_y=4.0)
        assert abs(dist - 5.0) < 0.001  # (6-3)² + (8-4)² = 9+16 = 25

    def test_build_haystack(self):
        class FakeSalle:
            nom_salle = "Bureau Admin"
        class FakeObj:
            type_objet = "Imprimante"
            nom_marque = "HP"
            nom_model = "LaserJet Pro"
            description = "Impressions rapides"
            salle = FakeSalle()
            fonctionnalites = []
        haystack = RankingEngine.build_haystack(FakeObj())
        assert "imprimante" in haystack
        assert "hp" in haystack
        assert "laserjet pro" in haystack
        assert "bureau admin" in haystack

    def test_build_haystack_none_values(self):
        class FakeObj:
            type_objet = None
            nom_marque = None
            nom_model = None
            description = None
            salle = None
            fonctionnalites = []
        haystack = RankingEngine.build_haystack(FakeObj())
        assert isinstance(haystack, str)


# ═══════════════════════════════════════════════════
#  3. INTEGRATION — Pipeline End-to-End
# ═══════════════════════════════════════════════════

class TestSearchPipeline:
    """Test the NLP pipeline: tokenize → clean → expand → autocorrect."""

    @pytest.fixture
    def parser(self):
        return NLPParser()

    def test_full_pipeline_french(self, parser):
        tokens = parser.extract_tokens("je veux une imprimante HP disponible")
        cleaned = clean_noise_terms(tokens)
        expanded = parser.expand_terms(cleaned)
        lower = [e.lower() for e in expanded]
        # Should find "imprimante" or "hp" after noise removal
        assert any("imprimante" in t or "hp" in t for t in lower)

    def test_full_pipeline_darija(self, parser):
        tokens = parser.extract_tokens("bghit printer")
        cleaned = clean_noise_terms(tokens)
        expanded = parser.expand_terms(cleaned)
        lower = [e.lower() for e in expanded]
        assert "printer" in lower or "imprimante" in lower

    def test_full_pipeline_arabic(self, parser):
        tokens = parser.extract_tokens("ابحث عن طابعة")
        cleaned = clean_noise_terms(tokens)
        expanded = parser.expand_terms(cleaned)
        assert len(expanded) > 0

    def test_status_detection(self, parser):
        tokens = parser.extract_tokens("imprimante en panne")
        filters, _ = parser.extract_filters(
            "imprimante en panne", tokens, ["Imprimante"], [], [], []
        )
        assert filters.get("statut") == "Panne"

    def test_floor_detection(self, parser):
        tokens = parser.extract_tokens("objet etage 2")
        filters, _ = parser.extract_filters(
            "objet etage 2", tokens, [], [], [], []
        )
        assert filters.get("num_etage") == 2

    def test_type_inference(self, parser):
        tokens = parser.extract_tokens("je cherche un scanner")
        filters, _ = parser.extract_filters(
            "je cherche un scanner", tokens, ["Scanner", "Imprimante"], [], [], []
        )
        assert filters.get("type_objet") == "Scanner"

