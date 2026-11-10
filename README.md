# Enterprise MLOps & LLMOps Platform

A deployable, modular ML release-control and inference application, with a versioned prompt registry and optional LLM provider adapter. Built as a portfolio companion to an Enterprise AI OS.

**Current verification:** 26 automated tests passed; 200 local HTTP requests at concurrency 5 completed without errors. This is a **local deployment and development-grade validation**, not a publicly verified cloud deployment or enterprise-scale performance certification.

## Quick start (local Python)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest -q tests
python scripts/bootstrap.py
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ and enter the local demonstration inference key `local-inference-key-change-me`. Run `python scripts/smoke.py` and `python benchmarks/http_benchmark.py` in another terminal.

## Docker with PostgreSQL

Copy `.env.example` to `.env`, create distinct strong `POSTGRES_PASSWORD`, `INFERENCE_API_KEY`, and `ADMIN_API_KEY`, then:

```bash
docker compose up --build -d
docker compose exec api python scripts/bootstrap.py
docker compose ps
```

The Docker Compose stack must be verified on your own machine; Docker was not available in the authoring environment. Dashboard: http://127.0.0.1:8000/ . Documentation: http://127.0.0.1:8000/docs (do not expose on a public demo).

## Files

- `docs/PRODUCTION_SETUP_GUIDE.md`: complete numbered Windows development and VPS production instructions, security gates, release/rollback procedure and benchmark methodology.
- `docs/architecture.png`, `.svg`, `.mmd`: architecture diagrams.
- `app/main.py`, `app/core.py`, `app/llm.py`: FastAPI, model lifecycle, LLMOps prompt lifecycle.
- `scripts/train.py`, `scripts/bootstrap.py`, `scripts/smoke.py`: model and deployment tools.
- `tests/`: automated tests.
- `benchmarks/results.json`, `benchmarks/http_results.json`: measured local results.
- `.github/workflows/`: CI test + build and manual container publication workflows.
- `compose.yaml`, `Dockerfile`, `prometheus/`: container/deployment assets.

## Scope limitations

The ML example is a small synthetic text sentiment classifier. The prompt eval currently checks *format/template substitutions*, not LLM output quality; real OpenAI calls require `OPENAI_API_KEY`. Model versioning uses a custom PostgreSQL-backed registry; **MLflow is not installed**. Deployment is single-node, not HA; SSO, policy-governed user RBAC, full drift monitoring and auto-deploy must be added before enterprise production usage.

Official references: [MLflow model registry](https://mlflow.org/docs/latest/model-registry), [Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/), [GitHub Actions](https://docs.github.com/en/actions), [Prometheus](https://prometheus.io/docs/), [Caddy](https://caddyserver.com/docs/).
