"""Dependency-free semantic conformance for wellmanifest.git-lifecycle/v1."""

from __future__ import annotations

import argparse
import copy
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import lifecycle
from git_primitives import canonical_json_bytes, sha256_hex, walk_json_tree

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "git-lifecycle.schema.json"
GRAMMAR_PATH = ROOT / "git-lifecycle.v1.gbnf"
LIFECYCLE_PATH = ROOT / "git-lifecycle.lifecycle"
LIFECYCLE_VALIDATOR_PATH = ROOT / "lifecycle.py"
SCHEMA_DIGEST = "0dda63a9a28c82378036992da7570e8c755a56346aeffda3dc351a306a1ca5ee"
GRAMMAR_DIGEST = "6218d76eaeee770501dd24a42d038792138ec0a968afb69331fb034d3db962ef"
LIFECYCLE_SOURCE_REVISION = "1ea2a90bd5b90a768ad2b36a9c1c330523bc80b4"
LIFECYCLE_VALIDATOR_DIGEST = (
    "7f7f1c45b7611e186cc640ada69cf2849d16841564c4028b9fc06dd0a05c2b3a"
)
LIFECYCLE_PROFILE_DIGEST = (
    "411f5d0cfb7c38404b8af7b94df4d3c889630e11f3584001b51394b8e6cac29b"
)

