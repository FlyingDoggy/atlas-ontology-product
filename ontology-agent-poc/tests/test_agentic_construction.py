from __future__ import annotations

from pathlib import Path

from ontology_agent.models import OntologyPackage
from ontology_agent.studio.agentic_construction import (
    compile_build_objective,
    continuation_engine_contract,
    freeze_agentic_build_plan,
    normalized_source_operations,
)
from ontology_agent.studio.skill_packages import LoadedSkillPackageV2, load_skill_package
from ontology_agent.studio.source_library import (
    FileSourceLibraryStore,
    SourceIntakeBatchManifestV1,
    StudioSourceLibraryService,
)
from ontology_agent.studio.source_projection import (
    MetricCandidateProjectionV1,
    RequirementProjectionV1,
    StudioAuthoringProjectionV1,
    build_authoring_projection,
)


HKEX_ROOT = Path(__file__).parents[2]
CASH_MATERIALS = HKEX_ROOT / "demo-materials" / "cash-trading-e2e"


def test_continuation_engine_keeps_authority_and_reduces_budget(monkeypatch) -> None:
    monkeypatch.setenv("ONTOLOGY_BUILDER_MAX_INPUT_TOKENS", "3000000")
    monkeypatch.setenv("ONTOLOGY_BUILDER_TOTAL_OUTPUT_TOKENS", "400000")
    # The exact fixture below is enough to obtain a checksum-valid frozen engine.
    source_version_id = "source-version." + "1" * 32
    objective_raw = {
        "contract": "studio-build-objective/v1",
        "objective_id": "build-objective." + "2" * 32,
        "solution_id": "ontology.example",
        "workspace_id": "workspace.example",
        "selected_source_version_ids": [source_version_id],
        "source_set_digest": "3" * 64,
        "capabilities": ["SEMANTIC"],
        "output_language": "en",
        "obligations": [
            {
                "obligation_id": "obligation.source",
                "kind": "SOURCE_COVERAGE",
                "title": "Cover source",
                "source_version_ids": [source_version_id],
                "source_locator": "complete-source",
                "required": True,
            }
        ],
        "required_validators": ["candidate.materialize"],
    }
    from ontology_agent.io import sha256_value
    from ontology_agent.studio.agentic_contracts import BuildObjectiveV1
    from ontology_agent.studio.agentic_construction import compile_engine_contract

    objective_raw["objective_checksum"] = sha256_value(objective_raw)
    objective = BuildObjectiveV1.model_validate(objective_raw)
    skill = load_skill_package("ontology-build", "2.0.10")
    assert isinstance(skill, LoadedSkillPackageV2)
    engine = compile_engine_contract(
        objective=objective,
        skill=skill,
        provider="qwen",
        requested_model="qwen3.8-max",
    )

    continuation = continuation_engine_contract(engine)

    assert continuation.max_model_calls == 24
    assert continuation.max_tool_calls == 48
    assert continuation.max_input_tokens == 650000
    assert continuation.max_output_tokens == 100000
    assert continuation.tool_registry_digest == engine.tool_registry_digest
    assert continuation.skill_checksum == engine.skill_checksum
    assert continuation.objective_checksum == engine.objective_checksum
    assert continuation.engine_checksum != engine.engine_checksum


