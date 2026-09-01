# Ticket 010: Define durable Git continuity boundary

- **ID**: ticket-010
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-09-01

## Goal and scope

Define the Git-side durability boundary for work that must survive conversation
compaction, process restart or handoff. A same-state checkpoint may reference
only an exact clean `HEAD` or a content-addressed, externally stored and
secret-scanned dirty-work snapshot. It never moves refs or grants authority.

## Acceptance criteria

- [x] AC-01: Schema, grammar and Lifecycle DSL expose identical checkpoint
  self-transitions for all nonterminal repository states after initialization.
- [x] AC-02: Applied checkpoint receipts cannot push, publish, move state or
  omit the single continuity receipt.
- [x] AC-03: Documentation rejects stash, chat, raw patch and untracked-only
  handoff as durable evidence and defines divergence-safe resume in
  `docs/WORK_CONTINUITY.md`.
- [x] AC-04: Standalone conformance and repository governance pass.

## Participants

- Human participant: unresolved; no user-* file was created by this script.
- Agent participant: [ai-codex.md](ai-codex.md)

## Resolved prerequisite

`new-project` 0.19.19 was published and adopted by protected merge receipt
`receipt:github-pr:wellmanifest/git-lifecycle:15`. The branch was rebased onto
merge commit `a6046717836fdbfbcd9c2dfd00c063e1153ec122` after a secret-scanned,
content-addressed checkpoint of its dirty ticket state.
