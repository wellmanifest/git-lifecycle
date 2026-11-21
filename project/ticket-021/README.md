# Ticket 021: Add multi-criteria workspace cleanup standard for non-LLM and LLM-assisted heuristics

- **ID**: ticket-021
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-21

## Session authorization

- `SESSION_EXECUTION_AUTHORIZATION`: Autonomous execution, conformance testing, documentation registration, and protected Validator publication requested by the repository owner.

## Goal and scope

1. **Closed policy & contract schema (`standard/workspace-cleanup-policy.schema.json`)**: Define `wellmanifest.git-lifecycle/workspace-cleanup-snapshot/v1`, `workspace-cleanup-report/v1`, and `workspace-cleanup-llm-advice/v1` with 12 artifact kinds, 4 safety tiers, 6 verdicts, `grantsCleanupAuthority: false`, and mandatory grounded `evidenceRefs`.
2. **Dependency-free evaluator (`standard/workspace_cleanup.py`, `standard/conformance.py`)**: Implement deterministic non-LLM multi-criteria scoring and 5 non-overridable hard vetoes (`CLEAN-TRACK-001`, `CLEAN-PROC-001`, `CLEAN-RECOVERY-001`, `CLEAN-LEASE-001`, `CLEAN-UNKNOWN-001`) plus bounded LLM brief builder and advice validator (`CLEAN-LLM-VETO-001`, `CLEAN-LLM-EVIDENCE-001`), wired into `standard/conformance.py`.
3. **Standard documentation (`docs/information/workspace-cleanup-standard.md`, `docs/README.md`)**: Document the dual-mode non-LLM and LLM-assisted standard per `wellmanifest/docs`.

## Acceptance criteria

- [x] AC-01: `standard/workspace_cleanup.py` stays `< 500` lines, passes `ruff check --no-cache`, `conformance.py --all`, `initial_ref_conformance.py --all`, `workspace_cleanup.py --all`, `wellmanifest/docs` deliverable check, and `./project/governance-check.sh --base origin/main --head HEAD`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
