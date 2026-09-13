---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "worktree-lifecycle-handoff",
  "kind": "information",
  "version": 2,
  "title": "Worktree layout and Git lifecycle handoff",
  "status": "proposed",
  "owner": "wellmanifest/git-lifecycle",
  "created": "2026-09-07",
  "updated": "2026-09-13",
  "review_after": "2026-10-07",
  "source_revision": "37a1fe04d9f3e9ca021018ed85790886c9827cc9",
  "affected_repositories": [
    "wellmanifest/git-lifecycle"
  ],
  "evidence": [
    "https://github.com/wellmanifest/worktrees/pull/17",
    "https://github.com/wellmanifest/new-project/pull/300"
  ]
}
---

# Worktree layout and Git lifecycle handoff

<!-- docs:section purpose -->
## Purpose

Define the boundary between worktree placement and lossless, authorized Git
handoff. Continue an already authorized reconciliation without asking again
merely because the next step is a local commit, push or protected review.

<!-- docs:section scope -->
## Scope

This document describes wellmanifest/git-lifecycle. Placement is HOME wellmanifest/worktrees; distribution is HOME wellmanifest/new-project. Cross-repository evidence is [owned by subactor/docs](https://github.com/subactor/docs/blob/main/architecture/analysis/hidden-worktree-rollout.md).

<!-- docs:section evidence -->
## Evidence

Worktrees 0.5.0 is bound to protected merge `87d17708895ffad603c5d71cb2b8ef02ab100279`; new-project 0.20.8 is bound to protected merge `5848c1efb3386765e221cde57090f8c221f3e857`. The metadata source revision records this repository's pre-change baseline. Implementation and validation are delivered in the same ticket.

<!-- docs:section content -->
## Behavior

ADOPT wellmanifest/worktrees 0.5.0 / v5 for placement; do not duplicate its planner in Git lifecycle. New delivery work is `<primaryCheckout>/.worktrees/<ticket-NNN>--<slug>`, branch `ticket/NNN-<slug>`, lease `<primaryCheckout>/.subactor/leases/<ticket-NNN>--<slug>.json`. The Worktrees pack supplies a validated layout and read-only inventory; it does not perform cleanup. Git lifecycle and the adopting runtime own exact, separately authorized creation, repair and removal effects. Before the first effect, the runtime resolves the registered Git primary, validates the exact layout and lease, rejects symlinks and feature-probes Git 2.51.0 add/repair relative-path support. Execution receipts bind the actual path, ticket, branch, source revision and lease fencing. Inventory or a valid layout is not execution authority. V4 undotted and external legacy paths remain read-only observations until independently audited dirty state, processes/IDEs, lease, PR and HEAD reachability establish a separately authorized exact effect. No broad clean or glob deletion is permitted. The abstract Git lifecycle transition request remains unchanged: it carries evidence references; authentication and current-state reobservation belong to the effect boundary.

<!-- docs:section limitations -->
## Limitations

Source publication does not prove active runtime deployment or fleet-wide adoption. No existing worktree is moved, repaired or deleted by this change. Existing lease and recovery evidence is preserved.

The procedure below is a controller contract, not an implemented editor lock,
new Git command or permission granted by a document. Existing request schemas,
hooks and immutable pins remain unchanged. A missing effect implementation is
reported as a coverage gap; it is not replaced with a hook bypass.

## Authorized reconciliation of existing checkouts

Use the existing matching ticket and canonical delivery worktree. A request to
finish and publish its work covers ordinary non-destructive integration and
verification within that accepted scope. If a prior owner has explicitly
handed off the affected checkouts, reuse that evidence and acquire the current
controller lease; do not repeat the ownership question at every stage.
Conversely, a generic request for autonomy, an idle process, an open IDE, a
matching username or a clean checkout does not establish that another writer
has relinquished ownership. Query current ownership and actual file changes.

```dsl
RULE GIT-HANDOFF-RECONCILE-001
WHEN EXISTING_CHECKOUT_RECONCILIATION_REQUESTED
DO RESOLVE EXACT_REPOSITORY TARGET_REF TICKET CHECKOUTS AND_EXISTING_AUTHORITY
DO VERIFY OWNER_HANDOFF_OR_CURRENT_EXCLUSIVE_OWNERSHIP AND_CONTROLLER_FENCING
DO PRESERVE INDEX WORKING_TREE UNTRACKED_SOURCE AND_REFERENCED_HISTORY
DO VERIFY SECRET_SCANNED_CONTENT_ADDRESSED_SNAPSHOT_BY_RESTORATION
DO CLASSIFY EACH_DELTA_AS IDENTICAL ONE_SIDED MERGEABLE CONFLICTING OR_UNKNOWN
DO RECONCILE_KNOWN_DELTAS_IN_EXISTING_CANONICAL_DELIVERY_WORKTREE
DO REOBSERVE EXACT_REFS CONTENT_DIGESTS AND_LEASE_BEFORE_EACH_EFFECT
FORBID REPEATED_CONFIRMATION_FOR_SAME_ALREADY_AUTHORIZED_EFFECT
FORBID UNKNOWN_WRITE_DISCARD HOOK_BYPASS FORCE_PUSH OR_SELF_APPROVAL
ASSERT SOURCE_RECOVERABLE_AND_EVERY_TRANSFERRED_DELTA_ACCOUNTED_FOR
NEXT VALIDATION OR BLOCKED
```

1. Inventory registered checkouts, branch ancestry, both Git index and working
   files, ordinary untracked source, ticket scopes, leases and relevant live
   mounts. An unbound branch rejected by a hook is not a merge conflict.
   Shared committed history is context, not a new competing delta.
2. Make and restore-check a private content-addressed snapshot before removing
   a duplicate or replacing a file. Preserve different staged and unstaged
   versions separately. Inspect ignored source metadata without collecting
   credentials, local databases or the whole ignored runtime directory. Record
   archive digest and provenance outside tracked source; a local backup is not
   cross-machine durability or publication.
3. Compare each path against the common Git base. Copy one-sided changes;
   deduplicate only byte-identical layers; merge independent edits with
   three-way evidence. Equal filenames or timestamps do not prove equivalence.
   Retain unresolved variants and stop only their dependent effects. Resolve
   missing authority once for the exact ambiguous operation, not by repeatedly
   asking whether to push the entire task.
4. Bind the complete reconciled set to the existing ticket's accepted intent.
   Preserve public registry metadata and references needed by a fresh clone.
   Never silently raise delivery budgets, relabel historic commits or modify
   managed hashes to pass a gate. If the real change needs a split, use the
   managed ticket lifecycle; keep already preserved work recoverable throughout.
5. Before clearing the old checkout, prove every removed delta is represented
   in the destination or an explicitly retained variant, and recheck hashes
   and fencing. Keep commit protection active in both checkouts. If a running
   service bind-mounts source, cleanup is also a runtime change: use the
   separately authorized deployment/rollback boundary, not a Git-only reset.
6. Run the unchanged governance and relevant isolated tests. Stage the exact
   accepted paths, inspect the actual staged diff and scan it for secrets.
   Commit with hooks enabled, push the ticket branch and verify the remote SHA
   and PR. Invoke the declared independent protected review/merge controller.
   A failed gate remains a failed gate; a pushed branch is not a merged change.
7. Retry from fresh observations. Reuse a matching snapshot, commit, remote
   head, PR and controller receipt instead of producing duplicates. A changed
   digest or stale lease invalidates the pending effect. Keep the backup and
   any unique source until the terminal cleanup contract is satisfied.

## Distribution and outcome reporting

Ownership remains separate: Worktrees defines placement and inventory;
Git lifecycle defines the effect and recovery boundary; Ticket lifecycle owns
scope and handoff; New-project distributes the adopted governance projection.
Update the owning source and obtain its protected publication before upgrading
consumers through the immutable adoption mechanism. Do not hand-edit managed
copies or point all projects at an unpublished local source revision.

Process eligible consumers serially, reusing matching adoption tickets and
checking each repository's dirty state, active owner, test environment and
protected delivery profile. Keep conflicting consumers queued with exact
reasons; do not overwrite them or declare the entire fleet updated after one
successful canary. A source/target digest and observed PR/merge outcome belong
to each consumer's receipt. New-project work admission and protected delivery
retain their independent enforcement.

Report these as separate outcomes: **preserved**, **reconciled**, **tested**,
**committed**, **pushed**, **PR open**, **merged**, **deployed**, **cleaned up**.
Only claim a stage after observing its postcondition. No remote branch, local
snapshot, HTTP 200 or stale ticket status proves all the other stages.

<!-- docs:section next_actions -->
## Verification

Run repository checks and the applicable real-Git allocation, relative relocation and rejection tests. Verify immutable adoption separately from protected publication and from any subsequent runtime deployment. Record cross-repository readbacks in the canonical Subactor report.
