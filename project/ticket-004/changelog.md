# Ticket Changelog (ticket-004)

- Added the canonical `wellmanifest/git` alias and pack ownership boundaries.
- Added the fast ticket/branch/draft-PR/freeze/merge-receipt lifecycle.
- Delegated local checkout cleanup and divergent-work decisions instead of
  duplicating their standards.

## [0.1.0] - 2026-08-15

- Added `wellmanifest.git-lifecycle/repo-hygiene/v1` with invariant
  `one_main_zero_pr` and a 7200s stale window.
- Evaluator proves clean, fresh PR, stale PR and stale extra-branch cases.
- No human participant identity or content was generated.
