from __future__ import annotations

from ontology_agent.studio.skill_packages import default_skill_root, load_skill_package


def test_default_skill_root_uses_the_platform_project_root(
    tmp_path, monkeypatch
) -> None:
    project_root = tmp_path / "installed-product"
    skill_root = project_root / "skills"
    skill_root.mkdir(parents=True)
    monkeypatch.delenv("ONTOLOGY_SKILL_ROOT", raising=False)
    monkeypatch.setenv("ONTOLOGY_AGENT_PROJECT_ROOT", str(project_root))

    assert default_skill_root() == skill_root


def test_explicit_platform_skill_root_has_priority(tmp_path, monkeypatch) -> None:
    explicit_root = tmp_path / "platform-skills"
    project_root = tmp_path / "installed-product"
    monkeypatch.setenv("ONTOLOGY_SKILL_ROOT", str(explicit_root))
    monkeypatch.setenv("ONTOLOGY_AGENT_PROJECT_ROOT", str(project_root))

    assert default_skill_root() == explicit_root


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


def test_build_skill_1_1_governs_sql_contract_candidates() -> None:
    package = load_skill_package("ontology-build", "1.1.0")

    assert package.manifest.version == "1.1.0"
    assert "SQL contract" in package.reference_texts[
        "references/modeling-rules.md"
    ]
    assert package.manifest.direct_draft_write is False
