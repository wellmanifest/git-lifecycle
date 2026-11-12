# Ticket 020: Modularize initial-ref conformance and harden RFC3339, ref, and schema parity

- **ID**: ticket-020
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-12

## Session authorization

- `SESSION_EXECUTION_AUTHORIZATION`: Autonomous execution, testing, security hardening, `< 500`-line modularization, and protected Validator publication requested by the repository owner.

## Goal and scope

1. **Modularize `< 500`-line `initial_ref_conformance.py` and fix terminal receipt binding (`standard/initial_ref_conformance.py`, `standard/initial_ref_fixtures.py`)**: Extract fixtures and adversarial runner into `standard/initial_ref_fixtures.py`; enforce `receipt:` prefix and distinctness between `terminal.receiptRef` and `terminal.publicationReceiptRef`; enforce strict ASCII RFC 3339 nanosecond expiry parsing, iterative non-recursive `reject_unsafe`, and `allow_nan=False` + UTF-16 surrogate rejection.
2. **Harden `repo_hygiene.py` (`standard/repo_hygiene.py`)**: Enforce `repo-hygiene.schema.json` parity (`staleWindowSeconds <= 604800`, canonical non-dot `owner/name` repository and `headRepository`, valid bounded Git ref names on `defaultBranch`/`branches[].name`/`openPullRequests[].headRef`, exact 0..9-digit UTC RFC 3339 timestamps), and replace raw `open()` + `json.load()` on `--snapshot` with descriptor-safe `O_NOFOLLOW` regular-file loading and strict finite/unique-key/surrogate-free JSON decoding.
3. **Align `conformance.py` and add regression tests (`standard/conformance.py`, `standard/test_hardening.py`)**: Enforce `isinstance(..., dict)` and `isinstance(..., str)` reference checks, `evidenceRefs` item schema pattern and `maxItems: 16`, surrogate/non-finite rejection, zero Ruff diagnostics, and full unit test coverage in `standard/test_hardening.py`.

## Acceptance criteria

- [x] AC-01: All owned `standard/*.py` modules stay `< 500` lines after `ruff format`, `ruff check --no-cache` passes with 0 errors, and `conformance.py --all`, `initial_ref_conformance.py --all`, `repo_hygiene.py --all`, `unittest`, `./project/governance-check.sh --base origin/main`, and `wellman check` pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