def test_freeze_build_plan_closes_source_business_and_data_obligations(
    tmp_path: Path,
) -> None:
    sources = FileSourceLibraryStore(tmp_path / "sources")
    requirement = sources.register(
        workspace_id="workspace.example",
        source_id="asset.requirements",
        kind="requirement_transcription",
        title="Requirements",
        original_name="requirements.md",
        media_type="text/markdown",
        body=b"Analyze daily trading activity.\n",
    )
    dictionary = sources.register(
        workspace_id="workspace.example",
        source_id="asset.data_dictionary.orders",
        kind="data_dictionary",
        title="Order dictionary",
        original_name="orders.csv",
        media_type="text/csv",
        body=b"column,type\norder_id,string\n",
    )
    authoring = StudioAuthoringProjectionV1(
        source_mode="EXACT_TRANSCRIPTION",
        requirements=(
            RequirementProjectionV1(
                requirement_key="O-01",
                question="Analyze daily trading activity",
                minimum_output="Daily answer",
                presentation="table",
                status="SOURCE_SUPPORTED",
                support_class="DIRECT_EXACT",
                source_anchor=None,
            ),
        ),
        metric_candidates=(
            MetricCandidateProjectionV1(
                metric_key="M-01",
                name="Daily turnover",
                definition="Daily executed turnover",
                calculation_logic="sum(amount)",
                filters_and_scope="executed only",
                grain_and_dimensions="day",
                unit="HKD",
                null_and_zero_policy="zero when no rows",
                primary_sources="orders",
                source_status="provided",
                support_class="DIRECT_EXACT",
                compile_status="SOURCE_CANDIDATE",
                ontology_status="UNMAPPED",
                runtime_status="NOT_APPLICABLE",
                governance_status="UNREVIEWED",
                source_anchor=None,
            ),
        ),
    )
    skill = load_skill_package("ontology-build", "2.0.5")
    assert isinstance(skill, LoadedSkillPackageV2)

    plan = freeze_agentic_build_plan(
        solution_id="ontology.example",
        workspace_id="workspace.example",
        versions=(dictionary, requirement),
        authoring=authoring,
        output_language="zh",
        skill=skill,
        provider="qwen",
        requested_model="qwen3.8-max",
    )

    kinds = {item.kind for item in plan.objective.obligations}
    assert plan.objective.capabilities == ("SEMANTIC", "ANALYTICS", "DATA_MAPPING")
    assert {"REQUIREMENT", "METRIC", "SOURCE_COVERAGE", "SEMANTIC_MODEL", "DATA_MAPPING"} <= kinds
    assert len(
        [item for item in plan.objective.obligations if item.kind == "SOURCE_COVERAGE"]
    ) == 2
    assert plan.engine.objective_checksum == plan.objective.objective_checksum
    assert plan.engine.source_set_digest == plan.objective.source_set_digest
    assert plan.engine.output_language == "zh"
    assert "Evidence-to-Ontology Modeling Method" in plan.skill_instructions
    obligations = {item.obligation_id: item for item in plan.objective.obligations}
    assert obligations[
        "obligation.requirement.O-01"
    ].required_candidate_collections == ("analysis_patterns", "questions")
    assert obligations[
        "obligation.semantic-relationships.closure"
    ].required_candidate_collections == ("relationships",)
    assert obligations[
        "obligation.business-process.closure"
    ].required_candidate_collections == ("processes",)
    assert obligations[
        "obligation.analytics-interface.closure"
    ].required_candidate_collections == ("analysis_patterns", "questions")
    assert obligations[
        "obligation.data-joins.closure"
    ].required_candidate_collections == ("joins",)


def test_frozen_sources_are_normalized_by_the_shell_not_invented_by_the_model(
    tmp_path: Path,
) -> None:
    store = FileSourceLibraryStore(tmp_path / "sources")
    version = store.register(
        workspace_id="workspace.example",
        source_id="asset.requirements",
        kind="requirement_transcription",
        title="Requirements",
        original_name="requirements.md",
        media_type="text/markdown",
        body=b"Analyze orders.\n",
    )
    operations = normalized_source_operations(
        (version,), owner="actor.solution_owner"
    )

    assert len(operations) == 1
    operation = operations[0]
    assert operation.collection == "sources"
    assert operation.object_id == version.source_id
    assert operation.payload == {
        "id": "asset.requirements",
        "source_type": "requirement_transcription",
        "title": "Requirements",
        "locator": f"source-library:{version.source_version_id}",
        "owner": "actor.solution_owner",
        "captured_on": version.registered_at.date().isoformat(),
        "trust": "primary",
        "notes": (
            "Frozen input normalized by Ontology Studio; "
            f"content checksum {version.content_checksum}; "
            f"processing mode {version.processing_mode}."
        ),
    }


