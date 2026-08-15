#!/usr/bin/env python3
"""Dependency-free semantic conformance for wellmanifest.git-lifecycle/v1."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

import lifecycle

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "git-lifecycle.schema.json"
GRAMMAR_PATH = ROOT / "git-lifecycle.v1.gbnf"
LIFECYCLE_PATH = ROOT / "git-lifecycle.lifecycle"
LIFECYCLE_VALIDATOR_PATH = ROOT / "lifecycle.py"
SCHEMA_DIGEST = "6c005cd86cfebcd2414ed7587faa047ee92f6bee29ba9a4ab9f88de74576f54d"
GRAMMAR_DIGEST = "0cc78ea824285d1da5cd30f8624e53bdfa0291a2052c3d108f473071c770856c"
LIFECYCLE_SOURCE_REVISION = "4b5e131a670afb46ca87291479fed7c0fefcf370"
LIFECYCLE_VALIDATOR_DIGEST = "9c3f3076b5b45408d3eefc34cd567b58821aa565d3fe3bf6339641111079ede0"
LIFECYCLE_PROFILE_DIGEST = "c148b6102e5c6ef3e2b55b6038b3dc510a2c64f3f7f2e9e3d61dc2aa2661463f"

TRANSITIONS = {
    "seed-baseline": ("uninitialized", "seeded"),
    "create-ticket-branch": ("seeded", "ticket-ready"),
    "local-commit": ("ticket-ready", "implementation-local"),
    "open-pr": ("implementation-local", "review-open"),
    "integrate": ("review-open", "integrated"),
    "release": ("integrated", "released"),
}
REQUEST_KEYS = {
    "schema", "kind", "requestId", "repositoryRef", "ticket", "action",
    "expectedState", "targetState", "authorizationRef", "seedProfileRef",
    "evidenceRefs", "idempotencyKey",
}
REFS = {
    "requestId": r"^request:[a-z][a-z0-9._-]{0,95}$",
    "repositoryRef": r"^repository:[a-z][a-z0-9._-]{0,95}$",
    "ticket": r"^ticket-[0-9]{3,}$",
    "authorizationRef": r"^authorization:[a-z][a-z0-9._-]{0,127}$",
    "seedProfileRef": r"^seed-profile:[a-z][a-z0-9._-]{0,95}$",
    "idempotencyKey": r"^idempotency:[a-z][a-z0-9._-]{0,127}$",
}
SENSITIVE = re.compile(r"(shell|command|argv|password|credential|token|secret|path|remote|url)", re.I)


class ContractError(ValueError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
    model = report.lifecycles[0]
    state_values = schema["$defs"]["state"]["enum"]  # type: ignore[index]
    expected_states = {lifecycle_name(str(value)) for value in state_values}
    expected_transitions = {
        (lifecycle_name(source), lifecycle_name(target), lifecycle_name(action))
        for action, (source, target) in TRANSITIONS.items()
    } | {
        ("INTEGRATED", "TERMINAL", "CLEANUP"),
        ("RELEASED", "TERMINAL", "CLEANUP"),
    }
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


def reject_sensitive(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if SENSITIVE.search(key):
                raise ContractError(f"unsafe key: {key}")
            reject_sensitive(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_sensitive(nested)


def validate_request(doc: dict[str, object]) -> None:
    if set(doc) - REQUEST_KEYS:
        raise ContractError("request contains an unknown field")
    required = REQUEST_KEYS - {"seedProfileRef"}
    if not required <= set(doc):
        raise ContractError("request field is missing")
    if doc["schema"] != "wellmanifest.git-lifecycle/v1" or doc["kind"] != "transition-request":
        raise ContractError("wrong document family")
    reject_sensitive(doc)
    for key, pattern in REFS.items():
        if key in doc and not re.fullmatch(pattern, str(doc[key])):
            raise ContractError(f"invalid reference: {key}")
    evidence = doc["evidenceRefs"]
    if not isinstance(evidence, list) or not evidence or len(evidence) != len(set(evidence)):
        raise ContractError("evidence references must be nonempty and unique")
    action = str(doc["action"])
    if action == "cleanup":
        if doc["expectedState"] not in {"integrated", "released"} or doc["targetState"] != "terminal":
            raise ContractError("invalid cleanup transition")
    elif TRANSITIONS.get(action) != (doc["expectedState"], doc["targetState"]):
        raise ContractError("invalid transition")
    if (action == "seed-baseline") != ("seedProfileRef" in doc):
        raise ContractError("seed profile is allowed only for seed-baseline")


def validate_seed_state(doc: dict[str, object]) -> None:
    required = {"state", "headSha", "baselineSha", "remoteConfigured", "implementationPresent"}
    if not required <= set(doc) or doc["state"] != "seeded":
        raise ContractError("invalid seeded state")
    sha = r"[0-9a-f]{40}"
    if not re.fullmatch(sha, str(doc["headSha"])) or not re.fullmatch(sha, str(doc["baselineSha"])):
        raise ContractError("seeded state requires real SHA values")
    if doc["remoteConfigured"] is not False or doc["implementationPresent"] is not False:
        raise ContractError("seeded state must have no remote or implementation")


def validate_seed_receipt(doc: dict[str, object]) -> None:
    if doc.get("action") != "seed-baseline" or doc.get("outcome") != "applied":
        raise ContractError("not an applied seed receipt")
    if doc.get("beforeState") != "uninitialized" or doc.get("afterState") != "seeded":
        raise ContractError("invalid seed receipt states")
    if doc.get("pushPerformed") is not False or doc.get("publicationPerformed") is not False:
        raise ContractError("seed baseline cannot publish")
    if doc.get("secretsRedacted") is not True or not re.fullmatch(r"[0-9a-f]{40}", str(doc.get("headSha"))):
        raise ContractError("invalid safe seed receipt")


def expect_rejected(name: str, validator, base: dict[str, object], mutation) -> str:
    doc = copy.deepcopy(base)
    mutation(doc)
    try:
        validator(doc)
    except ContractError:
        return name
    raise AssertionError(f"adversarial case accepted: {name}")


def run_all() -> dict[str, object]:
    schema = json.loads(SCHEMA_PATH.read_text())
    grammar = GRAMMAR_PATH.read_bytes()
    validate_lifecycle_profile(schema)
    if digest(canonical(schema)) != SCHEMA_DIGEST or digest(grammar) != GRAMMAR_DIGEST:
        raise ContractError("contract digest mismatch")
    lowered = grammar.lower()
    for forbidden in (b"shell", b"argv", b"password", b"credential", b"token", b"remoteurl", b"http://", b"ssh://"):
        if forbidden in lowered:
            raise ContractError(f"unsafe grammar surface: {forbidden.decode()}")

    request = {
        "schema": "wellmanifest.git-lifecycle/v1", "kind": "transition-request",
        "requestId": "request:seed", "repositoryRef": "repository:demo",
        "ticket": "ticket-001", "action": "seed-baseline",
        "expectedState": "uninitialized", "targetState": "seeded",
        "authorizationRef": "authorization:session",
        "seedProfileRef": "seed-profile:governed",
        "evidenceRefs": ["artifact:intent"], "idempotencyKey": "idempotency:seed",
    }
    sha = "a" * 40
    state = {"state": "seeded", "headSha": sha, "baselineSha": sha, "remoteConfigured": False, "implementationPresent": False}
    receipt = {"action": "seed-baseline", "outcome": "applied", "beforeState": "uninitialized", "afterState": "seeded", "headSha": sha, "pushPerformed": False, "publicationPerformed": False, "secretsRedacted": True}
    validate_request(request); validate_seed_state(state); validate_seed_receipt(receipt)
    rejected = [
        expect_rejected("shell-command", validate_request, request, lambda d: d.update(command="git push --force")),
        expect_rejected("remote-url", validate_request, request, lambda d: d.update(remoteUrl="ssh://attacker/repo")),
        expect_rejected("wrong-transition", validate_request, request, lambda d: d.update(targetState="released")),
        expect_rejected("seed-without-profile", validate_request, request, lambda d: d.pop("seedProfileRef")),
        expect_rejected("inline-token", validate_request, request, lambda d: d.update(token="secret")),
        expect_rejected("seeded-with-remote", validate_seed_state, state, lambda d: d.update(remoteConfigured=True)),
        expect_rejected("seed-push", validate_seed_receipt, receipt, lambda d: d.update(pushPerformed=True)),
        expect_rejected("seed-publication", validate_seed_receipt, receipt, lambda d: d.update(publicationPerformed=True)),
    ]
    import repo_hygiene

    hygiene = repo_hygiene.self_test()
    return {
        "schema": "wellmanifest.git-lifecycle-conformance/v1",
        "ok": True,
        "positiveDocuments": 3,
        "adversarialRejected": rejected,
        "schemaDigest": "sha256:" + SCHEMA_DIGEST,
        "grammarDigest": "sha256:" + GRAMMAR_DIGEST,
        "repoHygiene": hygiene,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.parse_args()
    print(json.dumps(run_all(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
