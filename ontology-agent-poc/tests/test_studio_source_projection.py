from pathlib import Path
from io import BytesIO
import hashlib

from openpyxl import Workbook

from ontology_agent.io import DEFAULT_CASH_TRADING_SCENARIO_DIR, load_package
from ontology_agent.studio.intake import ADTIntakeRegistry
from ontology_agent.studio.source_projection import (
    _canonical_metric_target,
    build_authoring_projection,
)
from ontology_agent.studio.source_library import (
    FileSourceLibraryStore,
    StudioSourceLibraryService,
)


def test_adt_transcriptions_project_all_requirements_and_metric_candidates(
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    intake = ADTIntakeRegistry(tmp_path / "intake", scenario_dir).register_reference()
    package = load_package(scenario_dir / "ontology" / "package.yaml")

    projection = build_authoring_projection(
        package=package,
        intake=intake,
        scenario_dir=scenario_dir,
    )

    assert [item.requirement_key for item in projection.requirements] == [
        "O-01", "O-02", "O-03", "O-04", "O-05"
    ]
    assert [item.metric_key for item in projection.metric_candidates] == [
        "M-01", "M-02", "M-03", "M-04", "M-05", "M-06", "M-07", "M-08"
    ]
    assert sum(item.compile_status == "EXECUTABLE" for item in projection.metric_candidates) == 3
    assert all(item.support_class == "DIRECT_EXACT" for item in projection.metric_candidates)
    assert all(len(item.source_anchor.snippet_checksum) == 64 for item in projection.metric_candidates)
    assert projection.metric_candidates[2].canonical_metric_id == "metric.average_daily_turnover"


def test_projection_falls_back_to_canonical_catalog_without_fabricating_source_support(
    scenario_dir: Path,
) -> None:
    package = load_package(scenario_dir / "ontology" / "package.yaml")

    projection = build_authoring_projection(
        package=package,
        intake={"contract": "empty-intake/v1"},
        scenario_dir=scenario_dir,
    )

    assert len(projection.requirements) == len(package.questions)
    assert len(projection.metric_candidates) == len(package.metrics)
    assert {item.support_class for item in projection.metric_candidates} == {
        "CANONICAL_DRAFT"
    }


def test_narrative_transcriptions_remain_builder_evidence_without_requiring_legacy_rows(
    scenario_dir: Path,
) -> None:
    package = load_package(scenario_dir / "ontology" / "package.yaml")
    requirement_text = "# Business requirements\n\nDescribe the process and seven questions."
    metric_text = (
        "# Metric logic\n\nEach metric is described in its own section.\n\n"
        "| M-01 | M-03 |\n|---|---|\n| M-02 | M-03 |"
    )
    intake = {
        "assets": [
            {
                "asset_id": "source.requirements",
                "kind": "requirement_transcription",
                "locator": "inline/requirements.md",
                "checksum": hashlib.sha256(requirement_text.encode()).hexdigest(),
                "content_text": requirement_text,
            },
            {
                "asset_id": "source.metrics",
                "kind": "metric_transcription",
                "locator": "inline/metrics.md",
                "checksum": hashlib.sha256(metric_text.encode()).hexdigest(),
                "content_text": metric_text,
            },
        ]
    }

    projection = build_authoring_projection(
        package=package,
        intake=intake,
        scenario_dir=scenario_dir,
    )

    assert projection.source_mode == "CANONICAL_FALLBACK"
    assert all(
        item.support_class == "CANONICAL_DRAFT"
        for item in projection.metric_candidates
    )


def test_metric_matching_accepts_a_single_language_name(
    package,
) -> None:
    metric = package.metrics[0]
    english_name = metric.name.en or "English-only metric"
    english_only = metric.model_copy(
        update={"name": metric.name.model_copy(update={"en": english_name, "zh": None})}
    )
    single_language_package = package.model_copy(
        update={"metrics": (english_only, *package.metrics[1:])}
    )

    assert _canonical_metric_target(
        single_language_package,
        metric_key="M-99",
        name=english_name,
    ) == metric.id


def test_combined_xlsx_template_projects_cash_requirements_and_metrics_with_exact_cells(
    tmp_path: Path,
) -> None:
    workbook = Workbook()
    requirements = workbook.active
    requirements.title = "01_Requirements_Process"
    requirements.append(["No.", "What to Describe", "How to Complete", "Input"])
    requirements.append([1, "Scenario", "Guidance", "Cash Trading"])
    requirements.append([None, None, None, None])
    requirements.append(["No.", "Business Question / Analytical Task to Answer", "Expected Output", "Use"])
    requirements.append([1, "Show self trades", "Timeline by participant", "Investigation"])
    requirements.append([2, "Show latency", "p50 and p95 by date", "Operations"])
    metrics = workbook.create_sheet("02_Metric_Logic")
    metrics.append(["Metric Name", "Business Definition and Purpose", "Calculation Formula / Step-by-Step Logic", "Data Scope and Conventions", "Output, Exception Handling and Validation"])
    metrics.append(["Trade capture latency", "Receive minus transaction time", "Calculate milliseconds", "Valid active trades", "Milliseconds; reject negative values"])
    metrics.append(["Potential self-trade rate", "Same normalized participant on both sides", "Candidate count / eligible trades", "Comparable period", "Percentage; clarify zero denominator"])
    payload = BytesIO()
    workbook.save(payload)

    source_library = StudioSourceLibraryService(
        FileSourceLibraryStore(tmp_path / "sources")
    )
    version = source_library.register(
        workspace_id="workspace.cash-trading.reference",
        kind="requirement_transcription",
        title="Cash Trading requirements and metrics",
        original_name="cash-input.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=payload.getvalue(),
    )
    package = load_package(
        DEFAULT_CASH_TRADING_SCENARIO_DIR / "ontology" / "package.yaml"
    )

    projection = build_authoring_projection(
        package=package,
        intake={"assets": source_library.current_intake_assets("workspace.cash-trading.reference")},
        scenario_dir=DEFAULT_CASH_TRADING_SCENARIO_DIR,
    )

    assert version.processing_mode == "STRUCTURED_TRANSCRIPTION"
    assert projection.source_mode == "EXACT_TRANSCRIPTION"
    assert [item.question for item in projection.requirements] == [
        "Show self trades",
        "Show latency",
    ]
    assert [item.name for item in projection.metric_candidates] == [
        "Trade capture latency",
        "Potential self-trade rate",
    ]
    assert projection.metric_candidates[0].canonical_metric_id == "metric.trade_capture_latency_ms"
    assert projection.metric_candidates[1].canonical_metric_id == "metric.potential_self_trade_rate"
    assert [item.ontology_status for item in projection.metric_candidates] == [
        "REVIEWED",
        "REVIEWED",
    ]
    assert [item.runtime_status for item in projection.metric_candidates] == [
        "SUPPORTED",
        "SUPPORTED",
    ]
    assert all(
        item.governance_status == "REVIEWED_WITH_ASSUMPTIONS"
        for item in projection.metric_candidates
    )
    assert all(item.source_anchor is not None for item in projection.requirements)
    assert projection.requirements[0].source_anchor.locator_kind == "XLSX_ROW"
    assert projection.requirements[0].source_anchor.sheet_name == "01_Requirements_Process"
    assert projection.metric_candidates[0].source_anchor.cell_range == "A2:E2"
