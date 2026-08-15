---
participant-id: agent:grok
participant: grok
role: agent
ticket: ticket-004
---
# Participant: grok (AI agent)

## Understanding

The Git lifecycle pack already owns ticket-branch cleanup semantics. This
ticket adds a closed observation for org-wide hygiene: one long-lived `main`
and zero open PRs when idle, with a 2h in-progress window. Doctor-agent is the
runtime consumer. This pack does not scan GitHub or mutate remotes.

The request to execute this work creates SESSION_EXECUTION_AUTHORIZATION.

## Execution plan

1. Record the bounded intent and allowed paths.
2. Add the snapshot schema, dependency-free evaluator and hygiene document.
3. Hook the evaluator into existing conformance `--all`.
4. Prove clean / fresh PR / stale PR / stale branch cases.

## Actual changes

- Initialized the bounded ticket and recorded SESSION_EXECUTION_AUTHORIZATION
  from the request to execute this work.
- Added `standard/repo-hygiene.schema.json`, `standard/repo_hygiene.py` and
  `docs/REPO_HYGIENE.md`.
- Extended `standard/conformance.py --all` to run the hygiene self-test.

## Blockers

- None inside the recorded intent; proceed without a second confirmation.
- New authority remains required for destructive action, secret access, new
  external coordination, material objective expansion and trusted merge.
  Opening a GitHub pull request is out of scope.
