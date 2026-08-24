from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .adt_scenario import (
    ADT_CERTIFICATION_PROFILE,
    adt_golden_certification,
    adt_synthetic_binding,
)
from .cash_trading_scenario import (
    CASH_CERTIFICATION_PROFILE,
    cash_trading_golden_certification,
    cash_trading_synthetic_binding,
)
from .evaluation import run_golden_suite
from .io import (
    DEFAULT_CASH_TRADING_SCENARIO_DIR,
    DEFAULT_PACKAGE_PATH,
    DEFAULT_PUBLISHED_DIR,
    DEFAULT_SCENARIO_DIR,
    load_package,
)
from .lifecycle import (
    AgentRuntime,
    FileResourceResolver,
)
from .publisher import PublicationError, publish_package
from .product_context import (
    ProductContextService,
    ProductInfrastructureError,
    ProductInfrastructureSettings,
)
from .release import StudioReleases
from .runtime import DEFAULT_EXECUTION_DIR, analyze_latest
from .studio.solutions import SolutionCatalogError, SolutionCatalogService
from .validation import validate_package


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ontology-based analytic agent reference POC")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="Validate ontology, mappings, data and RDF projection")
    commands.add_parser(
        "publish",
        help="Legacy demo composition: release, prepare, certify and activate",
    )
    commands.add_parser(
        "bootstrap-demo",
        help="Initialize the demo once without replacing an existing active snapshot",
    )
    commands.add_parser(
        "bootstrap-all-demo",
        help="Initialize every installed constructed-synthetic demo solution",
    )
    commands.add_parser(
        "bootstrap-cash-demo",
        help="Initialize only the Cash Trading demo solution",
    )
    commands.add_parser(
        "bootstrap-product-context",
        help="Import the current legacy active snapshot into PostgreSQL/S3 once",
    )
    commands.add_parser(
        "bootstrap-cash-product-context",
        help="Import the Cash Trading active snapshot into PostgreSQL/S3 once",
    )
    commands.add_parser(
        "bootstrap-solution-catalog",
        help="Register the exact ADT solution descriptor and component inventory",
    )
    commands.add_parser(
        "bootstrap-cash-solution-catalog",
        help="Register only the exact Cash Trading solution descriptor and component inventory",
    )
    construction_worker = commands.add_parser(
        "construction-worker",
        help="Consume durable Studio construction jobs from PostgreSQL",
    )
    construction_worker.add_argument("--once", action="store_true")
    construction_worker.add_argument("--poll-seconds", type=float, default=1.0)
    construction_worker.add_argument("--lease-seconds", type=int, default=120)
    commands.add_parser("release", help="Studio: publish a portable semantic release")
    gc = commands.add_parser(
        "gc-lifecycle-artifacts",
        help="Audit or delete old unreferenced release/runtime S3 versions",
    )
    gc.add_argument("--grace-seconds", type=int, default=86_400)
    gc.add_argument("--delete", action="store_true")
    prepare = commands.add_parser("prepare", help="Agent: bind a release to the local ADT runtime")
    prepare.add_argument("--version")
    prepare.add_argument("--without-certification", action="store_true")
    activate = commands.add_parser("activate", help="Agent: activate one prepared runtime snapshot")
    activate.add_argument("--snapshot", required=True)
    activate.add_argument("--environment", default="adt-poc")
    activate.add_argument("--without-certification-requirement", action="store_true")
    commands.add_parser("evaluate", help="Run all golden questions and the synthetic control oracle")
    analyze = commands.add_parser("analyze", help="Run a question against the published snapshot")
    analyze.add_argument("--question", required=True)
    analyze.add_argument("--role", default="MarketAnalyst")
    analyze.add_argument("--version")
    return parser


def _bootstrap_demo(studio: Any, agent: Any, package: Any) -> dict[str, Any]:
    return _bootstrap_scenario(
        studio,
        agent,
        package,
        environment_id="adt-poc",
        binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
        certification=adt_golden_certification(resource_root_id="adt-scenario"),
        certification_profile=ADT_CERTIFICATION_PROFILE,
    )


