# Worktree overlap before local-commit

`wellmanifest/git-lifecycle` owns repository-state transitions. It does not
invent a second worktree daemon. It **adopts** the guard published by
`wellmanifest/new-project`:

- `worktree-guard.yaml` — declarative trigger (same role as `pyqual.yaml`)
- `scripts/worktree_overlap_check.py` — deterministic git + intent overlap
- `scripts/worktree_guard.py --once|--watch`

## Rule

`local-commit` and `integrate` are unauthorized while two checkouts of the
same repository identity have intersecting dirty/unmerged paths, or while two
`IN_PROGRESS` tickets claim overlapping `allowedPaths` without
`conflictsWith`.

`cleanup` still uses `.governance/workspace_lifecycle_check.py` for leftover
worktrees after merge. That checker is terminal; this guard is proactive.

## Scope of the rule

The gate answers for **this repository identity only**. Discovery still walks
the whole workspace — that is how a worktree parked outside its own tree is
found — but a conflict in an unrelated repository must never withhold
`local-commit` authority here. That is `--scope repository`, which
`worktree_guard.py` selects automatically when `--root` is a checkout.

A workspace-wide scan (`--scope workspace`, the systemd timer and `.worktrees`
path unit) is advisory for this standard: it reports, it does not authorize.

## Install in an adopter

```bash
# from a new-project checkout
./scripts/install-worktree-guard.sh --target /path/to/repo
python3 /path/to/repo/.governance/worktree_guard.py --root /path/to/repo --once
```

Chain it into the repository's own hook so `local-commit` actually fails
closed; the installer never rewrites an existing `pre-commit`:

```bash
# .githooks/pre-commit
"$(git rev-parse --show-toplevel)/.githooks/pre-commit-worktree-guard"
```

Normative detail: `wellmanifest/new-project` `docs/WORKTREE_GUARD.md`.
