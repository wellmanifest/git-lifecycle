"""Shared RFC 3339 nanosecond, Git ref, canonical JSON, and descriptor-safe I/O primitives."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 8 * 1024 * 1024
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_RFC3339_RE = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]"
    r"([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?"
    r"(?:([Zz])|([+-])([0-9]{2}):([0-9]{2}))$",
    re.ASCII,
)
_UTC_Z_RE = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T"
    r"([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?Z$",
    re.ASCII,
)
_REPO_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", re.ASCII)
_FORBIDDEN_REF_CHARS = frozenset({"\\", "~", "^", ":", "?", "*", "["})


def has_forbidden_chars(raw: str) -> bool:
    return any(
        ord(ch) < 32
        or ord(ch) == 127
        or 0x80 <= ord(ch) <= 0x9F
        or 0xD800 <= ord(ch) <= 0xDFFF
        for ch in raw
    )


def walk_json_tree(
    value: Any,
    exc_type: type[Exception] = ValueError,
    *,
    unsafe_key_re: re.Pattern[str] | None = None,
    unsafe_text_re: re.Pattern[str] | None = None,
) -> None:
    stack = [value]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for key, child in cur.items():
                if not isinstance(key, str) or has_forbidden_chars(key):
                    raise exc_type(f"unsafe field: {key}")
                if unsafe_key_re is not None and unsafe_key_re.search(key):
                    raise exc_type(f"unsafe field: {key}")
                stack.append(child)
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
        elif isinstance(cur, float):
            if not math.isfinite(cur):
                raise exc_type("non-finite float is forbidden")
        elif isinstance(cur, str) and (
            has_forbidden_chars(cur)
            or (unsafe_text_re is not None and unsafe_text_re.search(cur))
        ):
            raise exc_type("forbidden control, surrogate, or transport text")


def ensure_finite_and_no_surrogates(
    node: Any, exc_type: type[Exception] = ValueError
) -> None:
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, str):
            if any(0xD800 <= ord(ch) <= 0xDFFF for ch in cur):
                raise exc_type("lone UTF-16 surrogate is forbidden")
        elif isinstance(cur, float):
            if not math.isfinite(cur):
                raise exc_type("non-finite float is forbidden")
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
        elif isinstance(cur, dict):
            for key, child in cur.items():
                if isinstance(key, str) and any(
                    0xD800 <= ord(ch) <= 0xDFFF for ch in key
                ):
                    raise exc_type("lone UTF-16 surrogate key is forbidden")
                stack.append(child)


def canonical_json_bytes(value: Any, exc_type: type[Exception] = ValueError) -> bytes:
    ensure_finite_and_no_surrogates(value, exc_type)
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_rfc3339_ns(
    value: Any,
    label: str,
    exc_type: type[Exception] = ValueError,
    *,
    require_z: bool = False,
) -> int:
    if not isinstance(value, str):
        raise exc_type(f"{label} must be an RFC3339 timestamp")
    pattern = _UTC_Z_RE if require_z else _RFC3339_RE
    match = pattern.fullmatch(value)
    if match is None:
        raise exc_type(f"{label} must be an RFC3339 timestamp")
    year, month, day, hour, minute, second = (int(match.group(i)) for i in range(1, 7))
    frac_raw = match.group(7) or ""
    offset_seconds = 0
    if not require_z:
        zulu = match.group(8)
        sign = match.group(9)
        off_h = int(match.group(10) or "0")
        off_m = int(match.group(11) or "0")
        if zulu is None:
            if off_h > 23 or off_m > 59 or (sign == "-" and off_h == 0 and off_m == 0):
                raise exc_type(f"{label} offset is invalid")
            offset_seconds = (off_h * 3600 + off_m * 60) * (-1 if sign == "-" else 1)
    try:
        base_dt = datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except ValueError as exc:
        raise exc_type(f"{label} is not a valid calendar timestamp") from exc
    whole_seconds = (base_dt - EPOCH) // timedelta(seconds=1)
    frac_ns = int(frac_raw.ljust(9, "0")) if frac_raw else 0
    return (whole_seconds - offset_seconds) * 1_000_000_000 + frac_ns


def datetime_to_ns(moment: datetime, exc_type: type[Exception] = ValueError) -> int:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise exc_type("clock reference must be timezone-aware")
    utc_moment = moment.astimezone(UTC)
    micros = (utc_moment - EPOCH) // timedelta(microseconds=1)
    return micros * 1_000


def validate_owner_repo(
    value: Any, label: str, exc_type: type[Exception] = ValueError
) -> str:
    if not isinstance(value, str):
        raise exc_type(f"{label} must be owner/name")
    match = _REPO_RE.fullmatch(value)
    if match is None or match.group(1) in (".", "..") or match.group(2) in (".", ".."):
        raise exc_type(f"{label} must be a canonical owner/name")
    return value


def validate_git_ref(
    value: Any, label: str, exc_type: type[Exception] = ValueError
) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 255:
        raise exc_type(f"{label} must be a 1..255 character Git ref")
    if (
        value in ("@", ".", "..")
        or value.startswith(("/", "."))
        or value.endswith(("/", ".", ".lock"))
        or ".." in value
        or "//" in value
        or "@{" in value
    ):
        raise exc_type(f"{label} is not a valid Git ref")
    for ch in value:
        code = ord(ch)
        if (
            ch.isspace()
            or code < 32
            or code == 127
            or 0x80 <= code <= 0x9F
            or 0xD800 <= ord(ch) <= 0xDFFF
            or ch in _FORBIDDEN_REF_CHARS
        ):
            raise exc_type(f"{label} contains forbidden characters")
    if any(seg.startswith(".") or seg.endswith(".lock") for seg in value.split("/")):
        raise exc_type(f"{label} contains an invalid Git ref component")
    return value


def load_strict_json_file(
    raw_path: str,
    exc_type: type[Exception] = ValueError,
    *,
    max_bytes: int = MAX_JSON_BYTES,
) -> dict[str, Any]:
    if not raw_path or "\x00" in raw_path:
        raise exc_type("JSON file path is invalid")
    target = Path(raw_path)
    anchor_base = target if target.is_absolute() else Path(os.getcwd())
    probe = Path(anchor_base.anchor)
    rel_parts = (
        target.parts[1:]
        if target.is_absolute()
        else (*anchor_base.parts[1:], *target.parts)
    )
    for part in rel_parts[:-1]:
        if part in ("", "."):
            continue
        if part == "..":
            probe = probe.parent
            continue
        probe = probe / part
        try:
            st = os.lstat(probe)
        except OSError as exc:
            raise exc_type("JSON ancestor cannot be inspected") from exc
        if stat.S_ISLNK(st.st_mode):
            raise exc_type("JSON ancestor must not be a symlink")
    abs_path = Path(os.path.abspath(raw_path))
    dir_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    file_flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    dir_fd: int | None = None
    file_fd: int | None = None
    try:
        dir_fd = os.open(abs_path.parts[0], dir_flags)
        for part in abs_path.parts[1:-1]:
            nxt = os.open(part, dir_flags, dir_fd=dir_fd)
            os.close(dir_fd)
            dir_fd = nxt
        lst = os.lstat(abs_path.name, dir_fd=dir_fd)
        if not stat.S_ISREG(lst.st_mode):
            raise exc_type("JSON input must be a regular file")
        file_fd = os.open(abs_path.name, file_flags, dir_fd=dir_fd)
        fst = os.fstat(file_fd)
        if not stat.S_ISREG(fst.st_mode) or (lst.st_dev, lst.st_ino) != (
            fst.st_dev,
            fst.st_ino,
        ):
            raise exc_type("JSON regular-file identity changed")
        if fst.st_size > max_bytes:
            raise exc_type("JSON input exceeds maximum size")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(file_fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw_bytes = b"".join(chunks)
    except exc_type:
        raise
    except OSError as exc:
        raise exc_type("JSON file cannot be opened safely") from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if dir_fd is not None:
            os.close(dir_fd)
    if len(raw_bytes) > max_bytes:
        raise exc_type("JSON input exceeds maximum size")

    def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for k, v in items:
            if k in obj:
                raise exc_type(f"duplicate JSON field: {k}")
            obj[k] = v
        return obj

    def _float(tok: str) -> float:
        val = float(tok)
        if not math.isfinite(val):
            raise exc_type("non-finite JSON number")
        return val

    def _const(_tok: str) -> Any:
        raise exc_type("non-standard JSON constant")

    try:
        loaded = json.loads(
            raw_bytes.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_float=_float,
            parse_constant=_const,
        )
    except exc_type:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise exc_type("JSON document is malformed") from exc
    ensure_finite_and_no_surrogates(loaded, exc_type)
    if not isinstance(loaded, dict):
        raise exc_type("JSON root must be an object")
    return loaded
