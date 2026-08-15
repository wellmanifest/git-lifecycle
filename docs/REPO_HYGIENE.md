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
