# Capability Analysis — Full Stack

A modernization of the legacy desktop capability analysis into a **FastAPI backend** and **Next.js frontend**. The project keeps the score explainable, places a learner against the topic cohort, and offers evidence-based next steps. The old project files are not changed.

## What the application provides

- Student lookup by registered email, with a choice when that email maps to multiple student accounts.
- Complexity-weighted performance by topic and overall.
- An early/developing/established evidence indicator based on the number of answered questions; early results are explicitly provisional.
- Topic-level percentile and nearest peers for cohort context. This is a stable sorted comparison, not a repeatedly refitted one-feature KMeans cluster.
- User-neighborhood collaborative filtering recommends unattempted topics taken by students with similar topic-score profiles; general popularity suggestions fill any remaining slots when peer evidence is sparse.
- Latest-test chapter feedback flags chapters below 60% within the selected topic, matching the legacy app's study-area guidance.
- Same-origin API routing: Next.js proxies `/api/*` to FastAPI during development; the included Nginx config routes `/api/*` to FastAPI in deployment.
- A one-time data-preparation step for the large source file. The API reads compact summaries and does not parse the 1.2 GB raw CSV in web requests.
- Email-based student lookup using a separate keyed-digest index; raw email and password fields are not copied into generated files.

## Project layout

- `backend/app/` — FastAPI endpoints and analytics service.
- `backend/scripts/prepare_dataset.py` — DuckDB-based source ingestion and preparation.
- `backend/data/processed/` — generated CSV files (not committed; contains derived student data).
- `backend/tests/` — analytics tests.
- `frontend/src/app/` — responsive Next.js dashboard.
- `DATASET_AND_METHODOLOGY.md` — step-by-step explanation of the source data, columns, scoring, endpoints, and caveats.
- `RECOMMENDATIONS.md` — modernization recommendations retained from the initial review.

## Quick start (macOS)

Prerequisites: Python 3.9 or newer and Node.js 20.9 or newer.

### 1. Prepare backend environment

From this folder:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Prepare the dataset (first run or after refreshing source data)

The default input is `../Final/final_revised.csv`, the available enriched response export. It is approximately 1.2 GB; allow disk space and time for DuckDB temporary files and output. The original source is only read, never modified. The processed results are written under `backend/data/processed/`.

Email lookup IDs and display names come from `../tables_chosen/tbl_users_1.csv`. The script reads only `id`, `first_name`, `last_name`, and `email`, hashes normalized email values with HMAC-SHA256, and writes the local lookup index. It does not copy user password hashes or plain email addresses. Shared email addresses are disambiguated by asking the operator to choose a named account. The default HMAC secret is for local development only; set `CAPABILITY_EMAIL_LOOKUP_SECRET` to the same private value before both preparation and API startup in any deployment, then regenerate the lookup index.

```sh
python scripts/prepare_dataset.py
```

To use a different file, set `CAPABILITY_RAW_DATA` to an absolute path before running the script. See the dataset guide for required source columns and generated outputs.

### 3. Start the API

Run from `backend/` with the virtual environment active:

```sh
uvicorn app.main:app --reload
```

The API docs are available at `http://localhost:8000/docs`. `GET /api/health` reports whether prepared data is ready. The browser uses `/api/*` on the frontend origin; Next.js development rewrites proxy these routes to FastAPI at `127.0.0.1:8000`.

### 4. Start the web app

In another terminal:

```sh
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000`. Frontend API requests use same-origin `/api/*` routes, proxied to FastAPI by Next.js in development.

## One-command Docker run (Nginx + backend + frontend)

Docker Compose starts the production Next.js container, FastAPI container, and Nginx reverse proxy. The browser only needs the Nginx URL; Nginx sends `/api/*` to FastAPI and all other requests to Next.js. The first startup automatically processes the mounted raw CSV and can take several minutes. Processed data is retained in the named `capability-data` volume for later starts.

Prerequisite: install and start Docker Desktop (or another Docker Engine with Compose v2). From this project directory:

```sh
docker compose up --build
```

Then open `http://localhost:8082` (the default avoids common local 8080 conflicts). Use `docker compose up --build -d` to run in the background, and `docker compose down` to stop. `docker compose down -v` also deletes the generated data volume and should only be used if you intend to rebuild all derived data.

The default bind mounts expect the original files at `../Final/final_revised.csv` and `../tables_chosen/tbl_users_1.csv`, relative to this project folder. If they are elsewhere, copy `.env.docker.example` to `.env` and update the paths. The optional `.env` can also change `APP_PORT` or set `CAPABILITY_EMAIL_LOOKUP_SECRET`. Keep the lookup secret stable after data preparation; changing it requires regenerating the index by removing/recreating the processed volume or rerunning the preparation script with the new secret. The sample secret is for a local demo only. Before exposing this stack to a network, configure a strong secret, HTTPS, and authentication/authorization; email lookup alone is not authentication.

## Frontend/backend connection and Nginx

The frontend does not call FastAPI from a separate browser origin. It requests `/api/...` relative to its own host. This avoids browser CORS configuration for the normal deployment path.

- **Local development:** `frontend/next.config.ts` rewrites `/api/:path*` to `http://127.0.0.1:8000/api/:path*` while `next dev` is running.
- **Deployment / Nginx:** the Docker Compose setup runs all three services on a private Compose network. Nginx forwards `/api/` to the FastAPI service and all other routes to Next.js. Only Nginx publishes a host port (`8080` by default).
- **Production security:** terminate HTTPS at Nginx, add authentication/authorization before exposing student records, and keep both app services private behind the proxy. The provided file is a starting point; TLS certificates, domain, and auth are deployment-specific and are not configured here.

## Tests and checks

Backend tests, from `backend/`:

```sh
pytest
```

Frontend production build, from `frontend/`:

```sh
npm run build
```

The preprocessor should be validated against a small, approved sample before processing the full export. Review source data quality and the limitations in `DATASET_AND_METHODOLOGY.md` before using results for consequential decisions.

## Important interpretation and privacy notes

The score weights correct answers by assigned complexity (1, 2, or 3) and divides by weighted maximum points. It does not award points merely for attempting more questions. It is still a baseline—not a validated psychometric ability estimate. Topic recommendations now use a neighborhood collaborative-filtering algorithm: similar students are identified from score profiles on shared topics, and unattempted topics are ranked using their similarity and peer results. General-popularity fallback items are labeled separately. Chapter feedback is a transparent rule: chapters below 60% on the latest available test date for the selected topic. This recommender is not a validated latent-factor model. The current delivery does **not** claim a fitted or validated IRT model; that should follow after item keys, response encoding, data sufficiency, and held-out evaluation are confirmed.

The processed attempt file and email digest index contain student-linked information. Treat them as sensitive and restrict access. Email lookup is **not authentication**: protect student endpoints with authorization before exposing the service. The UI/API omit names, plain emails, free-text answers, and queries. Do not expose this service publicly without authentication, authorization, privacy review, and transport security.
