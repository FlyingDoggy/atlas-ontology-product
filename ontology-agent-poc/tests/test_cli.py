from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from ontology_agent import cli
from ontology_agent.cli import _bootstrap_demo, _bootstrap_scenario
from ontology_agent.contracts import ReleaseRef, RuntimeSnapshotRef
from ontology_agent.io import DEFAULT_PACKAGE_PATH, load_package
from ontology_agent.publisher import PublicationError


def test_bootstrap_rebuilds_an_incompatible_active_snapshot_without_semantic_rollback() -> None:
    package = load_package(DEFAULT_PACKAGE_PATH)
    legacy_package = package.model_copy(
        update={"data_sources": package.data_sources[:-1]}
    )
    release = ReleaseRef(
        package_id=package.package_id,
        version="1.2.3",
        checksum="a" * 64,
    )
    current = RuntimeSnapshotRef(
        environment_id="adt-poc",
        release=release,
        checksum="b" * 64,
    )
    rebuilt = current.model_copy(update={"checksum": "c" * 64})

    class FakeStudio:
        def publish(self, *args, **kwargs):
            raise AssertionError("An existing semantic release must not be replaced")

        def load(self, release_ref):
            assert release_ref == release
            return SimpleNamespace(package=legacy_package)

    class FakeAgent:
        activated_expected = None

        def active_ref(self, environment_id, package_id):
            return current

        def open_active(self, environment_id, package_id):
            raise PublicationError("Runtime adapter build no longer matches the snapshot")

        def prepare(self, release_ref, *, binding, certification):
            assert release_ref == release
            assert {item.source_id for item in binding.data_resources} == {
                source.id for source in legacy_package.data_sources
            }
            return SimpleNamespace(ref=rebuilt)

        def activate(self, snapshot, *, expected_current, require_certification):
            assert snapshot == rebuilt
            self.activated_expected = expected_current
            return SimpleNamespace(active=rebuilt)

    agent = FakeAgent()
    result = _bootstrap_demo(FakeStudio(), agent, package)

    assert result["outcome"] == "REBUILT_EXISTING_ACTIVE"
    assert result["base_release"]["version"] == "1.2.3"
    assert result["active_snapshot"]["checksum"] == "c" * 64
    assert agent.activated_expected == current


def test_packaged_scenario_upgrade_publishes_prepares_and_cas_activates_new_release() -> None:
    package = load_package(DEFAULT_PACKAGE_PATH)
    old_release = ReleaseRef(
        package_id=package.package_id,
        version="1.1.0",
        checksum="a" * 64,
    )
    current = RuntimeSnapshotRef(
        environment_id="adt-poc",
        release=old_release,
        checksum="b" * 64,
    )
    new_release = ReleaseRef(
        package_id=package.package_id,
        version=package.version,
        checksum="c" * 64,
    )
    prepared = RuntimeSnapshotRef(
        environment_id="adt-poc",
        release=new_release,
        checksum="d" * 64,
    )

    class FakeStudio:
        def publish(self, candidate, *, limitations):
            assert candidate == package
            assert limitations == ("constructed synthetic; not customer validated",)
            return SimpleNamespace(ref=new_release)

        def load(self, *args, **kwargs):
            raise AssertionError("The replaced release does not need rebuilding")

    class FakeAgent:
        def active_ref(self, environment_id, package_id):
            assert environment_id == "adt-poc"
            assert package_id == package.package_id
            return current

        def open_active(self, *args, **kwargs):
            raise AssertionError("An explicit packaged upgrade must not reuse the old runtime")

        def prepare(self, release_ref, *, binding, certification):
            assert release_ref == new_release
            return SimpleNamespace(ref=prepared)

        def activate(self, snapshot, *, expected_current, require_certification):
            assert snapshot == prepared
            assert expected_current == current
            assert require_certification == "adt-golden-v1"
            return SimpleNamespace(active=prepared)

    result = _bootstrap_scenario(
        FakeStudio(),
        FakeAgent(),
        package,
        environment_id="adt-poc",
        binding=cli.adt_synthetic_binding(resource_root_id="adt-scenario"),
        certification=cli.adt_golden_certification(resource_root_id="adt-scenario"),
        certification_profile="adt-golden-v1",
        replace_different_release=True,
    )

    assert result["outcome"] == "UPGRADED_PACKAGED_RELEASE"
    assert result["previous_release"]["version"] == "1.1.0"
    assert result["base_release"]["version"] == package.version


def test_evaluate_reads_the_active_snapshot_instead_of_the_latest_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_snapshot = object()
    calls: list[tuple[str, str]] = []

    class FakeAgent:
        def __init__(self, **kwargs):
            del kwargs

        def open_active(self, environment_id: str, package_id: str):
            calls.append((environment_id, package_id))
            return SimpleNamespace(snapshot=active_snapshot)

    monkeypatch.setattr(cli, "AgentRuntime", FakeAgent)
    monkeypatch.setattr(cli, "StudioReleases", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        cli,
        "run_golden_suite",
        lambda snapshot, **kwargs: {
            "status": "PASS",
            "snapshot_is_active": snapshot is active_snapshot,
        },
    )
    monkeypatch.setattr(sys, "argv", ["ontology-agent", "evaluate"])

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 0
    assert calls == [("adt-poc", "ontology.exchange_analytics.adt")]
