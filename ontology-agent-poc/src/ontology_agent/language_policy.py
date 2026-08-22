from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from .models import (
    AuthoringLanguage,
    LocalizedName,
    OntologyAuthoringPolicyV1,
    OntologyPackage,
)


_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_ENGLISH_WORD = re.compile(r"[A-Za-z]{2,}")
_TECHNICAL_VALUE = re.compile(r"^[A-Za-z0-9_.$:/@+\-\[\](),=*<>\s]+$")
_HUMAN_TEXT_KEYS = {
    "definition",
    "description",
    "rationale",
    "assumptions",
    "clarification_question",
    "expected_answer",
    "question",
    "recommendation",
    "summary",
    "detail",
    "notes",
    "trigger",
    "grain",
    "lifecycle",
}
_EXACT_KEYS = {
    "id",
    "object_id",
    "predicate",
    "primary_key",
    "entity",
    "from_entity",
    "to_entity",
    "physical_table",
    "physical_column",
    "sql",
    "expression",
    "locator",
    "source_id",
    "fragment_id",
}


def create_authoring_policy(
    language: AuthoringLanguage,
    *,
    allowed_verbatim_terms: Iterable[str] = (),
) -> OntologyAuthoringPolicyV1:
    terms = tuple(dict.fromkeys(term.strip() for term in allowed_verbatim_terms if term.strip()))
    payload = {
        "authoring_language": language,
        "allowed_verbatim_terms": list(terms),
        "contract": "ontology-authoring-policy/v1",
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return OntologyAuthoringPolicyV1(
        authoring_language=language,
        allowed_verbatim_terms=terms,
        policy_digest=digest,
    )


def primary_text(name: LocalizedName, language: AuthoringLanguage) -> str:
    return name.primary(language)


def _without_allowlist(value: str, allowlist: tuple[str, ...]) -> str:
    cleaned = value
    for term in sorted(allowlist, key=len, reverse=True):
        cleaned = cleaned.replace(term, "")
    return cleaned


def text_language_violation(
    value: str,
    policy: OntologyAuthoringPolicyV1,
    *,
    short_label: bool = False,
) -> str | None:
    cleaned = _without_allowlist(value.strip(), policy.allowed_verbatim_terms)
    if not cleaned:
        return None
    if policy.authoring_language == "en":
        if _HAN.search(cleaned):
            return "contains Chinese text while the Solution authoring language is English"
        return None
    if _HAN.search(cleaned):
        return None
    words = _ENGLISH_WORD.findall(cleaned)
    if short_label and len(words) <= 4:
        return None
    if _TECHNICAL_VALUE.fullmatch(cleaned) and len(words) <= 8:
        return None
    if len(words) >= 5:
        return "contains English prose while the Solution authoring language is Chinese"
    return None


def operation_language_violations(
    payload: dict[str, Any] | None,
    policy: OntologyAuthoringPolicyV1,
) -> tuple[str, ...]:
    if payload is None:
        return ()
    violations: list[str] = []
    raw_name = payload.get("name")
    if isinstance(raw_name, dict):
        primary = raw_name.get(policy.authoring_language)
        if not isinstance(primary, str) or not primary.strip():
            violations.append(f"name.{policy.authoring_language}: primary name is missing")
        else:
            issue = text_language_violation(primary, policy, short_label=True)
            if issue:
                violations.append(f"name.{policy.authoring_language}: {issue}")

    def walk(value: Any, path: str, key: str | None = None) -> None:
        if key in _EXACT_KEYS:
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, f"{path}.{child_key}" if path else str(child_key), str(child_key))
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]", key)
        elif isinstance(value, str) and key in _HUMAN_TEXT_KEYS:
            issue = text_language_violation(value, policy)
            if issue:
                violations.append(f"{path}: {issue}")

    walk(payload, "")
    return tuple(dict.fromkeys(violations))


def package_language_violations(package: OntologyPackage) -> tuple[str, ...]:
    policy = package.authoring_policy
    if policy is None:
        return ()
    violations: list[str] = []
    for item in package.governed_objects():
        primary = getattr(item.name, policy.authoring_language)
        if primary is None:
            violations.append(f"{item.id}.name.{policy.authoring_language}: primary name is missing")
        else:
            issue = text_language_violation(primary, policy, short_label=True)
            if issue:
                violations.append(f"{item.id}.name.{policy.authoring_language}: {issue}")
        issue = text_language_violation(item.definition, policy)
        if issue:
            violations.append(f"{item.id}.definition: {issue}")
    return tuple(violations)
