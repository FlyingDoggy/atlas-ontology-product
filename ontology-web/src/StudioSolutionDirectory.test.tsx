import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { SolutionCatalog } from "./api";
import { LanguageSwitch, UiLocaleProvider } from "./i18n";
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

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe("StudioSolutionDirectory", () => {
  it("opens the guided document-build entry and exposes installed solutions as copyable references", () => {
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
    fireEvent.click(screen.getByLabelText("管理ADT参考分析"));
    expect(screen.getByRole("button", { name: "复制为可编辑方案" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "编辑信息" })).toBeNull();
    expect(screen.queryByRole("button", { name: "归档" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "新建解决方案" }));
    expect(screen.getByRole("dialog", { name: "新建解决方案" })).toBeTruthy();
    expect(screen.getByText("从材料构建")).toBeTruthy();
    expect(screen.getByText("空白创建")).toBeTruthy();
    expect(screen.getByText("复制参考方案")).toBeTruthy();
    expect(screen.queryByText("导入 Ontology Package")).toBeNull();
    expect(screen.getByRole("radio", { name: /从材料构建/ })).toHaveProperty("checked", true);
    expect(screen.getByRole("radio", { name: /空白创建/ })).toHaveProperty("checked", false);
    expect(screen.getByRole("region", { name: "Ontology 构建材料说明" })).toBeTruthy();
    expect(screen.getByText("需求与分析流程")).toBeTruthy();
    expect(screen.getByText("指标逻辑")).toBeTruthy();
    expect(screen.getByText("数据模型与字典")).toBeTruthy();
    expect(screen.getByText("现有 SQL（可选）")).toBeTruthy();
    expect(screen.getByRole("button", { name: "创建并登记材料" })).toBeTruthy();
    expect(screen.queryByText(/参考版本 v1.4.0/)).toBeNull();
    fireEvent.click(screen.getByRole("radio", { name: /复制参考方案/ }));
    expect(screen.getByText(/参考版本 v1.4.0/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "创建 Draft Solution" })).toBeTruthy();
  });

  it("renders the complete create-solution workflow in English after switching locale", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    queryClient.setQueryData(["agent-solution-catalog", "directory"], {
      contract: "agent-solution-catalog/v1",
      solutions: [{ ...solution, runtime: { state: "ACTIVE", environment_id: "adt-poc", snapshot_checksum: digest } }],
    });
    render(
      <UiLocaleProvider>
        <LanguageSwitch />
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <StudioSolutionDirectory
              catalog={{ contract: "studio-solution-catalog/v1", solutions: [solution] }}
              selectedSolutionId={solution.solution_id}
            />
          </MemoryRouter>
        </QueryClientProvider>
      </UiLocaleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    fireEvent.click(screen.getByRole("button", { name: "Create solution" }));

    const dialog = screen.getByRole("dialog", { name: "Create solution" });
    expect(screen.getByText("Creation method")).toBeTruthy();
    expect(screen.getByText("Build from source materials")).toBeTruthy();
    expect(screen.getByText("Create from blank")).toBeTruthy();
    expect(screen.getByText("Copy a reference solution")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Ontology build material guidance" })).toBeTruthy();
    expect(screen.getByText("Materials required for the build")).toBeTruthy();
    expect(screen.getByText("Requirements and analysis flow")).toBeTruthy();
    expect(screen.getByText("Metric logic")).toBeTruthy();
    expect(screen.getByText("Data model and dictionary")).toBeTruthy();
    expect(screen.getByText("Existing SQL (optional)")).toBeTruthy();
    expect(screen.getByText("Simplified Chinese name")).toBeTruthy();
    expect(screen.getByText("English name")).toBeTruthy();
    expect(screen.getByText("Business scenario description")).toBeTruthy();
    expect(screen.getByText("Owner")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Create and register materials" })).toBeTruthy();
    expect(dialog.textContent).not.toMatch(/[\u3400-\u4dbf\u4e00-\u9fff]/);

    fireEvent.click(screen.getByRole("radio", { name: /Copy a reference solution/ }));
    expect(screen.getByText("Reference solution")).toBeTruthy();
    expect(screen.getByText(/Reference version v1.4.0/)).toBeTruthy();
    expect(screen.getByRole("option", { name: "ADT Reference Analysis" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Create Draft solution" })).toBeTruthy();
    expect(dialog.textContent).not.toMatch(/[\u3400-\u4dbf\u4e00-\u9fff]/);
  });
});