def _binding_for_release(studio: Any, release: Any, binding: Any) -> Any:
    """Project the installed binding onto the exact source contract of one release."""

    release_package = studio.load(release).package
    expected_source_ids = tuple(source.id for source in release_package.data_sources)
    resources_by_id: dict[str, Any] = {}
    for resource in binding.data_resources:
        if resource.source_id in resources_by_id:
            raise PublicationError(
                f"Bootstrap binding contains duplicate source {resource.source_id}"
            )
        resources_by_id[resource.source_id] = resource
    missing = [source_id for source_id in expected_source_ids if source_id not in resources_by_id]
    if missing:
        raise PublicationError(
            "Bootstrap binding cannot rebuild the installed release; missing sources: "
            + ", ".join(missing)
        )
    return binding.model_copy(
        update={
            "data_resources": tuple(
                resources_by_id[source_id] for source_id in expected_source_ids
            )
        }
    )


def _bootstrap_scenario(
    studio: Any,
    agent: Any,
    package: Any,
    *,
    environment_id: str,
    binding: Any,
    certification: Any,
    certification_profile: str,
    replace_different_release: bool = False,
) -> dict[str, Any]:
    current = agent.active_ref(environment_id, package.package_id)
    if current is not None:
        if replace_different_release and current.release.version != package.version:
            release = studio.publish(
                package,
                limitations=("constructed synthetic; not HKEX validated",),
            )
            prepared = agent.prepare(
                release.ref,
                binding=binding,
                certification=certification,
            )
            receipt = agent.activate(
                prepared.ref,
                expected_current=current,
                require_certification=certification_profile,
            )
            return {
                "status": "PASS",
                "outcome": "UPGRADED_PACKAGED_RELEASE",
                "previous_release": current.release.model_dump(mode="json"),
                "base_release": release.ref.model_dump(mode="json"),
                "prepared_snapshot": prepared.ref.model_dump(mode="json"),
                "active_snapshot": receipt.active.model_dump(mode="json"),
            }
        try:
            agent.open_active(environment_id, package.package_id)
        except PublicationError:
            prepared = agent.prepare(
                current.release,
                binding=_binding_for_release(studio, current.release, binding),
                certification=certification,
            )
            receipt = agent.activate(
                prepared.ref,
                expected_current=current,
                require_certification=certification_profile,
            )
            return {
                "status": "PASS",
                "outcome": "REBUILT_EXISTING_ACTIVE",
                "base_release": current.release.model_dump(mode="json"),
                "prepared_snapshot": prepared.ref.model_dump(mode="json"),
                "active_snapshot": receipt.active.model_dump(mode="json"),
            }
        outcome = (
            "ALREADY_INITIALIZED"
            if current.release.version == package.version
            else "PRESERVED_EXISTING_ACTIVE"
        )
        return {
            "status": "PASS",
            "outcome": outcome,
            "base_release": current.release.model_dump(mode="json"),
            "prepared_snapshot": current.model_dump(mode="json"),
            "active_snapshot": current.model_dump(mode="json"),
        }

    release = studio.publish(
        package,
        limitations=("constructed synthetic; not HKEX validated",),
    )
    prepared = agent.prepare(
        release.ref,
        binding=binding,
        certification=certification,
    )
    receipt = agent.activate(
        prepared.ref,
        expected_current=None,
        require_certification=certification_profile,
    )
    return {
        "status": "PASS",
        "outcome": "INITIALIZED",
        "base_release": release.ref.model_dump(mode="json"),
        "prepared_snapshot": prepared.ref.model_dump(mode="json"),
        "active_snapshot": receipt.active.model_dump(mode="json"),
    }


