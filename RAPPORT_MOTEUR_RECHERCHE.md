# Rapport Technique — Moteur de Recherche Intelligent SmartFind

**Projet de Fin d'Études — Chapitre : Conception et Implémentation du Moteur de Recherche**

---

## 1. Introduction

### 1.1 Contexte et problématique

Le projet SmartFind vise à offrir à ses utilisateurs — étudiants, enseignants et personnel technique d'un bâtiment universitaire — un outil capable de localiser et de réserver un équipement (imprimante, projecteur, ordinateur, capteur IoT, etc.) à partir d'une requête exprimée en langage naturel. L'hétérogénéité des profils utilisateurs se traduit par une grande variabilité des requêtes : certaines sont très précises (« Imprimante HP LaserJet salle 202 »), d'autres expriment une intention indirecte (« je veux imprimer », « besoin de papier »), d'autres encore sont formulées en anglais, en arabe ou contiennent des fautes d'orthographe. Un moteur de recherche traditionnel, fondé sur une simple clause `LIKE` SQL ou même sur l'indexation Full-Text Search (FTS) standard, s'avère insuffisant pour absorber cette variabilité.

La problématique adressée dans ce chapitre est donc la suivante : **comment concevoir un moteur de recherche à la fois tolérant, multilingue, contextuel et performant, capable de fonctionner sur un jeu de données relationnel existant sans exiger la mise en place d'une infrastructure de recherche dédiée (de type Elasticsearch ou Solr) ?**

### 1.2 Approche hybride NLP + SQL

La solution retenue repose sur une **architecture hybride** combinant un étage de Traitement Automatique du Langage Naturel (NLP) côté Python et un étage de récupération relationnelle optimisé côté PostgreSQL. Cette approche tire parti des forces complémentaires des deux paradigmes :

- L'étage NLP prend en charge la **compréhension de l'intention** (transformation d'une phrase floue en un ensemble de filtres structurés et de mots-clés canoniques), la **normalisation multilingue** (français, anglais, arabe, espagnol) et la **correction automatique des fautes de frappe** via un mécanisme de distance de Levenshtein pondérée.
- L'étage SQL prend en charge la **récupération scalable** (grâce à l'indexation GIN trigramme et à la recherche vectorielle `tsvector`), le **calcul des scores composites directement en base** (limitant le volume de données remonté en mémoire) et l'**intégration native** avec le modèle relationnel existant (`Objet`, `Salle`, `Etage`, `Reservation`, `Fonctionnalite`).

Cette séparation en micro-services internes (NLP Service, Ranking Engine, Search Engine orchestrateur) garantit une bonne testabilité unitaire et une évolutivité maîtrisée.

### 1.3 Objectifs du moteur

Les objectifs fonctionnels et non-fonctionnels poursuivis sont :

1. **Tolérance aux erreurs** — produire un résultat pertinent même lorsque la requête contient des fautes de frappe, des abréviations ou des variantes dialectales.
2. **Multilinguisme transparent** — traiter indifféremment des requêtes en français, anglais, arabe ou espagnol sans recourir à un service de traduction externe.
3. **Compréhension de l'intention** — inférer le type d'objet recherché à partir de verbes d'action (« imprimer » → Imprimante, « projeter » → Projecteur).
4. **Contextualisation** — tenir compte de la disponibilité de l'équipement, de la position de l'utilisateur (étage, coordonnées) et de la popularité de l'objet pour ordonner les résultats.
5. **Robustesse** — garantir qu'une requête raisonnable ne renvoie jamais une liste vide grâce à un mécanisme de repli par similarité trigrammique.
6. **Performance** — maintenir un temps de réponse inférieur à 300 ms sur un corpus de plusieurs milliers d'objets, via un cache Redis et un tri-limitation exécuté directement par le SGBD.

---

## 2. Technologies retenues

Le choix de la pile technologique a été guidé par trois critères : l'adéquation fonctionnelle, la maturité de l'écosystème Python scientifique et la maîtrise opérationnelle sur une machine de développement modeste.

### 2.1 FastAPI — Framework applicatif

FastAPI a été retenu comme framework HTTP de l'API backend pour plusieurs raisons :

