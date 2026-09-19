# Ticket 007: Run initial-ref conformance in hosted CI

- **ID**: ticket-007
- **Owner**: agent:codex under SESSION_EXECUTION_AUTHORIZATION
- **Status**: DONE
- **Workflow state**: DONE
- **Created**: 2026-08-22

## Goal and scope

Run the already merged `repository-initial-ref/v1` semantic conformance suite
in the hosted lifecycle check. Keep the change limited to CI wiring; do not
alter either lifecycle contract or its conformance implementation.

## Acceptance criteria

- [x] AC-01: The hosted lifecycle workflow runs both the original repository
  lifecycle conformance and the complementary initial-ref conformance.
- [x] AC-02: A failure in either suite fails the same stable required check.
- [x] AC-03: Local conformance and repository governance remain green.

## Participants

- Human participant: initiating conversation; no user-* file was created.
- Agent participant: [ai-codex.md](ai-codex.md)
