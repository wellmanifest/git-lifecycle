# Ticket 023: Add read-only live workspace cleanup scanner for non-LLM and LLM-assisted multi-criteria triage

- **ID**: ticket-023
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-21

## Session authorization

- `SESSION_EXECUTION_AUTHORIZATION`: Autonomous execution, conformance testing, documentation update, and protected Validator publication requested by the repository owner.

## Goal and scope

1. **Read-only live scanner (`standard/workspace_cleanup_scan.py`)**: Scan any Git repo or multi-repo workspace directory without symlinks (`followlinks=False`, skipping symlinked directories), collecting real `diskContext`, tracked vs untracked `build_cache`/`test_artifacts`, primary vs duplicate virtualenvs, `.subactor/recovery`, non-primary worktree ancestry/dirty/lease signals, and live process/FD flags into `workspace-cleanup-snapshot/v1`, evaluating all 5 criteria profiles (`non_llm`) or emitting prioritized `llmBrief` JSON (`llm_assisted`) with `grantsCleanupAuthority: false`.
2. **Closed conformance fixtures (`standard/workspace_cleanup_scan_fixtures.py`) & wiring (`standard/workspace_cleanup.py`)**: Verify all 8 real-filesystem candidate classes, symlink skipping, all 5 profile consistency guarantees, and strict read-only non-mutation inside temporary workspaces, wired into `conformance.py --all`.
3. **Standard docs v3 (`docs/information/workspace-cleanup-standard.md`)**: Document live scanner CLI workflows and limitations.

## Acceptance criteria

- [x] AC-01: Owned modules stay `< 500` lines after `ruff format`, `ruff check --no-cache` passes with 0 errors, `conformance.py --all`, `initial_ref_conformance.py --all`, `workspace_cleanup.py --all`, `workspace_cleanup_scan.py --all`, `unittest`, `wellmanifest/docs` deliverable check (`check.py`), `wellman check`, and `./project/governance-check.sh --base origin/main --head HEAD` pass (`GOV-PASS`).

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
