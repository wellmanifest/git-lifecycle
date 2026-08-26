---
participant-id: agent:codex
participant: codex
role: agent
ticket: ticket-004
---
# Participant: codex (AI agent)

## Understanding

The existing repository-hygiene contract already owns Git branch and PR state.
The requested `wellmanifest/git` guidance must therefore extend this pack by
alias and reference rather than create a competing standard.

## Plan and changes

1. Document the bounded ticket-to-PR fast path and exact-head freeze.
2. Make the ownership handoff to worktrees, merge and attestation explicit.
3. Keep stale findings observational and preserve unique or unknown work.

No Git/GitHub effect, cleanup, secret access or history rewrite is authorized
by these documentation changes.
