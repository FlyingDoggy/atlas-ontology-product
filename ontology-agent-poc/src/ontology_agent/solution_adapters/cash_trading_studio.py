from __future__ import annotations

from pathlib import Path

from ..studio.cash_workspace import (
    CashDraftUpdate,
    CashDraftWorkspace,
    CashTradingDraftWorkspaceService,
)
from ..studio.editor import (
    DraftOperationsV1,
    EditorDescriptorError,
    EditorFieldDescriptor,
    load_editor_descriptor,
)
from ..studio.workspace import WorkspaceStateError


CASH_TRADING_STUDIO_ADAPTER_ID = "studio-adapter.cash-trading.reference@1"


class CashTradingStudioAdapter:
    adapter_id = CASH_TRADING_STUDIO_ADAPTER_ID

    def __init__(
        self,
        *,
        workspace: CashTradingDraftWorkspaceService,
        descriptor_path: Path,
        component_root: Path,
    ) -> None:
        self.workspace = workspace
        self.descriptor = load_editor_descriptor(
            descriptor_path, component_root=component_root
        )
        if self.descriptor.studio_adapter_id != self.adapter_id:
            raise EditorDescriptorError(
                "Cash Trading editor descriptor adapter identity mismatch"
            )

    @staticmethod
    def _validate_value(field: EditorFieldDescriptor, value: object) -> object:
        if field.value_kind == "STRING":
            if not isinstance(value, str) or not value:
                raise WorkspaceStateError(f"{field.path} requires a non-empty string")
            normalized: object = value
        elif field.value_kind == "BOOLEAN":
            if type(value) is not bool:
                raise WorkspaceStateError(f"{field.path} requires a boolean")
            normalized = value
        else:
            if not isinstance(value, tuple) or not value or not all(
                isinstance(item, str) and item for item in value
            ):
                raise WorkspaceStateError(
                    f"{field.path} requires a non-empty string list"
                )
            if len(value) != len(set(value)):
                raise WorkspaceStateError(f"{field.path} contains duplicate values")
            normalized = value
        allowed = {option.value for option in field.options}
        if allowed:
            proposed = set(normalized) if isinstance(normalized, tuple) else {normalized}
            if not proposed.issubset(allowed):
                raise WorkspaceStateError(f"{field.path} contains an unsupported value")
        return normalized

    def apply_operations(
        self,
        request: DraftOperationsV1,
        *,
        workspace_id: str,
    ) -> CashDraftWorkspace:
        if workspace_id != self.descriptor.workspace_id:
            raise WorkspaceStateError("Editor descriptor workspace identity mismatch")
        fields = {field.path: field for field in self.descriptor.fields}
        values: dict[str, object] = {}
        for operation in request.operations:
            field = fields.get(operation.path)
            if field is None:
                raise WorkspaceStateError("Draft operation path is not registered")
            values[operation.path] = self._validate_value(field, operation.value)
        return self.workspace.patch(
            CashDraftUpdate.model_validate(values),
            expected_revision=request.expected_revision,
            workspace_id=workspace_id,
        )

