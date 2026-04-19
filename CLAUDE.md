# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

SmartFind is a two-tier app for locating and reserving equipment inside a building.

- **Backend/** — FastAPI + SQLAlchemy against PostgreSQL, with Redis for search cache and a spaCy/rapidfuzz-powered NLP search pipeline.
- **Frontend/** — React 19 + Vite 7 SPA (React Router 7, Bootstrap, axios, recharts).

## Commands

Backend (from `Backend/`, inside the `venv/`):
```bash
source venv/bin/activate
uvicorn main:app --reload        # dev server on :8000
pytest tests/                    # run the test suite
pytest tests/test_search_engine.py::TestNormalizeText::test_basic  # single test
```

Frontend (from `Frontend/`):
```bash
npm run dev      # Vite dev server on :5173
npm run build
npm run lint     # ESLint 9 flat config
npm run preview
```

Services required locally: PostgreSQL on `127.0.0.1:5432` (DB `smartbuilding_db`, user `postgres`, password `1234` — hardcoded in `Backend/data/database.py`) and Redis on `localhost:6379`. The Postgres DB must have the `pg_trgm` extension enabled (`CREATE EXTENSION IF NOT EXISTS pg_trgm;`) — `models.Objet` declares a GIN trigram index on `nom_model/type_objet/nom_marque`, `search_engine.py` uses `plainto_tsquery`, and the trigram fallback path in `search_engine._trigram_fallback` calls `similarity()` directly.

Full stack via Docker: `docker-compose up` from the repo root brings up Postgres, Redis, the FastAPI backend (`:8000`), and the built frontend (`:80`). Containerized backend reads `DATABASE_URL` / `REDIS_HOST` from env, but the local-dev path still uses the hardcoded values in `database.py` / `redis_client.py`.

## Architecture

### Backend request flow
`main.py` boots FastAPI, calls `Base.metadata.create_all()` (no Alembic — schema lives in `data/models.py`), mounts `/uploads` as static files, configures permissive CORS, and wires seven routers from `routers/`: `users, objets, search, alertes, iot, public, admin`. The previous `reservations` and `notifications` routers have been removed — reservation and notification logic now live inside the remaining routers (`objets`, `alertes`). A background ping task (`ping_devices_background_task`) is defined but currently disabled in the startup hook.

Auth (`auth.py`) is JWT bearer via `python-jose` + bcrypt. The design has **no `role` column on `Utilisateur`**: regular users live in the DB, and there is exactly **one hardcoded admin** (email `admin@smartfind.com`, password `admin_2026`) that is *not* a DB row. The `/login` endpoint in `routers/users.py:60` short-circuits on the hardcoded pair and issues a JWT; `auth.py:46` synthesizes an in-memory `Utilisateur(id_utilisateur=0, …)` for that JWT subject without touching the DB. Three dependencies to know:
- `get_current_user` — 401 if missing/invalid; returns the synthetic admin object when the JWT subject is `admin@smartfind.com`.
- `get_current_user_optional` — returns `None` instead of 401; used by `/search` so anonymous users can query.
- `get_current_admin` — gates by `email == "admin@smartfind.com"`, NOT by any role field.

Implications: never add or assume a `role` column on `Utilisateur`; never write `filter_by(role="Admin")`; admin's `id_utilisateur=0` is fake, so any FK that would point to it (e.g. `Alerte.id_utilisateur`) must be handled as a special case.

The JWT `SECRET_KEY`, DB URL, and admin password are hardcoded. Treat them as dev-only; do not commit real secrets.

### Search subsystem (`Backend/search/`)
This is the non-obvious part of the codebase — five collaborating modules, not one monolithic search:

1. **`nlp_service.NLPParser`** — tokenization, accent/noise normalization, autocorrect via `rapidfuzz`, and rule-driven query expansion. Rules live in **`search/nlp_rules.json`** (synonyms, status keywords, type aliases). Loads domain vocabulary dynamically from the DB (types, marques, fonctions, salles). `REGEX_IP` / `REGEX_MAC` are fast-path shortcuts that bypass NLP. Imports `phonetic_key`/`phonetic_match` from `phonetic.py` for sound-alike matching.

2. **`ranking_service.RankingEngine`** — exposes SQL-level scoring columns (`sql_text_rank`, `sql_availability_score`, `sql_popularity_score`, `sql_waiting_score`) plus Python-side helpers (`build_haystack`, `distance_from_user`, `distance_score`). Scoring is split deliberately: coarse ranking runs in Postgres, fine-grained bonuses run in Python on a small result set. `MATCH_TIER_BONUS` is defined here.

3. **`bm25.bm25_scorer`** — canonical Okapi BM25 (`k1=1.5`, `b=0.75`) computed in Python with per-field weights (a hit in `nom_model` outweighs one in the description). Corpus stats (N, avgdl, doc_freq) are cached in Redis under `bm25:corpus_stats:v2` and invalidated by `clear_search_cache()`. Final BM25 contribution to the composite score is amplified by `BM25_WEIGHT = 25.0`.

4. **`semantic_service.semantic_service`** — vector layer using `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, multilingual, CPU-friendly). Per-equipment embeddings are built once and stored as JSON in Redis under `semantic:embeddings:v1` (TTL 1 h, 120 s in-memory freshness window); rebuilt on cache invalidation. Cosine similarity is scaled by `SEMANTIC_WEIGHT = 150.0`.

5. **`search_engine.SmartSearchEngine`** — orchestrates the pipeline: NLP parse → multilingual translation → autocorrect → expand → build SQL with joins + FTS (`@@ plainto_tsquery('simple', ...)`) + ILIKE fallbacks → composite SQL score with `ORDER BY … LIMIT 50/200` → Python re-scoring that combines **tiered match bonus** (`MATCH_TIER_BONUS`: exact=500 > synonym=250 > fuzzy=100 > trigram=40), BM25, and semantic similarity → **pg_trgm `similarity()` fallback** when FTS/ILIKE returned zero rows → final sort. Exported as a singleton `engine` imported by `routers/search.py`. Distance sort uses a lexicographic key `(floor_diff, distance, -relevance)` so same-floor results always beat farther floors; a soft +25 floor-match bonus is added even when the user doesn't request distance sorting.

The pipeline supports **FR/EN/AR/ES** queries transparently: `nlp_service.normalize_arabic` collapses Alif/Ya/Ta-marbouta variants and strips tatweel + diacritics, `detect_language` classifies the query as `ar` / `latin` / `mixed`, and `LANGUAGE_SYNONYMS` in `nlp_rules.json` drives the cross-language translation in `NLPParser.translate_to_canonical` + `expand_terms`. Every translation lookup first tries the multilingual map before falling back to rapidfuzz typo-correction against domain vocabulary.

Cache: `data/redis_client.clear_search_cache()` wipes `search:*` keys whenever object state changes. Any router that mutates `Objet.statut`, reservations, or inventory must call it. The same hook is what eventually triggers BM25 corpus-stat and semantic-embedding rebuilds on the next query.

### Data model (`Backend/data/models.py`)
`Utilisateur` (roles `Utilisateur`/`Admin`) → `Reservation` → `Objet` → `Salle` → `Etage`. Many-to-many `Objet ↔ Fonctionnalite` via `association_objet_fonction`. `Alerte` and `Notification` both hang off `Objet`/`Utilisateur`. Statuses on `Objet`: `Disponible`, `Occupé`, `Panne`, `Signalé`. Ping monitor transitions these automatically when enabled.

### Frontend architecture
`src/App.jsx` is the single router definition. Auth is a localStorage `access_token` checked by the `PrivateRoute` wrapper — no context, no refresh flow. All HTTP goes through `src/services/api.js`, an axios instance with a request interceptor that attaches the bearer token; base URL is hardcoded to `http://127.0.0.1:8000`. Pages under `src/pages/` are one-to-one with routes; admin pages live under `/admin/*`. i18n is a lightweight custom hook in `i18n.jsx` (not react-i18next).

## Conventions

- Code, comments, and log messages are in French. Match that style when editing — don't translate existing strings.
- There are numerous ad-hoc scripts at the root of `Backend/` (`req_test.py`, `test_db.py`, `test_nlp.py`, `out*.txt`, `*.log`) — these are developer scratch files, not part of the app. Don't import from them and don't treat them as authoritative. The real tests are under `Backend/tests/`.
- Schema changes are applied via `Base.metadata.create_all()` on startup. There is no migration tool — additive-only changes are safe; destructive ones require manual SQL.
