---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "workspace-cleanup-standard",
  "kind": "information",
  "version": 3,
  "title": "Multi-criteria workspace cleanup standard (non-LLM and LLM-assisted heuristics)",
  "status": "proposed",
  "owner": "wellmanifest/git-lifecycle",
  "scope": "repository",
  "created": "2026-11-21",
  "updated": "2026-11-21",
  "review_after": "2027-02-21",
  "source_revision": "66cc7c40883d57e4050286ff7cdb1dae4be872bd",
  "affected_repositories": [
    "wellmanifest/git-lifecycle"
  ],
  "evidence": [
    "https://github.com/wellmanifest/git-lifecycle/pull/26",
    "https://github.com/wellmanifest/git-lifecycle/pull/27",
    "https://github.com/wellmanifest/git-lifecycle/blob/main/standard/workspace-cleanup-policy.schema.json",
    "https://github.com/wellmanifest/git-lifecycle/blob/main/standard/workspace_cleanup.py",
    "https://github.com/wellmanifest/git-lifecycle/blob/main/standard/workspace_cleanup_scan.py"
  ]
}
---

# Multi-criteria workspace cleanup standard (non-LLM and LLM-assisted heuristics)

<!-- docs:section purpose -->
## Purpose

Define a dual-mode heuristic standard for evaluating disk, cache, build artifact, virtual environment, duplicate clone, and Git worktree cleanup candidates both **without an LLM** (deterministic, zero-token, zero-latency CI/host evaluation) and **with optional LLM assistance** (bounded triage over ambiguous, quarantined, or cross-repository candidates).

Both the snapshot evaluator and the read-only live scanner produce observation documents (`grantsCleanupAuthority: false`, `advisoryOnly: true`). Cleanup analysis never grants merge, deletion, lease override, or publication authority on its own.

<!-- docs:section scope -->
## Scope

This document applies to repositories adopting `wellmanifest.git-lifecycle/workspace-cleanup-snapshot/v1`, `wellmanifest.git-lifecycle/workspace-cleanup-report/v1`, and `wellmanifest.git-lifecycle/workspace-cleanup-llm-advice/v1`, alongside host storage triage (`semcod/fixos`, `wellmanifest/nolimits` `LIM-STORAGE-001`) and worktree layout planning (`wellmanifest/worktrees`).

Cross-repository remediation runs belong in `subactor/docs`; this specification defines the policy contract, reference evaluator, and read-only filesystem scanner in `wellmanifest/git-lifecycle`.

<!-- docs:section evidence -->
## Evidence

- Closed JSON Schema contract: [workspace-cleanup-policy.schema.json](../../standard/workspace-cleanup-policy.schema.json).
- Dependency-free Python 3.12 stdlib evaluator, LLM guardrails, and conformance fixtures: [workspace_cleanup.py](../../standard/workspace_cleanup.py), [workspace_cleanup_llm.py](../../standard/workspace_cleanup_llm.py), and [workspace_cleanup_fixtures.py](../../standard/workspace_cleanup_fixtures.py).
- Read-only live filesystem scanner and isolated fixture tests: [workspace_cleanup_scan.py](../../standard/workspace_cleanup_scan.py) and [workspace_cleanup_scan_fixtures.py](../../standard/workspace_cleanup_scan_fixtures.py).
- Unified conformance suite entrypoint: [conformance.py](../../standard/conformance.py).

<!-- docs:section content -->
## Multi-criteria model

### 1. Twelve artifact classes, four safety tiers, and named criteria profiles

Every candidate declares one `artifactKind` from 12 canonical classes: `worktree_merged`, `worktree_unmerged`, `worktree_dirty`, `build_cache`, `run_logs`, `test_artifacts`, `virtualenv_duplicate`, `virtualenv_primary`, `clone_duplicate`, `bundle_archived_tree`, `subactor_recovery`, and `unknown`.