def main() -> None:
    args = _parser().parse_args()
    if args.command == "validate":
        package = load_package(DEFAULT_PACKAGE_PATH)
        report = validate_package(package, DEFAULT_SCENARIO_DIR, include_data=True)
        _print(report.model_dump(mode="json"))
        raise SystemExit(0 if report.status == "PASS" else 1)
    if args.command in {"bootstrap-solution-catalog", "bootstrap-cash-solution-catalog"}:
        try:
            settings = ProductInfrastructureSettings.from_env()
            scenario_dirs = (
                (DEFAULT_CASH_TRADING_SCENARIO_DIR,)
                if args.command == "bootstrap-cash-solution-catalog"
                else (DEFAULT_SCENARIO_DIR, DEFAULT_CASH_TRADING_SCENARIO_DIR)
            )
            records = tuple(
                SolutionCatalogService.from_settings(
                    settings,
                    manifest_path=scenario_dir / "solution-registration.json",
                    component_root=scenario_dir,
                ).bootstrap()
                for scenario_dir in scenario_dirs
            )
        except (ProductInfrastructureError, SolutionCatalogError) as exc:
            _print({"status": "FAIL", "error": str(exc)})
            raise SystemExit(1) from exc
        _print(
            {
                "status": "PASS",
                "solutions": [
                    {
                        "solution_id": record.subject.solution_id,
                        "solution_version": record.subject.solution_version,
                        "workspace_id": record.subject.workspace_id,
                        "subject_checksum": record.subject_checksum,
                        "installable": record.bundle is not None,
                        "resource_count": len(record.subject.resources),
                        "bundle_checksum": (
                            record.bundle.subject_checksum
                            if record.bundle is not None
                            else None
                        ),
                        "persistence": record.persistence,
                    }
                    for record in records
                ],
            }
        )
        return
    if args.command == "construction-worker":
        from .api import _studio_construction
        from .studio.construction_jobs import PostgresConstructionJobStore
        from .studio.construction_worker import ConstructionWorker

        try:
            settings = ProductInfrastructureSettings.from_env()
            worker = ConstructionWorker(
                jobs=PostgresConstructionJobStore.from_settings(settings),
                service_factory=_studio_construction,
                lease_seconds=args.lease_seconds,
            )
            if args.once:
                result = worker.process_one()
                _print(
                    {
                        "status": "IDLE" if result is None else "PASS",
                        "job": result.model_dump(mode="json") if result else None,
                    }
                )
            else:
                worker.run_forever(poll_seconds=args.poll_seconds)
        except (ProductInfrastructureError, RuntimeError) as exc:
            _print({"status": "FAIL", "error": str(exc)})
            raise SystemExit(1) from exc
        return
    studio = StudioReleases(DEFAULT_PUBLISHED_DIR / "releases")
    agent = AgentRuntime(
        release_root=DEFAULT_PUBLISHED_DIR / "releases",
        runtime_root=DEFAULT_PUBLISHED_DIR / "runtime",
        resources=FileResourceResolver(
            {
                "adt-scenario": DEFAULT_SCENARIO_DIR,
                "cash-trading-scenario": DEFAULT_CASH_TRADING_SCENARIO_DIR,
            }
        ),
    )
    if args.command == "gc-lifecycle-artifacts":
        if agent.lifecycle_store is None:
            _print({"status": "FAIL", "error": "Durable lifecycle is not active"})
            raise SystemExit(1)
        try:
            report = agent.lifecycle_store.cleanup_orphans(
                grace_seconds=args.grace_seconds,
                delete=args.delete,
            )
        except PublicationError as exc:
            _print({"status": "FAIL", "error": str(exc)})
            raise SystemExit(1) from exc
        _print({"status": "PASS", **report})
        return
    if args.command == "release":
        package = load_package(DEFAULT_PACKAGE_PATH)
        try:
            release = studio.publish(
                package,
                limitations=("constructed synthetic; not HKEX validated",),
            )
        except PublicationError as exc:
            _print({"status": "FAIL", "error": str(exc)})
            raise SystemExit(1) from exc
        _print(
            {
                "status": "PASS",
                "release": release.ref.model_dump(mode="json"),
                "idempotent": release.idempotent,
            }
        )
        return
    if args.command == "bootstrap-demo":
        package = load_package(DEFAULT_PACKAGE_PATH)
        try:
            DEFAULT_EXECUTION_DIR.mkdir(parents=True, exist_ok=True)
            result = _bootstrap_demo(studio, agent, package)
        except PublicationError as exc:
            _print({"status": "FAIL", "error": str(exc)})
            raise SystemExit(1) from exc
        _print(result)
        return
    if args.command == "bootstrap-all-demo":
        adt_package = load_package(DEFAULT_PACKAGE_PATH)
        cash_package = load_package(
            DEFAULT_CASH_TRADING_SCENARIO_DIR / "ontology" / "package.yaml"
        )
        try:
            DEFAULT_EXECUTION_DIR.mkdir(parents=True, exist_ok=True)
            results = (
                _bootstrap_demo(studio, agent, adt_package),
                _bootstrap_scenario(
                    studio,
                    agent,
                    cash_package,
                    environment_id="cash-trading-poc",
                    binding=cash_trading_synthetic_binding(
                        resource_root_id="cash-trading-scenario"
                    ),
                    certification=cash_trading_golden_certification(
                        resource_root_id="cash-trading-scenario"
                    ),
                    certification_profile=CASH_CERTIFICATION_PROFILE,
                    replace_different_release=True,
                ),
            )
        except PublicationError as exc:
            _print({"status": "FAIL", "error": str(exc)})
            raise SystemExit(1) from exc
        _print({"status": "PASS", "solutions": list(results)})
        return
    if args.command == "bootstrap-cash-demo":
        cash_package = load_package(
            DEFAULT_CASH_TRADING_SCENARIO_DIR / "ontology" / "package.yaml"
        )
        try:
            DEFAULT_EXECUTION_DIR.mkdir(parents=True, exist_ok=True)
            result = _bootstrap_scenario(
                studio,
                agent,
                cash_package,
                environment_id="cash-trading-poc",
                binding=cash_trading_synthetic_binding(
                    resource_root_id="cash-trading-scenario"
                ),
                certification=cash_trading_golden_certification(
                    resource_root_id="cash-trading-scenario"
                ),
                certification_profile=CASH_CERTIFICATION_PROFILE,
                replace_different_release=True,
            )
        except PublicationError as exc:
            _print({"status": "FAIL", "error": str(exc)})
            raise SystemExit(1) from exc
        _print(result)
        return
    if args.command in {"bootstrap-product-context", "bootstrap-cash-product-context"}:
        try:
            environment_id, package_id = (
                ("cash-trading-poc", "ontology.exchange_analytics.cash_trading")
                if args.command == "bootstrap-cash-product-context"
                else ("adt-poc", "ontology.exchange_analytics.adt")
            )
            active = agent.open_active(environment_id, package_id)
            settings = ProductInfrastructureSettings.from_env()
            context, idempotent = ProductContextService.from_settings(
                settings
            ).import_initial(active.snapshot)
        except (PublicationError, ProductInfrastructureError) as exc:
            _print({"status": "FAIL", "error": str(exc)})
            raise SystemExit(1) from exc
        _print(
            {
                "status": "PASS",
                "idempotent": idempotent,
                "context_id": context.subject.context_id,
                "subject_checksum": context.subject_checksum,
                "artifact": context.artifact.model_dump(mode="json")
                if context.artifact
                else None,
            }
        )
        return
    if args.command == "prepare":
        package = load_package(DEFAULT_PACKAGE_PATH)
        version = args.version or package.version
        try:
            release_ref = studio.resolve(package.package_id, version)
            prepared = agent.prepare(
                release_ref,
                binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
                certification=(
                    None
                    if args.without_certification
                    else adt_golden_certification(resource_root_id="adt-scenario")
                ),
            )
        except PublicationError as exc:
            _print({"status": "FAIL", "error": str(exc)})
            raise SystemExit(1) from exc
        _print(
            {
                "status": "PASS",
                "snapshot": prepared.ref.model_dump(mode="json"),
                "readiness": prepared.readiness.model_dump(mode="json"),
                "idempotent": prepared.idempotent,
            }
        )
        return
    if args.command == "activate":
        try:
            snapshot = agent.resolve_prepared(args.environment, args.snapshot)
            receipt = agent.activate(
                snapshot,
                require_certification=(
                    None
                    if args.without_certification_requirement
                    else ADT_CERTIFICATION_PROFILE
                ),
            )
        except PublicationError as exc:
            _print({"status": "FAIL", "error": str(exc)})
            raise SystemExit(1) from exc
        _print({"status": "PASS", "activation": receipt.model_dump(mode="json")})
        return
    if args.command == "publish":
        package = load_package(DEFAULT_PACKAGE_PATH)
        try:
            publication = publish_package(package, DEFAULT_SCENARIO_DIR, DEFAULT_PUBLISHED_DIR)
        except PublicationError as exc:
            _print({"status": "FAIL", "error": str(exc)})
            raise SystemExit(1) from exc
        _print(
            {
                "status": "PASS",
                "package_id": publication.package_id,
                "version": publication.version,
                "package_checksum": publication.package_checksum,
                "snapshot_checksum": publication.snapshot_checksum,
                "path": str(publication.path),
                "idempotent": publication.idempotent,
            }
        )
        return
    if args.command == "evaluate":
        try:
            snapshot = agent.open_active(
                "adt-poc", "ontology.exchange_analytics.adt"
            ).snapshot
        except PublicationError as exc:
            _print({"status": "FAIL", "error": "No compatible governed snapshot"})
            raise SystemExit(1) from exc
        report = run_golden_suite(
            snapshot,
            execution_dir=Path(DEFAULT_SCENARIO_DIR).parents[1] / "outputs" / "executions",
        )
        _print(report)
        raise SystemExit(0 if report["status"] == "PASS" else 1)
    response = analyze_latest(
        question=args.question,
        role=args.role,
        version=args.version,
    )
    _print(response.model_dump(mode="json"))
    raise SystemExit(0 if response.status in {"ANSWERED", "CLARIFY", "REFUSED"} else 1)


if __name__ == "__main__":
    main()
