# Enterprise MLOps & LLMOps Platform — Production Setup Guide

**Revision:** 1.0 | **Date:** 2026-11-10 | **Platform:** Windows 11 development; Ubuntu 24.04 VM/VPS deployment

> **Deployment status:** This package contains a tested application and deployment configuration. It was run locally with a SQLite backend and HTTP API. It has **not** been deployed to a public cloud endpoint or verified end-to-end under Docker Compose/PostgreSQL. Do not call it publicly deployed until you perform the acceptance checks below. Public hosting introduces cost and security responsibility.

## 1. What is implemented

- FastAPI inference service with key-based authorization and OpenAPI documentation.
- JSON-based immutable version records for a small trained bag-of-words logistic-regression classifier. Stored SHA-256 checksums are checked before inference.
- Champion and candidate aliases; server-side quality gate evaluated against a frozen **eight-example synthetic holdout**; manual promotion and targeted rollback; audit records.
- LLM prompt versioning, template substitution, simple deterministic formatting evaluation and promotion gate. OpenAI Responses API adapter can be enabled with credentials. **No end-to-end real-provider LLM benchmark has been run.**
- Browser interface for inference and registry inspection; Prometheus-compatible counters and histograms; isolated metrics exporter on container port 9101.
- GitHub Actions workflow for tests, local benchmark, Docker build; separate manually triggered image publication workflow for GHCR.
- PostgreSQL via SQLAlchemy + psycopg for deployment; SQLite for rapid local testing.

**Not yet implemented:** enterprise SSO/OIDC, team RBAC, multitenant isolation, full experiment tracking with MLflow, scheduled retraining, feature store, full automated canary traffic splitting, drift detection, cost monitoring, schema migrations, tamper-resistant audit storage, full production-grade LLM security and evaluations, managed cloud deployment, and end-to-end automated deployment/rollback. The example benchmark is intentionally small and should not be represented as enterprise model accuracy.

## 2. Architecture

See `architecture.png`, `architecture.svg`, and `architecture.mmd`. Data flow:

1. A training script produces a deterministic, portable JSON model artifact.
2. An authenticated administrator registers the model. The server evaluates it against a frozen dataset; it does not trust the claimed accuracy sent in the request.
3. The registry stores the artifact, checksum, evaluation score, version and audit record.
4. An admin promotes an eligible version to `champion` or `candidate`. An API client sends text to `/v1/predict` and receives a class label and the deployed model version.
5. An admin can roll back the champion to a verified older version. Rollback events are stored in the audit table.
6. Inference exposes operational metrics to a private Prometheus scraper. The dashboard calls the API with an inference key.
7. Versioned LLM prompts have their own registration, basic formatting checks, aliases, and an optional OpenAI-backed `/v1/llm/run` execution API.

## 3. Windows development prerequisites

Install and launch: Python 3.12, Docker Desktop (WSL2), Git, Visual Studio Code. You can verify installation in PowerShell:

```powershell
python --version
git --version
docker --version
docker compose version
```

Unzip the entire `Enterprise_MLOps_LLMOps_Platform.zip` into `C:\AI-Projects\enterprise-mlops-llmops`, then use VS Code **Open Folder** and choose that folder.

## 4. Run and test locally without Docker

Open a PowerShell terminal in the extracted project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

The `.env` file is a reference for shell exports or Docker Compose; **Python does not automatically load it**. The default demonstration keys work in a local-only environment. For a new local terminal, set them explicitly:

