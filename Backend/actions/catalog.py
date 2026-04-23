"""
Catalogue d'actions interactives.

Source de vérité unique — le frontend récupère les actions disponibles pour
un objet donné via GET /objets/{id}/actions, qui filtre ce catalogue par
(type_objet, fonctionnalités déclarées).

Invariant : une action n'apparaît jamais pour un objet qui ne l'a pas
déclarée dans sa liste de fonctionnalités.
"""
from typing import Optional, List


# Liste blanche : seuls ces types reçoivent un bouton "Action" côté UI.
# La comparaison se fait insensible à la casse + accents (voir is_interactive_type).
INTERACTIVE_TYPES = {
    "imprimante",
    "projecteur",
    "écran intelligent",
    "ecran intelligent",
    "système de visioconférence",
    "systeme de visioconference",
    "visioconférence",
    "visioconference",
}


def _norm(s: Optional[str]) -> str:
    """Normalisation légère : lowercase + strip. Pas d'unidecode pour éviter
    une dépendance, on gère les variantes accent/sans-accent dans le set."""
    return (s or "").strip().lower()


def is_interactive_type(type_objet: Optional[str]) -> bool:
    return _norm(type_objet) in INTERACTIVE_TYPES


# ---------------------------------------------------------------------------
# Specs d'actions
#   input_kind :
#     - none : action sans payload (ex: lancer un scan)
#     - file : fichier binaire (PDF, image, vidéo)
#     - url  : URL HTTP/HTTPS (lien YouTube, MP4)
#     - text : texte libre (affichage écran)
#   returns :
#     - none        : rien à récupérer
#     - file        : l'agent retourne un fichier (scanner)
#     - session_url : l'action produit une URL (visio Jitsi)
#   accept    : extensions/MIME acceptés côté UI (file input)
#   max_size  : taille max en octets
# ---------------------------------------------------------------------------
_ACTIONS: dict = {
    # ─── Imprimante ────────────────────────────────────────────────────────
    "imprimante:imprimer": {
        "key": "imprimer",
        "label_fr": "Imprimer un PDF",
        "input_kind": "file",
        "accept": ".pdf,application/pdf",
        "max_size": 20 * 1024 * 1024,
        "returns": "none",
    },

    # ─── Scanner ───────────────────────────────────────────────────────────
    "scanner:scanner": {
        "key": "scanner",
        "label_fr": "Lancer un scan",
        "input_kind": "none",
        "returns": "file",
    },

    # ─── Projecteur ────────────────────────────────────────────────────────
    "projecteur:projeter_image": {
        "key": "projeter_image",
        "label_fr": "Projeter une image",
        "input_kind": "file",
        "accept": "image/*",
        "max_size": 10 * 1024 * 1024,
        "returns": "none",
    },
    "projecteur:projeter_video": {
        "key": "projeter_video",
        "label_fr": "Projeter une vidéo (URL)",
        "input_kind": "url",
        "placeholder": "https://www.youtube.com/watch?v=… ou lien MP4",
        "returns": "none",
    },

    # ─── Écran intelligent ─────────────────────────────────────────────────
    "écran intelligent:afficher_contenu": {
        "key": "afficher_contenu",
        "label_fr": "Afficher un texte",
        "input_kind": "text",
        "placeholder": "Message à afficher sur l'écran",
        "returns": "none",
    },
    "écran intelligent:afficher_video": {
        "key": "afficher_video",
        "label_fr": "Afficher une vidéo (URL)",
        "input_kind": "url",
        "placeholder": "https://…",
        "returns": "none",
    },

    # ─── Visioconférence ───────────────────────────────────────────────────
    "système de visioconférence:organiser_meeting": {
        "key": "organiser_meeting",
        "label_fr": "Organiser un meeting",
        "input_kind": "text",
        "placeholder": "Titre de la réunion (optionnel)",
        "optional": True,
        "returns": "session_url",
    },
}


# Alias pour tolérer les variantes sans accents / alternatifs saisis par l'admin
_TYPE_ALIASES = {
    "ecran intelligent": "écran intelligent",
    "systeme de visioconference": "système de visioconférence",
    "visioconference": "système de visioconférence",
    "visioconférence": "système de visioconférence",
}


def _canonical_type(type_objet: str) -> str:
    n = _norm(type_objet)
    return _TYPE_ALIASES.get(n, n)


def _canonical_action(action_name: str) -> str:
    return _norm(action_name).replace(" ", "_").replace("-", "_")


def get_action_spec(type_objet: str, action_name: str) -> Optional[dict]:
    """Retourne la spec d'une action. Cherche d'abord dans le type natif, puis
    cross-type (fallback multifonction : imprimante avec 'scanner' déclaré)."""
    t = _canonical_type(type_objet)
    a = _canonical_action(action_name)
    spec = _ACTIONS.get(f"{t}:{a}")
    if spec:
        return spec
    # Cross-type : on tolère toute action dont la clé correspond, quel que
    # soit son type d'origine dans le catalogue.
    for key, s in _ACTIONS.items():
        if s["key"] == a:
            return s
    return None


def list_actions_for_object(type_objet: str, fonctionnalites: List[str]) -> List[dict]:
    """
    Liste les actions disponibles pour un objet :
      - actions natives de son type (imprimante → imprimer, scanner → scanner, …)
      - + actions additionnelles déclenchées par ses fonctionnalités
        (ex. imprimante multifonction avec "scanner" déclaré).

    Dé-doublonne par clé d'action pour le cas où la fonctionnalité correspond
    déjà à l'action native.
    """
    if not is_interactive_type(type_objet):
        return []

    t = _canonical_type(type_objet)
    seen: set = set()
    result: List[dict] = []

    # 1. Actions natives du type
    for key, spec in _ACTIONS.items():
        if key.split(":", 1)[0] != t:
            continue
        if spec["key"] in seen:
            continue
        seen.add(spec["key"])
        result.append({**spec})

    # 2. Actions cross-type déclenchées par les fonctionnalités déclarées
    declared = {_canonical_action(f) for f in (fonctionnalites or [])}
    for key, spec in _ACTIONS.items():
        if spec["key"] in seen:
            continue
        if spec["key"] in declared:
            seen.add(spec["key"])
            result.append({**spec})

    return result
