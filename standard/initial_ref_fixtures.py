"""Fixtures and adversarial self-test suite for repository initial-ref conformance v1."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import lifecycle
from initial_ref_conformance import (
    DOCUMENT_SCHEMA,
    PROFILE_DIGEST,
    PROFILE_PATH,
    SCHEMA_DIGEST,
    SCHEMA_ID,
    SCHEMA_PATH,
    ContractError,
    digest,
    material_digest,
    plan_idempotency,
    validate_terminal,
)


def validate_schema_and_profile() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    variants = {
        "#/$defs/plan",
        "#/$defs/grantBinding",
        "#/$defs/publicationReceipt",
        "#/$defs/terminalReceipt",
    }
    if (
        schema.get("$id") != SCHEMA_ID
        or {item.get("$ref") for item in schema.get("oneOf", [])} != variants
    ):
        raise ContractError("initial-ref schema identity or variants are invalid")

    def require_closed(value: Any) -> None:
        if isinstance(value, dict):
            if (
                value.get("type") == "object"
                and value.get("additionalProperties") is not False
            ):
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
    if lifecycle.audit_path(PROFILE_PATH)["finding_count"] != 0:
        raise ContractError("initial-ref Lifecycle profile has compaction findings")
    model = report.lifecycles[0]
    transitions = {
        (item.source, item.target, item.event, item.evidence)
        for item in model.transitions
    }
    expected_graph = {
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
    if (
        model.name != "repository-initial-ref"
        or set(model.states)
        != {"REMOTE_EMPTY", "INITIAL_REF_PUBLISHED", "ACCEPTED", "QUARANTINED"}
        or model.summary()["initial_state"] != "REMOTE_EMPTY"
        or model.summary()["terminal_states"] != ["ACCEPTED", "QUARANTINED"]
        or transitions != expected_graph
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
        "secretScanEvidenceRef": "evidence:scan-evidence.pass",
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
            "credential-material-flag",
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
                docs,
                expiresAt=(now - timedelta(seconds=1)).isoformat(),
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
        rejected(
            "terminal-non-receipt-prefix",
            validate_terminal,
            documents,
            lambda docs: docs[3].update(receiptRef="plan:spoofed-terminal"),
            now=now,
        ),
        rejected(
            "terminal-reused-publication-ref",
            validate_terminal,
            documents,
            lambda docs: docs[3].update(receiptRef=docs[2]["receiptRef"]),
            now=now,
        ),
        rejected(
            "malformed-rfc3339-expiry",
            validate_terminal,
            documents,
            lambda docs: change_grant(docs, expiresAt="20260822T201000Z"),
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
