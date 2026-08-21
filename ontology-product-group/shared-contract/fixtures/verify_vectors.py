#!/usr/bin/env python3
"""Independent verifier for checked-in canonical-json-v1.0 vectors.

This file intentionally does not import the fixture generator or product code.
It independently parses, canonicalizes, hashes and validates the frozen vectors.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


SAFE_INT = 9_007_199_254_740_991
DIGEST_RE = re.compile(r"^sha-256:[0-9a-f]{64}$")
DECIMAL_COEFFICIENT_RE = re.compile(r"^(?:0|-?[1-9][0-9]*)$")
TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")
RESERVED_VERSIONS = {"latest", "current", "*"}
CANONICAL_TEST_FIELDS = {
    "subject_schema",
    "contract_version",
    "canonicalization_profile",
    "object_type",
    "object_id",
    "object_version",
    "scope",
    "chinese_nfc",
    "escaped",
    "decimal_value",
    "nullable",
    "ordered_values",
    "enabled",
}


class VectorError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def pairs_to_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    normalized: set[str] = set()
    for key, value in pairs:
        normalized_key = unicodedata.normalize("NFC", key)
        if key in result or normalized_key in normalized:
            raise VectorError("DUPLICATE_KEY")
        result[key] = value
        normalized.add(normalized_key)
    return result


def reject_constant(_: str) -> Any:
    raise VectorError("NON_FINITE_FORBIDDEN")


def parse(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=pairs_to_object, parse_constant=reject_constant)
    except VectorError:
        raise
    except UnicodeDecodeError as exc:
        raise VectorError("INVALID_UTF8") from exc
    except json.JSONDecodeError as exc:
        raise VectorError("INVALID_JSON") from exc


def quote(value: str) -> str:
    if unicodedata.normalize("NFC", value) != value:
        raise VectorError("NON_NFC")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise VectorError("UNPAIRED_SURROGATE")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def render(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if type(value) is int:
        if value < -SAFE_INT or value > SAFE_INT:
            raise VectorError("INTEGER_OUT_OF_RANGE")
        return f"{value:d}"
    if isinstance(value, float):
        raise VectorError("FLOAT_FORBIDDEN")
    if isinstance(value, str):
        return quote(value)
    if isinstance(value, list):
        return "[" + ",".join(render(item) for item in value) + "]"
    if isinstance(value, dict):
        for key in value:
            if unicodedata.normalize("NFC", key) != key:
                raise VectorError("NON_NFC_KEY")
        return "{" + ",".join(
            quote(key) + ":" + render(value[key]) for key in sorted(value)
        ) + "}"
    raise VectorError("UNSUPPORTED_TYPE")


def subject_digest(profile: str, schema: str, canonical_json: str) -> str:
    separated = b"\x00".join(
        [b"spc-v0.1", profile.encode("utf-8"), schema.encode("utf-8"), canonical_json.encode("utf-8")]
    )
    return "sha-256:" + hashlib.sha256(separated).hexdigest()


def verify_positive(document: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    profile = document["canonicalization_profile"]
    for vector in document["positive"]:
        try:
            parsed = parse(vector["input_json"])
            actual_json = render(parsed)
            actual_digest = subject_digest(profile, vector["subject_schema"], actual_json)
            if actual_json != vector["canonical_json"]:
                failures.append(f"{vector['id']}: canonical bytes differ")
            if actual_digest != vector["subject_digest"]:
                failures.append(f"{vector['id']}: digest differs")
        except Exception as exc:  # report every vector, do not stop early
            failures.append(f"{vector['id']}: unexpected {type(exc).__name__}: {exc}")
    return failures


def verify_known_ref_schema_pairs(document: dict[str, Any]) -> list[str]:
    """Ensure isolated refs still use the registered product type/schema pair."""
    failures: list[str] = []
    subjects: list[tuple[str, dict[str, Any]]] = []
    schema_by_type: dict[str, str] = {}
    for vector in document["positive"]:
        subject = parse(vector["input_json"])
        subjects.append((vector["id"], subject))
        object_type = subject["object_type"]
        schema = subject["subject_schema"]
        existing = schema_by_type.get(object_type)
        if existing is not None and existing != schema:
            failures.append(
                f"{vector['id']}: product object type {object_type} has conflicting schemas {existing} and {schema}"
            )
        schema_by_type[object_type] = schema

    ref_shape = {"object_type", "subject_schema", "subject_digest", "scope"}

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if ref_shape.issubset(value):
                expected = schema_by_type.get(value["object_type"])
                if expected is not None and value["subject_schema"] != expected:
                    failures.append(
                        f"{path}: {value['object_type']} ref uses {value['subject_schema']}, expected {expected}"
                    )
            for key, child in value.items():
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    for vector_id, subject in subjects:
        walk(subject, vector_id)
    return failures


def validate_timestamp(value: str) -> None:
    if not TIMESTAMP_RE.fullmatch(value):
        raise VectorError("TIMESTAMP_NOT_UTC_MILLISECOND_Z")
    try:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise VectorError("INVALID_TIMESTAMP") from exc


def canonical_items(values: list[Any]) -> list[str]:
    return [render(value) for value in values]


def exercise_negative(vector: dict[str, Any]) -> None:
    validation = vector["validation"]
    if "raw_utf8_hex" in vector:
        raw = bytes.fromhex(vector["raw_utf8_hex"])
        if raw.startswith(b"\xef\xbb\xbf"):
            raise VectorError("UTF8_BOM_FORBIDDEN")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VectorError("INVALID_UTF8") from exc
        parse(text)
        return

    if validation == "registry":
        case = vector["registry_case"]
        if case["existing_digest"] != case["incoming_digest"]:
            raise VectorError("IDENTITY_CONFLICT")
        return

    text = vector["input_json"]
    if validation == "raw-number" and re.search(r":-0(?:[,}])", text):
        raise VectorError("NEGATIVE_ZERO_FORBIDDEN")
    parsed = parse(text)

    if validation in {"raw-json", "canonical"}:
        render(parsed)
        return
    if validation == "timestamp":
        validate_timestamp(parsed["issued_at"])
        return
    if validation == "base-subject":
        if parsed.get("subject_schema") is None:
            raise VectorError("NULL_NOT_ALLOWED")
        return
    if validation == "canonical-test-schema":
        extra = set(parsed) - CANONICAL_TEST_FIELDS
        if extra:
            raise VectorError("UNKNOWN_FIELD")
        return
    if validation in {"set", "ref-set"}:
        values = parsed["limitations"] if validation == "set" else parsed["refs"]
        rendered = canonical_items(values)
        if len(set(rendered)) != len(rendered):
            raise VectorError("SET_DUPLICATE")
        if rendered != sorted(rendered):
            raise VectorError("SET_NOT_CANONICALLY_SORTED")
        return
    if validation == "digest":
        if not DIGEST_RE.fullmatch(parsed["subject_digest"]):
            raise VectorError("INVALID_DIGEST")
        return
    if validation == "version":
        if parsed["object_version"] in RESERVED_VERSIONS:
            raise VectorError("RESERVED_VERSION")
        return
    if validation == "decimal":
        value = parsed["decimal_value"]
        if not DECIMAL_COEFFICIENT_RE.fullmatch(value["coefficient"]):
            raise VectorError("INVALID_DECIMAL_COEFFICIENT")
        if type(value["scale"]) is not int or not 0 <= value["scale"] <= 18:
            raise VectorError("INVALID_DECIMAL_SCALE")
        return
    if validation == "runtime-scope":
        if set(parsed["scope"]) != {"tenant_id", "workspace_id", "environment_id"}:
            raise VectorError("INVALID_SCOPE_SHAPE")
        return
    raise AssertionError(f"unhandled validation mode {validation}")


def verify_negative(document: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for vector in document["negative"]:
        try:
            exercise_negative(vector)
        except VectorError as exc:
            if exc.code != vector["expected_error"]:
                failures.append(f"{vector['id']}: expected {vector['expected_error']}, got {exc.code}")
        except Exception as exc:
            failures.append(f"{vector['id']}: unexpected {type(exc).__name__}: {exc}")
        else:
            failures.append(f"{vector['id']}: accepted but expected {vector['expected_error']}")
    return failures


def main() -> int:
    default = Path(__file__).with_name("canonical-json-v1.0-vectors.json")
    path = Path(sys.argv[1]) if len(sys.argv) == 2 else default
    document = json.loads(path.read_text(encoding="utf-8"))
    failures = []
    failures.extend(verify_positive(document))
    failures.extend(verify_known_ref_schema_pairs(document))
    failures.extend(verify_negative(document))
    declared_positive = document["positive_count"]
    declared_negative = document["negative_count"]
    if declared_positive != len(document["positive"]) or declared_positive < 20:
        failures.append("positive vector count mismatch or below 20")
    if declared_negative != len(document["negative"]) or declared_negative < 20:
        failures.append("negative vector count mismatch or below 20")
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print(f"PASS {declared_positive} positive + {declared_negative} negative vectors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