def test_metric_obligations_freeze_identity_unit_and_scale_without_authoring_formula(
    tmp_path: Path,
) -> None:
    sources = FileSourceLibraryStore(tmp_path / "sources")
    version = sources.register(
        workspace_id="workspace.example",
        source_id="source.metric_logic",
        kind="metric_transcription",
        title="Metric logic",
        original_name="metrics.md",
        media_type="text/markdown",
        body=b"Source metric contract.\n",
    )

    def metric(
        key: str, name: str, logic: str, output: str
    ) -> MetricCandidateProjectionV1:
        return MetricCandidateProjectionV1(
            metric_key=key,
            name=name,
            definition=f"Definition for {name}",
            calculation_logic=logic,
            filters_and_scope="same reporting population",
            grain_and_dimensions="trading day",
            unit=output,
            null_and_zero_policy=output,
            primary_sources="registered metric source",
            source_status="provided",
            support_class="DIRECT_EXACT",
            compile_status="SOURCE_CANDIDATE",
            ontology_status="UNMAPPED",
            runtime_status="NOT_APPLICABLE",
            governance_status="UNREVIEWED",
            source_anchor=None,
        )

    objective = compile_build_objective(
        solution_id="ontology.example",
        workspace_id="workspace.example",
        versions=(version,),
        authoring=StudioAuthoringProjectionV1(
            source_mode="EXACT_TRANSCRIPTION",
            requirements=(),
            metric_candidates=(
                metric(
                    "M-01",
                    "Order-to-trade ratio",
                    "orders / (trades * 2)",
                    "Output a percentage with 2 decimal places",
                ),
                metric(
                    "M-02",
                    "Trading volume",
                    "Sum(notional_hkd)",
                    "Unit: HKD million per trading day",
                ),
                metric(
                    "M-03",
                    "Capture latency",
                    "receive timestamp - transaction timestamp",
                    "Milliseconds as whole numbers",
                ),
            ),
        ),
        output_language="zh",
        enforce_typed_candidate_shape=True,
        enforce_metric_semantic_contract=True,
    )
    contracts = {
        item.metric_semantic_contract.source_metric_key: item.metric_semantic_contract
        for item in objective.obligations
        if item.metric_semantic_contract is not None
    }

    ratio = contracts["M-01"]
    assert ratio.expected_metric_id == "metric.order_to_trade_ratio"
    assert ratio.expected_metric_type == "derived"
    assert ratio.expected_value_type == "percentage"
    assert ratio.expected_unit == "PERCENT"
    assert ratio.required_formula_root == "multiply"
    assert ratio.required_formula_operations == ("divide", "multiply")
    assert set(ratio.required_formula_literals) == {2, 100}

    volume = contracts["M-02"]
    assert volume.expected_metric_id == "metric.trading_volume"
    assert volume.expected_unit == "HKD_MN"
    assert volume.required_formula_root == "divide"
    assert set(volume.required_formula_literals) == {1000000}
    assert volume.required_referenced_units == ("HKD",)

    latency = contracts["M-03"]
    assert latency.expected_metric_id == "metric.capture_latency"
    assert latency.expected_value_type == "integer"
    assert latency.expected_unit == "MILLISECOND"
    assert latency.required_formula_root == "duration_ms"
    assert latency.required_formula_operations == ("duration_ms",)


