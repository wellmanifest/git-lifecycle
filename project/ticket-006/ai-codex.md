---
participant-id: agent:codex
participant: codex
role: agent
ticket: ticket-006
---
# Participant: codex (AI agent)

## Context and decision

`subactor founder` could not resolve a safe repository-development process,
and the existing OneDev bootstrap deliberately stops after creating and
validating an empty private repository. The current Git lifecycle owns one
local `seed-baseline` commit and explicitly forbids remote effects. Reusing
either authority would collapse two trust boundaries.

The `repository-responsibility-boundary` skill classifies this as a stable
security/authority boundary. Add a complementary standard here; later adopters
will implement it in a small Subactor runtime component.

## Execution plan

1. Add a closed initial-ref schema with separately bound plan, grant,
   publication and terminal Validator receipts.
2. Add a standalone Lifecycle DSL state machine for remote publication.
3. Add dependency-free positive and adversarial conformance checks.
4. Document composition with local seed and Skills handoffs.
5. Run all standard and governance checks before protected publication.

## Actual changes

- Added a closed four-document `repository-initial-ref/v1` handoff family.
- Added the independent remote state machine without changing the local v1
  lifecycle profile.
- Added digest pinning, positive accepted/quarantined flows and ten adversarial
  authority, drift, force, substitution, validation and secret cases.
- Documented ownership boundaries and raised the package version to 0.2.0-dev.
- Local JSON Schema fixtures, both conformance suites, Lifecycle validation,
  governance and diff hygiene pass.

## Blockers

- None inside the standard change. Runtime publication remains separately
  authority-bound.
