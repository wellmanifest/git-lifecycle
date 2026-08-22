#!/usr/bin/env python3
"""Dependency-free conformance for repository initial-ref handoffs v1."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import lifecycle


ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "repository-initial-ref.schema.json"
PROFILE_PATH = ROOT / "repository-initial-ref.lifecycle"
SCHEMA_ID = "https://wellmanifest.dev/schemas/repository-initial-ref/v1"
DOCUMENT_SCHEMA = "wellmanifest.repository-initial-ref/v1"
SCHEMA_DIGEST = "b2aa4920f9e1e1370f9eca2a6048ac1a8c9a63cc9c87195918150ef7d2745527"
PROFILE_DIGEST = "7ac49adfb92dac1d03e10efb382290e0e08c367b5ec655933d12db30803dbe2c"

SHA = re.compile(r"^[a-f0-9]{40}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
REPOSITORY_REF = re.compile(r"^repository:[a-z][a-z0-9._-]{0,95}$")
BRANCH_REF = re.compile(r"^branch:[a-z][a-z0-9._-]{0,95}$")
DOCUMENT_REF = re.compile(
    r"^(?:plan|grant|receipt|validation):[a-z][a-z0-9._-]{0,127}$"
)
EVIDENCE_REF = re.compile(
    r"^(?:artifact|evidence|profile|receipt):[a-z][a-z0-9._:-]{0,159}$"
)
ACTOR_REF = re.compile(r"^agent:[a-z][a-z0-9._-]{0,127}$")
UNSAFE_KEYS = re.compile(r"(?:command|remoteurl|credential|password|token|shell|argv)", re.I)
UNSAFE_TEXT = re.compile(r"(?:https?://|ssh://|-----BEGIN|bearer\s)", re.I)

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
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


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
    if isinstance(value, dict):
        for key, child in value.items():
            if UNSAFE_KEYS.search(key):
                raise ContractError(f"unsafe field: {key}")
            reject_unsafe(child)
    elif isinstance(value, list):
        for child in value:
            reject_unsafe(child)
    elif isinstance(value, str) and UNSAFE_TEXT.search(value):
        raise ContractError("transport or secret material is forbidden")


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
    for field in ("sourceTreeDigest", "allowlistDigest", "idempotencyKey", "planDigest"):
        text(value[field], SHA256, field)
    for field in (
        "secretScanEvidenceRef",
        "governanceEvidenceRef",
        "validationProfileRef",
    ):
        text(value[field], EVIDENCE_REF, field)
    if len(
        {
            value["secretScanEvidenceRef"],
            value["governanceEvidenceRef"],
            value["validationProfileRef"],
        }
    ) != 3:
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
    for field in (
        "grantDigest",
        "planDigest",
        "sourceTreeDigest",
        "allowlistDigest",
    ):
        text(value[field], SHA256, field)
    if value["grantDigest"] != material_digest(value, "grantDigest"):
        raise ContractError("initial-ref grant digest mismatch")
    try:
        expires_at = datetime.fromisoformat(value["expiresAt"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ContractError("initial-ref grant expiry is invalid") from exc
    if expires_at.tzinfo is None or expires_at <= (now or datetime.now(UTC)):
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
    if any(receipt[field] != expected_value for field, expected_value in expected.items()):
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
    text(terminal["publicationReceiptRef"], DOCUMENT_REF, "publication receipt reference")
    text(terminal["validatorRef"], ACTOR_REF, "validator reference")
    text(terminal["validationEvidenceRef"], EVIDENCE_REF, "validation evidence")
    evidence_refs(terminal["evidenceRefs"])
    for field in ("publicationReceiptDigest", "planDigest", "treeDigest"):
        text(terminal[field], SHA256, field)
    text(terminal["headSha"], SHA, "validated head")
    if terminal["validationOutcome"] not in {"approved", "rejected"}:
        raise ContractError("initial-ref validation outcome is invalid")
    expected_state = "accepted" if terminal["validationOutcome"] == "approved" else "quarantined"
    if terminal["state"] != expected_state:
        raise ContractError("initial-ref terminal state differs from Validator outcome")
    if terminal["validatorRef"] == grant["issuedByRef"]:
        raise ContractError("initial-ref Validator is not independent from grant issuer")
    expected = {
        "publicationReceiptRef": publication["receiptRef"],
        "publicationReceiptDigest": digest(publication),
        "planDigest": plan["planDigest"],
        "repositoryRef": plan["repositoryRef"],
        "targetBranchRef": plan["targetBranchRef"],
        "headSha": publication["headSha"],
        "treeDigest": publication["treeDigest"],
    }
    if any(terminal[field] != expected_value for field, expected_value in expected.items()):
        raise ContractError("Validator receipt differs from published initial ref")
    reject_unsafe(terminal)
    return terminal


def validate_schema_and_profile() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if schema.get("$id") != SCHEMA_ID or {
        item.get("$ref") for item in schema.get("oneOf", [])
    } != {
        "#/$defs/plan",
        "#/$defs/grantBinding",
        "#/$defs/publicationReceipt",
        "#/$defs/terminalReceipt",
    }:
        raise ContractError("initial-ref schema identity or variants are invalid")

    def require_closed(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object" and value.get("additionalProperties") is not False:
                raise ContractError("initial-ref schema contains an open object")
            for child in value.values():
                require_closed(child)
        elif isinstance(value, list):
            for child in value:
                require_closed(child)

    require_closed(schema)
    if digest(schema) != SCHEMA_DIGEST:
        raise ContractError("initial-ref schema digest mismatch")
    if hashlib.sha256(PROFILE_PATH.read_bytes()).hexdigest() != PROFILE_DIGEST:
        raise ContractError("initial-ref Lifecycle profile digest mismatch")
    report = lifecycle.validate_path(PROFILE_PATH, lifecycle.embedded_catalog())
    if not report.valid or len(report.lifecycles) != 1:
        raise ContractError("initial-ref Lifecycle profile is invalid")
    model = report.lifecycles[0]
    transitions = {(item.source, item.target, item.event, item.evidence) for item in model.transitions}
    if (
        model.name != "repository-initial-ref"
        or set(model.states) != {"REMOTE_EMPTY", "INITIAL_REF_PUBLISHED", "ACCEPTED", "QUARANTINED"}
        or model.summary()["initial_state"] != "REMOTE_EMPTY"
        or model.summary()["terminal_states"] != ["ACCEPTED", "QUARANTINED"]
        or transitions
        != {
            (
                "REMOTE_EMPTY",
                "INITIAL_REF_PUBLISHED",
                "PUBLISH_INITIAL_REF",
                "DIGEST_BOUND_SINGLE_USE_GRANT",
            ),
            (
                "INITIAL_REF_PUBLISHED",
                "ACCEPTED",
                "VALIDATE_INITIAL_REF",
                "INDEPENDENT_EXACT_HEAD_VALIDATION",
            ),
            (
                "INITIAL_REF_PUBLISHED",
                "QUARANTINED",
                "REJECT_INITIAL_REF",
                "INDEPENDENT_REJECTION_EVIDENCE",
            ),
        }
    ):
        raise ContractError("initial-ref Lifecycle state graph mismatch")


def rejected(
    name: str,
    validator: Callable[..., Any],
    documents: list[dict[str, Any]],
    mutation: Callable[[list[dict[str, Any]]], None],
    *,
    now: datetime,
) -> str:
    candidate = copy.deepcopy(documents)
    mutation(candidate)
    try:
        validator(*candidate, now=now)
    except ContractError:
        return name
    raise AssertionError(f"adversarial initial-ref case accepted: {name}")


def change_grant(documents: list[dict[str, Any]], **updates: Any) -> None:
    documents[1].update(updates)
    documents[1]["grantDigest"] = material_digest(documents[1], "grantDigest")


def fixtures(now: datetime) -> tuple[dict[str, Any], ...]:
    plan = {
        "schema": DOCUMENT_SCHEMA,
        "kind": "plan",
        "planId": "plan:process-identity-seed",
        "operationId": "repository:initial-ref",
        "repositoryRef": "repository:subactor.process-identity",
        "expectedRemoteState": "empty-no-refs",
        "targetBranchRef": "branch:main",
        "sourceCommitSha": "a" * 40,
        "sourceTreeDigest": "b" * 64,
        "allowlistDigest": "c" * 64,
        "secretScanEvidenceRef": "evidence:secret-scan.pass",
        "governanceEvidenceRef": "evidence:governance.pass",
        "validationProfileRef": "profile:node-library.v1",
        "idempotencyKey": "",
        "planDigest": "",
        "llmAuthority": "propose-only",
    }
    plan["idempotencyKey"] = plan_idempotency(plan)
    plan["planDigest"] = material_digest(plan, "planDigest")
    grant = {
        "schema": DOCUMENT_SCHEMA,
        "kind": "grant-binding",
        "grantRef": "grant:process-identity-seed",
        "grantDigest": "",
        "planDigest": plan["planDigest"],
        "operationId": plan["operationId"],
        "repositoryRef": plan["repositoryRef"],
        "targetBranchRef": plan["targetBranchRef"],
        "sourceCommitSha": plan["sourceCommitSha"],
        "sourceTreeDigest": plan["sourceTreeDigest"],
        "allowlistDigest": plan["allowlistDigest"],
        "authorizedEffect": "initial-ref-publish",
        "issuedByRef": "agent:authority-controller",
        "expiresAt": (now + timedelta(minutes=10)).isoformat(),
        "singleUse": True,
        "inheritedAuthority": False,
    }
    grant["grantDigest"] = material_digest(grant, "grantDigest")
    publication = {
        "schema": DOCUMENT_SCHEMA,
        "kind": "publication-receipt",
        "receiptRef": "receipt:process-identity-publication",
        "planDigest": plan["planDigest"],
        "grantRef": grant["grantRef"],
        "grantDigest": grant["grantDigest"],
        "repositoryRef": plan["repositoryRef"],
        "targetBranchRef": plan["targetBranchRef"],
        "beforeState": "empty-no-refs",
        "afterState": "initial-ref-published",
        "headSha": plan["sourceCommitSha"],
        "treeDigest": plan["sourceTreeDigest"],
        "refCountBefore": 0,
        "refCountAfter": 1,
        "pushPerformed": True,
        "forceUsed": False,
        "readBack": True,
        "validationRequired": True,
        "evidenceRefs": ["evidence:provider-readback.initial-ref"],
        "terminal": False,
        "secretMaterialIncluded": False,
    }
    terminal = {
        "schema": DOCUMENT_SCHEMA,
        "kind": "terminal-receipt",
        "receiptRef": "receipt:process-identity-accepted",
        "publicationReceiptRef": publication["receiptRef"],
        "publicationReceiptDigest": digest(publication),
        "planDigest": plan["planDigest"],
        "repositoryRef": plan["repositoryRef"],
        "targetBranchRef": plan["targetBranchRef"],
        "state": "accepted",
        "headSha": publication["headSha"],
        "treeDigest": publication["treeDigest"],
        "validatorRef": "agent:validator-agent",
        "validationEvidenceRef": "evidence:validator.exact-head",
        "validationOutcome": "approved",
        "readBack": True,
        "automaticRefDeletion": False,
        "forceUsed": False,
        "evidenceRefs": ["evidence:validator.exact-head"],
        "terminal": True,
        "secretMaterialIncluded": False,
    }
    return plan, grant, publication, terminal


def run_all() -> dict[str, Any]:
    validate_schema_and_profile()
    now = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    plan, grant, publication, terminal = fixtures(now)
    validate_terminal(plan, grant, publication, terminal, now=now)
    documents = [plan, grant, publication, terminal]
    cases = [
        rejected(
            "authority-inheritance",
            validate_terminal,
            documents,
            lambda docs: change_grant(docs, inheritedAuthority=True),
            now=now,
        ),
        rejected(
            "grant-plan-substitution",
            validate_terminal,
            documents,
            lambda docs: change_grant(docs, planDigest="d" * 64),
            now=now,
        ),
        rejected(
            "remote-not-empty",
            validate_terminal,
            documents,
            lambda docs: docs[2].update(refCountBefore=1),
            now=now,
        ),
        rejected(
            "force-update",
            validate_terminal,
            documents,
            lambda docs: docs[2].update(forceUsed=True),
            now=now,
        ),
        rejected(
            "substituted-tree",
            validate_terminal,
            documents,
            lambda docs: docs[2].update(treeDigest="d" * 64),
            now=now,
        ),
        rejected(
            "self-validation",
            validate_terminal,
            documents,
            lambda docs: docs[3].update(validatorRef=docs[1]["issuedByRef"]),
            now=now,
        ),
        rejected(
            "automatic-ref-deletion",
            validate_terminal,
            documents,
            lambda docs: docs[3].update(automaticRefDeletion=True),
            now=now,
        ),
        rejected(
            "secret-material",
            validate_terminal,
            documents,
            lambda docs: docs[2].update(secretMaterialIncluded=True),
            now=now,
        ),
        rejected(
            "expired-grant",
            validate_terminal,
            documents,
            lambda docs: change_grant(
                docs, expiresAt=(now - timedelta(seconds=1)).isoformat()
            ),
            now=now,
        ),
        rejected(
            "remote-url-field",
            validate_terminal,
            documents,
            lambda docs: docs[0].update(remoteUrl="ssh://provider/repository"),
            now=now,
        ),
    ]
    rejected_terminal = copy.deepcopy(documents)
    rejected_terminal[3].update(
        state="quarantined",
        validationOutcome="rejected",
        receiptRef="receipt:process-identity-quarantined",
    )
    validate_terminal(*rejected_terminal, now=now)
    return {
        "schema": "wellmanifest.repository-initial-ref-conformance/v1",
        "ok": True,
        "positiveFlows": ["accepted", "quarantined-no-delete"],
        "adversarialRejected": cases,
        "schemaDigest": "sha256:" + SCHEMA_DIGEST,
        "profileDigest": "sha256:" + PROFILE_DIGEST,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.parse_args()
    print(json.dumps(run_all(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
