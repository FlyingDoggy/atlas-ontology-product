from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ontology_agent.io import DEFAULT_SCENARIO_DIR, load_package
from ontology_agent.models import OntologyPackage
from ontology_agent.publisher import VerifiedSnapshot, load_verified_snapshot, publish_package


@pytest.fixture()
def scenario_dir(tmp_path: Path) -> Path:
    destination = tmp_path / "adt"
    shutil.copytree(DEFAULT_SCENARIO_DIR, destination)
    return destination


@pytest.fixture()
def package(scenario_dir: Path) -> OntologyPackage:
    return load_package(scenario_dir / "ontology" / "package.yaml")


@pytest.fixture()
def snapshot(
    package: OntologyPackage, scenario_dir: Path, tmp_path: Path
) -> VerifiedSnapshot:
    root = tmp_path / "published"
    publish_package(package, scenario_dir, root)
    return load_verified_snapshot(
        package.package_id,
        scenario_dir=scenario_dir,
        published_root=root,
    )
