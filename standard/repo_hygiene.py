#!/usr/bin/env python3
"""Dependency-free evaluator for wellmanifest.git-lifecycle/repo-hygiene/v1.

The document is an observation. It never merges, deletes branches, force-pushes
or opens a pull request. A runtime such as subactor/doctor-agent may emit a
problem when the verdict is stale; in-progress work is left alone.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

SCHEMA = "wellmanifest.git-lifecycle/repo-hygiene/v1"
INVARIANT = "one_main_zero_pr"
DEFAULT_STALE_SECONDS = 7200
REQUIRED_DEFAULT_BRANCH = "main"
MAX_ITEMS = 10_000
SNAPSHOT_FIELDS = {
    "schema",
    "kind",
    "invariant",
    "repository",
    "defaultBranch",
    "staleWindowSeconds",
    "observedAt",
    "openPullRequests",
    "branches",
}
PR_FIELDS = {"number", "headRef", "headRepository", "lastActivityAt"}
BRANCH_FIELDS = {"name", "committedAt"}


class HygieneError(ValueError):
    """The snapshot contract is invalid."""


@dataclass(frozen=True, order=True)
class HygieneFinding:
    code: str
    severity: str
    message: str
    remediation: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class HygieneVerdict:
    schema: str
    invariant: str
    repository: str
    status: str
    stale_window_seconds: int
    findings: tuple[HygieneFinding, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["staleWindowSeconds"] = payload.pop("stale_window_seconds")
        return payload


def parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise HygieneError(f"{label} must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise HygieneError(f"{label} is not a valid timestamp") from exc
    return parsed.astimezone(timezone.utc)


def _require_fields(value: dict[str, Any], fields: set[str], label: str) -> None:
    observed = set(value)
    if observed != fields:
        missing = sorted(fields - observed)
        extra = sorted(observed - fields)
        raise HygieneError(f"{label} fields are invalid (missing={missing}, extra={extra})")


def _age_seconds(moment: datetime, observed_at: datetime) -> float:
    return (observed_at - moment).total_seconds()


def evaluate(snapshot: dict[str, Any]) -> HygieneVerdict:
    """Classify one repository snapshot without performing GitHub effects."""

    if not isinstance(snapshot, dict):
        raise HygieneError("snapshot root must be an object")
    _require_fields(snapshot, SNAPSHOT_FIELDS, "snapshot")
    if snapshot["schema"] != SCHEMA:
        raise HygieneError(f"unsupported schema: {snapshot['schema']!r}")
    if snapshot["kind"] != "repo-hygiene-snapshot":
        raise HygieneError("kind must be repo-hygiene-snapshot")
    if snapshot["invariant"] != INVARIANT:
        raise HygieneError("invariant must be one_main_zero_pr")
    repository = snapshot["repository"]
    if not isinstance(repository, str) or "/" not in repository:
        raise HygieneError("repository must be owner/name")
    default_branch = snapshot["defaultBranch"]
    if not isinstance(default_branch, str) or not default_branch:
        raise HygieneError("defaultBranch must be a non-empty ref")
    stale_window = snapshot["staleWindowSeconds"]
    if not isinstance(stale_window, int) or isinstance(stale_window, bool) or stale_window < 1:
        raise HygieneError("staleWindowSeconds must be a positive integer")
    observed_at = parse_utc(snapshot["observedAt"], "observedAt")

    pulls_value = snapshot["openPullRequests"]
    if not isinstance(pulls_value, list) or len(pulls_value) > MAX_ITEMS:
        raise HygieneError("openPullRequests must be a bounded array")
    pulls: list[dict[str, Any]] = []
    numbers: set[int] = set()
    for index, item in enumerate(pulls_value):
        if not isinstance(item, dict):
            raise HygieneError(f"openPullRequests[{index}] must be an object")
        _require_fields(item, PR_FIELDS, f"openPullRequests[{index}]")
        number = item["number"]
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise HygieneError(f"openPullRequests[{index}].number must be a positive integer")
        if number in numbers:
            raise HygieneError("openPullRequests must not contain duplicate numbers")
        numbers.add(number)
        pulls.append(item)

    branches_value = snapshot["branches"]
    if not isinstance(branches_value, list) or not branches_value or len(branches_value) > MAX_ITEMS:
        raise HygieneError("branches must be a non-empty bounded array")
    branches: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, item in enumerate(branches_value):
        if not isinstance(item, dict):
            raise HygieneError(f"branches[{index}] must be an object")
        _require_fields(item, BRANCH_FIELDS, f"branches[{index}]")
        name = item["name"]
        if not isinstance(name, str) or not name:
            raise HygieneError(f"branches[{index}].name must be a non-empty ref")
        if name in names:
            raise HygieneError("branches must not contain duplicate names")
        names.add(name)
        parse_utc(item["committedAt"], f"branches[{index}].committedAt")
        branches.append(item)
    if default_branch not in names:
        raise HygieneError("defaultBranch is missing from branches")

    findings: list[HygieneFinding] = []
    if default_branch != REQUIRED_DEFAULT_BRANCH:
        findings.append(
            HygieneFinding(
                code="REPO-HYGIENE-DEFAULT-BRANCH",
                severity="error",
                message="The long-lived default branch is not main.",
                remediation="Rename or retarget the default branch to main. Do not force-delete history.",
                evidence={"repository": repository, "defaultBranch": default_branch},
            )
        )

    in_progress = False
    internal_heads: set[str] = set()
    for pull in pulls:
        activity = parse_utc(pull["lastActivityAt"], f"PR#{pull['number']}.lastActivityAt")
        age = _age_seconds(activity, observed_at)
        head_repository = pull["headRepository"]
        if isinstance(head_repository, str) and head_repository.lower() == repository.lower():
            internal_heads.add(str(pull["headRef"]))
        if age < stale_window:
            in_progress = True
            continue
        findings.append(
            HygieneFinding(
                code="REPO-HYGIENE-STALE-PR",
                severity="error",
                message="An open pull request has had no relevant activity for the stale window.",
                remediation=(
                    "Doctor-agent may emit a problem. Do not auto-merge, close the PR, "
                    "or delete its head branch from this observation."
                ),
                evidence={
                    "repository": repository,
                    "number": pull["number"],
                    "headRef": pull["headRef"],
                    "lastActivityAt": pull["lastActivityAt"],
                    "ageSeconds": int(age),
                },
            )
        )

    for branch in branches:
        name = branch["name"]
        if name == default_branch or name in internal_heads:
            continue
        committed = parse_utc(branch["committedAt"], f"branch {name}.committedAt")
        age = _age_seconds(committed, observed_at)
        if age < stale_window:
            in_progress = True
            continue
        findings.append(
            HygieneFinding(
                code="REPO-HYGIENE-STALE-BRANCH",
                severity="error",
                message="An extra branch has had no tip activity for the stale window.",
                remediation=(
                    "Doctor-agent may emit a problem. Do not force-delete the branch "
                    "or invent a pull request from this observation."
                ),
                evidence={
                    "repository": repository,
                    "branch": name,
                    "committedAt": branch["committedAt"],
                    "ageSeconds": int(age),
                },
            )
        )

    if findings:
        status = "stale"
    elif in_progress or pulls or any(branch["name"] != default_branch for branch in branches):
        status = "in_progress"
    else:
        status = "healthy"
    return HygieneVerdict(
        schema=SCHEMA,
        invariant=INVARIANT,
        repository=repository,
        status=status,
        stale_window_seconds=stale_window,
        findings=tuple(sorted(findings)),
    )


def _snapshot(
    *,
    repository: str,
    observed_at: str,
    default_branch: str = "main",
    stale_window_seconds: int = DEFAULT_STALE_SECONDS,
    pulls: list[dict[str, Any]] | None = None,
    branches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "kind": "repo-hygiene-snapshot",
        "invariant": INVARIANT,
        "repository": repository,
        "defaultBranch": default_branch,
        "staleWindowSeconds": stale_window_seconds,
        "observedAt": observed_at,
        "openPullRequests": pulls or [],
        "branches": branches or [{"name": "main", "committedAt": "2026-08-15T10:00:00Z"}],
    }


def self_test() -> dict[str, Any]:
    now = "2026-08-15T18:00:00Z"
    clean = evaluate(_snapshot(repository="wellmanifest/git-lifecycle", observed_at=now))
    if clean.status != "healthy" or clean.findings:
        raise AssertionError("clean repo must not emit")

    fresh_pr = evaluate(
        _snapshot(
            repository="subactor/doctor-agent",
            observed_at=now,
            pulls=[
                {
                    "number": 12,
                    "headRef": "ticket/004-repo-hygiene",
                    "headRepository": "subactor/doctor-agent",
                    "lastActivityAt": "2026-08-15T17:00:00Z",
                }
            ],
            branches=[
                {"name": "main", "committedAt": "2026-08-15T10:00:00Z"},
                {"name": "ticket/004-repo-hygiene", "committedAt": "2026-08-15T16:50:00Z"},
            ],
        )
    )
    if fresh_pr.status != "in_progress" or fresh_pr.findings:
        raise AssertionError("fresh PR must not emit")

    stale_pr = evaluate(
        _snapshot(
            repository="semcod/planfile",
            observed_at=now,
            pulls=[
                {
                    "number": 7,
                    "headRef": "feature/old",
                    "headRepository": "semcod/planfile",
                    "lastActivityAt": "2026-08-15T15:00:00Z",
                }
            ],
            branches=[
                {"name": "main", "committedAt": "2026-08-15T10:00:00Z"},
                {"name": "feature/old", "committedAt": "2026-08-15T14:00:00Z"},
            ],
        )
    )
    if stale_pr.status != "stale" or [item.code for item in stale_pr.findings] != ["REPO-HYGIENE-STALE-PR"]:
        raise AssertionError("stale PR must emit REPO-HYGIENE-STALE-PR")

    stale_branch = evaluate(
        _snapshot(
            repository="wellmanifest/hostguard",
            observed_at=now,
            branches=[
                {"name": "main", "committedAt": "2026-08-15T10:00:00Z"},
                {"name": "orphan-work", "committedAt": "2026-08-15T15:00:00Z"},
            ],
        )
    )
    if stale_branch.status != "stale" or [item.code for item in stale_branch.findings] != [
        "REPO-HYGIENE-STALE-BRANCH"
    ]:
        raise AssertionError("stale extra branch must emit REPO-HYGIENE-STALE-BRANCH")

    return {
        "schema": "wellmanifest.git-lifecycle/repo-hygiene-conformance/v1",
        "ok": True,
        "cases": ["clean", "fresh-pr", "stale-pr", "stale-branch"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Run the closed self-test.")
    parser.add_argument("--snapshot", help="Evaluate a snapshot JSON document.")
    args = parser.parse_args(argv)
    if args.all:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    if args.snapshot:
        with open(args.snapshot, encoding="utf-8") as handle:
            verdict = evaluate(json.load(handle))
        print(json.dumps(verdict.as_dict(), indent=2, sort_keys=True))
        return 0 if verdict.status != "stale" else 1
    parser.error("pass --all or --snapshot")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