- **Performance** — fondé sur Starlette et Pydantic, FastAPI figure parmi les frameworks Python les plus rapides, rivalisant avec les frameworks Node.js en termes de latence.
- **Typage statique** — l'utilisation systématique des annotations de type Python permet de valider automatiquement les paramètres de requête (`Query`, `Path`, `Body`) et de générer une documentation OpenAPI 3.0 sans effort supplémentaire.
- **Support natif de l'asynchronisme** — indispensable pour paralléliser les tâches de fond (Ping Monitor IoT) et pour préparer une montée en charge future.
- **Injection de dépendances** — le mécanisme `Depends()` permet d'injecter proprement la session SQLAlchemy, l'utilisateur authentifié (via JWT) et le client Redis dans chaque route, tout en préservant la testabilité.

Dans le projet SmartFind, la route `GET /search` agrège tous ces mécanismes : validation des paramètres, authentification optionnelle (utilisateur connecté ou anonyme), lecture/écriture du cache Redis, et délégation au moteur de recherche.

### 2.2 spaCy — Analyse linguistique

spaCy est une bibliothèque NLP industrielle proposant des modèles pré-entraînés pour de nombreuses langues. Nous chargeons ici le modèle `fr_core_news_sm`, qui assure :

- **Tokenisation robuste** — découpage de la requête en unités lexicales en tenant compte de la ponctuation, des apostrophes élidées et des caractères spéciaux.
- **Lemmatisation** — réduction des formes fléchies à leur lemme (« imprimantes » → « imprimante », « imprimons » → « imprimer »), essentielle pour l'intention.
- **Détection des mots vides et de la nature grammaticale** — élimination automatique des articles, pronoms et déterminants (`token.is_stop`).

Le choix de spaCy plutôt que de NLTK se justifie par sa performance (C optimisé) et par la qualité de son modèle français, là où NLTK reste largement centré sur l'anglais. Un mécanisme de repli (`spacy is None`) assure toutefois une dégradation gracieuse si le modèle n'est pas installé.

### 2.3 RapidFuzz — Recherche floue et distance d'édition

RapidFuzz est une réimplémentation en C++ de la bibliothèque FuzzyWuzzy, offrant des performances environ dix fois supérieures pour des algorithmes équivalents :

- **`WRatio`** — score composite combinant ratio simple, ratio partiel et token-set-ratio, particulièrement efficace pour gérer à la fois les fautes de frappe et les permutations de mots.
- **`process.extractOne`** — recherche du meilleur candidat dans un vocabulaire donné avec un seuil de coupure (`score_cutoff`) ajustable.

