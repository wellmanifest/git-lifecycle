# Durable Git work continuity

Conversation context, a local stash and an untracked-only handoff are not
durable Git state. A `checkpoint` is a same-state transition available in each
initialized nonterminal state from `seeded` through `released`. It points to
exactly one validated `new-project.work-continuity/v1` receipt and never moves
a ref, pushes, publishes, restores data or grants authority.

## Durability boundary

Clean work is recoverable only when the checkpoint binds the exact repository,
ticket branch and real `HEAD`. Dirty work may cross a context, process or agent
boundary only after an authorized controller stores a content-addressed
snapshot outside Git, records its SHA-256 and completes a secret scan. A chat
summary, raw patch, stash, filesystem path or untracked file without that
artifact and receipt is insufficient.

An applied Git checkpoint receipt preserves its lifecycle state, contains a
real `headSha`, sets `pushPerformed=false` and
`publicationPerformed=false`, keeps secrets redacted and includes exactly one
opaque `receipt:continuity.<id>` reference. Snapshot bytes and source diffs do
not belong in the lifecycle document.

## Divergence-safe resume

Resume first observes the current worktree, branch, `HEAD`, remote refs, PRs and
protected receipts. It verifies the monotonic checkpoint chain plus repository,
intent/scope and workspace digests before considering a restore. Authorization,
lease revision and fencing token are revalidated separately.

If the observed state differs, preserve both versions and route to
reconciliation or blocked. Never reset, overwrite, delete, force-push or apply
a snapshot automatically. Restore and every later Git effect remain separate,
explicitly authorized transitions.
