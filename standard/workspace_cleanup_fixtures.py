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
        _cand("c-cache-recent", "build_cache", size=1_500_000_000, age=3_600),
        _cand("c-cache-small", "build_cache", size=50_000_000, age=3_600),
        _cand(
            "c-wt-stale-small",
            "worktree_merged",
            size=20_000_000,
            age=400_000,
            merged=True,
        ),
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
        _cand("c-conflict-wt", "worktree_merged", size=3_000_000_000, merged=False),
        _cand(
            "c-conflict-clone",
            "clone_duplicate",
            size=3_000_000_000,
            canonical="/tmp/ws/c-conflict-clone",
        ),
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
    if report["profileId"] != "balanced" or report["heuristicMode"] != "non_llm":
        raise AssertionError("default report profile/mode mismatch")

    by_id = {ev["candidateId"]: ev for ev in report["evaluations"]}
    if by_id["c-cache-big"]["score"] <= by_id["c-cache-small"]["score"]:
        raise AssertionError(
            "larger/older safe cache must rank above small fresh cache"
        )
    for ev in report["evaluations"]:
        if not ev["ruleTrace"] or ev["ruleTrace"][0] != "profile:balanced":
            raise AssertionError(f"missing ruleTrace on {ev['candidateId']}")

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
        ("c-conflict-wt", "CLEAN-CONFLICT-001", "QUARANTINE_AND_ASK"),
        ("c-conflict-clone", "CLEAN-CONFLICT-001", "QUARANTINE_AND_ASK"),
    ]
    for cid, code, exp_v in veto_cases:
        ev = by_id[cid]
        if (
            code not in ev["vetoReasons"]
            or ev["score"] != 0.0
            or ev["reclaimableBytes"] != 0
            or ev["verdict"] != exp_v
        ):
            raise AssertionError(f"hard veto failed for {cid}: {ev}")

    profiles_ok = []
    disk_rep = wc.evaluate_snapshot(snap, profile_id="disk_emergency")
    git_rep = wc.evaluate_snapshot(snap, profile_id="git_hygiene")
    d_id = {e["candidateId"]: e for e in disk_rep["evaluations"]}
    g_id = {e["candidateId"]: e for e in git_rep["evaluations"]}
    if d_id["c-cache-recent"]["score"] <= d_id["c-wt-stale-small"]["score"]:
        raise AssertionError(
            "disk_emergency must prioritize big fresh cache over small stale worktree"
        )
    if g_id["c-wt-stale-small"]["score"] <= g_id["c-cache-recent"]["score"]:
        raise AssertionError(
            "git_hygiene must prioritize stale worktree over recent cache"
        )
    for prof in wc.CRITERIA_PROFILES:
        r = wc.evaluate_snapshot(snap, profile_id=prof)
        if r["profileId"] != prof or any(
            {e["candidateId"]: e for e in r["evaluations"]}[cid]["score"] != 0.0
            for cid, _, _ in veto_cases
        ):
            raise AssertionError(f"profile {prof} weakened a hard veto")
        profiles_ok.append(prof)

    triage_rep = wc.evaluate_snapshot(snap, profile_id="llm_triage_focus")
    tq = set(triage_rep["llmBrief"]["triageQueue"])
    for req_tq in ("c-bundle-unv", "c-conflict-wt", "c-conflict-clone", "c-veto-unk"):
        if req_tq not in tq:
            raise AssertionError(f"{req_tq} missing from triageQueue")
    if "c-cache-big" in tq or "c-veto-rec" in tq:
        raise AssertionError(
            "clean T0_SAFE and RECOVERY items must stay out of triageQueue"
        )
    if triage_rep["llmBrief"]["candidates"][0]["candidateId"] not in tq:
        raise AssertionError("llm_triage_focus must prioritize triageQueue first")

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
    adv_res = wc.validate_llm_advice(snap, adv, report=report)
    if not adv_res["ok"] or adv_res["heuristicMode"] != "llm_assisted":
        raise AssertionError("valid conservative LLM advice must pass as llm_assisted")

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
            "llm-conflict-override",
            {
                "adviceItems": [
                    {
                        **item0,
                        "candidateId": "c-conflict-wt",
                        "suggestedVerdict": "PRUNE_GIT_WORKTREE",
                        "suggestedTier": "T0_SAFE",
                        "evidenceRefs": ["snapshot:c-conflict-wt"],
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
        "profilesVerified": profiles_ok,
        "vetoesVerified": sorted({c[1] for c in veto_cases}),
        "adversarialAdviceRejected": rejected,
    }
