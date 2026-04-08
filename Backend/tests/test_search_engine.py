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
    split_words,
    clean_noise_terms,
    NLPParser,
    STATUS_KEYWORDS,
    REGEX_IP,
    REGEX_MAC,
)
from search.ranking_service import RankingEngine


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
        result = normalize_text("طابعة")
        assert result == "طابعة"


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

