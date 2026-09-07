---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "worktree-lifecycle-handoff",
  "kind": "information",
  "version": 1,
  "title": "Worktree layout and Git lifecycle handoff",
  "status": "proposed",
  "owner": "wellmanifest/git-lifecycle",
  "created": "2026-09-07",
  "updated": "2026-09-07",
  "review_after": "2026-10-07",
  "source_revision": "7d77d4b7af57e69bc75c3a0290b3a4805c5c4438",
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

Implement the user-requested hidden repository-local worktree layout.

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

<!-- docs:section next_actions -->
## Verification

Run repository checks and the applicable real-Git allocation, relative relocation and rejection tests. Verify immutable adoption separately from protected publication and from any subsequent runtime deployment. Record cross-repository readbacks in the canonical Subactor report.
