"""
Système d'actions utilisateur → équipement.

Le catalogue (catalog.py) définit la liste blanche des types interactifs et,
pour chaque couple (type_objet, fonctionnalité), la forme de payload attendue.
Le dispatcher (dispatcher.py) route l'action vers l'agent local de l'appareil
ou exécute une logique interne (ex: génération d'URL Jitsi pour la visio).
"""
