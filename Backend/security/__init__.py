"""Sous-système cybersécurité : détection d'anomalies comportementales
et d'équipements illicites (rogue devices).

Les détecteurs sont des fonctions pures qui interrogent Redis et renvoient
un dict sérialisable contenant (detected: bool, reason: str, details: dict).
Les routeurs appellent ces détecteurs puis décident de créer une alerte
critique et/ou de basculer l'objet en statut "Quarantaine".
"""
