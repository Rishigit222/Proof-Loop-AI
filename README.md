# ProofLoop AI

ProofLoop AI is an open-source, evidence-first reliability workbench for AI-generated decisions. It extracts candidate claims, checks them against named source text using conservative deterministic rules, proposes evidence-grounded repairs, and requires an explicit human decision.

## Principles

- The original answer is preserved; revisions are separate records.
- `supported` requires a direct textual match. Similarity alone is not proof.
- Explicit conflicts become `contradicted`; conflicting sources become `needs_review`.
- Missing evidence is reported as `unsupported`, never silently accepted.
- Verification metrics are coverage metrics, not probabilities that an answer is true.
- The core engine is offline and does not require model credentials or paid APIs.

## Requirements

- Python 3.12 (pinned in `.python-version`)
- Docker 24+ for container use

## Local setup and run

```bash
python -m venv .venv
# Windows: .venv\Scripts\python -m pip install -r requirements.lock
# Linux/macOS: .venv/bin/python -m pip install -r requirements.lock
python -m uvicorn proofloop.main:app --reload
```

Open http://127.0.0.1:8000. The SQLite database is created at `data/proofloop.db` by default. Configure `DATABASE_URL`, `HOST`, and `PORT` through `.env`; copy `.env.example` as a safe starting point.

## Test

The single documented test command is:

```bash
pytest -q
```

The suite is offline and uses the pure verification engine. It covers extraction offsets, direct support, unsupported claims, contradictions, ambiguity, provenance, metrics, malformed input, and repair proposals. API persistence tests are included in `tests/test_api.py` and use an isolated temporary SQLite database.

## Docker

```bash
docker build -t proofloop-ai .
docker run --rm -p 8000:8000 -v proofloop-data:/app/data proofloop-ai
```

The container binds to `0.0.0.0` and honors `PORT`. Mount `/app/data` to retain SQLite state. Deployments with ephemeral disks will lose cases after restart; use a persistent disk or migrate the SQLAlchemy layer to PostgreSQL for a multi-instance deployment.

## Demo

From the dashboard, choose:

1. **Supported: offline verification** — direct source-backed findings.
2. **Unsupported: enterprise synchronization** — no adequate evidence.
3. **Contradicted: external model required** — the source explicitly says the engine runs offline.

Then open a case, inspect source excerpts and offsets, run verification again, and record an approval or rejection. Export the audit JSON from the case page.

## API

- `GET /health`
- `GET /api/cases`
- `POST /api/cases`
- `GET /api/cases/{id}`
- `POST /api/cases/{id}/claims/extract`
- `PATCH /api/claims/{claim_id}`
- `POST /api/cases/{id}/verify`
- `POST /api/cases/{id}/repairs/apply`
- `POST /api/cases/{id}/decision`
- `GET /api/cases/{id}/audit`
- `GET /api/cases/{id}/export`
- `GET /api/demo/{supported|unsupported|contradicted}`

## Architecture

The app is a modular monolith. `proofloop/engine.py` is pure deterministic domain logic. `services.py` translates engine reports to persisted records. `models.py` contains the SQLite schema. `main.py` exposes FastAPI endpoints and server-rendered views. The optional future provider boundary should be used only for claim suggestions or summarization; it must never silently become the source of verification truth.

## Metrics

- Total claims = supported + contradicted + unsupported + needs review.
- Verification coverage = (supported + contradicted) / total claims.
- Verification completion is complete only when every active claim has a result from the current run.

These metrics describe what the local rules could verify. They are not calibrated truth probabilities.

## Deployment

Render, Railway, or another Docker host can run the image with `PORT` supplied by the platform. Configure a persistent volume for `/app/data`, expose `/health` as the health check, and do not put credentials in the image. A production multi-user deployment should add authentication, request limits, encrypted storage, and PostgreSQL before handling sensitive evidence.

## Limitations

The MVP uses sentence extraction and strict normalized token matching. It does not understand every entailment, resolve every coreference, ingest PDFs, browse the web, or use an external generative model. Compound claims and hedged language are deliberately routed toward review. Audit events are application records, not cryptographically tamper-proof logs.

## Demo talk track

In 2–3 minutes: open the supported demo, show the direct excerpt and offsets; open the unsupported demo and show the evidence gap; open the contradicted demo and show the explicit conflict; apply a remove/rewrite repair through the API/UI; re-run verification; approve or reject explicitly; export the audit JSON; finish by running `pytest -q`.
