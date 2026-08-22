# Ticket preprompt

- **Task ID**: ticket-006
- **Task title**: Define remote initial-ref publication lifecycle
- **Created**: 2026-08-22T20:46:45Z

Keep the existing `wellmanifest.git-lifecycle/v1` local history graph intact.
Add a complementary closed contract instead of widening `seed-baseline`.
Require exact absence/read-back evidence and independent validation. Keep
credentials, remote URLs, commands and execution outside the standard. Treat
validation failure as quarantine; never authorize automatic ref deletion or
force update.

The request to execute this work creates `SESSION_EXECUTION_AUTHORIZATION` for
the bounded standard and its protected delivery. Runtime mutation still needs
its own exact authority.
