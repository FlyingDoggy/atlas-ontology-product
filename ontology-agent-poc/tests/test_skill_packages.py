from __future__ import annotations

from ontology_agent.studio.skill_packages import load_skill_package


def test_build_skill_is_versioned_closed_and_domain_neutral() -> None:
    package = load_skill_package("ontology-build", "1.0.0")

    assert package.manifest.role == "BUILDER"
    assert package.manifest.human_review_required is True
    assert package.manifest.direct_draft_write is False
    assert package.manifest.max_model_calls == 3
    assert package.output_schema["additionalProperties"] is False
    corpus = package.instructions.casefold() + "\n" + "\n".join(
        package.resource_checksums
    ).casefold()
    assert "adt" not in corpus
    assert "cash trading" not in corpus


def test_review_skill_is_versioned_findings_only_and_domain_neutral() -> None:
    package = load_skill_package("ontology-review", "1.0.0")

    assert package.manifest.role == "REVIEWER"
    assert package.manifest.human_review_required is True
    assert package.manifest.direct_draft_write is False
    assert package.manifest.max_model_calls == 1
    assert package.output_schema["additionalProperties"] is False
    corpus = package.instructions.casefold() + "\n" + "\n".join(
        package.reference_texts.values()
    ).casefold()
    assert "adt" not in corpus
    assert "cash trading" not in corpus
    assert "approve" in corpus
