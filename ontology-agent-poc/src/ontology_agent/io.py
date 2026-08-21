from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from .models import OntologyPackage


_module_project_root = Path(__file__).resolve().parents[2]
_working_project_root = Path.cwd().resolve()
DEFAULT_PROJECT_ROOT = Path(
    os.environ.get(
        "ONTOLOGY_AGENT_PROJECT_ROOT",
        str(
            _module_project_root
            if (_module_project_root / "scenarios").is_dir()
            else _working_project_root
        ),
    )
).resolve()
DEFAULT_SCENARIO_DIR = DEFAULT_PROJECT_ROOT / "scenarios" / "adt"
DEFAULT_CASH_TRADING_SCENARIO_DIR = (
    DEFAULT_PROJECT_ROOT / "scenarios" / "cash_trading"
)
DEFAULT_PACKAGE_PATH = DEFAULT_SCENARIO_DIR / "ontology" / "package.yaml"
DEFAULT_PUBLISHED_DIR = DEFAULT_PROJECT_ROOT / "published"
DEFAULT_STUDIO_DIR = DEFAULT_PROJECT_ROOT / "studio"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping at {path}")
    return value


def load_package(path: Path = DEFAULT_PACKAGE_PATH) -> OntologyPackage:
    return OntologyPackage.model_validate(load_yaml(path))


def canonical_dict(package: OntologyPackage) -> dict[str, Any]:
    return package.model_dump(mode="json", exclude_none=True)


def canonical_bytes(value: Any) -> bytes:
    def encode(item: Any) -> Any:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json", exclude_none=True)
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, Path):
            return str(item)
        raise TypeError(f"Unsupported canonical value: {type(item).__name__}")

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=encode,
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def package_checksum(package: OntologyPackage) -> str:
    return sha256_value(canonical_dict(package))


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