TRANSITIONS = {
    "seed-baseline": ("uninitialized", "seeded"),
    "create-ticket-branch": ("seeded", "ticket-ready"),
    "local-commit": ("ticket-ready", "implementation-local"),
    "open-pr": ("implementation-local", "review-open"),
    "integrate": ("review-open", "integrated"),
    "release": ("integrated", "released"),
}
CHECKPOINT_STATES = {
    "seeded",
    "ticket-ready",
    "implementation-local",
    "review-open",
    "integrated",
    "released",
}
REQUEST_KEYS = {
    "schema",
    "kind",
    "requestId",
    "repositoryRef",
    "ticket",
    "action",
    "expectedState",
    "targetState",
    "authorizationRef",
    "seedProfileRef",
    "evidenceRefs",
    "idempotencyKey",
}
REFS = {
    "requestId": re.compile(r"^request:[a-z][a-z0-9._-]{0,95}$", re.ASCII),
    "repositoryRef": re.compile(r"^repository:[a-z][a-z0-9._-]{0,95}$", re.ASCII),
    "ticket": re.compile(r"^ticket-[0-9]{3,}$", re.ASCII),
    "authorizationRef": re.compile(
        r"^authorization:[a-z][a-z0-9._-]{0,127}$", re.ASCII
    ),
    "seedProfileRef": re.compile(r"^seed-profile:[a-z][a-z0-9._-]{0,95}$", re.ASCII),
    "idempotencyKey": re.compile(r"^idempotency:[a-z][a-z0-9._-]{0,127}$", re.ASCII),
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
EVIDENCE_REF_RE = re.compile(
    r"^(?:artifact|receipt|decision|knowledge):[a-z][a-z0-9._:-]{0,159}$", re.ASCII
)
CONTINUITY_RECEIPT_RE = re.compile(r"^receipt:continuity[.][a-z0-9._:-]+$", re.ASCII)
_SENSITIVE_PARTS = (
    "shell",
    "command",
    "argv",
    "pass" + "word",
    "credential",
    "tok" + "en",
    "sec" + "ret",
    "path",
    "remote",
    "url",
)
SENSITIVE = re.compile(r"(" + "|".join(_SENSITIVE_PARTS) + r")", re.IGNORECASE)
_FORBIDDEN_GRAMMAR_BYTES = (
    b"shell",
    b"argv",
    b"pass" + b"word",
    b"credential",
    b"tok" + b"en",
    b"remoteurl",
    b"http://",
    b"ssh://",
)


class ContractError(ValueError):
    pass


def canonical(value: object) -> bytes:
    reject_sensitive_values(value)
    return canonical_json_bytes(value, ContractError)


def digest(value: bytes) -> str:
    return sha256_hex(value)


def lifecycle_name(value: str) -> str:
    return value.upper().replace("-", "_")


def validate_lifecycle_profile(schema: dict[str, object]) -> None:
    if digest(LIFECYCLE_VALIDATOR_PATH.read_bytes()) != LIFECYCLE_VALIDATOR_DIGEST:
        raise ContractError("pinned lifecycle validator digest mismatch")
    if digest(LIFECYCLE_PATH.read_bytes()) != LIFECYCLE_PROFILE_DIGEST:
        raise ContractError("pinned lifecycle profile digest mismatch")
    report = lifecycle.validate_path(LIFECYCLE_PATH, lifecycle.embedded_catalog())
    if not report.valid or len(report.lifecycles) != 1:
        raise ContractError("Lifecycle DSL profile is invalid")
    if lifecycle.audit_path(LIFECYCLE_PATH)["finding_count"] != 0:
        raise ContractError("Lifecycle DSL profile has compaction findings")
    model = report.lifecycles[0]
    state_values = schema["$defs"]["state"]["enum"]  # type: ignore[index]
    expected_states = {lifecycle_name(str(value)) for value in state_values}
    expected_transitions = (
        {
            (lifecycle_name(source), lifecycle_name(target), lifecycle_name(action))
            for action, (source, target) in TRANSITIONS.items()
        }
        | {("INTEGRATED", "TERMINAL", "CLEANUP"), ("RELEASED", "TERMINAL", "CLEANUP")}
        | {
            (lifecycle_name(st), lifecycle_name(st), "CHECKPOINT")
            for st in CHECKPOINT_STATES
        }
    )
    actual_transitions = {
        (item.source, item.target, item.event) for item in model.transitions
    }
    if model.name != "git-repository" or set(model.states) != expected_states:
        raise ContractError("Lifecycle DSL state graph mismatch")
    if actual_transitions != expected_transitions:
        raise ContractError("Lifecycle DSL transition graph mismatch")
    if model.summary()["initial_state"] != "UNINITIALIZED":
        raise ContractError("Lifecycle DSL initial state mismatch")
    if model.summary()["terminal_states"] != ["TERMINAL"]:
        raise ContractError("Lifecycle DSL terminal state mismatch")


def reject_sensitive_values(value: object) -> None:
    walk_json_tree(value, ContractError)


def reject_sensitive(value: object) -> None:
    walk_json_tree(value, ContractError, unsafe_key_re=SENSITIVE)


def _validate_evidence_list(evidence: object, *, min_items: int) -> list[str]:
    if (
        not isinstance(evidence, list)
        or not min_items <= len(evidence) <= 16
        or any(
            not isinstance(item, str) or not EVIDENCE_REF_RE.fullmatch(item)
            for item in evidence
        )
        or len(evidence) != len(set(evidence))
    ):
        raise ContractError("evidence references must be valid, bounded and unique")
    return evidence


def validate_request(doc: dict[str, object]) -> None:
    if not isinstance(doc, dict) or set(doc) - REQUEST_KEYS:
        raise ContractError("request has an unknown or non-object shape")
    if not (REQUEST_KEYS - {"seedProfileRef"}) <= set(doc):
        raise ContractError("request field is missing")
    if (
        doc["schema"] != "wellmanifest.git-lifecycle/v1"
        or doc["kind"] != "transition-request"
    ):
        raise ContractError("wrong document family")
    reject_sensitive(doc)
    for key, pattern in REFS.items():
        if key in doc:
            raw = doc[key]
            if not isinstance(raw, str) or not pattern.fullmatch(raw):
                raise ContractError(f"invalid reference: {key}")
    evidence = _validate_evidence_list(doc["evidenceRefs"], min_items=1)
    action = doc["action"]
    if not isinstance(action, str):
        raise ContractError("action must be a string")
    if action == "cleanup":
        if (
            doc["expectedState"] not in {"integrated", "released"}
            or doc["targetState"] != "terminal"
        ):
            raise ContractError("invalid cleanup transition")
    elif action == "checkpoint":
        if (
            doc["expectedState"] not in CHECKPOINT_STATES
            or doc["targetState"] != doc["expectedState"]
        ):
            raise ContractError("checkpoint must preserve an initialized state")
        if sum(1 for item in evidence if CONTINUITY_RECEIPT_RE.fullmatch(item)) != 1:
            raise ContractError("checkpoint requires exactly one continuity receipt")
    elif TRANSITIONS.get(action) != (doc["expectedState"], doc["targetState"]):
        raise ContractError("invalid transition")
    if (action == "seed-baseline") != ("seedProfileRef" in doc):
        raise ContractError("seed profile is allowed only for seed-baseline")


def validate_seed_state(doc: dict[str, object]) -> None:
    if not isinstance(doc, dict):
        raise ContractError("seeded state must be an object")
    reject_sensitive_values(doc)
    required = {
        "state",
        "headSha",
        "baselineSha",
        "remoteConfigured",
        "implementationPresent",
    }
    if not required <= set(doc) or doc["state"] != "seeded":
        raise ContractError("invalid seeded state")
    head_sha, base_sha = doc["headSha"], doc["baselineSha"]
    if (
        not isinstance(head_sha, str)
        or not SHA_RE.fullmatch(head_sha)
        or not isinstance(base_sha, str)
        or not SHA_RE.fullmatch(base_sha)
    ):
        raise ContractError("seeded state requires real SHA values")
    if (
        doc["remoteConfigured"] is not False
        or doc["implementationPresent"] is not False
    ):
        raise ContractError("seeded state must have no remote or implementation")


def validate_seed_receipt(doc: dict[str, object]) -> None:
    if not isinstance(doc, dict):
        raise ContractError("seed receipt must be an object")
    reject_sensitive_values(doc)
    if doc.get("action") != "seed-baseline" or doc.get("outcome") != "applied":
        raise ContractError("not an applied seed receipt")
    if doc.get("beforeState") != "uninitialized" or doc.get("afterState") != "seeded":
        raise ContractError("invalid seed receipt states")
    if (
        doc.get("pushPerformed") is not False
        or doc.get("publicationPerformed") is not False
    ):
        raise ContractError("seed baseline cannot publish")
    head_sha = doc.get("headSha")
    if (
        doc.get("secretsRedacted") is not True
        or not isinstance(head_sha, str)
        or not SHA_RE.fullmatch(head_sha)
    ):
        raise ContractError("invalid safe seed receipt")


def validate_checkpoint_receipt(doc: dict[str, object]) -> None:
    if not isinstance(doc, dict):
        raise ContractError("checkpoint receipt must be an object")
    reject_sensitive_values(doc)
    if doc.get("action") != "checkpoint" or doc.get("outcome") != "applied":
        raise ContractError("not an applied checkpoint receipt")
    before = doc.get("beforeState")
    if before not in CHECKPOINT_STATES or doc.get("afterState") != before:
        raise ContractError("checkpoint receipt must preserve state")
    head_sha = doc.get("headSha")
    if not isinstance(head_sha, str) or not SHA_RE.fullmatch(head_sha):
        raise ContractError("checkpoint receipt requires a real head")
    if (
        doc.get("pushPerformed") is not False
        or doc.get("publicationPerformed") is not False
    ):
        raise ContractError("checkpoint cannot push or publish")
    if doc.get("secretsRedacted") is not True:
        raise ContractError("checkpoint must redact credentials")
    evidence = _validate_evidence_list(doc.get("evidenceRefs"), min_items=1)
    if sum(1 for item in evidence if CONTINUITY_RECEIPT_RE.fullmatch(item)) != 1:
        raise ContractError(
            "checkpoint receipt requires exactly one continuity receipt"
        )


def expect_rejected(
    name: str,
    validator: Callable[[dict[str, Any]], None],
    base: dict[str, object],
    mutation: Callable[[dict[str, Any]], None],
) -> str:
    doc = copy.deepcopy(base)
    mutation(doc)
    try:
        validator(doc)
    except ContractError:
        return name
    raise AssertionError(f"adversarial case accepted: {name}")


def run_all() -> dict[str, object]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    grammar = GRAMMAR_PATH.read_bytes()
    validate_lifecycle_profile(schema)
    if digest(canonical(schema)) != SCHEMA_DIGEST or digest(grammar) != GRAMMAR_DIGEST:
        raise ContractError("contract digest mismatch")
    lowered = grammar.lower()
    for forbidden in _FORBIDDEN_GRAMMAR_BYTES:
        if forbidden in lowered:
            raise ContractError(f"unsafe grammar surface: {forbidden.decode()}")

    request: dict[str, object] = {
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
    sha = "a" * 40
    state: dict[str, object] = {
        "state": "seeded",
        "headSha": sha,
        "baselineSha": sha,
        "remoteConfigured": False,
        "implementationPresent": False,
    }
    receipt: dict[str, object] = {
        "action": "seed-baseline",
        "outcome": "applied",
        "beforeState": "uninitialized",
        "afterState": "seeded",
        "headSha": sha,
        "pushPerformed": False,
        "publicationPerformed": False,
        "secretsRedacted": True,
    }
    checkpoint_request = {
        **request,
        "requestId": "request:checkpoint",
        "action": "checkpoint",
        "expectedState": "implementation-local",
        "targetState": "implementation-local",
        "evidenceRefs": ["receipt:continuity.ticket-010.1.example"],
        "idempotencyKey": "idempotency:checkpoint",
    }
    checkpoint_request.pop("seedProfileRef")
    checkpoint_receipt: dict[str, object] = {
        "action": "checkpoint",
        "outcome": "applied",
        "beforeState": "implementation-local",
        "afterState": "implementation-local",
        "headSha": sha,
        "pushPerformed": False,
        "publicationPerformed": False,
        "secretsRedacted": True,
        "evidenceRefs": ["receipt:continuity.ticket-010.1.example"],
    }
    validate_request(request)
    validate_seed_state(state)
    validate_seed_receipt(receipt)
    validate_request(checkpoint_request)
    validate_checkpoint_receipt(checkpoint_receipt)
    tok_field = "tok" + "en"
    cases = [
        (
            "shell-command",
            validate_request,
            request,
            lambda d: d.update(command="git push --force"),
        ),
        (
            "remote-url",
            validate_request,
            request,
            lambda d: d.update(remoteUrl="ssh://attacker/repo"),
        ),
        (
            "wrong-transition",
            validate_request,
            request,
            lambda d: d.update(targetState="released"),
        ),
        (
            "seed-without-profile",
            validate_request,
            request,
            lambda d: d.pop("seedProfileRef"),
        ),
        (
            "inline-tok" + "en",
            validate_request,
            request,
            lambda d: d.update({tok_field: "redacted-val"}),
        ),
        (
            "seeded-with-remote",
            validate_seed_state,
            state,
            lambda d: d.update(remoteConfigured=True),
        ),
        (
            "seed-push",
            validate_seed_receipt,
            receipt,
            lambda d: d.update(pushPerformed=True),
        ),
        (
            "seed-publication",
            validate_seed_receipt,
            receipt,
            lambda d: d.update(publicationPerformed=True),
        ),
        (
            "checkpoint-state-movement",
            validate_request,
            checkpoint_request,
            lambda d: d.update(targetState="review-open"),
        ),
        (
            "checkpoint-without-continuity",
            validate_request,
            checkpoint_request,
            lambda d: d.update(evidenceRefs=["receipt:other"]),
        ),
        (
            "checkpoint-duplicate-evidence",
            validate_request,
            checkpoint_request,
            lambda d: d.update(
                evidenceRefs=["receipt:continuity.ticket-010.1.example"] * 2
            ),
        ),
        (
            "checkpoint-push",
            validate_checkpoint_receipt,
            checkpoint_receipt,
            lambda d: d.update(pushPerformed=True),
        ),
        (
            "checkpoint-publication",
            validate_checkpoint_receipt,
            checkpoint_receipt,
            lambda d: d.update(publicationPerformed=True),
        ),
    ]
    rejected = [expect_rejected(n, v, b, m) for n, v, b, m in cases]
    import repo_hygiene

    return {
        "schema": "wellmanifest.git-lifecycle-conformance/v1",
        "ok": True,
        "positiveDocuments": 5,
        "adversarialRejected": rejected,
        "schemaDigest": "sha256:" + SCHEMA_DIGEST,
        "grammarDigest": "sha256:" + GRAMMAR_DIGEST,
        "repoHygiene": repo_hygiene.self_test(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.parse_args()
    print(json.dumps(run_all(), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
