# Ticket Changelog (ticket-006)

## [0.1.0] - 2026-08-22

- Added a separate remote initial-ref contract without changing the local Git
  lifecycle v1 graph.
- Bound publication to an exact source commit, tree, allowlist, plan and
  single-use grant.
- Made publication non-terminal until independent exact-head validation and
  defined quarantine without automatic ref deletion as the failure posture.