```powershell
$env:DATABASE_URL = 'sqlite:///./data/platform.db'
$env:INFERENCE_API_KEY = 'local-inference-key-change-me'
$env:ADMIN_API_KEY = 'local-admin-key-change-me'
python -m pytest -q tests
python benchmarks/run.py
python scripts/bootstrap.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a **second** PowerShell terminal in the same project directory:

```powershell
$env:INFERENCE_API_KEY = 'local-inference-key-change-me'
python scripts/smoke.py
python benchmarks/http_benchmark.py
```

Open http://127.0.0.1:8000/ and enter your inference key. Use a positive or negative short sentence and view the prediction. The API schema is available at http://127.0.0.1:8000/docs; do not expose interactive admin documentation on an unrestricted public demo.

## 5. Launch PostgreSQL-based Docker deployment locally

Docker Compose reads `.env` automatically. Create fresh random secrets before leaving local-only mode. Generate each secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Edit `.env` to contain **unique random** values:

```dotenv
POSTGRES_PASSWORD=REPLACE_WITH_LONG_RANDOM_PASSWORD_WITHOUT_URL_SPECIAL_CHARACTERS
INFERENCE_API_KEY=REPLACE_WITH_LONG_RANDOM_INFERENCE_KEY
ADMIN_API_KEY=REPLACE_WITH_DIFFERENT_LONG_RANDOM_ADMIN_KEY
MIN_ACCURACY=0.75
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
```

Run:

```powershell
docker compose up --build -d
docker compose ps
docker compose exec api python scripts/bootstrap.py
curl.exe http://127.0.0.1:8000/healthz
curl.exe http://127.0.0.1:8000/readyz
```

If `bootstrap.py` is rerun it registers a new immutable version; this is expected, not idempotent. In PowerShell, set the matching inference key and run the smoke test:

```powershell
$env:INFERENCE_API_KEY = 'THE_SAME_KEY_AS_IN_DOT_ENV'
python scripts/smoke.py
python benchmarks/http_benchmark.py
```

**Caveat:** The Compose configuration was authored but **not executed** in the authoring environment because Docker was unavailable. Verify it on your machine. Metrics are scraped on `api:9101` inside the Compose network; neither the database nor metrics exporter is bound to the public internet. Prometheus is accessible only from the host on `127.0.0.1:9090`.

## 6. Turn on LLMOps with an actual LLM

Use `OPENAI_API_KEY` in your local shell or Docker Compose `.env`. Without a key, `/v1/llm/run` deliberately returns HTTP 503. The baseline LLMOps workflow is **prompt registry and controlled template promotion**, not a claim of evaluated LLM answer quality.

Register a prompt via `/v1/prompts/register` with an administrator credential. Example JSON body:

```json
{
  "name": "enterprise-summary",
  "template": "Summarize the following synthetic operational note in 3 factual bullets: {note}",
  "cases": [
    {
      "context": {"note": "Three sites completed inspections."},
      "must_contain": ["Summarize", "Three sites"]
    }
  ]
}
```

Then promote `{ "name": "enterprise-summary", "version": 1 }` using `/v1/prompts/promote`. Call `/v1/llm/run` with an inference key:

```json
{"name":"enterprise-summary","context":{"note":"Three sites completed inspections."}}
```

**Security note:** Never use untrusted prompt contents to execute privileged tools. For a real production LLMOps service, add an LLM evaluation dataset (groundedness, refusal, injection resistance), per-model cost/usage caps, content filtering, retries/circuit breaker, PII policy, and vendor rate-limit handling.

## 7. Publish source code and enable CI/CD

1. Create a **private GitHub repository** first. Do not commit `.env`, credentials, local databases, customer data, or real enterprise prompts.
2. From the repository root:

```powershell
git init
git add .
git commit -m "Initial enterprise MLOps and LLMOps platform"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

3. GitHub Actions will run `pytest`, the in-process benchmark, and Docker build on each push/PR, subject to your repository's Actions settings.
4. Run **Publish immutable release to GHCR** using Actions > Workflow dispatch. The resulting image is tagged with a full commit SHA.
5. Configure branch protection, required reviews, dependency vulnerability checks, security scanning, and least-privilege GitHub Actions permissions.

**Important:** `publish.yml` **publishes** a container image; it does **not** automatically deploy the image to a server. That separation makes explicit deployment approval possible.

