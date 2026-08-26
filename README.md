# git-lifecycle

Versioned Wellmanifest standard for safe repository bootstrap, local history,
review, integration, release and terminal workspace cleanup.

The runtime boundary accepts typed lifecycle AST documents. It is not a shell
or arbitrary Git command executor and never carries credentials or remote URLs.

`wellmanifest/git` is the public navigation alias for this pack. It MUST resolve
to `wellmanifest/git-lifecycle`; creating a second Git pack would duplicate
branch and remote semantics.

## Ownership boundary

- This pack owns repository identity, origin/default-branch observations,
  branch/ref transitions, pull-request lifecycle and terminal branch hygiene.
- `wellmanifest/worktrees` owns physical checkout placement and lease paths.
- `wellmanifest/merge` decides the disposition of divergent work.
- `wellmanifest/validation-attestation` defines trusted exact-head evidence.
- An adopting runtime performs effects and records receipts; this pack does not
  execute arbitrary Git or GitHub commands.

## Fast delivery path

1. Observe a usable `origin` and the current default branch before allocation.
2. Bind one ticket to one temporary branch and one canonical leased worktree.
3. Publish a draft pull request early so ownership and checks are visible.
4. Keep implementation moving on that branch; do not create replacement
   branches for retries.
5. Freeze the exact HEAD before independent validation and do not push during
   the decision.
6. After a trusted merge receipt, remove the remote ticket branch and hand the
   exact checkout to the `wellmanifest/worktrees` terminal audit.

The healthy terminal state is one default branch, zero open pull requests and
no released ticket branches. Stale state is evidence for Doctor/Repair, never
implicit authority to delete or merge.
