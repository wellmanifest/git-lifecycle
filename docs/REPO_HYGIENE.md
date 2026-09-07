# Repository hygiene (`one_main_zero_pr`)

```dsl
DOCUMENT REPO_HYGIENE
VERSION 1
LANGUAGE EN
MODE STRICT
SCHEMA "wellmanifest.git-lifecycle/repo-hygiene/v1"
INVARIANT one_main_zero_pr
STALE_WINDOW_SECONDS 7200
CONSUMER "subactor/doctor-agent"
```

This observation contract belongs to `wellmanifest/git-lifecycle`. It describes
a healthy GitHub repository and when an implementing scanner may emit a
problem. It does not merge, close pull requests, delete branches, force-push or
open a GitHub pull request.

## HOME versus ADOPT

Wellmanifest HOMEs the schema. `subactor/doctor-agent` HOMEs the GitHub org
scan and problem emission. Semcod ADOPTs the same contract: doctor-agent scans
the `semcod` org; Semcod tools must not grow a second org scanner.

Monitored organizations: `wellmanifest`, `subactor`, `semcod`.

## Healthy repository

```text
default branch = main
open pull requests = 0
remote branches = [main]
```

`main` is the only long-lived branch.

## In progress — leave it

Do not emit a problem, close a PR, delete a branch or nag while work is moving:

- an open pull request whose last relevant activity (push, comment, review or
  check run, represented as `lastActivityAt`) is newer than the stale window;
- or a non-`main` branch whose tip commit is newer than the stale window.

The default stale window is **7200 seconds (2 hours)** and is configurable.

## Stale window — emit a Doctor problem

When extra branches and/or open pull requests exist **and** the last relevant
activity is **≥ 7200s** old, the verdict is `stale`. The implementing scanner
emits one deduplicated problem into the existing doctor-agent issue /
operational-event pipeline so repair-lifecycle can observe. It MUST NOT:

- auto-merge;
- force-delete branches;
- fabricate ticket numbers;
- open a new GitHub pull request from the scanner for each stale repo.

Codes:

| Code | When |
| --- | --- |
| `REPO-HYGIENE-STALE-PR` | Open PR `lastActivityAt` is ≥ stale window |
| `REPO-HYGIENE-STALE-BRANCH` | Extra branch with no open PR and tip ≥ stale window |
| `REPO-HYGIENE-DEFAULT-BRANCH` | Default branch is not `main` |

A GitHub App 404 on a repository is a **scan** problem for that repository. It
must not abort the rest of the organization scan.

## Evaluator

```text
python3 standard/repo_hygiene.py --all
python3 standard/repo_hygiene.py --snapshot path.json
```

The evaluator is dependency-free and performs no network I/O.

## Operational sequence

The observation contract is consumed in this order:

1. verify repository identity, `origin` and default branch;
2. correlate every non-default branch with its ticket and pull request;
3. treat activity inside the stale window as in progress;
4. freeze an exact HEAD before trusted validation;
5. accept merge state only from a receipt bound to repository, pull request,
   head SHA, ticket and actor;
6. delete the merged remote ticket branch when repository policy permits;
7. use `wellmanifest/worktrees` for placement and read-only checkout inventory;
   keep exact authorized cleanup effects in Git lifecycle and the adopting runtime.
   See [the v5 handoff](information/worktree-lifecycle-handoff.md).

Missing origin, an unbound branch, a closed-unmerged pull request or unique
local commits are explicit findings. They are not repaired by guessing,
force-pushing or deleting the workspace. `wellmanifest/merge` first assigns an
evidence-backed disposition such as adopt, rebuild, superseded or defer.

## Complex-change delivery profile

For changes spanning multiple components or shared/generated files:

1. allocate one ticket and atomically reserve its `allowedPaths`;
2. use one writer branch/worktree; competing tickets become `BLOCKED` or
   declare an explicit `conflictsWith` relationship;
3. enqueue the exact head SHA and rebase onto current `main` before checks;
4. on `STALE_HEAD_CHANGED`, release the lease, rebase from a fresh head and
   rerun all gates — never force-push over another writer;
5. merge only after trusted Validator approval and an external receipt binding
   repository, PR, ticket, head SHA and merge SHA;
6. deploy the integrated head, run a bounded canary/readback, then release the
   lease and clean the worktree.

The queue exposes `LEASED`, `VALIDATING`, `STALE_REBASE`, `APPROVED`,
`MERGED`, `CANARY_FAILED` and `RELEASED`. A failed canary leaves an evidence
receipt and rolls back to the last integrated head; retries are bounded.
