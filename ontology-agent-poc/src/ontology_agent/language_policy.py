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
_TECHNICAL_VALUE = re.compile(r"^[A-Za-z0-9_.$:/@+|\[\](),=*<>]+$")
_HUMAN_TEXT_KEYS = {
    "name",
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
    "operation",
    "exception_paths",
    "failure_conditions",
    "examples",
    "null_meaning",
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


def _english_prose_words(value: str) -> list[str]:
    words: list[str] = []
    for match in _ENGLISH_WORD.finditer(value):
        start = match.start()
        end = match.end()
        while start > 0 and not value[start - 1].isspace():
            start -= 1
        while end < len(value) and not value[end].isspace():
            end += 1
        token = value[start:end].strip("，。；：、（）()[]{}<>\"'`")
        # Inline identifiers, checksums, locators and acronyms are contracts,
        # even when they appear next to Chinese prose. Hyphenated natural words
        # are deliberately not exempted (for example, "Append-only event").
        if any(char.isdigit() or char in "_.$:/@+|[](),=*<>" for char in token):
            continue
        word = match.group(0)
        if word.isupper():
            continue
        words.append(word)
    return words


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
        # Chinese prose may legitimately contain exact identifiers and common
        # acronyms, but a Han character must not become an escape hatch for an
        # otherwise English sentence.  Lower-case prose of three or more words
        # is a reliable boundary while terms such as SQL, ID and SCD2 remain
        # usable without manufacturing translations.
        prose_words = _english_prose_words(cleaned)
        if len(prose_words) >= 3:
            return "contains English prose while the Solution authoring language is Chinese"
        return None
    words = _ENGLISH_WORD.findall(cleaned)
    # Exact identifiers and governed literals have no prose whitespace.  They
    # are contracts, not authoring-language content.  Brand/domain phrases must
    # be explicit allowed_verbatim_terms instead of relying on word count.
    if _TECHNICAL_VALUE.fullmatch(cleaned):
        return None
    if words:
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
        # Candidate writes and final package validation must enforce the same
        # boundary.  Checking only name/definition allowed English grain,
        # lifecycle, field descriptions and question examples to leak into an
        # otherwise Chinese ontology after materialisation.
        for violation in operation_language_violations(
            item.model_dump(mode="json"),
            policy,
        ):
            violations.append(f"{item.id}.{violation}")
    return tuple(dict.fromkeys(violations))