## 8. Deploy behind HTTPS on Ubuntu 24.04 VPS (single-node reference)

This is a pragmatic portfolio deployment path, not a highly available enterprise cluster.

1. Provision an Ubuntu 24.04 VM/VPS, size it for at least 2 vCPUs and ~4 GB RAM; choose a trusted provider and configure billing alerts.
2. Create a DNS `A` record for a subdomain you control (e.g., `mlops.example.com`) pointing to the VM's public IP.
3. Restrict inbound firewall traffic to 22/TCP from your management IP and 80/443 from intended clients. **Do not open 8000, 9101, 9090, or 5432 publicly.** Prefer SSH keys, disable password SSH, enable unattended security updates.
4. Install Docker Engine and its Compose plugin from the **official Docker Ubuntu repository**: https://docs.docker.com/engine/install/ubuntu/ . Follow the post-install least-privilege guidance; Docker group membership is effectively root-level access.
5. Install Caddy from https://caddyserver.com/docs/install . Caddy will provision and renew TLS certificates when your DNS and ports are correctly configured.
6. Clone your private repository to `/opt/enterprise-mlops-llmops` using a secure deploy key, or copy a released artifact via your deployment system. Do not copy your development `.env` blindly.
7. Create `/opt/enterprise-mlops-llmops/.env` with unique production API keys and database password. Set file permissions to owner-only and use a dedicated deploy account.
8. In that directory run `docker compose up --build -d`, then `docker compose ps`. Verify `curl http://127.0.0.1:8000/readyz` returns ready.
9. Run the seed **one time**: `docker compose exec api python scripts/bootstrap.py`.
10. Copy `infra/Caddyfile.example` to the system Caddy config, replace `mlops.example.com` with your actual domain, validate the config, and restart Caddy. It proxies HTTPS requests to the API on host loopback port 8000.
11. Confirm that `https://YOUR_DOMAIN/healthz` responds and HTTPS is valid. Run `BASE_URL=https://YOUR_DOMAIN python scripts/smoke.py` with the appropriate inference key in the environment.
12. Set up backups of the Postgres data, encryption at rest, secret rotation, patching, log retention and a restore drill. For a more robust production workload use a managed database, multi-instance deployment and infrastructure-as-code.

### Deployment safety gate — do before sharing the link

The included sample dashboard accepts an API key typed into a browser; **it is not appropriate for unrestricted public visitor access**. Add OIDC/SSO or put the entire application behind a trusted identity-aware reverse proxy (such as OAuth2 Proxy) and restrict admin endpoints to an internal network. Apply rate limiting, request body size limits, and a suitable WAF/abuse protection. Avoid leaving `/docs` and administrative operations available to the internet. A public portfolio demo should preferably expose only a **read-only, rate-limited** prediction view against synthetic data. Add tenant-scoped permissions if connecting real organizational agents.

## 9. Release promotion and rollback procedure

1. Train and evaluate a candidate. Keep the training dataset, held-out dataset, configuration, code commit, and hash of the model artifact.
2. Register a new model version via `/v1/models/register` (administrator credential). The server computes its own score on the synthetic holdout before registration.
3. Promote to `candidate` alias using `/v1/deployments/promote`. Run shadow / separate candidate tests; the included API does not automatically split real traffic.
4. Review measured error rate, p95 latency, classification quality, model behavior, and business approval.
5. Promote the chosen version to `champion` with `/v1/deployments/promote`. Confirm `/v1/predict` returns the correct version.
6. If performance regresses, send `/v1/deployments/rollback` with the exact previously validated `version` and verify new predictions use it. An audit record is written.
7. **Application/container rollbacks** require redeploying the prior immutable container image SHA. Model alias rollback does not revert API schema or code changes.

## 10. Operational metrics and alerting

