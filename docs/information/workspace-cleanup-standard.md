---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "workspace-cleanup-standard",
  "kind": "information",
  "version": 2,
  "title": "Multi-criteria workspace cleanup standard (non-LLM and LLM-assisted heuristics)",
  "status": "proposed",
  "owner": "wellmanifest/git-lifecycle",
  "scope": "repository",
  "created": "2026-11-21",
  "updated": "2026-11-21",
  "review_after": "2027-02-21",
  "source_revision": "8a38ba3db2257baec3a2f22a621b8a0851f27eb1",
  "affected_repositories": [
    "wellmanifest/git-lifecycle"
  ],
  "evidence": [
    "https://github.com/wellmanifest/git-lifecycle/pull/26",
    "https://github.com/wellmanifest/git-lifecycle/blob/main/standard/workspace-cleanup-policy.schema.json",
    "https://github.com/wellmanifest/git-lifecycle/blob/main/standard/workspace_cleanup.py"
  ]
}
---

# Multi-criteria workspace cleanup standard (non-LLM and LLM-assisted heuristics)

<!-- docs:section purpose -->
## Purpose

Define a dual-mode heuristic standard for evaluating disk, cache, build artifact, virtual environment, duplicate clone, and Git worktree cleanup candidates both **without an LLM** (deterministic, zero-token, zero-latency CI/host evaluation) and **with optional LLM assistance** (bounded triage over ambiguous, quarantined, or cross-repository candidates).

Evaluators produce observation documents (`grantsCleanupAuthority: false`, `advisoryOnly: true`). Cleanup never grants merge, deletion, lease override, or publication authority on its own.

<!-- docs:section scope -->
## Scope

This document applies to repositories adopting `wellmanifest.git-lifecycle/workspace-cleanup-snapshot/v1`, `wellmanifest.git-lifecycle/workspace-cleanup-report/v1`, and `wellmanifest.git-lifecycle/workspace-cleanup-llm-advice/v1`, alongside host storage triage (`semcod/fixos`, `wellmanifest/nolimits` `LIM-STORAGE-001`) and worktree layout planning (`wellmanifest/worktrees`).

Cross-repository remediation runs belong in `subactor/docs`; this specification defines only the policy contract and reference evaluator in `wellmanifest/git-lifecycle`.

<!-- docs:section evidence -->
## Evidence

- Closed JSON Schema contract: [workspace-cleanup-policy.schema.json](../../standard/workspace-cleanup-policy.schema.json).
- Dependency-free Python 3.12 stdlib evaluator, LLM guardrails, and conformance fixtures: [workspace_cleanup.py](../../standard/workspace_cleanup.py), [workspace_cleanup_llm.py](../../standard/workspace_cleanup_llm.py), and [workspace_cleanup_fixtures.py](../../standard/workspace_cleanup_fixtures.py).
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

### 3. Non-LLM vs bounded LLM-assisted execution

- **Without LLM (`heuristicMode: "non_llm"`)**:
  `python3 standard/workspace_cleanup.py --snapshot snap.json --profile disk_emergency`
- **With LLM (`heuristicMode: "llm_assisted"`)**:
  1. Emit compact brief prioritizing `triageQueue`:
     `python3 standard/workspace_cleanup.py --snapshot snap.json --profile llm_triage_focus --emit-llm-brief`
  2. Validate model output against snapshot & deterministic vetoes (`CLEAN-LLM-EVIDENCE-001`, `CLEAN-LLM-VETO-001`, `grantsCleanupAuthority: false`, `advisoryOnly: true`):
     `python3 standard/workspace_cleanup.py --snapshot snap.json --validate-llm-advice advice.json`

<!-- docs:section limitations -->
## Limitations

This standard evaluates caller-supplied snapshot observations and does not scan live filesystems or run `git` or `ps` probes internally. It grants zero authorization to bypass repository governance, lease fencing, or operator approval requirements.

<!-- docs:section next_actions -->
## Next actions

Adopt `standard/workspace-cleanup-policy.schema.json` and `standard/workspace_cleanup.py` from `semcod/fixos`, `wellmanifest/hostguard`, and `wellmanifest/nolimits` storage remediation pipelines, and record cross-repository cleanup outcomes in `subactor/docs`.
