from __future__ import annotations

from pathlib import Path, PurePosixPath

from ontology_agent.io import file_checksum, write_json
from ontology_agent.studio.solutions import (
    SolutionComponentDescriptor,
    SolutionDisplayName,
    SolutionRegistrationSubjectV1,
    SolutionResourceDescriptor,
    verify_solution_components,
)


MEDIA_TYPES = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".md": "text/markdown",
    ".parquet": "application/vnd.apache.parquet",
    ".sql": "text/sql",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    scenario_root = project_root / "scenarios" / "cash_trading"
    registration_path = scenario_root / "solution-registration.json"
    paths = [
        path
        for path in sorted(scenario_root.rglob("*"))
        if path.is_file()
        and path != registration_path
        and not any(
            part.startswith(".") or part == "__pycache__"
            for part in path.relative_to(scenario_root).parts
        )
    ]
    unsupported = [path for path in paths if path.suffix.lower() not in MEDIA_TYPES]
    if unsupported:
        raise RuntimeError(f"Unsupported scenario resources: {unsupported}")

    resources = tuple(
        SolutionResourceDescriptor(
            locator=path.relative_to(scenario_root).as_posix(),
            media_type=MEDIA_TYPES[path.suffix.lower()],
            sha256=file_checksum(path),
            size_bytes=path.stat().st_size,
        )
        for path in paths
    )
    by_locator = {item.locator: item for item in resources}

    component_specs = (
        (
            "component.cash-trading.semantic-source",
            "semantic_source",
            "ontology/package.yaml",
        ),
        (
            "component.cash-trading.authoring-profile",
            "authoring_profile",
            "authoring/editor-descriptor.json",
        ),
        (
            "component.cash-trading.agent-experience",
            "agent_experience",
            "llm/question-family.json",
        ),
        (
            "component.cash-trading.reference-evaluation",
            "reference_evaluation",
            "golden/questions.yaml",
        ),
    )
    components = tuple(
        SolutionComponentDescriptor(
            component_id=component_id,
            kind=kind,  # type: ignore[arg-type]
            locator=locator,
            media_type=by_locator[locator].media_type,  # type: ignore[arg-type]
            sha256=by_locator[locator].sha256,
        )
        for component_id, kind, locator in component_specs
    )
    subject = SolutionRegistrationSubjectV1(
        solution_id="ontology.exchange_analytics.cash_trading",
        solution_version="1.2.0",
        semantic_source_version="0.2.0",
        scenario_id="scenario.cash_trading_activity_monitoring",
        workspace_id="workspace.cash_trading.reference",
        studio_adapter_id="studio-adapter.cash-trading.reference@1",
        authoring_root_id="cash-trading-scenario",
        display_name=SolutionDisplayName(
            en="Cash Market Order and Trading Activity Monitoring",
            zh="现金市场订单与成交活动监控",
        ),
        components=components,
        resources=resources,
        limitations=(
            "Constructed-synthetic reference derived from Deloitte HK transcriptions; not HKEX validated",
            "Unconfirmed business rules remain linked to the assumption and external-confirmation registers",
            "Registration is a delivery/catalog record, not release or activation authority",
        ),
    )
    write_json(registration_path, subject.model_dump(mode="json"))
    verify_solution_components(subject, scenario_root)
    print(
        {
            "registration": str(registration_path),
            "resource_count": len(resources),
            "registration_sha256": file_checksum(registration_path),
        }
    )


if __name__ == "__main__":
    main()
