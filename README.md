# AI CV Advisory Board — Production Edition

A spec-first reconstruction of the AI CV Advisory Board. The repository is intended to demonstrate not only a product, but a repeatable engineering process: explicit requirements, architectural decisions, threat modeling, deterministic evaluation, automated tests, observability, and browser-level regression evidence.

## Current vertical slice

- Paste a CV and a job description.
- Receive a deterministic, explainable CV–job match assessment.
- See matched requirements, evidence gaps, and safe recommendations.
- Use a synthetic demo without an API key.
- Export a JSON result carrying schema and scoring versions.
- Run unit, integration, evaluation, and Playwright browser tests without paid services.

The deterministic engine is deliberate: it establishes a measurable baseline before adding Gemini behind a typed adapter. No score is presented as a simulation of a commercial ATS.

## Engineering trail

1. [Product specification](docs/specs/001-product.md)
2. [Architecture specification](docs/specs/002-architecture.md)
3. [Quality and evaluation specification](docs/specs/003-quality-evaluation.md)
4. [Advisory workspace interface specification](docs/specs/004-interface-redesign.md)
5. [Product interface recovery specification](docs/specs/005-product-interface-recovery.md)
6. [Threat model](docs/THREAT_MODEL.md)
7. [ADR 001: deterministic baseline first](docs/adr/001-deterministic-baseline.md)

## Local setup

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
playwright install chromium
uvicorn src.advisory.web:app --reload
```

Open `http://127.0.0.1:8000`.

## Quality gates

```bash
ruff check .
mypy
pytest
python -m evals.runner
pytest tests_e2e -q
```

## Deployment target

Google Cloud project: `ai-cv-advisory-board`. The container is designed for Cloud Run and listens on `$PORT`.

- Production service: https://ai-cv-advisory-board-production-142795288331.us-central1.run.app
- Region: `us-central1`
- Cloud Run service: `ai-cv-advisory-board-production`
- Initial production revision: `ai-cv-advisory-board-production-00001-6tc`
