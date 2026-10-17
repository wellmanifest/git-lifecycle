# Ticket 017: Wire optional parameters in repo_hygiene snapshot helper

- **ID**: ticket-017
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-17

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: On 2026-10-17 user authorized fixing PERF-AUDIT findings and aligning `.governance/standard-adoption.json` across wellmanifest repositories.
Wire default_branch and stale_window_seconds at the _snapshot call site in standard/repo_hygiene.py and align .governance/standard-adoption.json.

## Acceptance criteria

- [x] AC-01: Wire default_branch and stale_window_seconds at the _snapshot call site in standard/repo_hygiene.py and align .governance/standard-adoption.json.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
