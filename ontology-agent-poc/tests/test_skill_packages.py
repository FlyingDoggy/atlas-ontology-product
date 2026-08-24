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


def test_build_skill_1_2_closes_phase_coverage_without_domain_customization() -> None:
    package = load_skill_package("ontology-build", "1.2.0")

    assert package.manifest.version == "1.2.0"
    assert package.manifest.max_model_calls == 4
    assert package.output_schema["properties"]["proposals"]["maxItems"] == 48
    assert "For every formal metric definition" in package.instructions
    corpus = package.instructions.casefold() + "\n" + "\n".join(
        package.reference_texts.values()
    ).casefold()
    assert "adt" not in corpus
    assert "cash trading" not in corpus


def test_load_agentic_builder_skill_v2_without_fixed_phase_output() -> None:
    package = load_skill_package("ontology-build", "2.0.0")

    assert package.manifest.contract == "agent-skill-package/v2"
    assert package.manifest.completion_tool_id == "run.request_completion"
    assert "candidate.upsert" in package.manifest.tool_ids
    assert "fixed semantic/analytics/data phase" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_latest_builder_package_reconciles_units_currency_scale_and_sql() -> None:
    package = load_skill_package("ontology-build", "2.0.1")

    assert package.manifest.version == "2.0.1"
    assert "Never relabel one currency as another" in package.instructions
    assert "percentage" in package.instructions
    assert "SQL" in package.instructions


def test_latest_reviewer_package_audits_the_full_metric_denominator() -> None:
    package = load_skill_package("ontology-review", "2.0.1")

    assert package.manifest.version == "2.0.1"
    assert "Audit every Metric obligation" in package.instructions
    assert "currency relabeling" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_builder_2_0_2_enforces_typed_end_to_end_candidate_shape() -> None:
    package = load_skill_package("ontology-build", "2.0.2")

    assert package.manifest.version == "2.0.2"
    assert package.manifest.max_model_calls == 360
    assert "required_candidate_collections" in package.instructions
    assert "both a governed `question`" in package.instructions
    assert "relationships" in package.instructions
    assert "joins" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_reviewer_2_0_2_challenges_wrong_type_and_orphan_coverage() -> None:
    package = load_skill_package("ontology-review", "2.0.2")

    assert package.manifest.version == "2.0.2"
    assert "wrong-type" in package.instructions
    assert "A collection count is not closure" in package.instructions
    assert "Question and Analysis Pattern" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_reviewer_2_0_3_batches_mechanical_reads_and_bounds_cost() -> None:
    package = load_skill_package("ontology-review", "2.0.3")

    assert package.manifest.version == "2.0.3"
    assert package.manifest.max_model_calls == 32
    assert package.manifest.max_tool_calls == 64
    assert "studio-review-execution-plan/v1" in package.instructions
    assert "Never turn a supplied batch into singleton reads" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_builder_2_0_3_uses_flat_writes_and_server_owned_provenance() -> None:
    package = load_skill_package("ontology-build", "2.0.3")

    assert package.manifest.version == "2.0.3"
    assert package.manifest.max_model_calls == 240
    assert "flat contract" in package.instructions
    assert "derives exact logical source IDs" in package.instructions
    assert "there is no nested `operation`" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_builder_2_0_4_has_an_evidence_based_completion_budget() -> None:
    package = load_skill_package("ontology-build", "2.0.4")

    assert package.manifest.version == "2.0.4"
    assert package.manifest.max_model_calls == 320
    assert "`_runtime_budget` signal" in package.instructions
    assert "valid Candidate is not complete" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_builder_2_0_5_closes_source_frozen_metric_semantics() -> None:
    package = load_skill_package("ontology-build", "2.0.5")

    assert package.manifest.version == "2.0.5"
    assert package.manifest.max_model_calls == 320
    assert "`metric_semantic_contract`" in package.instructions
    assert "Never make validation pass by changing a label" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_builder_2_0_6_exposes_executable_semantic_primitives() -> None:
    package = load_skill_package("ontology-build", "2.0.6")

    assert package.manifest.version == "2.0.6"
    assert package.manifest.max_model_calls == 320
    assert "`yn_to_boolean_not`" in package.instructions
    assert "`eq_property`/`neq_property`" in package.instructions
    assert "`duration_ms(end_timestamp, start_timestamp)`" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_builder_2_0_7_uses_rules_for_derived_population_scope() -> None:
    package = load_skill_package("ontology-build", "2.0.7")

    assert package.manifest.version == "2.0.7"
    assert package.manifest.max_model_calls == 320
    assert "`query.population_rule`" in package.instructions
    assert "Never invent a" in package.instructions
    assert "boolean Property" in package.instructions
    assert "Do not manufacture period IDs" in package.instructions
    assert "derived metrics compose governed `metric_ref`" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_builder_2_0_8_preserves_a_real_completion_reserve() -> None:
    package = load_skill_package("ontology-build", "2.0.8")

    assert package.manifest.version == "2.0.8"
    assert package.manifest.max_model_calls == 480
    assert package.manifest.max_tool_calls == 960
    assert "When the budget state becomes `LOW`" in package.instructions
    assert "Do not spend the completion reserve" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_builder_2_0_9_closes_envelope_and_cost_failure_modes() -> None:
    package = load_skill_package("ontology-build", "2.0.9")

    assert package.manifest.version == "2.0.9"
    assert package.manifest.max_model_calls == 140
    assert package.manifest.max_tool_calls == 280
    assert "Inspect `scenario` early" in package.instructions
    assert "batch" in package.instructions
    assert "`collections` selector" in package.instructions
    assert "Do not call it after every write" in package.instructions
    assert package.manifest.direct_draft_write is False


def test_builder_2_0_10_keeps_known_authority_out_of_model_repair_loops() -> None:
    package = load_skill_package("ontology-build", "2.0.10")

    assert package.manifest.version == "2.0.10"
    assert package.manifest.max_model_calls == 140
    assert package.manifest.max_tool_calls == 280
    assert "shell always binds the singleton" in package.instructions
    assert "optional `obligation_ids`" in package.instructions
    assert "up to 32 objects" in package.instructions
    assert package.manifest.direct_draft_write is False
