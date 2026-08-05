# Threat model

## Assets

- CV content and contact information.
- Job-search intentions.
- Provider credentials in future phases.
- Integrity of recommendations.

## Trust boundaries

All browser input is untrusted. Future scraped documents and LLM output are also untrusted. Application logs and downloadable artifacts are separate disclosure surfaces.

## v0.1 controls

- Strict input size and type constraints.
- No arbitrary URL fetching, eliminating SSRF in this slice.
- No persistence and no user-built authentication.
- No live LLM, eliminating prompt-injection execution in this slice.
- HTML escaping through Jinja defaults.
- Structured output schema and versioned deterministic policy.
- Logs contain metadata only, never submitted text.

## Deferred risks

Before URL ingestion: safe DNS/IP validation, redirect validation, byte limits and content-type rules are mandatory. Before live LLM use: data delimiters, typed outputs, evidence citations, claim validation, bounded retries and adversarial evaluations are mandatory. Before persistence: verified identity-derived ownership and authorization tests are mandatory.