def test_deloitte_cash_pack_compiles_the_exact_7_plus_8_denominator(
    tmp_path: Path, package: OntologyPackage
) -> None:
    workspace_id = "workspace.cash.agentic.acceptance"
    physical_files = (
        CASH_MATERIALS
        / "01_Deloitte_HK_Input"
        / "HKEX_Analytics_Scenario_Input_Template_with_ADT_Reference_v20260819.xlsx",
        CASH_MATERIALS
        / "01_Deloitte_HK_Input"
        / "order_trade_activities_data_dictionary.xlsx",
        CASH_MATERIALS
        / "01_Deloitte_HK_Input"
        / "cash_trading_sample_data.xlsx",
        CASH_MATERIALS / "01_Deloitte_HK_Input" / "email screenshot.jpeg",
        CASH_MATERIALS / "02_Product_Supplement" / "reference_controls.sql",
    )
    library = StudioSourceLibraryService(
        FileSourceLibraryStore(tmp_path / "sources")
    )
    manifest = SourceIntakeBatchManifestV1.model_validate(
        {
            "idempotency_key": "cash-agentic-acceptance-v1",
            "items": [
                {
                    "client_file_id": "requirements-metrics",
                    "original_name": physical_files[0].name,
                    "declared_media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "registrations": [
                        {"kind": "requirement_transcription", "title": "Cash Trading requirements"},
                        {"kind": "metric_transcription", "title": "Cash Trading metrics"},
                    ],
                },
                {
                    "client_file_id": "model-dictionary",
                    "original_name": physical_files[1].name,
                    "declared_media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "registrations": [
                        {"kind": "data_model", "title": "Cash Trading data model"},
                        {"kind": "data_dictionary", "title": "Cash Trading data dictionary"},
                    ],
                },
                {
                    "client_file_id": "sample",
                    "original_name": physical_files[2].name,
                    "declared_media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "registrations": [
                        {"kind": "data_dictionary", "title": "Cash Trading sample data"}
                    ],
                },
                {
                    "client_file_id": "email",
                    "original_name": physical_files[3].name,
                    "declared_media_type": "image/jpeg",
                    "registrations": [
                        {"kind": "other", "title": "Source limitation evidence"}
                    ],
                },
                {
                    "client_file_id": "sql",
                    "original_name": physical_files[4].name,
                    "declared_media_type": "text/sql",
                    "registrations": [
                        {"kind": "sql", "title": "Product reference SQL"}
                    ],
                },
            ],
        }
    )
    receipt = library.register_batch(
        workspace_id=workspace_id,
        manifest=manifest,
        bodies=tuple(path.read_bytes() for path in physical_files),
    )
    versions = library.list_current(workspace_id)
    intake = {
        "assets": library.current_intake_assets(
            workspace_id, include_parsed_attachments=True
        )
    }
    authoring = build_authoring_projection(
        package=package,
        intake=intake,
        scenario_dir=CASH_MATERIALS,
    )
    skill = load_skill_package("ontology-build", "2.0.5")
    assert isinstance(skill, LoadedSkillPackageV2)
    plan = freeze_agentic_build_plan(
        solution_id="ontology.cash.agentic.acceptance",
        workspace_id=workspace_id,
        versions=versions,
        authoring=authoring,
        output_language="zh",
        skill=skill,
        provider="qwen",
        requested_model="qwen3.8-max",
    )

    assert receipt.failures == ()
    assert len(receipt.physical_files) == 5
    assert len(receipt.registrations) == 7
    assert len(authoring.requirements) == 7
    assert len(authoring.metric_candidates) == 8
    assert len(plan.objective.obligations) == 31
    assert sum(item.kind == "SOURCE_COVERAGE" for item in plan.objective.obligations) == 7
    assert plan.objective.capabilities == (
        "SEMANTIC",
        "ANALYTICS",
        "DATA_MAPPING",
    )
    metric_contracts = {
        item.metric_semantic_contract.source_metric_key: item.metric_semantic_contract
        for item in plan.objective.obligations
        if item.metric_semantic_contract is not None
    }
    assert len(metric_contracts) == 8
    assert metric_contracts["M-01"].expected_metric_id == "metric.order_rejection_rate"
    assert metric_contracts["M-02"].expected_metric_id == "metric.order_fill_rate"
    assert metric_contracts["M-03"].expected_metric_id == "metric.trade_capture_latency"
    assert metric_contracts["M-03"].expected_unit == "MILLISECOND"
    assert metric_contracts["M-03"].required_formula_root == "duration_ms"
    assert metric_contracts["M-03"].required_formula_operations == ("duration_ms",)
    assert (
        metric_contracts["M-04"].expected_metric_id
        == "metric.active_client_trading_volume"
    )
    assert metric_contracts["M-04"].expected_unit == "HKD_MN"
    assert set(metric_contracts["M-04"].required_formula_literals) == {1000000}
    assert metric_contracts["M-04"].required_referenced_units == ("HKD",)
    assert (
        metric_contracts["M-05"].expected_metric_id
        == "metric.client_order_completion_rate"
    )
    assert metric_contracts["M-06"].expected_metric_id == "metric.cancel_to_trade_ratio"
    assert metric_contracts["M-07"].expected_metric_id == "metric.order_to_trade_ratio"
    assert set(metric_contracts["M-07"].required_formula_literals) == {2, 100}
    assert (
        metric_contracts["M-08"].expected_metric_id
        == "metric.potential_self_trade_rate"
    )
