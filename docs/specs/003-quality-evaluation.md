# Spec 003 — Quality and evaluation

Status: Accepted

## Test pyramid

- Unit: tokenization, requirement extraction, evidence matching, scoring, validation, redaction.
- Integration: FastAPI routes and structured response contracts.
- Evaluation: versioned synthetic cases with expected bands, required gaps, and forbidden claims.
- E2E: Playwright against a real local server.
- Final regression: browser inspection of the built application, console errors, responsive layout, and critical path.

## Initial gates

- Domain/application coverage: at least 85%.
- Schema validity: 100%.
- Score boundedness: 100%.
- Forbidden-claim rate: 0%.
- Expected-band accuracy on committed dataset: 100% for deterministic baseline.
- No live provider credentials in CI.

## Regression rule

Changing scoring behavior requires updating the scoring version and an explicit evaluation-baseline diff. Tests must not be weakened merely to accommodate an accidental regression.

