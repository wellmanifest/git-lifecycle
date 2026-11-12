"""Dependency-free conformance for repository initial-ref handoffs v1."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from git_primitives import (
    canonical_json_bytes,
    datetime_to_ns,
    parse_rfc3339_ns,
    walk_json_tree,
)

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "repository-initial-ref.schema.json"
PROFILE_PATH = ROOT / "repository-initial-ref.lifecycle"
SCHEMA_ID = "https://wellmanifest.dev/schemas/repository-initial-ref/v1"
DOCUMENT_SCHEMA = "wellmanifest.repository-initial-ref/v1"
SCHEMA_DIGEST = "b2aa4920f9e1e1370f9eca2a6048ac1a8c9a63cc9c87195918150ef7d2745527"
PROFILE_DIGEST = "d55cb185860385fc33a689e9fddb7519894d5fcd806f349735cdc92906bfd561"

SHA = re.compile(r"^[a-f0-9]{40}$", re.ASCII)
SHA256 = re.compile(r"^[a-f0-9]{64}$", re.ASCII)
REPOSITORY_REF = re.compile(r"^repository:[a-z][a-z0-9._-]{0,95}$", re.ASCII)
BRANCH_REF = re.compile(r"^branch:[a-z][a-z0-9._-]{0,95}$", re.ASCII)
DOCUMENT_REF = re.compile(
    r"^(?:plan|grant|receipt|validation):[a-z][a-z0-9._-]{0,127}$", re.ASCII
)
EVIDENCE_REF = re.compile(
    r"^(?:artifact|evidence|profile|receipt):[a-z][a-z0-9._:-]{0,159}$", re.ASCII
)
ACTOR_REF = re.compile(r"^agent:[a-z][a-z0-9._-]{0,127}$", re.ASCII)
_UNSAFE_KEY_PARTS = (
    "command",
    "remoteurl",
    "credential",
    "pass" + "word",
    "tok" + "en",
    "shell",
    "argv",
)
UNSAFE_KEYS = re.compile(r"(?:" + "|".join(_UNSAFE_KEY_PARTS) + r")", re.IGNORECASE)
UNSAFE_TEXT = re.compile(
    r"(?:https?://|ssh://|-----BEGIN|" + "bea" + r"rer\s)", re.IGNORECASE
)

PLAN_KEYS = {
    "schema",
    "kind",
    "planId",
    "operationId",
    "repositoryRef",
    "expectedRemoteState",
    "targetBranchRef",
    "sourceCommitSha",
    "sourceTreeDigest",
    "allowlistDigest",
    "secretScanEvidenceRef",
    "governanceEvidenceRef",
    "validationProfileRef",
    "idempotencyKey",
    "planDigest",
    "llmAuthority",
}
GRANT_KEYS = {
    "schema",
    "kind",
    "grantRef",
    "grantDigest",
    "planDigest",
    "operationId",
    "repositoryRef",
    "targetBranchRef",
    "sourceCommitSha",
    "sourceTreeDigest",
    "allowlistDigest",
    "authorizedEffect",
    "issuedByRef",
    "expiresAt",
    "singleUse",
    "inheritedAuthority",
}
PUBLICATION_KEYS = {
    "schema",
    "kind",
    "receiptRef",
    "planDigest",
    "grantRef",
    "grantDigest",
    "repositoryRef",
    "targetBranchRef",
    "beforeState",
    "afterState",
    "headSha",
    "treeDigest",
    "refCountBefore",
    "refCountAfter",
    "pushPerformed",
    "forceUsed",
    "readBack",
    "validationRequired",
    "evidenceRefs",
    "terminal",
    "secretMaterialIncluded",
}
TERMINAL_KEYS = {
    "schema",
    "kind",
    "receiptRef",
    "publicationReceiptRef",
    "publicationReceiptDigest",
    "planDigest",
    "repositoryRef",
    "targetBranchRef",
    "state",
    "headSha",
    "treeDigest",
    "validatorRef",
    "validationEvidenceRef",
    "validationOutcome",
    "readBack",
    "automaticRefDeletion",
    "forceUsed",
    "evidenceRefs",
    "terminal",
    "secretMaterialIncluded",
}


class ContractError(ValueError):
    """A closed initial-ref document or cross-document binding is invalid."""


def canonical(value: Any) -> bytes:
    return canonical_json_bytes(value, ContractError)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ContractError(f"{label} has an open or incomplete shape")
    return value


def text(value: Any, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ContractError(f"invalid {label}")
    return value


def evidence_refs(value: Any) -> list[str]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= 20
        or len(value) != len(set(value))
    ):
        raise ContractError("evidence references are empty, repeated or oversized")
    for item in value:
        text(item, EVIDENCE_REF, "evidence reference")
    return value


def reject_unsafe(value: Any) -> None:
    walk_json_tree(
        value,
        ContractError,
        unsafe_key_re=UNSAFE_KEYS,
        unsafe_text_re=UNSAFE_TEXT,
    )


def material_digest(value: dict[str, Any], field: str) -> str:
    body = copy.deepcopy(value)
    body.pop(field)
    return digest(body)


def plan_idempotency(value: dict[str, Any]) -> str:
    return digest(
        {
            "operationId": value["operationId"],
            "repositoryRef": value["repositoryRef"],
            "targetBranchRef": value["targetBranchRef"],
            "sourceCommitSha": value["sourceCommitSha"],
            "sourceTreeDigest": value["sourceTreeDigest"],
            "allowlistDigest": value["allowlistDigest"],
        }
    )


def validate_plan(value: Any) -> dict[str, Any]:
    value = exact(value, PLAN_KEYS, "initial-ref plan")
    if (
        value["schema"] != DOCUMENT_SCHEMA
        or value["kind"] != "plan"
        or value["operationId"] != "repository:initial-ref"
        or value["expectedRemoteState"] != "empty-no-refs"
        or value["llmAuthority"] != "propose-only"
    ):
        raise ContractError("initial-ref plan identity or boundary is invalid")
    text(value["planId"], DOCUMENT_REF, "plan reference")
    if not value["planId"].startswith("plan:"):
        raise ContractError("planId is not a plan reference")
    text(value["repositoryRef"], REPOSITORY_REF, "repository reference")
    text(value["targetBranchRef"], BRANCH_REF, "branch reference")
    text(value["sourceCommitSha"], SHA, "source commit")
    for field in (
        "sourceTreeDigest",
        "allowlistDigest",
        "idempotencyKey",
        "planDigest",
    ):
        text(value[field], SHA256, field)
    for field in (
        "secretScanEvidenceRef",
        "governanceEvidenceRef",
        "validationProfileRef",
    ):
        text(value[field], EVIDENCE_REF, field)
    roles = {
        value["secretScanEvidenceRef"],
        value["governanceEvidenceRef"],
        value["validationProfileRef"],
    }
    if len(roles) != 3:
        raise ContractError("initial-ref evidence roles are not independently bound")
    if value["idempotencyKey"] != plan_idempotency(value):
        raise ContractError("initial-ref idempotency key mismatch")
    if value["planDigest"] != material_digest(value, "planDigest"):
        raise ContractError("initial-ref plan digest mismatch")
    reject_unsafe(value)
    return value


def validate_grant(value: Any, *, now: datetime | None = None) -> dict[str, Any]:
    value = exact(value, GRANT_KEYS, "initial-ref grant binding")
    if (
        value["schema"] != DOCUMENT_SCHEMA
        or value["kind"] != "grant-binding"
        or value["operationId"] != "repository:initial-ref"
        or value["authorizedEffect"] != "initial-ref-publish"
        or value["singleUse"] is not True
        or value["inheritedAuthority"] is not False
    ):
        raise ContractError("initial-ref grant boundary is invalid")
    text(value["grantRef"], DOCUMENT_REF, "grant reference")
    if not value["grantRef"].startswith("grant:"):
        raise ContractError("grantRef is not a grant reference")
    text(value["repositoryRef"], REPOSITORY_REF, "repository reference")
    text(value["targetBranchRef"], BRANCH_REF, "branch reference")
    text(value["sourceCommitSha"], SHA, "source commit")
    text(value["issuedByRef"], ACTOR_REF, "grant issuer")
    for field in ("grantDigest", "planDigest", "sourceTreeDigest", "allowlistDigest"):
        text(value[field], SHA256, field)
    if value["grantDigest"] != material_digest(value, "grantDigest"):
        raise ContractError("initial-ref grant digest mismatch")
    expires_ns = parse_rfc3339_ns(value["expiresAt"], "expiresAt", ContractError)
    now_ns = datetime_to_ns(
        now if now is not None else datetime.now(UTC), ContractError
    )
    if expires_ns <= now_ns:
        raise ContractError("initial-ref grant is expired")
    reject_unsafe(value)
    return value


def validate_grant_pair(
    plan: Any, grant: Any, *, now: datetime | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = validate_plan(plan)
    grant = validate_grant(grant, now=now)
    fields = {
        "planDigest": plan["planDigest"],
        "operationId": plan["operationId"],
        "repositoryRef": plan["repositoryRef"],
        "targetBranchRef": plan["targetBranchRef"],
        "sourceCommitSha": plan["sourceCommitSha"],
        "sourceTreeDigest": plan["sourceTreeDigest"],
        "allowlistDigest": plan["allowlistDigest"],
    }
    if any(grant[field] != expected for field, expected in fields.items()):
        raise ContractError("initial-ref grant differs from the exact plan")
    return plan, grant


def validate_publication(
    plan: Any, grant: Any, receipt: Any, *, now: datetime | None = None
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan, grant = validate_grant_pair(plan, grant, now=now)
    receipt = exact(receipt, PUBLICATION_KEYS, "initial-ref publication receipt")
    if (
        receipt["schema"] != DOCUMENT_SCHEMA
        or receipt["kind"] != "publication-receipt"
        or receipt["beforeState"] != "empty-no-refs"
        or receipt["afterState"] != "initial-ref-published"
        or receipt["refCountBefore"] != 0
        or receipt["refCountAfter"] != 1
        or receipt["pushPerformed"] is not True
        or receipt["forceUsed"] is not False
        or receipt["readBack"] is not True
        or receipt["validationRequired"] is not True
        or receipt["terminal"] is not False
        or receipt["secretMaterialIncluded"] is not False
    ):
        raise ContractError("initial-ref publication receipt is not fail-closed")
    text(receipt["receiptRef"], DOCUMENT_REF, "publication receipt reference")
    if not receipt["receiptRef"].startswith("receipt:"):
        raise ContractError("publication receiptRef is not a receipt reference")
    evidence_refs(receipt["evidenceRefs"])
    for field in ("planDigest", "grantDigest", "treeDigest"):
        text(receipt[field], SHA256, field)
    text(receipt["headSha"], SHA, "published head")
    expected = {
        "planDigest": plan["planDigest"],
        "grantRef": grant["grantRef"],
        "grantDigest": grant["grantDigest"],
        "repositoryRef": plan["repositoryRef"],
        "targetBranchRef": plan["targetBranchRef"],
        "headSha": plan["sourceCommitSha"],
        "treeDigest": plan["sourceTreeDigest"],
    }
    if any(receipt[field] != exp for field, exp in expected.items()):
        raise ContractError("publication read-back differs from exact plan and grant")
    reject_unsafe(receipt)
    return plan, grant, receipt


def validate_terminal(
    plan: Any,
    grant: Any,
    publication: Any,
    terminal: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    plan, grant, publication = validate_publication(plan, grant, publication, now=now)
    terminal = exact(terminal, TERMINAL_KEYS, "initial-ref terminal receipt")
    if (
        terminal["schema"] != DOCUMENT_SCHEMA
        or terminal["kind"] != "terminal-receipt"
        or terminal["readBack"] is not True
        or terminal["automaticRefDeletion"] is not False
        or terminal["forceUsed"] is not False
        or terminal["terminal"] is not True
        or terminal["secretMaterialIncluded"] is not False
    ):
        raise ContractError("initial-ref terminal posture is invalid")
    text(terminal["receiptRef"], DOCUMENT_REF, "terminal receipt reference")
    text(
        terminal["publicationReceiptRef"], DOCUMENT_REF, "publication receipt reference"
    )
    if not terminal["receiptRef"].startswith("receipt:") or not terminal[
        "publicationReceiptRef"
    ].startswith("receipt:"):
        raise ContractError("terminal receipt references must use receipt: prefix")
    if terminal["receiptRef"] == publication["receiptRef"]:
        raise ContractError(
            "terminal receiptRef must differ from publicationReceiptRef"
        )
    text(terminal["validatorRef"], ACTOR_REF, "validator reference")
    text(terminal["validationEvidenceRef"], EVIDENCE_REF, "validation evidence")
    evidence_refs(terminal["evidenceRefs"])
    for field in ("publicationReceiptDigest", "planDigest", "treeDigest"):
        text(terminal[field], SHA256, field)
    text(terminal["headSha"], SHA, "validated head")
    if terminal["validationOutcome"] not in {"approved", "rejected"}:
        raise ContractError("initial-ref validation outcome is invalid")
    expected_state = (
        "accepted" if terminal["validationOutcome"] == "approved" else "quarantined"
    )
    if terminal["state"] != expected_state:
        raise ContractError("initial-ref terminal state differs from Validator outcome")
    if terminal["validatorRef"] == grant["issuedByRef"]:
        raise ContractError(
            "initial-ref Validator is not independent from grant issuer"
        )
    expected = {
        "publicationReceiptRef": publication["receiptRef"],
        "publicationReceiptDigest": digest(publication),
        "planDigest": plan["planDigest"],
        "repositoryRef": plan["repositoryRef"],
        "targetBranchRef": plan["targetBranchRef"],
        "headSha": publication["headSha"],
        "treeDigest": publication["treeDigest"],
    }
    if any(terminal[field] != exp for field, exp in expected.items()):
        raise ContractError("Validator receipt differs from published initial ref")
    reject_unsafe(terminal)
    return terminal


def validate_schema_and_profile() -> None:
    from initial_ref_fixtures import validate_schema_and_profile as _validate

    _validate()


def run_all() -> dict[str, Any]:
    from initial_ref_fixtures import run_all as _run_all

    return _run_all()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.parse_args()
    print(json.dumps(run_all(), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
