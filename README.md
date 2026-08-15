<div align="center">

[![AI CV Advisory Board walkthrough](docs/assets/demo/free-advisory-review.gif)](https://ai-cv-advisory-board-production-142795288331.us-central1.run.app/workspace)

# 🧭 AI CV Advisory Board

**An evidence-grounded career workspace — review CVs with an AI panel, tailor them safely, and track every application with the exact CV version sent.**

A production-oriented career platform where a selectable panel of AI specialists compares a CV with a role, explains the evidence and gaps, and proposes defensible next steps without inventing experience.

*A portfolio build by [Carlos Rodríguez](https://github.com/carlosan1708) demonstrating production AI-feature engineering: structured model output, deterministic evaluation, privacy-safe observability, hard cost controls, browser security, and spec-first delivery.*

[**🌐 Live demo → AI CV Advisory Board**](https://ai-cv-advisory-board-production-142795288331.us-central1.run.app/)

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-8E75B2?logo=googlegemini&logoColor=white)
![Cloud Run](https://img.shields.io/badge/Google_Cloud-Cloud_Run-4285F4?logo=googlecloud&logoColor=white)
![Firestore](https://img.shields.io/badge/Data-Firestore-FFCA28?logo=firebase&logoColor=black)
![Playwright](https://img.shields.io/badge/Tests-Playwright-2EAD33?logo=playwright&logoColor=white)

</div>

---

## 🧠 AI engineering highlights

The interesting engineering here is the trust boundary around the AI, not a generic prompt-to-text form:

- **User-composed advisory board** — the user selects up to three specialists. Their briefs are included in one bounded Gemini request, and the report contains one grounded finding per selected advisor ([`advisors.py`](src/advisory/advisors.py), [`ai.py`](src/advisory/ai.py)).
- **Canonical deterministic evidence layer** — a versioned scorer extracts role requirements and maps them to direct CV evidence before model prose is shown. If Gemini is unavailable or a budget is exhausted, the evidence review still completes without pretending the fallback is AI-generated ([`domain.py`](src/advisory/domain.py), [`service.py`](src/advisory/service.py)).
- **Strict structured output** — Gemini 2.5 Flash returns a typed review contract with bounded output and thinking disabled. Model output is validated, escaped, and never allowed to create unsupported candidate claims.
- **Hardened document and URL ingestion** — PDF/TXT uploads are bounded by bytes, pages, and extracted characters. Job-link fetching permits only public HTTPS destinations, revalidates redirects and DNS results, checks the connected peer, limits response size, and falls back to manual paste ([`ingestion.py`](src/advisory/ingestion.py)).
- **Atomic cost controls** — every model request reserves its maximum possible cost in Firestore before reaching Vertex AI, then reconciles against actual token usage. Separate ledgers enforce the anonymous pool, approved-member allowance, and project emergency ceiling ([`budget.py`](src/advisory/budget.py), [`google_persistence.py`](src/advisory/google_persistence.py)).
- **Private, immutable career assets** — CV versions are independent records. An application stores the exact version used, while edits create a new version instead of silently changing historical evidence.
- **Privacy-safe AI operations** — the administrator sees usage, status, model, advisor composition, tokens, estimated cost, and latency. CV text, job text, prompts, and generated prose are deliberately excluded from the audit store ([`ai_audit.py`](src/advisory/ai_audit.py)).
- **Browser-level security** — verified Google identity, owner-scoped records, administrator-controlled access, same-origin write checks, HTTP-only sessions, CSP, HSTS, no-store private responses, rate limits, and structured abuse signals protect the public Cloud Run service.

**How a free advisory review flows:**

```text
CV upload + job URL (or pasted description)
  → bounded document parsing + SSRF-safe job retrieval
  → deterministic requirement/evidence cross-check
  → selected specialist briefs
  → one Gemini structured review (or clearly labelled fallback)
  → grounded panel report + safe edits + interview preparation
```

The anonymous flow is session-only and does not persist the uploaded CV or job description. Approved members can explicitly save CV versions, applications, and their attachments in an owner-scoped private workspace.

---

## ✨ Features

|  | Feature | Description |
|--|---------|-------------|
| 🧑‍⚖️ | **Selectable AI expert panel** | Choose a balanced board or compose up to three specialists for the review you need. |
| 📄 | **Document-first CV review** | Upload a PDF/TXT CV and review it independently or compare it with a specific opportunity. |
| 🔗 | **Job-link ingestion** | Start with a public HTTPS job URL and recover with a paste fallback when the source blocks automated reading. |
| 🧾 | **Evidence ledger** | See which requirements have direct CV support, what is missing, and exactly which source lines were used. |
| ✍️ | **Safe CV tailoring** | Receive edits grounded in existing experience; approved users can save revisions as new immutable CV versions. |
| 📊 | **Application pipeline** | Track Interested → Applied → Interviewing → Offer → Closed in an interactive dashboard. |
| 🔒 | **Exact-version attachment** | Preserve the CV version sent with every application so later edits never rewrite history. |
| 🗂️ | **Read-only workspace history** | Archive the active search, start clean, and inspect past applications and CV versions without restoring them. |
| 👤 | **Controlled private access** | Anyone can try the free review; only administrator-approved Google identities enter the persistent workspace. |
| 🛡️ | **Admin control center** | Approve members and inspect privacy-safe AI usage, cost, latency, status, and abuse signals. |

---

## 📸 More demos

All walkthroughs use synthetic career data and the deterministic local reviewers. They expose no personal CV and consume no paid AI allowance.

### Application tracker and AI expert panel

Track applications across the funnel, focus a stage, preserve the CV version used for each role, and open the three-lens expert panel for a second opinion.

[![Animated walkthrough of the application tracker and AI expert panel](docs/assets/demo/application-tracker.gif)](https://ai-cv-advisory-board-production-142795288331.us-central1.run.app/dashboard)

### CV library and immutable revisions

Review a CV independently, inspect its strengths and gaps, edit the extracted content, and save a new version without overwriting the original.

[![Animated walkthrough of standalone CV review and immutable versioning](docs/assets/demo/cv-library-review.gif)](https://ai-cv-advisory-board-production-142795288331.us-central1.run.app/cvs)

The capture scenarios, privacy rules, and media constraints are documented in [Spec 016](docs/specs/016-readme-product-demos.md).

---

## 🛠 Stack

| Layer | Technology |
|-------|------------|
| Web UI | Server-rendered Jinja2, semantic HTML, CSS, and vanilla JavaScript |
| API | Python 3.11+, FastAPI, Pydantic |
| Identity | Google ID-token verification + hardened HTTP-only application session |
| Database | Firestore for owner-scoped career records, budgets, access, and audit metadata |
| Files | Private Cloud Storage objects for immutable CV bytes |
| AI | Vertex AI + Gemini 2.5 Flash with strict structured output |
| Runtime | Docker on Google Cloud Run |
| Tests | pytest, coverage, offline evaluations, and Playwright E2E |

---

## 🚀 Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
playwright install chromium
uvicorn src.advisory.web:app --reload
```

Open `http://127.0.0.1:8000`.

Local mode uses in-memory adapters, a development identity, deterministic reviewers, and synthetic demo data. It does not require Google credentials, Firestore, Cloud Storage, or a paid model call.

### Requirements

- Python 3.11+
- A Chromium browser for Playwright
- Google Cloud credentials only when running the production adapters

Production configuration and rollout checks are documented in [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

---

## 📋 Quality commands

```powershell
ruff check .
mypy
pytest
python -m evals.runner
pytest tests_e2e --override-ini='testpaths=tests_e2e' --no-cov -q
```

The default pytest gate enforces at least **85% coverage** for `src/advisory`.

---

## 🧪 Tests and evaluations

Four complementary layers keep the AI feature testable without paid services:

- **Unit and domain tests** — scoring, advisors, budgets, access, repositories, ingestion, rate limits, audit events, and services.
- **API and security tests** — FastAPI contracts, authentication, authorization, same-origin mutations, headers, upload bounds, URL-fetch defenses, provider failures, and budget enforcement.
- **Deterministic evaluations** — synthetic compatible, partial, incompatible, and adversarial CV/job pairs in [`evals/cases.json`](evals/cases.json), run through a versioned offline scorer.
- **Playwright E2E** — real browser flows for the welcome choice, free review, panel composition, dashboard, CV library, archive history, administrator view, recovery states, mobile layout, and clean console output.

No test contacts Gemini, Firestore, Cloud Storage, or a production identity provider.

---

## 🏗 Architecture

```text
Browser
  ├─ Free review ───────────────┐
  └─ Approved workspace        │
       ├─ Application tracker  │
       ├─ CV library           │
       ├─ Read-only history    │
       └─ Admin control center │
                               ▼
FastAPI web adapter
  ├─ CV parser + SSRF-safe job fetcher
  ├─ Deterministic assessment service
  ├─ Gemini review adapters
  ├─ Identity, access, rate, and budget guards
  └─ Privacy-safe logging and AI audit events
             │
             ├─ Firestore (records, access, budgets, audit metadata)
             ├─ Cloud Storage (private immutable CV files)
             └─ Vertex AI (Gemini 2.5 Flash)
```

```text
src/advisory/
  web.py                  # Routes, sessions, HTTP security, dependency wiring
  service.py              # Deterministic CV–job assessment orchestration
  domain.py               # Versioned evidence scoring and typed results
  ai.py                   # Structured Gemini adapters and fallback behavior
  advisors.py             # Selectable specialist catalog and board rules
  ingestion.py            # Bounded CV parsing and hardened job retrieval
  career.py               # Application, CV-version, and archive domain models
  tracker_service.py      # Owner-scoped career-workspace use cases
  access.py / auth.py     # Approval and verified identity boundaries
  budget.py               # Atomic reservation-ledger contract
  ai_audit.py             # Privacy-safe operational review metadata
  google_persistence.py   # Firestore and Cloud Storage production adapters
  observability.py        # Structured logging with sensitive-field filtering
  templates/              # Welcome, review, tracker, CV library, and admin views
  static/                 # Route-specific CSS and JavaScript
```

The domain and service layers do not depend on FastAPI, the browser, Google Cloud, or Gemini. Production adapters implement the same contracts as the deterministic in-memory test adapters.

---

## 🔐 Access, privacy, and spend controls

- The **free mode** needs no login, keeps source documents in memory only, and shares a monthly USD 5 AI ceiling.
- The **approved mode** uses administrator-controlled Google identities and has a monthly USD 10 AI ceiling per member.
- A project-wide USD 50 emergency ceiling applies before every provider call.
- Firestore transactions reserve worst-case request cost atomically across Cloud Run instances.
- Burst guards permit 2 anonymous AI attempts/minute/client and 10 approved attempts/minute/user.
- Private career data is keyed by Google's stable subject claim, not a mutable email address.
- Logs and the admin audit view never store CV text, job text, prompts, filenames, full URLs, or generated AI prose.
- Security denials, repeated uploads, and blocked AI bursts emit structured events for monitoring and alerting.

See the complete [`threat model`](docs/THREAT_MODEL.md) and [`operations guide`](docs/OPERATIONS.md).

---

## 🚢 Deployment

- **Google Cloud project:** `ai-cv-advisory-board`
- **Cloud Run service:** `ai-cv-advisory-board-production`
- **Region:** `us-central1`
- **Health endpoint:** [`/api/health`](https://ai-cv-advisory-board-production-142795288331.us-central1.run.app/api/health)

The service is stateless, listens on `$PORT`, and can scale to zero. Firestore and Cloud Storage hold durable private state; Vertex AI provides the model boundary.

---

## 📐 Spec-first engineering trail

The repository records product decisions before implementation so the result demonstrates a repeatable way of working, not only a finished interface:

1. [Product specification](docs/specs/001-product.md)
2. [Architecture specification](docs/specs/002-architecture.md)
3. [Quality and evaluation specification](docs/specs/003-quality-evaluation.md)
4. [Advisory workspace interface](docs/specs/004-interface-redesign.md)
5. [Product interface recovery](docs/specs/005-product-interface-recovery.md)
6. [Document-first review](docs/specs/006-document-first-review.md)
7. [Career pipeline](docs/specs/007-career-pipeline.md)
8. [Tiered access](docs/specs/008-tiered-access.md)
9. [CV library and navigation](docs/specs/009-cv-library-and-navigation.md)
10. [Expert panel and persistent session](docs/specs/010-expert-panel-and-session.md)
11. [Browser security guardrails](docs/specs/011-browser-security-guardrails.md)
12. [AI cost and abuse guardrails](docs/specs/013-ai-cost-and-abuse-guardrails.md)
13. [Workspace history](docs/specs/014-workspace-history.md)
14. [Free advisory-board experience](docs/specs/015-free-advisory-board-experience.md)
15. [README product demos](docs/specs/016-readme-product-demos.md)
16. [ADR 001: deterministic baseline first](docs/adr/001-deterministic-baseline.md)

Together, the specs, threat model, operations guide, automated tests, deterministic evaluation set, and browser demos form the engineering evidence for the project.
