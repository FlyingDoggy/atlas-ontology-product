from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from ..contracts import Sha256
from ..io import sha256_value
from ..models import StrictModel


class SkillPackageError(RuntimeError):
    """A versioned Agent Skill Package is missing, unsafe or invalid."""


class AgentSkillManifestV1(StrictModel):
    contract: Literal["agent-skill-package/v1"] = "agent-skill-package/v1"
    skill_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    role: Literal["BUILDER", "REVIEWER"]
    entrypoint: str
    output_schema: str
    references: tuple[str, ...] = ()
    evals: tuple[str, ...] = ()
    tool_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    max_iterations: int = Field(ge=1, le=20)
    max_model_calls: int = Field(ge=1, le=20)
    human_review_required: Literal[True] = True
    direct_draft_write: Literal[False] = False

    @model_validator(mode="after")
    def unique_tools_and_paths(self) -> AgentSkillManifestV1:
        if len(self.tool_ids) != len(set(self.tool_ids)):
            raise ValueError("Skill tools must be unique")
        paths = (self.entrypoint, self.output_schema, *self.references, *self.evals)
        for value in paths:
            path = PurePosixPath(value)
            if path.is_absolute() or not path.parts or ".." in path.parts:
                raise ValueError("Skill resource path is unsafe")
        return self


class AgentSkillManifestV2(StrictModel):
    """Agentic method package. It teaches judgment; server tools govern effects."""

    contract: Literal["agent-skill-package/v2"] = "agent-skill-package/v2"
    skill_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    role: Literal["BUILDER", "REVIEWER"]
    entrypoint: str
    references: tuple[str, ...] = ()
    evals: tuple[str, ...] = ()
    tool_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    completion_tool_id: Literal["run.request_completion"]
    max_model_calls: int = Field(ge=1, le=500)
    max_tool_calls: int = Field(ge=1, le=1000)
    human_review_required: Literal[True] = True
    direct_draft_write: Literal[False] = False

    @model_validator(mode="after")
    def unique_tools_and_paths(self) -> AgentSkillManifestV2:
        if len(self.tool_ids) != len(set(self.tool_ids)):
            raise ValueError("Skill tools must be unique")
        if self.completion_tool_id not in self.tool_ids:
            raise ValueError("Agentic skill must declare its completion tool")
        paths = (self.entrypoint, *self.references, *self.evals)
        for value in paths:
            path = PurePosixPath(value)
            if path.is_absolute() or not path.parts or ".." in path.parts:
                raise ValueError("Skill resource path is unsafe")
        return self


class LoadedSkillPackageV1(StrictModel):
    contract: Literal["loaded-agent-skill-package/v1"] = (
        "loaded-agent-skill-package/v1"
    )
    manifest: AgentSkillManifestV1
    instructions: str = Field(min_length=1)
    reference_texts: dict[str, str]
    output_schema: dict[str, object]
    resource_checksums: dict[str, Sha256]
    package_checksum: Sha256


class LoadedSkillPackageV2(StrictModel):
    contract: Literal["loaded-agent-skill-package/v2"] = (
        "loaded-agent-skill-package/v2"
    )
    manifest: AgentSkillManifestV2
    instructions: str = Field(min_length=1)
    reference_texts: dict[str, str]
    eval_texts: dict[str, str]
    resource_checksums: dict[str, Sha256]
    package_checksum: Sha256


def default_skill_root() -> Path:
    configured_root = os.environ.get("ONTOLOGY_SKILL_ROOT", "").strip()
    if configured_root:
        return Path(configured_root)
    project_root = os.environ.get("ONTOLOGY_AGENT_PROJECT_ROOT", "").strip()
    if project_root:
        return Path(project_root) / "skills"
    return Path(__file__).resolve().parents[3] / "skills"


def load_skill_package(
    skill_id: str,
    version: str,
    *,
    root: Path | None = None,
) -> LoadedSkillPackageV1 | LoadedSkillPackageV2:
    package_root = ((root or default_skill_root()) / skill_id / version).resolve()
    manifest_path = package_root / "manifest.json"
    try:
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_contract = manifest_payload.get("contract")
        if manifest_contract == "agent-skill-package/v1":
            manifest: AgentSkillManifestV1 | AgentSkillManifestV2 = (
                AgentSkillManifestV1.model_validate(manifest_payload)
            )
        elif manifest_contract == "agent-skill-package/v2":
            manifest = AgentSkillManifestV2.model_validate(manifest_payload)
        else:
            raise ValueError("Unsupported Agent Skill Package contract")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SkillPackageError("Skill manifest is unavailable or invalid") from exc
    if manifest.skill_id != skill_id or manifest.version != version:
        raise SkillPackageError("Skill package identity mismatch")

    declared = (
        (manifest.entrypoint, manifest.output_schema, *manifest.references, *manifest.evals)
        if isinstance(manifest, AgentSkillManifestV1)
        else (manifest.entrypoint, *manifest.references, *manifest.evals)
    )
    contents: dict[str, bytes] = {"manifest.json": manifest_path.read_bytes()}
    for relative in declared:
        path = package_root.joinpath(*PurePosixPath(relative).parts).resolve()
        if not path.is_relative_to(package_root) or not path.is_file():
            raise SkillPackageError(f"Skill resource is unavailable: {relative}")
        try:
            contents[relative] = path.read_bytes()
        except OSError as exc:
            raise SkillPackageError(f"Skill resource is unreadable: {relative}") from exc
    try:
        instructions = contents[manifest.entrypoint].decode("utf-8")
        reference_texts = {
            name: contents[name].decode("utf-8") for name in manifest.references
        }
        output_schema = (
            json.loads(contents[manifest.output_schema].decode("utf-8"))
            if isinstance(manifest, AgentSkillManifestV1)
            else None
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillPackageError("Skill text or output schema is invalid") from exc
    if isinstance(manifest, AgentSkillManifestV1) and not isinstance(output_schema, dict):
        raise SkillPackageError("Skill output schema must be a JSON object")
    checksums = {
        name: hashlib.sha256(body).hexdigest()
        for name, body in sorted(contents.items())
    }
    package_checksum = sha256_value(
        [{"path": name, "sha256": digest} for name, digest in checksums.items()]
    )
    if isinstance(manifest, AgentSkillManifestV1):
        return LoadedSkillPackageV1(
            manifest=manifest,
            instructions=instructions,
            reference_texts=reference_texts,
            output_schema=output_schema or {},
            resource_checksums=checksums,
            package_checksum=package_checksum,
        )
    return LoadedSkillPackageV2(
        manifest=manifest,
        instructions=instructions,
        reference_texts=reference_texts,
        eval_texts={name: contents[name].decode("utf-8") for name in manifest.evals},
        resource_checksums=checksums,
        package_checksum=package_checksum,
    )
