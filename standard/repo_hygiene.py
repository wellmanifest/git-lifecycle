"""Dependency-free evaluator for wellmanifest.git-lifecycle/repo-hygiene/v1.

The document is an observation. It never merges, deletes branches, force-pushes
or opens a pull request. A runtime such as subactor/doctor-agent may emit a
problem when the verdict is stale; in-progress work is left alone.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from git_primitives import (
    EPOCH,
    load_strict_json_file,
    parse_rfc3339_ns,
    validate_git_ref,
    validate_owner_repo,
)

SCHEMA = "wellmanifest.git-lifecycle/repo-hygiene/v1"
INVARIANT = "one_main_zero_pr"
DEFAULT_STALE_SECONDS = 7200
MAX_STALE_SECONDS = 604_800
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
    evidence: dict[str, Any] = field(compare=False)


def _sort_key(finding: HygieneFinding) -> tuple[str, str, str, str]:
    return (
        finding.code,
        finding.severity,
        finding.message,
        json.dumps(
            finding.evidence, sort_keys=True, separators=(",", ":"), allow_nan=False
        ),
    )


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


def _parse_utc_ns(value: Any, label: str) -> int:
    return parse_rfc3339_ns(value, label, HygieneError, require_z=True)


def parse_utc(value: Any, label: str) -> datetime:
    total_ns = _parse_utc_ns(value, label)
    whole_seconds, rem_ns = divmod(total_ns, 1_000_000_000)
    return EPOCH + timedelta(seconds=whole_seconds, microseconds=rem_ns // 1_000)


def _require_fields(value: dict[str, Any], fields: set[str], label: str) -> None:
    observed = set(value)
    if observed != fields:
        missing = sorted(fields - observed)
        extra = sorted(observed - fields)
        raise HygieneError(
            f"{label} fields are invalid (missing={missing}, extra={extra})"
        )


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
    repository = validate_owner_repo(snapshot["repository"], "repository", HygieneError)
    default_branch = validate_git_ref(
        snapshot["defaultBranch"], "defaultBranch", HygieneError
    )
    stale_window = snapshot["staleWindowSeconds"]
    if (
        not isinstance(stale_window, int)
        or isinstance(stale_window, bool)
        or not 1 <= stale_window <= MAX_STALE_SECONDS
    ):
        raise HygieneError("staleWindowSeconds must be an integer in 1..604800")
    observed_ns = _parse_utc_ns(snapshot["observedAt"], "observedAt")
    window_ns = stale_window * 1_000_000_000

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
            raise HygieneError(
                f"openPullRequests[{index}].number must be a positive integer"
            )
        if number in numbers:
            raise HygieneError("openPullRequests must not contain duplicate numbers")
        validate_git_ref(
            item["headRef"], f"openPullRequests[{index}].headRef", HygieneError
        )
        head_repo = item["headRepository"]
        if head_repo is not None:
            validate_owner_repo(
                head_repo, f"openPullRequests[{index}].headRepository", HygieneError
            )
        numbers.add(number)
        pulls.append(item)

    branches_value = snapshot["branches"]
    if (
        not isinstance(branches_value, list)
        or not branches_value
        or len(branches_value) > MAX_ITEMS
    ):
        raise HygieneError("branches must be a non-empty bounded array")
    branches: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, item in enumerate(branches_value):
        if not isinstance(item, dict):
            raise HygieneError(f"branches[{index}] must be an object")
        _require_fields(item, BRANCH_FIELDS, f"branches[{index}]")
        name = validate_git_ref(item["name"], f"branches[{index}].name", HygieneError)
        if name in names:
            raise HygieneError("branches must not contain duplicate names")
        names.add(name)
        _parse_utc_ns(item["committedAt"], f"branches[{index}].committedAt")
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
        activity_ns = _parse_utc_ns(
            pull["lastActivityAt"], f"PR#{pull['number']}.lastActivityAt"
        )
        age_ns = observed_ns - activity_ns
        head_repository = pull["headRepository"]
        if (
            isinstance(head_repository, str)
            and head_repository.lower() == repository.lower()
        ):
            internal_heads.add(pull["headRef"])
        if age_ns < window_ns:
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
                    "ageSeconds": int(age_ns / 1_000_000_000),
                },
            )
        )

    for branch in branches:
        name = branch["name"]
        if name == default_branch or name in internal_heads:
            continue
        committed_ns = _parse_utc_ns(
            branch["committedAt"], f"branch {name}.committedAt"
        )
        age_ns = observed_ns - committed_ns
        if age_ns < window_ns:
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
                    "ageSeconds": int(age_ns / 1_000_000_000),
                },
            )
        )

    if findings:
        status = "stale"
    elif (
        in_progress
        or pulls
        or any(branch["name"] != default_branch for branch in branches)
    ):
        status = "in_progress"
    else:
        status = "healthy"
    return HygieneVerdict(
        schema=SCHEMA,
        invariant=INVARIANT,
        repository=repository,
        status=status,
        stale_window_seconds=stale_window,
        findings=tuple(sorted(findings, key=_sort_key)),
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
        "branches": branches
        or [{"name": "main", "committedAt": "2026-08-15T10:00:00Z"}],
    }


def self_test() -> dict[str, Any]:
    now = "2026-08-15T18:00:00Z"
    clean = evaluate(
        _snapshot(
            repository="wellmanifest/git-lifecycle",
            observed_at=now,
            default_branch="main",
            stale_window_seconds=DEFAULT_STALE_SECONDS,
        )
    )
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
                {
                    "name": "ticket/004-repo-hygiene",
                    "committedAt": "2026-08-15T16:50:00Z",
                },
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
    if stale_pr.status != "stale" or [item.code for item in stale_pr.findings] != [
        "REPO-HYGIENE-STALE-PR"
    ]:
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
    if stale_branch.status != "stale" or [
        item.code for item in stale_branch.findings
    ] != ["REPO-HYGIENE-STALE-BRANCH"]:
        raise AssertionError("stale extra branch must emit REPO-HYGIENE-STALE-BRANCH")

    two_stale_pulls = [
        {
            "number": 9,
            "headRef": "ticket/009-late",
            "headRepository": "subactor/www-sub-actor",
            "lastActivityAt": "2026-08-15T15:00:00Z",
        },
        {
            "number": 4,
            "headRef": "ticket/004-later",
            "headRepository": "subactor/www-sub-actor",
            "lastActivityAt": "2026-08-15T14:00:00Z",
        },
    ]
    two_stale_branches = [
        {"name": "main", "committedAt": "2026-08-15T10:00:00Z"},
        {"name": "ticket/009-late", "committedAt": "2026-08-15T14:30:00Z"},
        {"name": "ticket/004-later", "committedAt": "2026-08-15T13:30:00Z"},
    ]
    two_stale = evaluate(
        _snapshot(
            repository="subactor/www-sub-actor",
            observed_at=now,
            pulls=two_stale_pulls,
            branches=two_stale_branches,
        )
    )
    if [item.code for item in two_stale.findings] != ["REPO-HYGIENE-STALE-PR"] * 2:
        raise AssertionError("two stale pull requests must emit two findings")
    reversed_input = evaluate(
        _snapshot(
            repository="subactor/www-sub-actor",
            observed_at=now,
            pulls=list(reversed(two_stale_pulls)),
            branches=list(reversed(two_stale_branches)),
        )
    )
    if reversed_input.as_dict() != two_stale.as_dict():
        raise AssertionError(
            "one snapshot must yield one verdict regardless of input order"
        )

    return {
        "schema": "wellmanifest.git-lifecycle/repo-hygiene-conformance/v1",
        "ok": True,
        "cases": ["clean", "fresh-pr", "stale-pr", "stale-branch", "two-stale-prs"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Run the closed self-test.")
    parser.add_argument("--snapshot", help="Evaluate a snapshot JSON document.")
    args = parser.parse_args(argv)
    if args.all:
        print(json.dumps(self_test(), indent=2, sort_keys=True, allow_nan=False))
        return 0
    if args.snapshot:
        verdict = evaluate(load_strict_json_file(args.snapshot, HygieneError))
        print(json.dumps(verdict.as_dict(), indent=2, sort_keys=True, allow_nan=False))
        return 0 if verdict.status != "stale" else 1
    parser.error("pass --all or --snapshot")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
