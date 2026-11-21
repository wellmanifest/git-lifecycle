"""Bounded LLM-assisted workspace cleanup brief builder and advice validator.

Enforces evidence grounding (CLEAN-LLM-EVIDENCE-001), non-override of hard
vetoes (CLEAN-LLM-VETO-001), and advisory-only boundaries.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from git_primitives import parse_rfc3339_ns, walk_json_tree

SCHEMA_FILE = Path(__file__).resolve().with_name("workspace-cleanup-policy.schema.json")


class CleanupError(ValueError):
    """The cleanup snapshot or LLM advice violates contract invariants."""


def chk(cond: bool, msg: str) -> None:
    if not cond:
        raise CleanupError(msg)


def req_keys(obj: Any, expected: set[str], lbl: str) -> dict[str, Any]:
    chk(isinstance(obj, dict) and set(obj) == expected, f"{lbl} keys mismatch schema")
    return obj


def req_int(val: Any, lbl: str, *, lo: int = 0, hi: int | None = None) -> int:
    ok = not isinstance(val, bool) and isinstance(val, int) and val >= lo
    chk(ok, f"{lbl} invalid int")
    chk(hi is None or val <= hi, f"{lbl} exceeds max {hi}")
    return val


def req_str(val: Any, lbl: str, *, max_len: int = 1024) -> str:
    chk(isinstance(val, str) and 1 <= len(val) <= max_len, f"{lbl} invalid string")
    return val


def req_bool(val: Any, lbl: str) -> bool:
    chk(isinstance(val, bool), f"{lbl} must be bool")
    return val


def candidate_evidence_refs(
    cand: dict[str, Any], rt_flags: tuple[str, ...]
) -> list[str]:
    git = cand["git"]
    rt_on = any(cand["runtime"][f] for f in rt_flags)
    git_dirty = git["dirtyFilesCount"] > 0 or git["unpushedCommitsCount"] > 0
    refs = [
        f"snapshot:{cand['candidateId']}",
        f"lease:{cand['lease']['state']}",
        "runtime:active" if rt_on else "runtime:clear",
        "git:dirty" if git_dirty else "git:clean",
    ]
    if git["hasVerifiedBundle"]:
        refs.append("bundle:verified")
    return refs


def build_llm_brief(
    snapshot: dict[str, Any],
    evals: list[dict[str, Any]],
    rt_flags: tuple[str, ...],
    max_cands: int = 200,
) -> dict[str, Any]:
    by_id = {c["candidateId"]: c for c in snapshot["candidates"]}
    items = [
        {
            "candidateId": ev["candidateId"],
            "artifactKind": ev["artifactKind"],
            "sizeBytes": by_id[ev["candidateId"]]["sizeBytes"],
            "ageSeconds": by_id[ev["candidateId"]]["ageSeconds"],
            "safetyTier": ev["safetyTier"],
            "verdict": ev["verdict"],
            "score": ev["score"],
            "vetoReasons": ev["vetoReasons"],
            "availableEvidenceRefs": candidate_evidence_refs(
                by_id[ev["candidateId"]], rt_flags
            ),
        }
        for ev in evals[:max_cands]
    ]
    return {
        "schema": "wellmanifest.git-lifecycle/workspace-cleanup-llm-brief/v1",
        "grantsCleanupAuthority": False,
        "repository": snapshot["repository"],
        "observedAt": snapshot["observedAt"],
        "diskContext": snapshot["diskContext"],
        "hardConstraints": [
            "Never override CLEAN-TRACK/PROC/RECOVERY/LEASE/UNKNOWN-001 vetoes",
            "Never lower safetyTier or escalate verdict destructiveness",
            "Every adviceItem requires >= 1 grounded evidenceRef",
        ],
        "candidates": items,
        "omittedCount": max(0, len(evals) - len(items)),
    }


def validate_llm_advice_doc(
    snapshot: dict[str, Any],
    advice: dict[str, Any],
    report: dict[str, Any],
    defs: dict[str, Any],
    tier_rank: dict[str, int],
    verdict_risk: dict[str, int],
    rt_flags: tuple[str, ...],
) -> dict[str, Any]:
    walk_json_tree(advice, CleanupError)
    advice_schema = defs["llmAdviceDocument"]["properties"]["schema"]["const"]
    ev_pat = defs["llmAdviceItem"]["properties"]["evidenceRefs"]["items"]["pattern"]
    ev_re = re.compile(ev_pat, re.ASCII)

    doc = req_keys(advice, set(defs["llmAdviceDocument"]["required"]), "llmAdvice")
    chk(doc["schema"] == advice_schema, "llmAdvice schema invalid")
    chk(doc["kind"] == "workspace-cleanup-llm-advice", "llmAdvice kind invalid")
    chk(
        doc["grantsCleanupAuthority"] is False and doc["advisoryOnly"] is True,
        "llmAdvice grantsCleanupAuthority must be false and advisoryOnly true",
    )
    chk(doc["repository"] == report["repository"], "llmAdvice repository mismatch")
    parse_rfc3339_ns(doc["observedAt"], "observedAt", CleanupError, require_z=True)
    req_str(doc["modelId"], "llmAdvice.modelId", max_len=128)
    items = doc["adviceItems"]
    chk(
        isinstance(items, list) and len(items) <= 500,
        "llmAdvice.adviceItems must be <= 500 items",
    )

    ev_by_id = {ev["candidateId"]: ev for ev in report["evaluations"]}
    cand_by_id = {c["candidateId"]: c for c in snapshot["candidates"]}
    seen: set[str] = set()
    req_item = set(defs["llmAdviceItem"]["required"])
    for idx, raw in enumerate(items):
        item = req_keys(raw, req_item, f"adviceItems[{idx}]")
        cid = req_str(item["candidateId"], f"adviceItems[{idx}].candidateId")
        chk(
            cid not in seen and cid in ev_by_id,
            f"unknown or duplicate candidateId: {cid}",
        )
        seen.add(cid)
        sv, st, conf = (
            item["suggestedVerdict"],
            item["suggestedTier"],
            item["confidence"],
        )
        chk(sv in verdict_risk and st in tier_rank, f"invalid verdict/tier on {cid}")
        chk(
            not isinstance(conf, bool)
            and isinstance(conf, (int, float))
            and 0 <= conf <= 1,
            f"invalid confidence on {cid}",
        )
        req_str(item["rationale"], f"adviceItems[{idx}].rationale", max_len=512)
        req_bool(item["needsHumanDecision"], f"adviceItems[{idx}].needsHumanDecision")

        refs = item["evidenceRefs"]
        allowed = set(candidate_evidence_refs(cand_by_id[cid], rt_flags))
        chk(
            isinstance(refs, list) and 1 <= len(refs) <= 16,
            f"CLEAN-LLM-EVIDENCE-001: {cid} missing evidenceRefs",
        )
        for ref in refs:
            ok_ref = (
                isinstance(ref, str)
                and ev_re.fullmatch(ref) is not None
                and ref in allowed
            )
            chk(ok_ref, f"CLEAN-LLM-EVIDENCE-001: ungrounded ref {ref!r} on {cid}")

        det = ev_by_id[cid]
        if det["vetoReasons"]:
            chk(
                st == "T3_PROTECTED" and sv == det["verdict"],
                f"CLEAN-LLM-VETO-001: cannot override veto on {cid}",
            )
        chk(
            tier_rank[st] >= tier_rank[det["safetyTier"]]
            and verdict_risk[sv] <= verdict_risk[det["verdict"]],
            f"CLEAN-LLM-VETO-001: cannot downgrade safety on {cid}",
        )
    return {"schema": advice_schema, "ok": True, "validatedItems": sorted(seen)}