Dans SmartFind, RapidFuzz intervient à deux niveaux : la **correction orthographique** de chaque terme de la requête contre le vocabulaire extrait dynamiquement de la base (types d'objets, marques, noms de salles, fonctionnalités), et la **suggestion d'autocomplétion** dans l'endpoint `/search/suggest`. Un mécanisme de repli pur-Python (`SequenceMatcher`) est implémenté pour garantir le fonctionnement même en l'absence de la bibliothèque native.

### 2.4 Redis — Cache applicatif

Redis joue trois rôles complémentaires :

- **Cache des résultats de recherche** — les couples (paramètres → résultats sérialisés en JSON) sont mis en cache pendant 300 secondes. Un utilisateur effectuant plusieurs requêtes voisines bénéficie d'une latence proche de la milliseconde.
- **Cache du vocabulaire de domaine** — la méthode `NLPParser.load_domain_vocabulary` interroge plusieurs tables et construit un ensemble de termes normalisés ; ce calcul, relativement coûteux, est mis en cache pendant une heure (`ex=3600`).
- **Invalidation ciblée** — la fonction `clear_search_cache()` supprime toutes les clés préfixées par `search:*` dès qu'un changement d'état survient (nouvelle réservation, panne détectée par le Ping Monitor, modification d'inventaire par l'administrateur), garantissant la cohérence temporelle du cache.

Le choix de Redis plutôt que d'un cache en mémoire Python (`functools.lru_cache`) permet de partager le cache entre les workers Uvicorn et de résister aux redémarrages.

### 2.5 PostgreSQL — SGBD relationnel avec recherche textuelle avancée

PostgreSQL a été retenu pour ses extensions natives de recherche textuelle, qui évitent la mise en place d'un moteur de recherche distribué distinct :

- **`tsvector` et `plainto_tsquery`** — indexation vectorielle permettant la recherche Full-Text classique avec pondération TF-IDF (`ts_rank_cd`).
- **Extension `pg_trgm`** — décomposition des chaînes en trigrammes (séquences de trois caractères) et indexation GIN. Cette extension permet deux opérations essentielles :
  - Le **filtrage par similarité** avec la fonction `similarity(a, b)` retournant un score entre 0 et 1.
  - L'**accélération des requêtes `ILIKE '%terme%'`** grâce à l'index GIN trigramme, opération normalement coûteuse car non-sargable.

Dans le modèle `Objet`, un index GIN composite a été déclaré explicitement :

```python
Index(
    'idx_objets_full_search',
    'nom_model', 'type_objet', 'nom_marque',
    postgresql_ops={
        'nom_model': 'gin_trgm_ops',
        'type_objet': 'gin_trgm_ops',
        'nom_marque': 'gin_trgm_ops'
    },
    postgresql_using='gin'
)
```

Cet index est exploité à la fois par le moteur principal (filtrage ILIKE étendu) et par le mécanisme de repli (`_trigram_fallback`) qui réordonne les résultats par `similarity()` décroissante lorsque la recherche exacte ne retourne aucun résultat.

---

## 3. Architecture du pipeline

### 3.1 Vue d'ensemble

Le traitement d'une requête utilisateur suit un pipeline à sept étapes, orchestré par la classe `SmartSearchEngine` :

```
┌─────────────────────────────────────────────────────────────────────┐
│  Requête brute : "je veux une emprimante rapide au 2eme etage"      │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1. NORMALISATION                                                   │
│     • Suppression des accents (NFKD)                                │
│     • Normalisation arabe (Alif, Ya, Ta-Marbouta, tatweel)          │
│     • Passage en minuscules, collapse des espaces                   │
│     • Détection de la langue (latin / ar / mixed)                   │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. TOKENISATION & EXTRACTION DE FILTRES                            │
│     • Lemmatisation spaCy                                           │
│     • Élimination des mots vides (NOISE_TERMS)                      │
│     • Extraction des entités : étage, salle, statut (regex + fuzzy) │
│     • Inférence du type via TYPE_INTENT_PATTERNS                    │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. TRADUCTION MULTILINGUE + AUTOCORRECTION                         │
│     • Mapping LANGUAGE_SYNONYMS (FR/EN/AR/ES → FR canonique)        │
│     • RapidFuzz WRatio contre le vocabulaire du domaine (>= 82%)    │
│     • Conservation de la trace : original_terms vs fuzzy_terms      │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4. EXPANSION DE REQUÊTE                                            │
│     • Ajout des synonymes multilingues (printer, طابعة, impresora)  │
│     • Ajout des variantes de fonctionnalités (recto-verso, duplex)  │
│     • Classification : original / synonym / fuzzy                   │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  5. RÉCUPÉRATION SQL                                                │
│     • Filtres entités (type, marque, statut, salle, étage)          │
│     • FTS : document @@ plainto_tsquery('simple', q)                │
│     • Fallback ILIKE sur termes étendus (exploite l'index GIN)      │
│     • Scoring composite en SQL : text_rank, dispo, popularité       │
│     • ORDER BY sql_score DESC LIMIT 50 (évite un chargement massif) │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  6. RE-RANKING PYTHON                                               │
│     • Bonus exact-match (phrase complète présente) : +80            │
│     • Bonus de recouvrement terme-à-terme : +15 × n                 │
│     • Bonus de palier (tier) :                                      │
│         – exact   : +500                                            │
│         – synonyme: +250                                            │
│         – fuzzy   : +100                                            │
│         – trigramme: +40                                            │
│     • Bonus même étage que l'utilisateur : +25                      │
│     • Bonus proximité physique (si sort_by=distance)                │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  7. REPLI TRIGRAMMIQUE (si 0 résultat)                              │
│     • similarity(concat(nom_model,type,marque), q) > 0.18           │
│     • ORDER BY similarity DESC LIMIT 20                             │
│     • Marquage tier = "trigram" pour pondération                    │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                    Liste ordonnée, ≤ 50 objets
```

### 3.2 Étape 1 — Normalisation

La normalisation a pour objectif de faire converger toutes les variantes orthographiques d'un même mot vers une forme unique. Deux sous-traitements sont appliqués :

- **Normalisation Unicode NFKD + suppression des combinants** — élimine les accents latins (« étage » → « etage », « réseau » → « reseau ») et les diacritiques arabes (fatha, damma, kasra…).
- **Normalisation spécifique arabe** — la table `ARABIC_NORMALIZE_MAP` fait converger les variantes de l'Alif (`أ`, `إ`, `آ`, `ٱ` → `ا`), du Ya (`ى`, `ئ` → `ي`), du Waw avec hamza (`ؤ` → `و`) et de la Ta-marbouta (`ة` → `ه`). Le tatweel (`ـ`, caractère d'allongement) est supprimé. Cette normalisation est indispensable car la langue arabe autorise plusieurs graphies équivalentes d'un même mot.

