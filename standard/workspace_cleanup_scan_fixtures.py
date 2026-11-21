"""Deterministic temporary-workspace fixtures for live cleanup scanner tests."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import workspace_cleanup as wc
import workspace_cleanup_scan as wcs


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _setup_fixture_workspace(base: Path) -> tuple[Path, list[Path]]:
    repo = base / "sample-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "user.email", "test@example.invalid")

    tracked_nm = repo / "node_modules"
    tracked_nm.mkdir()
    tracked_pkg = tracked_nm / "pkg.js"
    tracked_pkg.write_text("module.exports = 1;\n", encoding="utf-8")
    readme = repo / "README.md"
    readme.write_text("# Sample\n", encoding="utf-8")
    _git(repo, "add", "node_modules/pkg.js", "README.md")
    _git(repo, "commit", "-m", "initial")

    rec_bundle = repo / ".subactor" / "recovery" / "backup.bundle"
    rec_bundle.parent.mkdir(parents=True)
    rec_bundle.write_bytes(b"bundle-bytes")

    prim_py = repo / ".venv" / "bin" / "python"
    prim_py.parent.mkdir(parents=True)
    prim_py.write_text("py", encoding="utf-8")

    sub_req = repo / "sub" / "pyproject.toml"
    sub_req.parent.mkdir()
    sub_req.write_text("[project]\nname='sub'\n", encoding="utf-8")
    dup_py = repo / "sub" / "venv" / "bin" / "python"
    dup_py.parent.mkdir(parents=True)
    dup_py.write_text("py" * 1024, encoding="utf-8")

    dist_whl = repo / "dist" / "out.whl"
    dist_whl.parent.mkdir()
    dist_whl.write_bytes(b"wheel" * 1024)

    # Merged released worktree
    wt_merged = repo / ".worktrees" / "ticket-001--merged"
    _git(repo, "checkout", "-b", "ticket/001-merged")
    merged_file = repo / "feature.txt"
    merged_file.write_text("done\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-m", "feat")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "ticket/001-merged", "-m", "merge t1")
    _git(repo, "worktree", "add", str(wt_merged), "ticket/001-merged")

    leases = repo / ".subactor" / "leases"
    leases.mkdir(parents=True, exist_ok=True)
    (leases / "ticket-001--merged.json").write_text(
        json.dumps({"phase": "released", "ownerActor": "agent:test"}),
        encoding="utf-8",
    )

    # Dirty worktree
    wt_dirty = repo / ".worktrees" / "ticket-002--dirty"
    _git(repo, "worktree", "add", "-b", "ticket/002-dirty", str(wt_dirty), "main")
    dirty_file = wt_dirty / "uncommitted.txt"
    dirty_file.write_text("wip\n", encoding="utf-8")

    # Active claimed lease worktree
    wt_claimed = repo / ".worktrees" / "ticket-003--claimed"
    _git(repo, "worktree", "add", "-b", "ticket/003-claimed", str(wt_claimed), "main")
    (leases / "ticket-003--claimed.json").write_text(
        json.dumps(
            {
                "phase": "claimed",
                "ownerActor": "agent:worker",
                "expiresAt": "2026-11-22T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    # Symlink alias must be skipped without duplicating candidates
    os.symlink(repo, base / "alias-symlink")

    must_exist = [
        tracked_pkg,
        rec_bundle,
        prim_py,
        dup_py,
        dist_whl,
        dirty_file,
        wt_claimed / "README.md",
    ]
    return base, must_exist


def run_self_test() -> dict[str, Any]:
    """Execute end-to-end read-only scan and multi-profile verification."""
    with tempfile.TemporaryDirectory() as tmp:
        base, must_exist = _setup_fixture_workspace(Path(tmp))
        snapshot = wcs.scan_workspace(base, "wellmanifest/test-ws")
        if len(snapshot["candidates"]) != 8:
            raise AssertionError(
                f"expected 8 unique candidates (symlink skipped), got {len(snapshot['candidates'])}"
            )
        evals_by_profile: dict[str, dict[str, dict[str, Any]]] = {}
        for prof in wc.CRITERIA_PROFILES:
            rep = wcs.evaluate_live_workspace(
                base, "wellmanifest/test-ws", profile_id=prof
            )
            if rep["grantsCleanupAuthority"] is not False:
                raise AssertionError(
                    "live report must set grantsCleanupAuthority=false"
                )
            evals_by_profile[prof] = {
                ev["candidateId"]: ev for ev in rep["evaluations"]
            }

        balanced = evals_by_profile["balanced"]
        checks = [
            ("cache_sample-repo_node_modules", "HOLD_PROTECTED", "CLEAN-TRACK-001"),
            ("rec_sample-repo", "HOLD_PROTECTED", "CLEAN-RECOVERY-001"),
            ("venv_sample-repo_.venv", "HOLD_PROTECTED", None),
            ("venv_sample-repo_sub/venv", "DEDUPE_KEEP_CANONICAL", None),
            ("cache_sample-repo_dist", "DELETE_NOW", None),
            ("wt_sample-repo_ticket-001--merged", "PRUNE_GIT_WORKTREE", None),
            ("wt_sample-repo_ticket-002--dirty", "HOLD_PROTECTED", None),
            ("wt_sample-repo_ticket-003--claimed", "HOLD_PROTECTED", "CLEAN-LEASE-001"),
        ]
        for cid, exp_verdict, exp_veto in checks:
            if cid not in balanced:
                raise AssertionError(f"missing candidate {cid}: {sorted(balanced)}")
            ev = balanced[cid]
            if ev["verdict"] != exp_verdict:
                raise AssertionError(
                    f"{cid}: expected {exp_verdict}, got {ev['verdict']}"
                )
            if exp_veto and exp_veto not in ev["vetoReasons"]:
                raise AssertionError(
                    f"{cid}: missing veto {exp_veto}: {ev['vetoReasons']}"
                )

        # All 5 profiles must protect every T3_PROTECTED item identically
        for prof, by_id in evals_by_profile.items():
            for cid in (
                "cache_sample-repo_node_modules",
                "rec_sample-repo",
                "venv_sample-repo_.venv",
                "wt_sample-repo_ticket-002--dirty",
                "wt_sample-repo_ticket-003--claimed",
            ):
                if by_id[cid]["verdict"] != "HOLD_PROTECTED":
                    raise AssertionError(f"{prof} weakened {cid}: {by_id[cid]}")

        for p in must_exist:
            if not p.exists():
                raise AssertionError(f"read-only scanner deleted or moved {p}")

    return {
        "ok": True,
        "schema": wc.SNAPSHOT_SCHEMA,
        "candidatesVerified": 8,
        "profilesVerified": sorted(wc.CRITERIA_PROFILES),
        "readOnlyGuaranteed": True,
    }
