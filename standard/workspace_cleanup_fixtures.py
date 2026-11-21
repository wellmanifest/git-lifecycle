"""Deterministic fixture suite for workspace_cleanup conformance checks."""

from __future__ import annotations

from typing import Any

import workspace_cleanup as wc


def _cand(
    cid: str,
    kind: str,
    *,
    size: int = 10_485_760,
    age: int = 172_800,
    tracked: int = 0,
    dirty: int = 0,
    unpushed: int = 0,
    merged: bool = False,
    bundle: bool = False,
    canonical: str | None = None,
    lease: str = "none",
    active_flag: str | None = None,
) -> dict[str, Any]:
    return {
        "candidateId": cid,
        "path": f"/tmp/ws/{cid}",
        "artifactKind": kind,
        "sizeBytes": size,
        "ageSeconds": age,
        "trackedFilesCount": tracked,
        "git": {
            "isGitTracked": tracked > 0,
            "dirtyFilesCount": dirty,
            "unpushedCommitsCount": unpushed,
            "mergedIntoDefault": merged,
            "hasVerifiedBundle": bundle,
            "canonicalCopyPath": canonical,
        },
        "lease": {
            "state": lease,
            "owner": "agent:test" if lease != "none" else None,
            "expiresAt": None,
        },
        "runtime": {flag: (flag == active_flag) for flag in wc.RT_FLAGS},
    }


def run_self_test() -> dict[str, Any]:
    cands = [
        _cand("c-cache-big", "build_cache", size=2_000_000_000, age=259_200),
        _cand("c-cache-small", "build_cache", size=50_000_000, age=3_600),
        _cand("c-wt-merged", "worktree_merged", size=400_000_000, merged=True),
        _cand("c-clone-dup", "clone_duplicate", size=500_000_000, canonical="/r/main"),
        _cand("c-bundle-unv", "worktree_unmerged", size=600_000_000, unpushed=2),
        _cand("c-veto-track", "build_cache", size=3_000_000_000, tracked=1),
        _cand(
            "c-veto-proc",
            "virtualenv_duplicate",
            size=3_000_000_000,
            active_flag="activeDaemon",
        ),
        _cand("c-veto-rec", "subactor_recovery", size=3_000_000_000),
        _cand(
            "c-veto-lease",
            "worktree_merged",
            size=3_000_000_000,
            merged=True,
            lease="editing",
        ),
        _cand("c-veto-unk", "unknown", size=3_000_000_000),
    ]
    snap = {
        "schema": wc.SNAPSHOT_SCHEMA,
        "kind": "workspace-cleanup-snapshot",
        "repository": "semcod/fixos",
        "observedAt": "2026-11-21T12:00:00Z",
        "diskContext": {
            "freeBytes": 40_000_000_000,
            "totalBytes": 1_000_000_000_000,
            "freePercent": 4.0,
            "pressureTier": "critical",
        },
        "candidates": cands,
    }
    report = wc.evaluate_snapshot(snap)
    if report != wc.evaluate_snapshot({**snap, "candidates": list(reversed(cands))}):
        raise AssertionError("evaluation ordering must be deterministic")

    by_id = {ev["candidateId"]: ev for ev in report["evaluations"]}
    if by_id["c-cache-big"]["score"] <= by_id["c-cache-small"]["score"]:
        raise AssertionError(
            "larger/older safe cache must rank above small fresh cache"
        )
    expected_verdicts = [
        ("c-wt-merged", "PRUNE_GIT_WORKTREE"),
        ("c-clone-dup", "DEDUPE_KEEP_CANONICAL"),
        ("c-bundle-unv", "ARCHIVE_BUNDLE_THEN_DELETE"),
    ]
    for cid, exp in expected_verdicts:
        if by_id[cid]["verdict"] != exp:
            raise AssertionError(f"unexpected verdict on {cid}: {by_id[cid]}")

    veto_cases = [
        ("c-veto-track", "CLEAN-TRACK-001", "HOLD_PROTECTED"),
        ("c-veto-proc", "CLEAN-PROC-001", "HOLD_PROTECTED"),
        ("c-veto-rec", "CLEAN-RECOVERY-001", "HOLD_PROTECTED"),
        ("c-veto-lease", "CLEAN-LEASE-001", "HOLD_PROTECTED"),
        ("c-veto-unk", "CLEAN-UNKNOWN-001", "QUARANTINE_AND_ASK"),
    ]
    for cid, code, exp_v in veto_cases:
        ev = by_id[cid]
        if (
            code not in ev["vetoReasons"]
            or ev["score"] != 0.0
            or ev["verdict"] != exp_v
        ):
            raise AssertionError(f"hard veto failed for {cid}: {ev}")

    item0 = {
        "candidateId": "c-cache-small",
        "suggestedVerdict": "QUARANTINE_AND_ASK",
        "suggestedTier": "T3_PROTECTED",
        "confidence": 0.9,
        "rationale": "Escalate caution only.",
        "evidenceRefs": ["snapshot:c-cache-small"],
        "needsHumanDecision": True,
    }
    adv = {
        "schema": wc.LLM_ADVICE_SCHEMA,
        "kind": "workspace-cleanup-llm-advice",
        "grantsCleanupAuthority": False,
        "advisoryOnly": True,
        "repository": "semcod/fixos",
        "observedAt": "2026-11-21T12:01:00Z",
        "modelId": "triage-test",
        "adviceItems": [item0],
    }
    if not wc.validate_llm_advice(snap, adv, report=report)["ok"]:
        raise AssertionError("valid conservative LLM advice must pass")

    bad_cases = [
        (
            "llm-veto-override",
            {
                "adviceItems": [
                    {
                        **item0,
                        "candidateId": "c-veto-lease",
                        "suggestedVerdict": "DELETE_NOW",
                        "suggestedTier": "T0_SAFE",
                        "evidenceRefs": ["snapshot:c-veto-lease"],
                    }
                ]
            },
            "CLEAN-LLM-VETO-001",
        ),
        (
            "llm-empty-evidence",
            {"adviceItems": [{**item0, "evidenceRefs": []}]},
            "CLEAN-LLM-EVIDENCE-001",
        ),
        (
            "llm-authority-escalation",
            {"grantsCleanupAuthority": True},
            "grantsCleanupAuthority",
        ),
        (
            "llm-unknown-candidate",
            {
                "adviceItems": [
                    {
                        **item0,
                        "candidateId": "c-missing",
                        "evidenceRefs": ["snapshot:c-missing"],
                    }
                ]
            },
            "unknown or duplicate candidateId",
        ),
    ]
    rejected = []
    for name, patch, needle in bad_cases:
        try:
            wc.validate_llm_advice(snap, {**adv, **patch}, report=report)
        except wc.CleanupError as exc:
            if needle not in str(exc):
                raise AssertionError(f"{name}: unexpected {exc}") from exc
            rejected.append(name)
        else:
            raise AssertionError(f"{name} was not rejected")

    return {
        "schema": "wellmanifest.git-lifecycle/workspace-cleanup-conformance/v1",
        "ok": True,
        "vetoesVerified": [c[1] for c in veto_cases],
        "adversarialAdviceRejected": rejected,
    }
