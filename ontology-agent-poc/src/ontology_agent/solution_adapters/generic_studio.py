from __future__ import annotations

from pathlib import Path

from ..studio.editor import (
    DraftOperationsV1,
    EditorDescriptorError,
    load_editor_descriptor,
)
from ..studio.generic_workspace import (
    GenericDraftWorkspace,
    GenericDraftWorkspaceService,
)
from ..studio.workspace import WorkspaceStateError


GENERIC_STUDIO_ADAPTER_ID = "studio-adapter.generic@1"


class GenericStudioAdapter:
    """Thin UI adapter for the case-neutral workspace.

    Domain assets are edited through typed package operations. The descriptor-driven
    form intentionally owns only the Solution intent, so adding a new business case
    never requires a Python adapter.
    """

    adapter_id = GENERIC_STUDIO_ADAPTER_ID

    def __init__(
        self,
        *,
        workspace: GenericDraftWorkspaceService,
        descriptor_path: Path,
        component_root: Path,
    ) -> None:
        self.workspace = workspace
        self.descriptor = load_editor_descriptor(
            descriptor_path,
            component_root=component_root,
        )
        if self.descriptor.studio_adapter_id != self.adapter_id:
            raise EditorDescriptorError(
                "Generic editor descriptor adapter identity mismatch"
            )

    def apply_operations(
        self,
        request: DraftOperationsV1,
        *,
        workspace_id: str,
    ) -> GenericDraftWorkspace:
        if workspace_id != self.descriptor.workspace_id:
            raise WorkspaceStateError("Editor descriptor workspace identity mismatch")
        if len(request.operations) != 1:
            raise WorkspaceStateError(
                "Generic metadata editor accepts one Solution intent operation"
            )
        operation = request.operations[0]
        if operation.path != "solution_intent" or not isinstance(operation.value, str):
            raise WorkspaceStateError("Unsupported generic metadata operation")
        return self.workspace.update_intent(
            operation.value,
            expected_revision=request.expected_revision,
            workspace_id=workspace_id,
        )