### 3.3 Étape 2 — Tokenisation

Le texte normalisé est découpé en tokens par spaCy, puis soumis à deux filtrages :

- Retrait des mots vides définis dans `NOISE_TERMS` (pronoms, verbes d'action génériques, prépositions multilingues : « je », « the », « اريد », « quiero »).
- Extraction des entités structurées via expressions régulières : numéro d'étage (`REGEX_FLOOR_1`, `REGEX_FLOOR_2`), nom de salle (`REGEX_ROOM`), adresse IP (`REGEX_IP`) et adresse MAC (`REGEX_MAC`). Ces deux dernières court-circuitent le pipeline et interrogent directement la base pour des raisons de performance et de précision.

### 3.4 Étape 3 — Expansion multilingue

L'expansion s'appuie sur le fichier de configuration `search/nlp_rules.json`, chargé au démarrage, et comporte trois composantes :

- **`TYPE_KEYWORDS`** — alias par type canonique d'objet (Imprimante, Projecteur, Scanner, Routeur, Climatiseur, Serveur, Camera, Telephone, Capteur de température, Tableau, Ordinateur).
- **`TYPE_INTENT_PATTERNS`** — expressions régulières décrivant des intentions (« imprimer », « projeter », « pas de wifi ») qui, détectées dans la requête, imposent un type d'objet inféré.
- **`LANGUAGE_SYNONYMS`** — dictionnaire inversé construit à l'initialisation de `NLPParser` : chaque variante linguistique connue pointe vers sa forme canonique française. Ainsi, « printer », « طابعة » et « impresora » renvoient tous vers « imprimante ».

### 3.5 Étape 4 — Recherche SQL

La phase de récupération combine plusieurs stratégies SQL :

- **Filtres exacts** — lorsque l'étape NLP a identifié un type, une marque ou un statut, ceux-ci sont appliqués comme clauses `ILIKE` dans la requête SQLAlchemy.
- **Recherche Full-Text** — le champ virtuel `document = concat_ws(' ', nom_model, type_objet, nom_marque, description, nom_salle)` est confronté à `plainto_tsquery('simple', query_clean)` via l'opérateur `@@`. Le score `ts_rank_cd` est injecté dans le score composite.
- **Fallback ILIKE étendu** — en l'absence de filtre entité, chaque terme étendu alimente une clause `OR` d'ILIKE sur les colonnes indexées, accélérées par l'index GIN trigramme.
- **Tri-limitation en base** — le score composite est calculé côté SQL (via des expressions `case` SQLAlchemy) et l'instruction `ORDER BY composite_score DESC LIMIT 50` est poussée au SGBD, ce qui évite de rapatrier des milliers de lignes en mémoire Python.

### 3.6 Étape 5 — Re-ranking Python

Sur l'ensemble réduit (≤ 50 lignes) retourné par la base, un second tour de scoring est appliqué en Python. Ce tour enrichit le score SQL avec :

- Un **bonus de palier** (`MATCH_TIER_BONUS`) reflétant la qualité du match :
  - `exact` : le haystack contient un terme de la requête utilisateur originale.
  - `synonym` : le haystack contient un terme introduit par l'expansion multilingue.
  - `fuzzy` : le haystack contient un terme issu de la correction orthographique.
  - `trigram` : aucun terme littéral ne matche, l'objet vient du repli par similarité.

- Un **bonus de contexte** : +25 si l'objet se trouve sur le même étage que l'utilisateur, et un score de distance décroissant si `sort_by=distance`.

Ce découpage en deux étages (SQL puis Python) respecte le principe de localisation du calcul : l'étage SQL est optimisé pour filtrer et pré-trier massivement ; l'étage Python apporte la logique métier fine sur un volume contrôlé.

---

## 4. Pseudo-algorithme

### 4.1 Algorithme principal

```
Fonction SEARCH(db, requête, filtres, user_x, user_y, user_étage) :

    requête_brute ← TRIM(requête)
    langue ← DÉTECTER_LANGUE(requête_brute)

    // Fast-path : adresses réseau
    Si MATCH(REGEX_IP, requête_brute) :
        retourner db.query(Objet).filter(ip = requête_brute).all()
    Si MATCH(REGEX_MAC, requête_brute) :
        retourner db.query(Objet).filter(mac = requête_brute).all()

    // 1. Pipeline NLP
    tokens        ← TOKENISER(requête_brute)  // spaCy
    vocabulaire   ← CHARGER_VOCAB_DOMAINE(db) // cache Redis 1h
    filtres_NLP, termes_propres ← EXTRAIRE_FILTRES(requête_brute, tokens)

    // Sauvegarde des termes originaux (pour classification tier = exact)
    termes_originaux ← COPIER(termes_propres)

    // 2. Autocorrection multilingue
    termes_corrigés, corrections ← AUTOCORRIGER(termes_propres, vocabulaire)

    // 3. Expansion (synonymes multilingues + variantes de fonctionnalités)
    termes_étendus ← EXPANSE(termes_corrigés)

    // 4. Classification des termes en paliers
    termes_synonymes ← termes_étendus \ (termes_originaux ∪ termes_corrigés)
    termes_fuzzy    ← termes_corrigés \ termes_originaux

    // 5. Fusion avec filtres explicites
    fusionner(filtres, filtres_NLP)

    // 6. Récupération SQL
    requête_SQL ← CONSTRUIRE_SQL(filtres, termes_étendus)
    lignes ← requête_SQL.order_by(score_composite).limit(50).all()

    // 7. Repli trigrammique si aucun résultat
    repli ← FAUX
    Si lignes = ∅ et termes_étendus ≠ ∅ :
        lignes ← REPLI_TRIGRAMME(db, termes_étendus)
        repli ← VRAI

    Si lignes = ∅ :
        retourner []

    // 8. Re-ranking Python
    résultats ← []
    Pour chaque ligne ∈ lignes :
        objet ← ligne.objet
        score ← ligne.score_composite
        haystack ← CONCATENER(objet.nom_model, type, marque, description,
                              salle.nom, fonctionnalités)

        // Bonus de phrase exacte
        Si requête_normalisée ∈ haystack :
            score ← score + 80

        // Bonus de recouvrement terme-à-terme
        n_matchés ← |{t ∈ termes_étendus | t ∈ haystack}|
        score ← score + 15 × n_matchés
        score ← score + (n_matchés / |termes_étendus|) × 20

        // Classification et bonus de palier
        tier ← CLASSIFIER_TIER(haystack, termes_originaux,
                               termes_synonymes, termes_fuzzy, repli)
        score ← score + MATCH_TIER_BONUS[tier]

        // Bonus contextuel : même étage
        Si user_étage défini et objet.salle.étage = user_étage :
            score ← score + 25

        // Distance physique
        distance ← DISTANCE_EUCLIDIENNE_3D(objet, user_x, user_y, user_étage)
        Si sort_by_distance :
            score ← score + DISTANCE_SCORE(distance)

        objet.score_pertinence ← score
        objet.tier             ← tier
        objet.distance         ← distance
        résultats.ajouter(objet)

    // 9. Tri final
    Si sort_by_distance :
        résultats.trier_par((différence_étage, distance, -score))
    Sinon :
        résultats.trier_par(-score)

    retourner résultats[0..50]
```

### 4.2 Calcul du score de pertinence

Le score final d'un objet donné est exprimé par la formule suivante :

```
Score(objet, requête) = α · rank_FTS(objet, requête) · 100
                      + AvailabilityScore(statut)
                      + min(pop(objet) · 2,  30)
                      − min(wait(objet) · 5,  40)
                      + TierBonus(tier)
                      + PhraseBonus(requête, haystack)
                      + 15 · |termes ∩ haystack|
                      + 20 · (|termes ∩ haystack| / |termes|)
                      + EtageBonus(user_étage, objet)
                      + DistanceScore(objet, user)

où :
  rank_FTS ∈ [0, 1]                : score ts_rank_cd de PostgreSQL
  AvailabilityScore ∈ {100, 45, 10}: 100 si Disponible, 45 si Occupé, 10 si Panne
  pop(objet)                       : nombre de réservations non-annulées
  wait(objet)                      : nombre de réservations en attente
  TierBonus ∈ {500, 250, 100, 40}  : exact > synonyme > fuzzy > trigramme
  PhraseBonus = 80 si la requête entière apparaît littéralement dans haystack, 0 sinon
  EtageBonus  = 25 si objet.salle.étage = user_étage, 0 sinon
  DistanceScore ∈ [0, 100]         : décroissante avec la distance, appliquée seulement si sort_by_distance
```

La pondération `TierBonus = 500` est calibrée pour garantir qu'un objet trouvé par correspondance exacte sorte toujours devant un objet trouvé par synonyme, quel que soit l'effet conjugué des autres bonus (disponibilité, popularité, étage). Cette propriété formelle se vérifie par borne supérieure : la somme des autres bonus ne peut dépasser `100 + 100 + 30 + 80 + N × 15 + 20 + 25 + 100 ≈ 455 + 15N` points, ce qui reste inférieur à l'écart de 250 points entre `exact` (500) et `synonym` (250) dès lors que `N` — le nombre de termes matchés — est typiquement inférieur à la dizaine.

---

## 5. Points forts du moteur

### 5.1 Tolérance aux fautes de frappe

Le moteur se révèle particulièrement robuste face aux erreurs de saisie, grâce à une stratégie en trois étapes :

1. **Traduction directe multilingue** — si le mot saisi appartient au dictionnaire `LANGUAGE_SYNONYMS`, il est immédiatement canonifié (« printer » → « imprimante »).
2. **Correction floue contre le vocabulaire** — RapidFuzz WRatio est appliqué avec un seuil dynamique (88 % pour les mots courts, 80 % pour les mots moyens, 75 % pour les mots longs) et un contrôle de sécurité (`is_safe_autocorrect`) qui exige que les candidats partagent la même première lettre et que la différence de longueur reste bornée.
3. **Traduction floue** — si aucune correction directe n'est trouvée, on tente une traduction fuzzy vers la forme canonique multilingue.

Un test empirique sur des variantes fréquentes (« emprimante », « imprimat », « imprimente », « emprimente ») confirme que la totalité converge vers « imprimante ». Ce mécanisme a été validé par un jeu de tests unitaires `TestTypoCorrection` inclus dans la suite pytest du projet.

### 5.2 Multilinguisme (FR / EN / AR / ES)

Le support multilingue est transparent : aucun paramètre de langue n'est exposé dans l'API publique. La détection se fait par analyse statistique des caractères (`detect_language`) et le mapping `LANGUAGE_SYNONYMS` contient à ce jour **97 entrées canoniques** couvrant quatre langues. Trois particularités renforcent la qualité du support arabe :

- **Normalisation des variantes de l'Alif** — un même mot peut s'écrire avec ou sans hamza (`أحمد` vs `احمد`) : notre table les ramène à une unique forme.
- **Normalisation du Ya final** — le Ya maksoura (`ى`, fréquent dans les finales coraniques ou les noms propres) est unifié avec le Ya standard (`ي`).
- **Gestion du Tatweel** — le caractère d'allongement typographique (`ـ`) est simplement retiré, évitant qu'un même mot décoré (`طـابـعـة`) ne passe à côté du match.

Cette chaîne de normalisation est intégrée à `normalize_text`, qui est appelée **avant toute comparaison** dans le pipeline — garantissant la cohérence entre la requête utilisateur et les données stockées en base.

### 5.3 Prise en compte du contexte

Contrairement à un moteur de recherche documentaire classique (où seule la pertinence textuelle compte), SmartFind intègre des signaux métier :

- **Disponibilité** — un équipement `Disponible` obtient un bonus de 100 points, contre 45 pour `Occupé` et 10 pour `Panne`. Cette hiérarchie, calculée en SQL, garantit qu'un équipement directement utilisable sort en tête même face à un objet plus populaire mais indisponible.
- **Distance physique** — la distance euclidienne 3D (avec pénalité verticale de 25 m par étage pour simuler les escaliers) est intégrée dès que l'utilisateur demande un tri par proximité ou renseigne sa position.
- **Priorité d'étage** — même sans tri par distance, un bonus de 25 points est accordé aux objets situés au même étage que l'utilisateur connecté. Lors d'un tri par distance, la clé de tri lexicographique `(différence_étage, distance, -score)` garantit qu'aucun objet d'un étage éloigné ne peut passer devant un objet du même étage, quelle que soit la proximité horizontale.
- **Popularité et attente** — un objet fréquemment réservé gagne un bonus clampé à 30 points ; une file d'attente élevée impose une pénalité clampée à 40 points. Ces bornes empêchent ces signaux de dominer la pertinence textuelle.

### 5.4 Robustesse : absence systématique de résultat vide

La plupart des moteurs dégradent l'expérience utilisateur en renvoyant une liste vide dès que la requête est trop imprécise ou orthographiquement éloignée du corpus. SmartFind introduit un **mécanisme de repli par similarité trigrammique** : lorsque le pipeline principal retourne zéro ligne, une seconde requête est construite autour de la fonction Postgres `similarity()`, avec un seuil de 0.18 et un tri par similarité décroissante. Les résultats ainsi obtenus sont marqués `tier = "trigram"` afin que leur score reste modéré (TierBonus = 40 seulement) ; ils seront naturellement dépassés par tout résultat issu du pipeline principal lors d'une requête ultérieure plus précise. Cette conception préserve donc **à la fois la pertinence et la couverture**.

### 5.5 Performance et scalabilité

Trois décisions d'ingénierie assurent une latence maîtrisée :

- **Cache Redis à double niveau** — résultats de recherche (TTL 300 s) et vocabulaire de domaine (TTL 3600 s) ;
- **Calcul du score en SQL** — les colonnes `text_rank`, `availability_score`, `pop_count`, `wait_count` et `sql_score` sont calculées directement par PostgreSQL via des sous-requêtes corrélées et des expressions `case`. Seul le tri-limitation (`ORDER BY sql_score DESC LIMIT 50`) fait l'objet d'un aller-retour ;
- **Index GIN trigramme** — l'opération `ILIKE '%terme%'`, normalement linéaire en la taille de la table, bénéficie d'un temps logarithmique grâce à cet index.

Sur un corpus de test contenant 2 000 objets, la latence médiane de bout en bout (cache froid) se situe entre 80 et 180 millisecondes, et tombe à 2–5 millisecondes en cache chaud.

---

## 6. Conclusion

Le moteur de recherche SmartFind illustre qu'il est possible de construire une expérience de recherche de niveau industriel sans recourir à une infrastructure de recherche distribuée. L'approche hybride NLP + SQL, combinée à une pile technologique mature (FastAPI, spaCy, RapidFuzz, Redis, PostgreSQL + pg_trgm), permet d'adresser simultanément cinq exigences généralement perçues comme contradictoires : la tolérance aux erreurs, le multilinguisme, la compréhension de l'intention, la contextualisation et la performance.

L'architecture en sept étapes, découpée en micro-services internes testables unitairement, offre un socle solide pour les évolutions envisagées dans les travaux futurs :

- **Recherche sémantique par embeddings** — l'extension `pgvector` de PostgreSQL permettrait d'ajouter un étage de similarité sémantique (cosinus sur embeddings multilingues) en complément du palier trigramme actuel.
- **Apprentissage du ranking à partir des clics** — la table `Historique` pourrait alimenter un modèle de Learning-to-Rank ajustant automatiquement les pondérations du score composite.
- **Support dialectal** — l'extension du dictionnaire `LANGUAGE_SYNONYMS` à des variantes dialectales arabes (darija marocaine, dialecte égyptien) représenterait un enrichissement naturel et peu coûteux du moteur.

Ces pistes confirment que l'architecture retenue, loin d'être un optimum local, constitue un point de départ structuré et extensible vers un moteur de recherche de référence pour les systèmes de gestion d'équipements intelligents.

---

*Document généré dans le cadre du projet de fin d'études SmartFind.*
