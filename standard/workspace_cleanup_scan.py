"""Read-only live workspace scanner for multi-criteria cleanup triage.

Observation only: never deletes files, mutates Git state, or uses network I/O.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import workspace_cleanup as wc
from git_primitives import parse_rfc3339_ns
from workspace_cleanup_llm import CleanupError

_ID_SANITIZE = re.compile(r"[^A-Za-z0-9_./:@-]+")
_VENV_MANIFESTS = (
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
    "poetry.lock",
    "setup.py",
)
_BUILD_DIRS = frozenset(
    {
        "node_modules",
        "target",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".code2llm_cache",
        "__pycache__",
        ".gradle",
        ".next",
        ".turbo",
        ".parcel-cache",
        ".dirac-symbol-index",
    }
)
_TEST_DIRS = frozenset(
    {"htmlcov", ".vdisplay", ".intent-t2c-semcod-batch", "artifacts"}
)
_PRUNE_SUBDIRS = frozenset({".git", ".worktrees", ".venv", "venv", ".subactor"})
_DEFAULT_REFS = ("origin/main", "origin/master", "main", "master")


def _run_cmd(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=30)


def collect_disk_context(root: Path) -> dict[str, Any]:
    """Read filesystem capacity telemetry for ``root`` via ``os.statvfs``."""
    st = os.statvfs(root)
    total = max(1, int(st.f_blocks) * int(st.f_frsize))
    free = max(0, int(st.f_bavail) * int(st.f_frsize))
    pct = round(min(100.0, max(0.0, (free / total) * 100.0)), 2)
    tier = (
        "emergency"
        if pct < 5.0
        else ("critical" if pct < 10.0 else ("elevated" if pct < 20.0 else "normal"))
    )
    return {
        "freeBytes": free,
        "totalBytes": total,
        "freePercent": pct,
        "pressureTier": tier,
    }


def collect_process_table() -> str:
    """Return active process lines excluding the current and parent PIDs."""
    skip = {str(os.getpid()), str(os.getppid())}
    try:
        proc = _run_cmd(["ps", "-eo", "pid,args"])
    except OSError:
        return ""
    if proc.returncode != 0:
        return ""
    return "\n".join(
        raw
        for raw in proc.stdout.splitlines()
        if (parts := raw.strip().split(None, 1)) and parts[0] not in skip
    )


def _dir_stats(target: Path, now_s: float) -> tuple[int, int]:
    """Return ``(sizeBytes, ageSeconds)`` without following symlinks."""
    try:
        root_st = target.lstat()
    except OSError:
        return 0, 0
    if not target.is_dir() or target.is_symlink():
        return max(0, int(root_st.st_size)), max(0, int(now_s - root_st.st_mtime))
    total, newest = 0, root_st.st_mtime
    for dirpath, _, filenames in os.walk(target, followlinks=False):
        try:
            newest = max(newest, os.lstat(dirpath).st_mtime)
        except OSError:
            pass
        for name in filenames:
            try:
                f_st = os.lstat(os.path.join(dirpath, name))
                total += max(0, int(f_st.st_size))
                newest = max(newest, f_st.st_mtime)
            except OSError:
                pass
    return total, max(0, int(now_s - newest))


def discover_git_repos(root: Path, max_repo_depth: int = 2) -> list[Path]:
    """Find non-symlink Git repositories under ``root`` within ``max_repo_depth``."""
    resolved = root.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise CleanupError(f"root directory does not exist: {root}")
    if (resolved / ".git").exists():
        return [resolved]
    repos: list[Path] = []
    for dirpath, dirnames, _ in os.walk(resolved, followlinks=False):
        dp = Path(dirpath)
        depth = len(dp.relative_to(resolved).parts) if dp != resolved else 0
        kept: list[str] = []
        for name in sorted(dirnames):
            sub = dp / name
            if name.startswith(".") or sub.is_symlink():
                continue
            if (sub / ".git").exists():
                repos.append(sub)
            elif depth + 1 < max_repo_depth:
                kept.append(name)
        dirnames[:] = kept
    return repos


def _normalize_expires_at(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    norm = raw[:-6] + "Z" if raw.endswith("+00:00") else raw
    try:
        parse_rfc3339_ns(norm, "expiresAt", CleanupError, require_z=True)
        return norm
    except CleanupError:
        return None


def _read_lease_info(repo: Path, wt_name: str) -> dict[str, Any]:
    lease_path = repo / ".subactor" / "leases" / f"{wt_name}.json"
    if not lease_path.is_file() or lease_path.is_symlink():
        return {"state": "none", "owner": None, "expiresAt": None}
    try:
        data = json.loads(lease_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"state": "foreign", "owner": None, "expiresAt": None}
    phase = data.get("phase")
    owner = data.get("ownerActor") or data.get("owner")
    return {
        "state": phase if phase in wc.LEASE_STATES else "foreign",
        "owner": owner[:255] if isinstance(owner, str) and owner else None,
        "expiresAt": _normalize_expires_at(data.get("expiresAt")),
    }


def _has_open_fds(target: Path, check_lsof: bool) -> bool:
    if not check_lsof:
        return False
    cmd = ["lsof", "+D", str(target)] if target.is_dir() else ["lsof", str(target)]
    try:
        return bool(_run_cmd(cmd).stdout.strip())
    except OSError:
        return False


def _git_output(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run_cmd(["git", "-C", str(repo), *args])


def _default_ref(repo: Path) -> str | None:
    return next(
        (
            r
            for r in _DEFAULT_REFS
            if _git_output(repo, "rev-parse", "--verify", "--quiet", r).returncode == 0
        ),
        None,
    )


def _is_git_tracked(repo: Path, rel: str) -> int:
    proc = _git_output(repo, "ls-files", "--", rel)
    return (
        len(proc.stdout.splitlines())
        if proc.returncode == 0 and proc.stdout.strip()
        else 0
    )


def _canonical_manifest(parent: Path) -> str | None:
    for name in _VENV_MANIFESTS:
        if (parent / name).is_file():
            return str(parent / name)[:1024]
    return None


def _make_candidate(
    raw_id: str,
    path: Path,
    kind: str,
    ctx: tuple[float, str, bool],
    *,
    tracked: int = 0,
    dirty: int = 0,
    merged: bool = False,
    bundle: bool = False,
    canonical: str | None = None,
    lease: dict[str, Any] | None = None,
    locked: bool = False,
) -> dict[str, Any]:
    now_s, ps_text, check_lsof = ctx
    size_b, age_s = _dir_stats(path, now_s)
    cid = _ID_SANITIZE.sub("_", raw_id).strip("_")[:240] or "cand"
    return {
        "candidateId": cid,
        "path": str(path)[:1024],
        "artifactKind": kind,
        "sizeBytes": size_b,
        "ageSeconds": age_s,
        "trackedFilesCount": tracked,
        "git": {
            "isGitTracked": tracked > 0,
            "dirtyFilesCount": dirty,
            "unpushedCommitsCount": 0,
            "mergedIntoDefault": merged,
            "hasVerifiedBundle": bundle,
            "canonicalCopyPath": canonical[:1024] if canonical else None,
        },
        "lease": lease or {"state": "none", "owner": None, "expiresAt": None},
        "runtime": {
            "openFileHandles": _has_open_fds(path, check_lsof),
            "activeDaemon": bool(ps_text and str(path) in ps_text),
            "activeIdeSession": locked,
            "activeMountOrSymlinkTarget": path.is_symlink(),
        },
    }


def _scan_worktrees(repo: Path, ctx: tuple[float, str, bool]) -> list[dict[str, Any]]:
    wt_out = _git_output(repo, "worktree", "list", "--porcelain").stdout
    blocks = [b for b in wt_out.strip().split("\n\n") if b.strip()]
    def_ref = _default_ref(repo)
    items: list[dict[str, Any]] = []
    for blk in blocks[1:]:
        lines = blk.splitlines()
        locked = any(l == "locked" or l.startswith("locked ") for l in lines)
        meta = dict(l.split(" ", 1) for l in lines if " " in l)
        wp = Path(meta.get("worktree", ""))
        if not wp.exists() or wp.is_symlink():
            continue
        br = meta.get("branch", "").replace("refs/heads/", "")
        rec_dir = wp / ".subactor" / "recovery"
        if rec_dir.is_dir() and any(rec_dir.iterdir()):
            items.append(
                _make_candidate(
                    f"wt_{repo.name}_{wp.name}_rec",
                    wp,
                    "subactor_recovery",
                    ctx,
                    locked=locked,
                )
            )
            continue
        dirty_out = _git_output(wp, "status", "--porcelain").stdout
        dirty_cnt = sum(1 for l in dirty_out.splitlines() if l.strip())
        merged = bool(
            br
            and def_ref
            and _git_output(repo, "merge-base", "--is-ancestor", br, def_ref).returncode
            == 0
        )
        kind = (
            "worktree_dirty"
            if dirty_cnt > 0
            else ("worktree_merged" if merged else "worktree_unmerged")
        )
        items.append(
            _make_candidate(
                f"wt_{repo.name}_{wp.name}",
                wp,
                kind,
                ctx,
                dirty=dirty_cnt,
                merged=merged,
                canonical=str(repo),
                lease=_read_lease_info(repo, wp.name),
                locked=locked,
            )
        )
    return items


def _scan_repo(
    repo: Path, max_depth: int, ctx: tuple[float, str, bool]
) -> list[dict[str, Any]]:
    found = _scan_worktrees(repo, ctx)
    rec = repo / ".subactor" / "recovery"
    if rec.exists() and not rec.is_symlink():
        has_bundle = rec.is_dir() and any(rec.glob("*.bundle"))
        found.append(
            _make_candidate(
                f"rec_{repo.name}", rec, "subactor_recovery", ctx, bundle=has_bundle
            )
        )
    for dirpath, dirnames, _ in os.walk(repo, followlinks=False):
        dp = Path(dirpath)
        depth = len(dp.relative_to(repo).parts) if dp != repo else 0
        kept: list[str] = []
        for d in sorted(dirnames):
            full = dp / d
            if full.is_symlink():
                continue
            rel = str(full.relative_to(repo))
            if d in {".venv", "venv", ".testvenv"}:
                prim = dp == repo and d == ".venv"
                kind = "virtualenv_primary" if prim else "virtualenv_duplicate"
                canon = None if prim else (_canonical_manifest(dp) or str(repo))
                tr = _is_git_tracked(repo, rel)
                found.append(
                    _make_candidate(
                        f"venv_{repo.name}_{rel}",
                        full,
                        kind,
                        ctx,
                        tracked=tr,
                        canonical=canon,
                    )
                )
            elif d in _BUILD_DIRS or d.endswith(".egg-info") or d in _TEST_DIRS:
                kind = "test_artifacts" if d in _TEST_DIRS else "build_cache"
                tr = _is_git_tracked(repo, rel)
                found.append(
                    _make_candidate(
                        f"cache_{repo.name}_{rel}",
                        full,
                        kind,
                        ctx,
                        tracked=tr,
                        canonical=str(repo),
                    )
                )
            elif d not in _PRUNE_SUBDIRS and depth + 1 < max_depth:
                kept.append(d)
        dirnames[:] = kept
    return found


def scan_workspace(
    root: Path,
    repository: str,
    *,
    max_depth: int = 3,
    min_bytes: int = 0,
    check_lsof: bool = False,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Scan ``root`` read-only and emit a ``workspace-cleanup-snapshot/v1`` document."""
    now_dt = datetime.now(UTC)
    ctx = (now_dt.timestamp(), collect_process_table(), check_lsof)
    repos = discover_git_repos(root)
    if not repos:
        raise CleanupError(f"no git repositories found under {root}")
    raw_cands = [c for r in repos for c in _scan_repo(r, max_depth, ctx)]
    filtered = [c for c in raw_cands if c["sizeBytes"] >= min_bytes]
    if not filtered:
        raise CleanupError("no cleanup candidates matched scan filters")
    filtered.sort(key=lambda c: (-c["sizeBytes"], c["path"]))
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for idx, cand in enumerate(filtered[:10_000]):
        cid = cand["candidateId"]
        cand["candidateId"] = cid if cid not in seen else f"{cid[:220]}_{idx}"
        seen.add(cand["candidateId"])
        unique.append(cand)
    snap: dict[str, Any] = {
        "schema": wc.SNAPSHOT_SCHEMA,
        "kind": "workspace-cleanup-snapshot",
        "repository": repository,
        "observedAt": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "diskContext": collect_disk_context(root),
        "candidates": unique,
    }
    if profile_id is not None:
        snap["profileId"] = profile_id
    return snap


