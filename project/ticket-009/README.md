# Ticket 009: Standardize complex merge queue delivery

- **ID**: ticket-009
- **Owner**: unresolved:human
- **Status**: DONE
- **Workflow state**: DONE
- **Created**: 2026-08-31

## Goal and scope

Define one-writer leases, merge-queue rebases, bounded retries and exact-head
receipts for complex multi-component changes.

## Acceptance criteria

- [x] AC-01: Complex delivery sequence is documented.
- [x] AC-02: Stale-head and canary-failure recovery is bounded and fail-closed.

## Participants

- Human participant: unresolved; no user-* file was created by this script.
- Agent participant: [ai-codex.md](ai-codex.md)
