"""Non-LLM deterministic and bounded LLM-assisted workspace cleanup evaluator.

Observation only: never deletes files, mutates Git state, or uses network I/O.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from git_primitives import (
    load_strict_json_file,
    parse_rfc3339_ns,
    validate_owner_repo,
    walk_json_tree,
)
from workspace_cleanup_llm import (
    SCHEMA_FILE,
    CleanupError,
    build_llm_brief,
    chk,
    req_bool,
    req_int,
    req_keys,
    req_str,
    validate_llm_advice_doc,
)

_DEFS: dict[str, Any] = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))["$defs"]
SNAPSHOT_SCHEMA = _DEFS["snapshotDocument"]["properties"]["schema"]["const"]
REPORT_SCHEMA = _DEFS["reportDocument"]["properties"]["schema"]["const"]
LLM_ADVICE_SCHEMA = _DEFS["llmAdviceDocument"]["properties"]["schema"]["const"]
ARTIFACT_KINDS = frozenset(_DEFS["artifactKind"]["enum"])
LEASE_STATES = frozenset(_DEFS["leaseState"]["enum"])
ACTIVE_LEASES = frozenset({"claimed", "editing", "validating", "publication_frozen"})
RT_FLAGS = tuple(_DEFS["runtimeSignals"]["required"])
TIER_RANK = {t: i for i, t in enumerate(_DEFS["safetyTier"]["enum"])}
SAFETY_SCORES = {
    "T0_SAFE": 100.0,
    "T1_VERIFY": 75.0,
    "T2_ARCHIVE_FIRST": 40.0,
    "T3_PROTECTED": 0.0,
}
VERDICT_RISK = {
    "HOLD_PROTECTED": 0,
    "QUARANTINE_AND_ASK": 1,
    "ARCHIVE_BUNDLE_THEN_DELETE": 2,
    "DEDUPE_KEEP_CANONICAL": 3,
    "PRUNE_GIT_WORKTREE": 4,
    "DELETE_NOW": 5,
}
PRESSURE_MULTS = {"normal": 1.0, "elevated": 1.15, "critical": 1.35, "emergency": 1.5}
DEFAULT_POLICY: dict[str, int] = {
    "reclaimWeight": 35,
    "ageWeight": 20,
    "reversibilityWeight": 25,
    "safetyWeight": 20,
    "staleAgeSeconds": 86_400,
    "reclaimReferenceBytes": 1_073_741_824,
    "maxCandidates": 200,
}


def _finding(c: str, s: str, m: str, r: str, e: dict[str, Any]) -> dict[str, Any]:
    return {"code": c, "severity": s, "message": m, "remediation": r, "evidence": e}


def _validate_policy(raw: Any) -> dict[str, int]:
    if raw is None:
        return dict(DEFAULT_POLICY)
    pol = req_keys(raw, set(DEFAULT_POLICY), "policy")
    limits = {
        "reclaimWeight": (0, 100),
        "ageWeight": (0, 100),
        "reversibilityWeight": (0, 100),
        "safetyWeight": (0, 100),
        "staleAgeSeconds": (1, 31_536_000),
        "reclaimReferenceBytes": (1, None),
        "maxCandidates": (1, 10_000),
    }
    out = {k: req_int(pol[k], k, lo=lo, hi=hi) for k, (lo, hi) in limits.items()}
    w_keys = ("reclaimWeight", "ageWeight", "reversibilityWeight", "safetyWeight")
    chk(sum(out[k] for k in w_keys) > 0, "policy weights must sum to > 0")
    return out


def _validate_candidate(raw: Any, idx: int) -> dict[str, Any]:
    pfx = f"candidates[{idx}]"
    cand = req_keys(raw, set(_DEFS["candidate"]["required"]), pfx)
    req_str(cand["candidateId"], f"{pfx}.candidateId", max_len=255)
    req_str(cand["path"], f"{pfx}.path")
    chk(cand["artifactKind"] in ARTIFACT_KINDS, f"{pfx}.artifactKind invalid")
    for k in ("sizeBytes", "ageSeconds", "trackedFilesCount"):
        req_int(cand[k], f"{pfx}.{k}")

    git = req_keys(cand["git"], set(_DEFS["gitSignals"]["required"]), f"{pfx}.git")
    for k in ("isGitTracked", "mergedIntoDefault", "hasVerifiedBundle"):
        req_bool(git[k], f"{pfx}.git.{k}")
    for k in ("dirtyFilesCount", "unpushedCommitsCount"):
        req_int(git[k], f"{pfx}.git.{k}")
    if git["canonicalCopyPath"] is not None:
        req_str(git["canonicalCopyPath"], f"{pfx}.git.canonicalCopyPath")

    lease = req_keys(
        cand["lease"], set(_DEFS["leaseSignals"]["required"]), f"{pfx}.lease"
    )
    chk(lease["state"] in LEASE_STATES, f"{pfx}.lease.state invalid")
    if lease["owner"] is not None:
        req_str(lease["owner"], f"{pfx}.lease.owner", max_len=255)
    if lease["expiresAt"] is not None:
        parse_rfc3339_ns(lease["expiresAt"], "expiresAt", CleanupError, require_z=True)

    rt = req_keys(cand["runtime"], set(RT_FLAGS), f"{pfx}.runtime")
    for flag in RT_FLAGS:
        req_bool(rt[flag], f"{pfx}.runtime.{flag}")
    return cand


def validate_snapshot(
    snapshot: dict[str, Any],
) -> tuple[dict[str, int], dict[str, Any]]:
    walk_json_tree(snapshot, CleanupError)
    req = set(_DEFS["snapshotDocument"]["required"])
    chk(
        isinstance(snapshot, dict) and set(snapshot) - {"policy"} == req,
        "snapshot schema mismatch",
    )
    chk(snapshot["schema"] == SNAPSHOT_SCHEMA, "snapshot schema invalid")
    chk(snapshot["kind"] == "workspace-cleanup-snapshot", "snapshot kind invalid")
    validate_owner_repo(snapshot["repository"], "repository", CleanupError)
    parse_rfc3339_ns(snapshot["observedAt"], "observedAt", CleanupError, require_z=True)

    disk = req_keys(
        snapshot["diskContext"], set(_DEFS["diskContext"]["required"]), "diskContext"
    )
    req_int(disk["freeBytes"], "diskContext.freeBytes")
    req_int(disk["totalBytes"], "diskContext.totalBytes", lo=1)
    fp = disk["freePercent"]
    chk(
        not isinstance(fp, bool) and isinstance(fp, (int, float)) and 0 <= fp <= 100,
        "freePercent invalid",
    )
    chk(disk["pressureTier"] in PRESSURE_MULTS, "pressureTier invalid")

    policy = _validate_policy(snapshot.get("policy"))
    raw_cands = snapshot["candidates"]
    chk(
        isinstance(raw_cands, list) and 1 <= len(raw_cands) <= 10_000,
        "candidates invalid",
    )
    seen: set[str] = set()
    for idx, raw in enumerate(raw_cands):
        cid = _validate_candidate(raw, idx)["candidateId"]
        chk(cid not in seen, f"duplicate candidateId: {cid}")
        seen.add(cid)
    return policy, disk


def _apply_hard_vetoes(cand: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    vetoes: list[str] = []
    findings: list[dict[str, Any]] = []
    active_rt = [flag for flag in RT_FLAGS if cand["runtime"][flag]]

    def add(code: str, msg: str, rem: str, ev: dict[str, Any]) -> None:
        vetoes.append(code)
        findings.append(_finding(code, "veto", msg, rem, ev))

    if cand["trackedFilesCount"] > 0 or cand["git"]["isGitTracked"]:
        add(
            "CLEAN-TRACK-001",
            "Git-tracked content protected.",
            "Check git status.",
            {"tracked": cand["trackedFilesCount"]},
        )
    if active_rt:
        add(
            "CLEAN-PROC-001",
            "Live runtime active.",
            "Stop owner first.",
            {"activeFlags": active_rt},
        )
    if cand["artifactKind"] == "subactor_recovery":
        add(
            "CLEAN-RECOVERY-001",
            "Protected recovery tree.",
            "Retain bundle.",
            {"kind": "subactor_recovery"},
        )
    if cand["lease"]["state"] in ACTIVE_LEASES:
        add(
            "CLEAN-LEASE-001",
            "Active lease blocks cleanup.",
            "Wait for release.",
            {"leaseState": cand["lease"]["state"]},
        )
    if cand["artifactKind"] == "unknown":
        add(
            "CLEAN-UNKNOWN-001",
            "Unknown artifact quarantined.",
            "Classify first.",
            {"kind": "unknown"},
        )
    return vetoes, findings


def _classify_no_veto(
    cand: dict[str, Any],
) -> tuple[str, str, list[dict[str, Any]], float]:
    kind, git = cand["artifactKind"], cand["git"]
    if git["dirtyFilesCount"] > 0 or kind == "worktree_dirty":
        f = _finding("CLEAN-DIRTY-001", "warning", "Dirty tree.", "Commit/stash.", {})
        return ("T3_PROTECTED", "HOLD_PROTECTED", [f], 0.0)
    if kind == "virtualenv_primary":
        f = _finding("CLEAN-VENV-PRIMARY-001", "info", "Primary venv.", "Keep/uv.", {})
        return ("T3_PROTECTED", "HOLD_PROTECTED", [f], 0.0)
    unp = [_finding("CLEAN-UNPUSHED-001", "warning", "Unpushed.", "Bundle first.", {})]
    if kind == "worktree_merged":
        if git["unpushedCommitsCount"] > 0 and not git["hasVerifiedBundle"]:
            return ("T2_ARCHIVE_FIRST", "ARCHIVE_BUNDLE_THEN_DELETE", unp, 45.0)
        return ("T0_SAFE", "PRUNE_GIT_WORKTREE", [], 95.0)
    if kind == "worktree_unmerged":
        if git["hasVerifiedBundle"]:
            return ("T1_VERIFY", "PRUNE_GIT_WORKTREE", [], 85.0)
        if git["unpushedCommitsCount"] > 0:
            return ("T2_ARCHIVE_FIRST", "ARCHIVE_BUNDLE_THEN_DELETE", unp, 45.0)
        f = _finding("CLEAN-UNMERGED-001", "warning", "Unmerged.", "Confirm.", {})
        return ("T1_VERIFY", "QUARANTINE_AND_ASK", [f], 30.0)
    if kind == "clone_duplicate":
        if git["canonicalCopyPath"] and git["unpushedCommitsCount"] == 0:
            return ("T1_VERIFY", "DEDUPE_KEEP_CANONICAL", [], 90.0)
        if git["hasVerifiedBundle"]:
            return ("T1_VERIFY", "DELETE_NOW", [], 85.0)
        return ("T2_ARCHIVE_FIRST", "ARCHIVE_BUNDLE_THEN_DELETE", unp, 45.0)
    if kind == "bundle_archived_tree":
        if git["hasVerifiedBundle"] and git["unpushedCommitsCount"] == 0:
            return ("T1_VERIFY", "DELETE_NOW", [], 90.0)
        return ("T2_ARCHIVE_FIRST", "ARCHIVE_BUNDLE_THEN_DELETE", [], 40.0)
    if kind == "virtualenv_duplicate":
        verdict = "DEDUPE_KEEP_CANONICAL" if git["canonicalCopyPath"] else "DELETE_NOW"
        return ("T0_SAFE", verdict, [], 95.0)
    return ("T0_SAFE", "DELETE_NOW", [], 100.0)


def evaluate_candidate(
    cand: dict[str, Any], disk: dict[str, Any], policy: dict[str, int] | None = None
) -> dict[str, Any]:
    pol = policy if policy is not None else DEFAULT_POLICY
    vetoes, findings = _apply_hard_vetoes(cand)
    if vetoes:
        tier = "T3_PROTECTED"
        verdict = (
            "QUARANTINE_AND_ASK"
            if vetoes == ["CLEAN-UNKNOWN-001"]
            else "HOLD_PROTECTED"
        )
        rev_s = 0.0
    else:
        tier, verdict, extra, rev_s = _classify_no_veto(cand)
        findings.extend(extra)

    mult = PRESSURE_MULTS[disk["pressureTier"]]
    raw_rec = (cand["sizeBytes"] / pol["reclaimReferenceBytes"]) * 100.0 * mult
    rec_s = round(min(100.0, raw_rec), 2)
    age_s = round(min(100.0, (cand["ageSeconds"] / pol["staleAgeSeconds"]) * 100.0), 2)
    blast_s = SAFETY_SCORES[tier]
    if vetoes or verdict in {"HOLD_PROTECTED", "QUARANTINE_AND_ASK"}:
        score, reclaimable = 0.0, 0
    else:
        w_sum = (
            pol["reclaimWeight"]
            + pol["ageWeight"]
            + pol["reversibilityWeight"]
            + pol["safetyWeight"]
        )
        weighted = (
            rec_s * pol["reclaimWeight"]
            + age_s * pol["ageWeight"]
            + rev_s * pol["reversibilityWeight"]
            + blast_s * pol["safetyWeight"]
        )
        score, reclaimable = round(weighted / w_sum, 2), cand["sizeBytes"]
    return {
        "candidateId": cand["candidateId"],
        "path": cand["path"],
        "artifactKind": cand["artifactKind"],
        "safetyTier": tier,
        "verdict": verdict,
        "score": score,
        "vetoReasons": vetoes,
        "criteriaScores": {
            "reclaimScore": rec_s,
            "ageScore": age_s,
            "reversibilityScore": rev_s,
            "blastRadiusSafety": blast_s,
        },
        "findings": findings,
        "reclaimableBytes": reclaimable,
    }


def evaluate_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    policy, disk = validate_snapshot(snapshot)
    evals = [evaluate_candidate(c, disk, policy) for c in snapshot["candidates"]]
    evals.sort(
        key=lambda e: (-e["score"], -e["reclaimableBytes"], e["candidateId"], e["path"])
    )
    return {
        "schema": REPORT_SCHEMA,
        "kind": "workspace-cleanup-report",
        "grantsCleanupAuthority": False,
        "repository": snapshot["repository"],
        "observedAt": snapshot["observedAt"],
        "diskContext": disk,
        "evaluations": evals,
        "llmBrief": build_llm_brief(snapshot, evals, RT_FLAGS, policy["maxCandidates"]),
    }


def validate_llm_advice(
    snapshot: dict[str, Any],
    advice: dict[str, Any],
    *,
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rep = report if report is not None else evaluate_snapshot(snapshot)
    return validate_llm_advice_doc(
        snapshot, advice, rep, _DEFS, TIER_RANK, VERDICT_RISK, RT_FLAGS
    )


def self_test() -> dict[str, Any]:
    import workspace_cleanup_fixtures

    return workspace_cleanup_fixtures.run_self_test()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--all", action="store_true", help="Run closed conformance tests.")
    p.add_argument("--snapshot", help="Evaluate workspace cleanup snapshot JSON.")
    p.add_argument("--emit-llm-brief", action="store_true", help="Emit llmBrief only.")
    p.add_argument("--validate-llm-advice", help="Validate LLM advice JSON.")
    args = p.parse_args(argv)
    if args.all:
        print(json.dumps(self_test(), indent=2, sort_keys=True, allow_nan=False))
        return 0
    if args.snapshot:
        snap = load_strict_json_file(args.snapshot, CleanupError)
        rep = evaluate_snapshot(snap)
        if args.validate_llm_advice:
            adv = load_strict_json_file(args.validate_llm_advice, CleanupError)
            res = validate_llm_advice(snap, adv, report=rep)
            print(json.dumps(res, indent=2, sort_keys=True, allow_nan=False))
            return 0
        payload = rep["llmBrief"] if args.emit_llm_brief else rep
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        return 0
    p.error("pass --all or --snapshot")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