def evaluate_live_workspace(
    root: Path,
    repository: str,
    *,
    max_depth: int = 3,
    min_bytes: int = 0,
    check_lsof: bool = False,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Scan ``root`` read-only and return multi-criteria cleanup evaluation JSON."""
    snap = scan_workspace(
        root,
        repository,
        max_depth=max_depth,
        min_bytes=min_bytes,
        check_lsof=check_lsof,
        profile_id=profile_id,
    )
    return wc.evaluate_snapshot(snap, profile_id=profile_id)


def self_test() -> dict[str, Any]:
    """Run live scanner self-test fixtures without leaving temporary files behind."""
    import workspace_cleanup_scan_fixtures

    return workspace_cleanup_scan_fixtures.run_self_test()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--all", action="store_true", help="Run live scanner conformance tests."
    )
    p.add_argument(
        "--root", type=Path, help="Workspace or repository root to scan read-only."
    )
    p.add_argument(
        "--repository", help="Owner/repo identifier for the generated report."
    )
    p.add_argument(
        "--profile", choices=sorted(wc.CRITERIA_PROFILES), help="Evaluation profile."
    )
    p.add_argument(
        "--emit-snapshot", action="store_true", help="Emit raw snapshot JSON."
    )
    p.add_argument(
        "--emit-llm-brief", action="store_true", help="Emit llmBrief JSON only."
    )
    p.add_argument(
        "--max-depth", type=int, default=3, help="Max relative dir scan depth."
    )
    p.add_argument(
        "--min-bytes", type=int, default=0, help="Ignore smaller candidates."
    )
    p.add_argument("--check-lsof", action="store_true", help="Probe lsof open handles.")
    args = p.parse_args(argv)
    if args.all:
        print(json.dumps(self_test(), indent=2, sort_keys=True, allow_nan=False))
        return 0
    if args.root and args.repository:
        if args.emit_snapshot:
            payload = scan_workspace(
                args.root,
                args.repository,
                max_depth=args.max_depth,
                min_bytes=args.min_bytes,
                check_lsof=args.check_lsof,
                profile_id=args.profile,
            )
        else:
            rep = evaluate_live_workspace(
                args.root,
                args.repository,
                max_depth=args.max_depth,
                min_bytes=args.min_bytes,
                check_lsof=args.check_lsof,
                profile_id=args.profile,
            )
            payload = rep["llmBrief"] if args.emit_llm_brief else rep
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        return 0
    p.error("pass --all or both --root and --repository")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
