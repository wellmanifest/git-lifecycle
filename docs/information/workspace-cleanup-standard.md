---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "workspace-cleanup-standard",
  "kind": "information",
  "version": 1,
  "title": "Multi-criteria workspace cleanup standard (non-LLM and LLM-assisted heuristics)",
  "status": "proposed",
  "owner": "wellmanifest/git-lifecycle",
  "scope": "repository",
  "created": "2026-11-21",
  "updated": "2026-11-21",
  "review_after": "2027-02-21",
  "source_revision": "81a8c3d98d8d57486184516fe103fea0cacd689f",
  "affected_repositories": [
    "wellmanifest/git-lifecycle"
  ],
  "evidence": [
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

### 1. Twelve artifact classes and four safety tiers

Every candidate declares one `artifactKind` from 12 canonical classes: `worktree_merged`, `worktree_unmerged`, `worktree_dirty`, `build_cache`, `run_logs`, `test_artifacts`, `virtualenv_duplicate`, `virtualenv_primary`, `clone_duplicate`, `bundle_archived_tree`, `subactor_recovery`, and `unknown`.

Deterministic classification assigns one of four safety tiers and six verdicts:

- `T0_SAFE`: `DELETE_NOW` (clean untracked caches/logs/test artifacts or verified bundles), `PRUNE_GIT_WORKTREE` (clean merged worktree), `DEDUPE_KEEP_CANONICAL` (duplicate virtualenv with canonical copy).
- `T1_VERIFY`: `DEDUPE_KEEP_CANONICAL` (clean duplicate clone with canonical copy), `PRUNE_GIT_WORKTREE` (unmerged worktree backed by a verified Git bundle), `QUARANTINE_AND_ASK` (unmerged clean worktree without bundle).
- `T2_ARCHIVE_FIRST`: `ARCHIVE_BUNDLE_THEN_DELETE` (unpushed commits or unbundled archived trees).
- `T3_PROTECTED`: `HOLD_PROTECTED` or `QUARANTINE_AND_ASK` (vetoed, dirty, primary virtualenv, or unknown).

### 2. Five non-overridable hard vetoes

Before any weight, disk-pressure multiplier, or LLM suggestion applies, five hard vetoes unconditionally force `T3_PROTECTED` (`score = 0.0`, `reclaimableBytes = 0`):

1. `CLEAN-TRACK-001`: `trackedFilesCount > 0` or `git.isGitTracked = true`.
2. `CLEAN-PROC-001`: Any live runtime signal (`openFileHandles`, `activeDaemon`, `activeIdeSession`, `activeMountOrSymlinkTarget`).
3. `CLEAN-RECOVERY-001`: `artifactKind == "subactor_recovery"`.
4. `CLEAN-LEASE-001`: Active lease state in `{claimed, editing, validating, publication_frozen}`.
5. `CLEAN-UNKNOWN-001`: `artifactKind == "unknown"` (assigned `QUARANTINE_AND_ASK`).

### 3. Non-LLM deterministic scoring

When no hard veto or `T3_PROTECTED` gate applies, `evaluate_candidate` computes weighted criteria scores in `[0, 100]` using reclaim size normalized by `diskContext.pressureTier` (`normal` 1.0, `elevated` 1.15, `critical` 1.35, `emergency` 1.5), age staleness, artifact reversibility, and blast-radius safety. Evaluations sort deterministically regardless of candidate input ordering.

### 4. Bounded LLM-assisted heuristic boundary

For ambiguous (`T1_VERIFY`/`QUARANTINE_AND_ASK`) or cross-repository prioritization, callers extract a compact, secret-free `llmBrief` (`build_llm_brief`) listing hard constraints and grounded `availableEvidenceRefs`. Optional LLM output (`workspace-cleanup-llm-advice/v1`) MUST pass `validate_llm_advice`:

- `CLEAN-LLM-EVIDENCE-001`: Every advice item must cite >= 1 valid snapshot-grounded ref (`snapshot:`, `git:`, `lease:`, `runtime:`, `bundle:`).
- `CLEAN-LLM-VETO-001`: LLM advice may escalate caution (`T0_SAFE` -> `T3_PROTECTED`), NEVER override a hard veto or downgrade `safetyTier` / escalate verdict destructiveness.
- Authority lock: `grantsCleanupAuthority: false` and `advisoryOnly: true` are enforced strictly.

<!-- docs:section limitations -->
## Limitations

This standard evaluates caller-supplied snapshot observations and does not scan live filesystems or run `git` or `ps` probes internally. It grants zero authorization to bypass repository governance, lease fencing, or operator approval requirements.

<!-- docs:section next_actions -->
## Next actions

Adopt `standard/workspace-cleanup-policy.schema.json` and `standard/workspace_cleanup.py` from `semcod/fixos`, `wellmanifest/hostguard`, and `wellmanifest/nolimits` storage remediation pipelines, and record cross-repository cleanup outcomes in `subactor/docs`.
