"""Regression and hardening test suite for wellmanifest/git-lifecycle (ticket-020)."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import conformance
import initial_ref_conformance
import initial_ref_fixtures
import repo_hygiene


class GitLifecycleHardeningTests(unittest.TestCase):
    def test_conformance_and_initial_ref_suites_pass(self) -> None:
        res1 = conformance.run_all()
        self.assertIs(res1["ok"], True)
        res2 = initial_ref_conformance.run_all()
        self.assertIs(res2["ok"], True)

    def test_initial_ref_terminal_prefix_distinctness_and_rfc3339(self) -> None:
        now = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
        docs = list(initial_ref_fixtures.fixtures(now))

        # Valid 9-digit nanosecond UTC timestamp in grant expiresAt
        ns_docs = copy.deepcopy(docs)
        initial_ref_fixtures.change_grant(
            ns_docs, expiresAt="2026-08-22T20:00:00.000000001Z"
        )
        ns_docs[2]["grantDigest"] = ns_docs[1]["grantDigest"]
        ns_docs[3]["publicationReceiptDigest"] = initial_ref_conformance.digest(
            ns_docs[2]
        )
        initial_ref_conformance.validate_terminal(*ns_docs, now=now)

        # Reject non-RFC3339 Python fromisoformat forms and -00:00
        for bad_ts in (
            "20260822T201000Z",
            "2026-08-22 20:10:00Z",
            "2026-08-22_20:10:00Z",
            "2026-08-22T20:10:00-00:00",
            "2026-08-22T20:10:00Z+00:00",
            12345,
        ):
            with self.subTest(bad_ts=bad_ts):
                cand = copy.deepcopy(docs)
                cand[1]["expiresAt"] = bad_ts
                cand[1]["grantDigest"] = initial_ref_conformance.material_digest(
                    cand[1], "grantDigest"
                )
                with self.assertRaises(initial_ref_conformance.ContractError):
                    initial_ref_conformance.validate_grant(cand[1], now=now)

        # Reject terminal receiptRef with non-receipt prefix or reused publicationReceiptRef
        for bad_ref in (
            "plan:wrong-prefix",
            "grant:wrong-prefix",
            docs[2]["receiptRef"],
        ):
            cand = copy.deepcopy(docs)
            cand[3]["receiptRef"] = bad_ref
            with self.assertRaises(initial_ref_conformance.ContractError):
                initial_ref_conformance.validate_terminal(*cand, now=now)

        # Reject lone UTF-16 surrogates and non-finite floats in canonical()
        for bad_val in ({"k": "\ud800"}, {"\udfff": "v"}, {"n": float("inf")}):
            with self.assertRaises(initial_ref_conformance.ContractError):
                initial_ref_conformance.canonical(bad_val)

    def test_repo_hygiene_nanoseconds_refs_windows_and_snapshot_io(self) -> None:
        # 9-digit nanosecond timestamps are supported deterministically
        snap = repo_hygiene._snapshot(
            repository="wellmanifest/git-lifecycle",
            observed_at="2026-08-15T18:00:00.000000500Z",
            branches=[
                {"name": "main", "committedAt": "2026-08-15T10:00:00.123456789Z"}
            ],
        )
        verdict = repo_hygiene.evaluate(snap)
        self.assertEqual(verdict.status, "healthy")

        # Reject malformed timestamps accepted by naive fromisoformat slicing
        for bad_ts in (
            "20260815T180000Z",
            "2026-08-15 18:00:00Z",
            "2026-08-15T18:00Z",
            "2026-08-15T18:00:00+02:00Z",
        ):
            with self.assertRaises(repo_hygiene.HygieneError):
                repo_hygiene.evaluate(
                    repo_hygiene._snapshot(
                        repository="wellmanifest/git-lifecycle",
                        observed_at=bad_ts,
                    )
                )

        # Reject staleWindowSeconds > 604800, dot-segment repositories, and invalid Git refs
        with self.assertRaises(repo_hygiene.HygieneError):
            repo_hygiene.evaluate(
                repo_hygiene._snapshot(
                    repository="wellmanifest/git-lifecycle",
                    observed_at="2026-08-15T18:00:00Z",
                    stale_window_seconds=604_801,
                )
            )
        for bad_repo in ("../..", "owner/..", "./repo", "a/b/c"):
            with self.assertRaises(repo_hygiene.HygieneError):
                repo_hygiene.evaluate(
                    repo_hygiene._snapshot(
                        repository=bad_repo,
                        observed_at="2026-08-15T18:00:00Z",
                    )
                )
        for bad_ref in (
            "feat..bad",
            "branch.lock",
            "/leading",
            "space ref",
            "ctrl\x7f",
        ):
            with self.assertRaises(repo_hygiene.HygieneError):
                repo_hygiene.evaluate(
                    repo_hygiene._snapshot(
                        repository="wellmanifest/git-lifecycle",
                        observed_at="2026-08-15T18:00:00Z",
                        branches=[
                            {"name": "main", "committedAt": "2026-08-15T10:00:00Z"},
                            {"name": bad_ref, "committedAt": "2026-08-15T17:59:00Z"},
                        ],
                    )
                )

        # Descriptor-safe --snapshot rejects symlinks, symlinked ancestors, duplicate keys, 1e309, surrogates
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real_dir = base / "real"
            real_dir.mkdir()
            snap_file = real_dir / "snap.json"
            snap_file.write_text(json.dumps(snap), encoding="utf-8")
            self.assertEqual(repo_hygiene.main(["--snapshot", str(snap_file)]), 0)

            sym_file = base / "sym.json"
            sym_file.symlink_to(snap_file)
            with self.assertRaises(repo_hygiene.HygieneError):
                repo_hygiene.main(["--snapshot", str(sym_file)])

            sym_dir = base / "sym_dir"
            sym_dir.symlink_to(real_dir)
            with self.assertRaises(repo_hygiene.HygieneError):
                repo_hygiene.main(["--snapshot", f"{sym_dir}/../real/snap.json"])

            for bad_raw in (
                '{"a": 1, "a": 2}',
                '{"x": 1e309}',
                '{"s": "\\ud800"}',
            ):
                bad_path = real_dir / "bad.json"
                bad_path.write_text(bad_raw, encoding="utf-8")
                with self.assertRaises(repo_hygiene.HygieneError):
                    repo_hygiene.main(["--snapshot", str(bad_path)])

    def test_conformance_strict_types_evidence_bounds_and_modularity_budget(
        self,
    ) -> None:
        base_req: dict[str, object] = {
            "schema": "wellmanifest.git-lifecycle/v1",
            "kind": "transition-request",
            "requestId": "request:seed",
            "repositoryRef": "repository:demo",
            "ticket": "ticket-001",
            "action": "seed-baseline",
            "expectedState": "uninitialized",
            "targetState": "seeded",
            "authorizationRef": "authorization:session",
            "seedProfileRef": "seed-profile:governed",
            "evidenceRefs": ["artifact:intent"],
            "idempotencyKey": "idempotency:seed",
        }
        with self.assertRaises(conformance.ContractError):
            conformance.validate_request(
                {**base_req, "evidenceRefs": ["http://invalid"]}
            )
        with self.assertRaises(conformance.ContractError):
            conformance.validate_request(
                {**base_req, "evidenceRefs": [f"artifact:item-{i}" for i in range(17)]}
            )
        with self.assertRaises(conformance.ContractError):
            conformance.validate_request({**base_req, "ticket": 123})

        for py_path in ROOT.glob("*.py"):
            if py_path.name == "lifecycle.py":
                continue
            lines = len(py_path.read_text(encoding="utf-8").splitlines())
            self.assertLess(lines, 500, f"{py_path} has {lines} lines (>= 500)")


if __name__ == "__main__":
    unittest.main()
