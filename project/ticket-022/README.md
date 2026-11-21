# Ticket 022: Add multi-criteria cleanup profiles, cross-field conflict veto, and explainable non-LLM/LLM triage

- **ID**: ticket-022
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-21

## Session authorization

- `SESSION_EXECUTION_AUTHORIZATION`: Autonomous execution, conformance testing, documentation update, and protected Validator publication requested by the repository owner.

## Goal and scope

1. **Named multi-criteria cleanup profiles (`balanced`, `disk_emergency`, `git_hygiene`, `dedupe_conservative`, `llm_triage_focus`)**: Support deterministic priority weighting via schema `profileId` and CLI `--profile` without ever bypassing hard vetoes.
2. **Cross-field conflict hardening (`CLEAN-CONFLICT-001`)**: Quarantine mislabeled `worktree_merged` (`mergedIntoDefault=false`) and self-referencing `clone_duplicate` (`canonicalCopyPath == path`) with `QUARANTINE_AND_ASK` and block LLM override via `CLEAN-LLM-VETO-001`.
3. **Explainable audit trail & LLM triage (`ruleTrace`, `triageQueue`, `heuristicMode`)**: Record exact decision trace on every candidate, surface ambiguous/conflict candidates in `llmBrief.triageQueue`, and document non-LLM vs LLM-assisted usage in v2 of `docs/information/workspace-cleanup-standard.md`.

## Acceptance criteria

- [x] AC-01: Owned modules stay `< 500` lines after `ruff format`, `ruff check --no-cache` passes with 0 errors, `conformance.py --all`, `workspace_cleanup.py --all`, `unittest`, `check.py`, `wellman check`, and `./project/governance-check.sh --base origin/main --head HEAD` pass (`GOV-PASS`).

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