- `mlops_inferences_total{model,status}`: count of inferences and missing deployments.
- `mlops_inference_seconds_bucket{model}`: request latency histogram, enabling p50/p95/p99 calculations.
- `/readyz`: database connectivity check.
- `/v1/audit`: restricted release history.
- The Prometheus exporter is on private TCP 9101; Prometheus is bound to host loopback at TCP 9090.

Configure alerts for service-down events, elevated 5xx response rates, p95 latency regressions, insufficient model accuracy, and data/storage issues. Add OpenTelemetry traces and provider tokens/cost tracking for an advanced portfolio submission. Current metrics do **not** capture LLM token usage/cost, drift, or data-quality distributions.

## 11. Benchmark and evaluation methodology

Run `python benchmarks/run.py` for **in-process** classifier throughput. Run `python benchmarks/http_benchmark.py` with a seeded running API for **local HTTP + SQLAlchemy database** latency. Record CPU/OS, dataset, version, commit SHA, database backend, concurrency, request count, warm-up behavior, and model type.

The packaged baseline reports 26 passing automated tests. The synthetic holdout classifier has eight cases and yielded 100% accuracy. This tiny, deliberately easy dataset is **not representative production accuracy**. The local HTTP benchmark used 200 requests with 5 concurrent threads; see `benchmarks/http_results.json` for measured throughput and percentiles. These numbers are **not cloud performance benchmarks**, nor LLM latency or throughput.

Next, create a de-identified 500–2000-example external evaluation set with previously unseen language and edge cases. Add class-imbalance checks, confidence calibration, confusion matrix, and time-based drift analysis. For real LLM evaluations, score factuality, safety, instruction following, prompt injection and cost per successful task. Run k6/Locust against the *deployed* system with explicit load ceilings and provider quotas.

## 12. Enterprise AI OS integration

Give each AI OS department agent access through a scoped server-side adapter, not a hard-coded key in its browser or prompt. Example Python:

```python
import os, requests

def classify_visitor_message(text: str):
    url = os.environ['MLOPS_BASE_URL'].rstrip('/') + '/v1/predict'
    response = requests.post(
        url,
        headers={'X-API-Key': os.environ['MLOPS_INFERENCE_API_KEY']},
        json={'model': 'sentiment', 'text': text, 'alias': 'champion'},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
```

Wrap the adapter in your orchestration layer, enforce department/tenant scope, and log request identifiers without leaking proprietary prompt contents. Treat the current toy model as a deployment demonstration rather than a useful enterprise business classifier.

## 13. Portfolio publication checklist

- [ ] Public demo URL works over HTTPS with suitable authentication and abuse controls.
- [ ] GitHub repository includes README, architecture, design decisions and clear implementation status.
- [ ] CI test workflow and container build green; image pinned by commit SHA.
- [ ] One successful promotion and one tested rollback shown in a recorded demo.
- [ ] ML holdout results and HTTP benchmark reproduced on deployed infrastructure.
- [ ] At least one real LLM task evaluated with provider usage, quality and cost if claiming full LLMOps deployment.
- [ ] Real secrets excluded from git; admin endpoints restricted; backup restore verified.
- [ ] Screenshots or video demonstrate actual behavior, not a mock image.
- [ ] Published metrics identify dataset size, hardware, environment, model and date.

## 14. Resume language (only after verified)

**Local-verified version:** “Built an API-driven MLOps/LLMOps operations platform with versioned model artifacts, evaluation-based promotions, authenticated inference, rollback auditing, CI testing, container configuration, prompt registry, and measurable local API benchmarks.”

**After hosting and completing security/observability gates:** “Deployed an HTTPS-accessible MLOps/LLMOps platform with reproducible model promotion and rollback, containerized CI/CD release artifacts, operational monitoring, and documented accuracy and latency benchmarks.”

Do not claim Kubernetes orchestration, MLflow integration, full enterprise-grade SSO, continuous deployment, production LLM quality, or multi-tenant isolation until those capabilities have actually been implemented and independently verified.
