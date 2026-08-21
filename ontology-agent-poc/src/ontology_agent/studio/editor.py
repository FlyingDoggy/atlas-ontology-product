from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import Field, model_validator

from ..contracts import Sha256
from ..io import file_checksum
from ..models import StrictModel


EDITOR_DESCRIPTOR_CONTRACT = "studio-editor-descriptor/v1"
DRAFT_OPERATIONS_CONTRACT = "studio-draft-operations/v1"


class EditorDescriptorError(RuntimeError):
    pass


class LocalizedText(StrictModel):
    en: str = Field(min_length=1, max_length=500)
    zh: str = Field(min_length=1, max_length=500)


class EditorOption(StrictModel):
    value: str = Field(min_length=1, max_length=255)
    label: LocalizedText


class EditorFieldDescriptor(StrictModel):
    path: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    label: LocalizedText
    help: LocalizedText
    control: Literal["TEXTAREA", "SELECT", "CHECKBOX", "MULTI_SELECT"]
    value_kind: Literal["STRING", "BOOLEAN", "STRING_LIST"]
    required: bool
    options: tuple[EditorOption, ...] = ()

    @model_validator(mode="after")
    def validate_control_shape(self) -> EditorFieldDescriptor:
        expected_kind = {
            "TEXTAREA": "STRING",
            "SELECT": "STRING",
            "CHECKBOX": "BOOLEAN",
            "MULTI_SELECT": "STRING_LIST",
        }[self.control]
        if self.value_kind != expected_kind:
            raise ValueError("Editor control and value kind do not match")
        if self.control in {"SELECT", "MULTI_SELECT"} and not self.options:
            raise ValueError("Choice controls require a closed option set")
        if self.control in {"TEXTAREA", "CHECKBOX"} and self.options:
            raise ValueError("Free-text and checkbox controls cannot declare options")
        values = [item.value for item in self.options]
        if len(values) != len(set(values)):
            raise ValueError("Editor option values must be unique")
        return self


class ExactLocalComponentRef(StrictModel):
    locator: str = Field(min_length=1, max_length=500)
    sha256: Sha256

    @model_validator(mode="after")
    def validate_locator(self) -> ExactLocalComponentRef:
        candidate = PurePosixPath(self.locator)
        if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
            raise ValueError("Editor component locator is unsafe")
        return self


class StudioEditorDescriptorV1(StrictModel):
    contract: Literal["studio-editor-descriptor/v1"] = EDITOR_DESCRIPTOR_CONTRACT
    descriptor_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    workspace_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    studio_adapter_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._@-]*$")
    draft_schema_version: str = Field(min_length=1, max_length=255)
    operations_contract: Literal["studio-draft-operations/v1"] = (
        DRAFT_OPERATIONS_CONTRACT
    )
    title: LocalizedText
    description: LocalizedText
    semantic_slot_manifest: ExactLocalComponentRef
    fields: tuple[EditorFieldDescriptor, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_field_set(self) -> StudioEditorDescriptorV1:
        paths = [item.path for item in self.fields]
        if len(paths) != len(set(paths)):
            raise ValueError("Editor field paths must be unique")
        return self


class DraftOperationV1(StrictModel):
    path: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    value: str | bool | tuple[str, ...]


class DraftOperationsV1(StrictModel):
    contract: Literal["studio-draft-operations/v1"] = DRAFT_OPERATIONS_CONTRACT
    expected_revision: int = Field(ge=1)
    operations: tuple[DraftOperationV1, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_unique_paths(self) -> DraftOperationsV1:
        paths = [item.path for item in self.operations]
        if len(paths) != len(set(paths)):
            raise ValueError("A draft operation path may be supplied only once")
        return self


def load_editor_descriptor(
    path: Path,
    *,
    component_root: Path,
) -> StudioEditorDescriptorV1:
    try:
        descriptor = StudioEditorDescriptorV1.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise EditorDescriptorError("Studio editor descriptor is invalid") from exc

    root = component_root.resolve()
    candidate = PurePosixPath(descriptor.semantic_slot_manifest.locator)
    slot_path = root.joinpath(*candidate.parts).resolve()
    if not slot_path.is_relative_to(root) or not slot_path.is_file():
        raise EditorDescriptorError("Editor semantic slot manifest is unavailable")
    if file_checksum(slot_path) != descriptor.semantic_slot_manifest.sha256:
        raise EditorDescriptorError("Editor semantic slot manifest digest mismatch")
    try:
        slot_payload: dict[str, Any] = json.loads(slot_path.read_text(encoding="utf-8"))
        slot_paths = tuple(str(item["draft_path"]) for item in slot_payload["slots"])
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise EditorDescriptorError("Editor semantic slot manifest cannot be read") from exc
    if slot_paths != tuple(field.path for field in descriptor.fields):
        raise EditorDescriptorError("Editor fields do not close the semantic slot set")
    return descriptor
