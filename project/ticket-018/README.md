# Ticket 018: Vendor compact Lifecycle DSL validator and compact git lifecycle profiles

- **ID**: ticket-018
- **Owner**: codex
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-19

## Goal and scope

Vendor the compact `wellmanifest/lifecycle` validator (`1ea2a90bd5b90a768ad2b36a9c1c330523bc80b4`), compact `standard/git-lifecycle.lifecycle` and `standard/repository-initial-ref.lifecycle` using `STATES [...]`, `EVENTS [...]`, `EVIDENCES [...]`, and multi-source `TRANSITION [...] -> TARGET`, and enforce zero compaction findings in `standard/conformance.py` and `standard/initial_ref_conformance.py`.

## Acceptance criteria

- [x] AC-01: Both lifecycle profiles validate with `finding_count == 0` under `lifecycle.audit_path`, and `conformance.py --all`, `initial_ref_conformance.py --all`, and `./project/governance-check.sh` pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
