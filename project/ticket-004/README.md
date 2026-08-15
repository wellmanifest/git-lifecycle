# Ticket 004: Define one-main zero-PR repo hygiene invariant

- **ID**: ticket-004
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-08-15

## Goal and scope

Publish a closed observation contract for GitHub repository hygiene: default
branch `main` is the only long-lived branch and a healthy repo has 0 open pull
requests. Work that moved in the last 2 hours is in-progress and must be left
alone. Stale extras are data for `subactor/doctor-agent`, not an instruction to
merge or delete.

## Acceptance criteria

- [ ] AC-01: `python3 standard/repo_hygiene.py --all` proves clean (no emit),
  fresh PR (no emit), stale PR ≥2h (emit) and stale extra branch ≥2h (emit).
- [ ] AC-02: Existing Lifecycle DSL conformance still passes.
- [ ] AC-03: Governance and diff hygiene pass against `c01a822`.

## Authorization

The request to implement this invariant across wellmanifest/subactor/semcod
creates `SESSION_EXECUTION_AUTHORIZATION`. It does not authorize a pull
request, merge, force-push or branch deletion.

## Participants

- Human participant: unresolved; no user-* file was created by this script.
- Agent participant: [ai-grok.md](ai-grok.md)