Deterministic classification assigns one of four safety tiers (`T0_SAFE`, `T1_VERIFY`, `T2_ARCHIVE_FIRST`, `T3_PROTECTED`) and six verdicts (`DELETE_NOW`, `PRUNE_GIT_WORKTREE`, `ARCHIVE_BUNDLE_THEN_DELETE`, `DEDUPE_KEEP_CANONICAL`, `QUARANTINE_AND_ASK`, `HOLD_PROTECTED`), plus an ordered audit trail (`ruleTrace`).

Five named criteria profiles adjust non-vetoed ranking priorities without ever weakening safety vetoes:

- `balanced`: default balanced weights (`reclaim=35, age=20, reversibility=25, safety=20`, stale 24h, ref 1 GiB).
- `disk_emergency`: maximizes urgent storage reclaim (`reclaim=60`, stale 6h, ref 256 MiB) for `LIM-STORAGE-001`.
- `git_hygiene`: prioritizes aging stale branches/worktrees (`age=40`, stale 12h).
- `dedupe_conservative`: emphasizes safety & reversibility (`safety=35, reversibility=25`, stale 72h).
- `llm_triage_focus`: keeps `maxCandidates=100` and sorts `llmBrief.candidates` so ambiguous `triageQueue` items appear first.

### 2. Six non-overridable hard vetoes

Before any weight, profile, disk-pressure multiplier, or LLM suggestion applies, six hard vetoes force `T3_PROTECTED` (`score = 0.0`, `reclaimableBytes = 0`):

1. `CLEAN-TRACK-001`: `trackedFilesCount > 0` or `git.isGitTracked = true`.
2. `CLEAN-PROC-001`: Any live runtime signal (`openFileHandles`, `activeDaemon`, `activeIdeSession`, `activeMountOrSymlinkTarget`).
3. `CLEAN-RECOVERY-001`: `artifactKind == "subactor_recovery"`.
4. `CLEAN-LEASE-001`: Active lease state in `{claimed, editing, validating, publication_frozen}`.
5. `CLEAN-UNKNOWN-001`: `artifactKind == "unknown"` (`QUARANTINE_AND_ASK`).
6. `CLEAN-CONFLICT-001`: Conflicting label vs Git/path evidence (`worktree_merged` with `mergedIntoDefault = false`, or `clone_duplicate` where `canonicalCopyPath == path`), quarantined as `QUARANTINE_AND_ASK`.

### 3. Non-LLM vs bounded LLM-assisted execution (snapshot & live scan)

- **Snapshot without LLM (`heuristicMode: "non_llm"`)**:
  `python3 standard/workspace_cleanup.py --snapshot snap.json --profile disk_emergency`
- **Live directory scan without LLM (`heuristicMode: "non_llm"`)**:
  `python3 standard/workspace_cleanup_scan.py --root <path> --repository owner/repo --profile dedupe_conservative --min-bytes 20971520`
  Add `--emit-snapshot` to persist the observed `workspace-cleanup-snapshot/v1` JSON or `--check-lsof` for open-file-handle checks.
- **With LLM (`heuristicMode: "llm_assisted"`)**:
  1. Emit compact brief prioritizing `triageQueue`:
     `python3 standard/workspace_cleanup_scan.py --root <path> --repository owner/repo --profile llm_triage_focus --emit-llm-brief`
  2. Validate model output against snapshot & deterministic vetoes (`CLEAN-LLM-EVIDENCE-001`, `CLEAN-LLM-VETO-001`, `grantsCleanupAuthority: false`, `advisoryOnly: true`):
     `python3 standard/workspace_cleanup.py --snapshot snap.json --validate-llm-advice advice.json`

<!-- docs:section limitations -->
## Limitations

`standard/workspace_cleanup_scan.py` performs strictly read-only filesystem, Git metadata, and process observations and never deletes files or mutates Git state. Live execution still requires an authorized remediation step honoring all hard vetoes, repository governance, lease fencing, and operator approval requirements.

<!-- docs:section next_actions -->
## Next actions

Adopt `standard/workspace-cleanup-policy.schema.json`, `standard/workspace_cleanup.py`, and `standard/workspace_cleanup_scan.py` from `semcod/fixos`, `wellmanifest/hostguard`, and `wellmanifest/nolimits` storage remediation pipelines, and record cross-repository cleanup outcomes in `subactor/docs`.
