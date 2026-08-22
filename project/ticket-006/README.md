# Ticket 006: Define remote initial-ref publication lifecycle

- **ID**: ticket-006
- **Owner**: unresolved:human
- **Status**: DONE
- **Workflow state**: DONE
- **Created**: 2026-08-22

## Goal and scope

Define a separate, data-only lifecycle contract for publishing the first Git
reference to an already existing repository that has no refs. The contract is
complementary to the local `seed-baseline` transaction: it requires a fresh
digest-bound single-use grant, an exact source commit and tree/allowlist
digests, secret-scan and governance evidence, a normal non-force push, remote
read-back and independent Validator evidence. It must not execute Git, carry a
remote URL or credential, inherit repository-bootstrap authority, or
automatically delete the new ref after a failed validation.

## Acceptance criteria

- [x] AC-01: A closed v1 schema defines plan, grant binding, non-terminal
  publication receipt and terminal independent-validation receipt.
- [x] AC-02: A standalone Lifecycle DSL profile models only
  `REMOTE_EMPTY -> INITIAL_REF_PUBLISHED -> ACCEPTED|QUARANTINED`.
- [x] AC-03: Dependency-free conformance accepts the complete approved flow
  and rejects authority inheritance, remote drift, force update, substituted
  tree/commit, self-validation, secret material and automatic ref deletion.
- [x] AC-04: Architecture guidance keeps local seed, remote publication,
  runtime execution and Skills composition in separate responsibility owners.
- [x] AC-05: Contract, lifecycle, governance and diff checks pass locally;
  hosted checks and independent exact-head review remain publication gates.

## Authorization

The user's continuing instruction to implement and publish the autonomy
improvements is `SESSION_EXECUTION_AUTHORIZATION` for this bounded standard
change and its protected pull-request delivery. It does not issue the runtime
grant described by this contract and does not authorize this repository to
push an initial ref to another repository.

## Participants

- Human participant: unresolved; no user-* file was created by this script.
- Agent participant: [ai-codex.md](ai-codex.md)

## Closure evidence

- Implementation PR: `wellmanifest/git-lifecycle#9`.
- Integrated main SHA: `72ade3b6c7ad68f617a50871a1f7466e7a868ab9`.
- Exact implementation head: `f53a446acb81c7fd4a32d3aa4d9dffe39c0e7fec`.
- Trusted Validator review: `5001042582`.
- Validator run: `subactor/validator-agent#32598215420`.
- Planfile receipt: `PLF-7373`, status `done`.
