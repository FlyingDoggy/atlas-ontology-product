import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { SolutionCatalog } from "./api";
import { StudioSolutionDirectory } from "./StudioSolutionDirectory";

const digest = "a".repeat(64);

const solution = {
  solution_id: "ontology.exchange_analytics.adt",
  solution_version: "1.4.0",
  semantic_source_version: "1.2.0",
  scenario_id: "scenario.adt_reference",
  workspace_id: "workspace.adt.reference",
  studio_adapter_id: "studio-adapter.adt.reference@1",
  classification: "constructed_synthetic",
  display_name: { en: "ADT Reference Analysis", zh: "ADT参考分析" },
  directory: {
    contract: "studio-solution-directory-entry/v1",
    solution_id: "ontology.exchange_analytics.adt",
    status: "ACTIVE",
    display_name: { en: "ADT Reference Analysis", zh: "ADT参考分析" },
    description: "ADT ontology solution",
    owner: "Ontology Product Team",
    creation_mode: "INSTALLED",
    template_solution_id: null,
    created_at: "2026-08-20T01:00:00Z",
    updated_at: "2026-08-20T01:00:00Z",
  },
  components: ["authoring_profile", "semantic_source", "agent_experience", "reference_evaluation"].map((kind) => ({
    component_id: `component.adt.${kind}`,
    kind,
    sha256: digest,
    media_type: "application/json",
  })),
  limitations: ["Synthetic only"],
  persistence: "postgresql-s3",
  subject_checksum: digest,
  artifact: {
    store: "s3-compatible",
    bucket: "ontology-artifacts",
    key: `studio/solution-registration/sha256/${digest}.json`,
    version_id: "version-1",
    sha256: digest,
    size_bytes: 1024,
    media_type: "application/json",
  },
  installable: true,
  resource_count: 23,
  bundle_checksum: digest,
} as unknown as SolutionCatalog["solutions"][number];

afterEach(cleanup);

describe("StudioSolutionDirectory", () => {
  it("renders the global solution layer and opens the real template workflow", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    queryClient.setQueryData(["agent-solution-catalog", "directory"], {
      contract: "agent-solution-catalog/v1",
      solutions: [{ ...solution, runtime: { state: "ACTIVE", environment_id: "adt-poc", snapshot_checksum: digest } }],
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <StudioSolutionDirectory
            catalog={{ contract: "studio-solution-catalog/v1", solutions: [solution] }}
            selectedSolutionId={solution.solution_id}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("heading", { name: "全部解决方案" })).toBeTruthy();
    expect(screen.getByText("ADT参考分析")).toBeTruthy();
    expect(screen.getByRole("link", { name: "打开" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "新建解决方案" }));
    expect(screen.getByRole("dialog", { name: "新建解决方案" })).toBeTruthy();
    expect(screen.getByText("从模板创建")).toBeTruthy();
    expect(screen.queryByText("导入 Ontology Package")).toBeNull();
    expect(screen.queryByText("空白创建")).toBeNull();
    expect(screen.getByText("当前通过已安装模板创建独立解决方案；源材料、运行记录和发布历史不会继承。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "创建 Draft Solution" })).toBeTruthy();
  });
});
