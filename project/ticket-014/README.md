# Ticket 014: Hidden worktree adoption and Git lifecycle handoff

- **ID**: ticket-014
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-07

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user requested implementation and rollout of the hidden repository-local worktree convention across related Wellmanifest standards, including Git. This ticket adopts the immutable new-project package carrying Worktrees v5 and documents the lifecycle evidence handoff. Its new worktree uses the explicitly requested `.worktrees` location. Protected independent publication is required; no existing checkout is moved or removed.

Canonical result: [worktree lifecycle handoff](../../docs/information/worktree-lifecycle-handoff.md).

## Acceptance criteria

- [ ] AC-01: New allocation policy points to the adopted Worktrees v5 planner; Git lifecycle keeps effect authority and preserves historical worktrees.
- [ ] AC-02: Managed adoption and lifecycle conformance pass, followed by protected publication.
