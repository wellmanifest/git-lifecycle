# Ticket 001: Define standalone Git lifecycle standard

- **ID**: ticket-001
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: PLAN
- **Created**: 2026-08-12

## Goal and scope

Extract the Git lifecycle module into an independently versioned local
repository. Define repository bootstrap, history, review, integration, release
and terminal workspace cleanup as a closed typed state machine. Include the
one-time autonomous seed-baseline transaction that resolves unborn `HEAD`
without authorizing a remote or publication effect.

## Acceptance criteria

- [ ] AC-01: The repository has an immutable published governance adoption and
  a real local seed baseline created before implementation.
- [ ] AC-02: A closed Draft 2020-12 schema defines request, state and receipt.
- [ ] AC-03: Request-only GBNF excludes shell, argv, paths, remote URLs and
  secret material.
- [ ] AC-04: Documentation defines the state machine, authority boundaries,
  autonomous seed transaction, idempotency and failure behavior.
- [ ] AC-05: Positive and adversarial conformance passes locally and in
  networkless, read-only Docker.
- [ ] AC-06: Governance and diff hygiene pass against the exact baseline.

## Authorization

The request to continue and extract this module as a new repository creates
`SESSION_EXECUTION_AUTHORIZATION` and the narrow autonomous seed-baseline
authorization. It allows exactly one local governance-only baseline commit
while `HEAD` is unborn and implementation is absent. It does not authorize a
remote, push, PR, merge, tag or release.

## Participants

- Human participant: unresolved; no `user-*` file was created.
- Agent participant: [ai-codex.md](ai-codex.md)
