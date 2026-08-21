import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { ConstructionCandidate, StudioAuthoringProjection, StudioSourceLibrary, StudioWorkbench } from "./api";
import {
  MappingWorkbenchView,
  MetricCatalogView,
  OntologyGraphEditor,
  RequirementsCatalogView,
  SampleAndEnumView,
  SchemaCatalogView,
  SourceLibraryView,
  StudioVersionLineage,
  buildOntologyGraphProjection,
  graphImpactForNode,
} from "./StudioProductViews";
import { SemanticAssetCatalog } from "./SemanticAssetCatalog";

const governed = (id: string, zh: string) => ({
  id,
  version: "1.0.0",
  status: "confirmed" as const,
  name: { en: id, zh },
  definition: `${zh} definition`,
  owner: "actor.owner",
  sources: ["source.requirements"],
  decisions: [],
  tags: [],
});

const ontologyPackage = {
  package_id: "ontology.exchange_analytics.adt",
  version: "1.0.0",
  status: "confirmed",
  created_at: "2026-08-21T00:00:00Z",
  scenario: governed("scenario.adt", "ADT分析"),
  actors: [{ ...governed("actor.owner", "业务负责人"), roles: ["owner"] }],
  processes: [governed("process.monitoring", "市场活动监控")],
  sources: [{ id: "source.requirements", source_type: "requirement_transcription", title: "需求文档", locator: "requirements.md", owner: "actor.owner", captured_on: "2026-08-21", trust: "primary", notes: "" }],
  decisions: [],
  entities: [
    { ...governed("entity.trade", "成交"), primary_key: "property.trade.id", grain: "one trade", lifecycle: "executed" },
    { ...governed("entity.instrument", "证券"), primary_key: "property.instrument.id", grain: "one instrument", lifecycle: "listed" },
  ],
  properties: [{ ...governed("property.trade.market", "市场"), entity: "entity.trade", data_type: "enum", required: true, unit: null, enum_values: ["MAIN", "GEM"], null_meaning: "not_allowed" }],
  relationships: [{ ...governed("relationship.trade.instrument", "成交对应证券"), from_entity: "entity.trade", to_entity: "entity.instrument", predicate: "referencesInstrument", cardinality: "N:1" }],
  dimensions: [],
  rules: [],
  metrics: [
    { ...governed("metric.eligible_turnover", "合资格成交额"), metric_type: "base", base_entity: "entity.trade", result_grain: [], value_type: "decimal", unit: "HKD mn", aggregation_semantics: "additive", formula: { op: "sum" }, query: {}, allowed_dimensions: [], null_policy: "exclude", zero_denominator_policy: "not_applicable" },
    { ...governed("metric.trading_day_count", "交易日数"), metric_type: "base", base_entity: "entity.trade", result_grain: [], value_type: "integer", unit: "day", aggregation_semantics: "count", formula: { op: "count" }, query: {}, allowed_dimensions: [], null_policy: "exclude", zero_denominator_policy: "not_applicable" },
    { ...governed("metric.average_daily_turnover", "平均每日成交额"), metric_type: "derived", base_entity: "entity.trade", result_grain: [], value_type: "decimal", unit: "HKD mn/day", aggregation_semantics: "ratio_of_sums", formula: { op: "divide", args: [{ op: "metric_ref", ref: "metric.eligible_turnover" }, { op: "metric_ref", ref: "metric.trading_day_count" }] }, query: {}, allowed_dimensions: [], null_policy: "exclude", zero_denominator_policy: "refuse" },
  ],
  data_sources: [{ ...governed("data_source.trades", "成交数据"), protocol: "tabular/v1", tables: [{ name: "trades", grain: "one trade", primary_key: ["trade_id"], fields: [{ name: "trade_id", data_type: "string", nullable: false, description: "成交编号", unit: null }, { name: "market", data_type: "string", nullable: false, description: "市场", unit: null }] }] }],
  bindings: [{ ...governed("binding.trade.market", "市场字段映射"), logical_target: "property.trade.market", source: "data_source.trades", table: "trades", column: "market", data_type: "string", unit: null, transformation: "identity" }],
  joins: [{ ...governed("join.trades.self", "成交自关联"), left_source: "data_source.trades", left_table: "trades", right_source: "data_source.trades", right_table: "trades", keys: [{ left_column: "trade_id", right_column: "trade_id" }], expected_cardinality: "1:1", fanout_policy: "block" }], analysis_patterns: [], policies: [],
  questions: [
    { ...governed("question.adt_fact", "ADT是多少"), examples: ["上月ADT是多少？"] },
    { ...governed("question.adt_compare", "ADT比较"), examples: ["两个期间有何差异？"] },
  ],
} as unknown as StudioWorkbench["package"];

const candidate = (overrides: Partial<ConstructionCandidate>): ConstructionCandidate => ({
  contract: "construction-candidate/v1",
  candidate_id: "candidate.11111111111111111111111111111111",
  occurrence_key: "1".repeat(64),
  revision_digest: "2".repeat(64),
  candidate_type: "METRIC",
  label: "ADT 候选定义",
  definition: "来源材料中的待复核指标定义",
  support_class: "DIRECT_EXACT",
  risk_class: "HIGH",
  review_status: "UNREVIEWED",
  compile_eligible: false,
  canonical_target: "metric.average_daily_turnover",
  proposal: {},
  proposed_operation: null,
  source_anchors: [],
  impact_refs: ["metric.average_daily_turnover"],
  limitations: [],
  ...overrides,
});

afterEach(cleanup);
const originalResizeObserver = globalThis.ResizeObserver;
beforeAll(() => {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});
afterAll(() => { globalThis.ResizeObserver = originalResizeObserver; });

describe("mature Studio product views", () => {
  it("shows the four distinct authorities from exact inputs to Agent runtime", () => {
    render(<StudioVersionLineage
      sourcePack={{ physicalFileCount: 4, logicalSourceCount: 6, installedSourceCount: 6 }}
      draft={{ revision: 7, targetVersion: "0.2.1", validation: "PASS" }}
      reviewed={{ version: "0.2.0", status: "INTERNAL_REVIEWED_WITH_PROVISIONAL_ASSUMPTIONS", metricCount: 8 }}
      active={{ version: "0.2.0", environmentId: "demo" }}
      solutionId="ontology.exchange_analytics.cash_trading"
    />);

    expect(screen.getByText("Source Pack")).toBeTruthy();
    expect(screen.getByText("Construction Draft")).toBeTruthy();
    expect(screen.getByText("Reviewed Baseline")).toBeTruthy();
    expect(screen.getByText("Agent Active")).toBeTruthy();
    expect(screen.getByText("4 份文件 · 6 个逻辑来源")).toBeTruthy();
    expect(screen.getByText("内部已审核（含待确认假设）")).toBeTruthy();
    expect(screen.getByRole("link", { name: "进入 Agent 查询" }).getAttribute("href"))
      .toBe("/ontology-agent/?solution=ontology.exchange_analytics.cash_trading");
    expect(screen.getByText("不等同于生产审批或运行激活")).toBeTruthy();
  });

  it("separates business requirements from the complete metric catalog", () => {
    render(<MemoryRouter><RequirementsCatalogView solutionId="ontology.exchange_analytics.adt" ontologyPackage={ontologyPackage} /></MemoryRouter>);
    expect(screen.getByText("2 条业务配置")).toBeTruthy();
    expect(screen.getAllByText("ADT是多少").length).toBeGreaterThan(0);
    expect(screen.getByText("ADT比较")).toBeTruthy();
    expect(screen.getByRole("link", { name: "编辑这条需求" }).getAttribute("href")).toContain("assetType=questions");

    cleanup();
    render(<MetricCatalogView ontologyPackage={ontologyPackage} />);
    expect(screen.getByText("3 个本体指标")).toBeTruthy();
    expect(screen.getByText("3 个已进入 Ontology")).toBeTruthy();
    expect(screen.getByText("0 个 Agent 已支持")).toBeTruthy();
    expect(screen.getAllByText("合资格成交额").length).toBeGreaterThan(0);
    expect(screen.getByText("交易日数")).toBeTruthy();
    expect(screen.getByText("平均每日成交额")).toBeTruthy();
  });

  it("separates source, ontology review, governance and Agent runtime coverage for all eight metrics", () => {
    const authoring = {
      contract: "studio-authoring-projection/v1",
      source_mode: "EXACT_TRANSCRIPTION",
      requirements: [],
      metric_candidates: Array.from({ length: 8 }, (_, index) => ({
        contract: "metric-candidate-projection/v1",
        metric_key: `M-${String(index + 1).padStart(2, "0")}`,
        name: index === 7 ? "Potential self-trade rate" : `Cash metric ${index + 1}`,
        definition: `Definition ${index + 1}`,
        calculation_logic: `Formula ${index + 1}`,
        filters_and_scope: "Same reporting cohort",
        grain_and_dimensions: "Business date",
        unit: index === 2 ? "Milliseconds" : "Percentage",
        null_and_zero_policy: "Refuse on zero denominator",
        primary_sources: "Exact source row",
        source_status: "Transcribed input",
        support_class: "DIRECT_EXACT",
        compile_status: "EXECUTABLE",
        canonical_metric_id: `metric.cash_${index + 1}`,
        ontology_status: "REVIEWED",
        runtime_status: index === 2 || index === 7 ? "SUPPORTED" : "NOT_YET_SUPPORTED",
        governance_status: "REVIEWED_WITH_ASSUMPTIONS",
        source_anchor: null,
      })),
    } as unknown as StudioAuthoringProjection;

    render(<MetricCatalogView ontologyPackage={ontologyPackage} authoring={authoring} />);

    expect(screen.getByText("8 个来源指标")).toBeTruthy();
    expect(screen.getByText("8 个已进入 Ontology")).toBeTruthy();
    expect(screen.getByText("2 个 Agent 已支持")).toBeTruthy();
    expect(screen.queryByText(/已编译可执行/)).toBeNull();
    expect(screen.getAllByText("本体已审核")).toHaveLength(6);
    expect(screen.getAllByText("Agent 可用")).toHaveLength(2);
    fireEvent.click(screen.getByText("Potential self-trade rate"));
    expect(screen.getByText("已审核（含待确认假设）")).toBeTruthy();
  });

  it("registers a transcribed source as a new exact version instead of editing installed bytes", async () => {
    const onUpload = vi.fn().mockResolvedValue(undefined);
    render(<SourceLibraryView
      ontologyPackage={ontologyPackage}
      intake={{ assets: [] }}
      library={{ contract: "studio-source-library/v1", workspace_id: "workspace.adt.reference", current: [], versions: [] }}
      onUpload={onUpload}
    />);

    fireEvent.click(screen.getByText("登记材料版本"));
    expect((screen.getByRole("button", { name: "登记新版本" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText("可粘贴 O-xx / M-xx Markdown 表格，或直接上传标准 Excel template。"), {
      target: { value: "| O-01 | ADT？ | 期间、ADT | 表格 |" },
    });
    expect((screen.getByRole("button", { name: "登记新版本" }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByText("登记新版本"));

    await waitFor(() => expect(onUpload).toHaveBeenCalledWith(expect.objectContaining({
      kind: "requirement_transcription",
      originalName: "requirements.md",
      mediaType: "text/markdown",
    }))); 
  });

  it("does not silently discard a partially transcribed source", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<SourceLibraryView
      ontologyPackage={ontologyPackage}
      intake={{ assets: [] }}
      library={{ contract: "studio-source-library/v1", workspace_id: "workspace.adt.reference", current: [], versions: [] }}
      onUpload={vi.fn()}
    />);

    fireEvent.click(screen.getByText("登记材料版本"));
    const transcription = screen.getByPlaceholderText("可粘贴 O-xx / M-xx Markdown 表格，或直接上传标准 Excel template。");
    fireEvent.change(transcription, { target: { value: "尚未登记的业务材料" } });
    fireEvent.click(screen.getByRole("button", { name: "取消" }));

    expect(confirm).toHaveBeenCalledWith("放弃尚未保存的修改？");
    expect((transcription as HTMLTextAreaElement).value).toBe("尚未登记的业务材料");
    expect(screen.getAllByText("登记材料版本").length).toBeGreaterThan(0);
    confirm.mockRestore();
  });

  it("loads the packaged Cash Trading reference source pack as an explicit user action", async () => {
    const onInstallReferencePack = vi.fn().mockResolvedValue(undefined);
    render(<SourceLibraryView
      ontologyPackage={ontologyPackage}
      intake={{
        assets: [],
        reference_source_pack: {
          pack_id: "cash-trading.deloitte-hk.reference.20260820",
          title: "Deloitte HK Cash Trading reference source pack",
          physical_file_count: 4,
          registrations: Array.from({ length: 6 }, (_, index) => ({ source_id: `asset.cash_${index}` })),
          limitations: ["No source SQL supplied"],
        },
      }}
      library={{ contract: "studio-source-library/v1", workspace_id: "workspace.cash.reference", current: [], versions: [] }}
      onInstallReferencePack={onInstallReferencePack}
    />);

    fireEvent.click(screen.getByRole("button", { name: "载入参考材料包" }));
    await waitFor(() => expect(onInstallReferencePack).toHaveBeenCalledOnce());
    expect(screen.getByText("逻辑角色")).toBeTruthy();
    expect(screen.getByText("6 个")).toBeTruthy();
  });

  it("versions installed package materials before offering exact preview", async () => {
    const onImportInstalledSources = vi.fn().mockResolvedValue(undefined);
    render(<SourceLibraryView
      ontologyPackage={ontologyPackage}
      intake={{ assets: [{ asset_id: "asset.requirements", title: "需求", locator: "input/requirements.md", kind: "requirement_transcription", checksum: "a".repeat(64) }] }}
      library={{ contract: "studio-source-library/v1", workspace_id: "workspace.adt.reference", current: [], versions: [] }}
      onImportInstalledSources={onImportInstalledSources}
    />);

    expect(screen.getByText("先把安装材料登记为可追溯版本")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "版本化安装材料" }));
    await waitFor(() => expect(onImportInstalledSources).toHaveBeenCalledOnce());
  });

  it("opens a source version in a dedicated preview drawer", async () => {
    const current = [{
      contract: "studio-source-version/v1",
      persistence: "local-compatibility",
      source_version_id: `source-version.${"1".repeat(32)}`,
      workspace_id: "workspace.adt.reference",
      source_id: "asset.requirements",
      kind: "requirement_transcription",
      title: "需求说明",
      original_name: "requirements.md",
      media_type: "text/markdown",
      processing_mode: "TRANSCRIBED",
      content_checksum: "a".repeat(64),
      size_bytes: 128,
      registered_at: "2026-08-21T00:00:00Z",
      artifact: null,
      subject_checksum: "b".repeat(64),
      is_current: true,
    }] as unknown as StudioSourceLibrary["current"];
    const onPreview = vi.fn().mockResolvedValue({
      contract: "studio-source-preview/v1",
      source_version_id: current[0].source_version_id,
      content_checksum: current[0].content_checksum,
      parser_build: "ontology-studio/source-preview@1",
      status: "PARSED",
      text_lines: [{ line_number: 1, text: "# 需求说明", snippet_checksum: "c".repeat(64) }],
      sheets: [],
      limitation: null,
    });
    render(<SourceLibraryView
      ontologyPackage={ontologyPackage}
      intake={{ assets: [] }}
      library={{ contract: "studio-source-library/v1", workspace_id: "workspace.adt.reference", current, versions: current }}
      onPreview={onPreview}
    />);

    const previewTrigger = screen.getByRole("button", { name: "查看详情" });
    fireEvent.click(previewTrigger);
    expect(await screen.findByRole("dialog", { name: "需求说明" })).toBeTruthy();
    expect(await screen.findByText("# 需求说明")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "需求说明" })).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(previewTrigger));
  });

  it("does not duplicate physical package files beside their registered logical sources", () => {
    const current = Array.from({ length: 6 }, (_, index) => ({
      contract: "studio-source-version/v1",
      persistence: "postgresql-s3",
      source_version_id: `source-version.${String(index + 1).padStart(32, "0")}`,
      workspace_id: "workspace.cash.reference",
      source_id: `asset.cash_${index}`,
      kind: index < 2 ? "requirement_transcription" : "data_dictionary",
      title: `逻辑来源 ${index + 1}`,
      original_name: `source-${index + 1}.xlsx`,
      media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      processing_mode: "STRUCTURED_TRANSCRIPTION",
      content_checksum: String(index + 1).repeat(64),
      size_bytes: 1024,
      registered_at: "2026-08-21T00:00:00Z",
      artifact: null,
      subject_checksum: String(index + 2).repeat(64),
      is_current: true,
    })) as unknown as StudioSourceLibrary["current"];

    render(<SourceLibraryView
      ontologyPackage={ontologyPackage}
      intake={{
        assets: Array.from({ length: 4 }, (_, index) => ({
          file_id: `inherited-${index + 1}`,
          locator: `physical-${index + 1}.xlsx`,
        })),
      }}
      library={{
        contract: "studio-source-library/v1",
        workspace_id: "workspace.cash.reference",
        current,
        versions: current,
      }}
    />);

    expect(screen.getByText("6 个当前来源")).toBeTruthy();
    expect(screen.queryByText("inherited-1")).toBeNull();
    expect(document.querySelectorAll(".source-library-table article strong")).toHaveLength(6);
  });

  it("projects canonical objects, relations and metric dependencies into the graph", () => {
    const projection = buildOntologyGraphProjection(ontologyPackage);
    expect(projection.nodes.map((node) => node.id)).toEqual(expect.arrayContaining([
      "entity.trade",
      "entity.instrument",
      "metric.average_daily_turnover",
    ]));
    expect(projection.edges.map((edge) => edge.id)).toEqual(expect.arrayContaining([
      "relationship.trade.instrument",
      "dependency:metric.average_daily_turnover:metric.eligible_turnover",
    ]));
  });

  it("keeps construction candidates in an explicit non-canonical graph overlay", () => {
    const metricCandidate = candidate({});
    const linkCandidate = candidate({
      candidate_id: "candidate.22222222222222222222222222222222",
      occurrence_key: "3".repeat(64),
      revision_digest: "4".repeat(64),
      candidate_type: "LINK",
      label: "候选关系",
      canonical_target: null,
      proposal: { subject: "entity.trade", predicate: "referencesInstrument", object: "entity.instrument" },
      impact_refs: [],
      support_class: "MODEL_INFERRED",
    });
    const projection = buildOntologyGraphProjection(ontologyPackage, [metricCandidate, linkCandidate]);
    expect(projection.nodes.find((node) => node.id === `candidate-node:${metricCandidate.candidate_id}`)?.data.layer).toBe("candidate");
    expect(projection.edges.find((edge) => edge.id === `candidate-link:${linkCandidate.candidate_id}`)?.data?.layer).toBe("candidate");
    expect(projection.nodes.find((node) => node.id === "metric.average_daily_turnover")?.data.layer).toBe("canonical");
  });

  it("projects a 500-node graph and computes exact one-hop canonical impact", () => {
    const entities = Array.from({ length: 500 }, (_, index) => ({
      ...governed(`entity.synthetic_${index}`, `对象 ${index}`),
      primary_key: `property.synthetic_${index}.id`,
      grain: `one synthetic ${index}`,
      lifecycle: "defined",
    }));
    const relationships = Array.from({ length: 1500 }, (_, index) => ({
      ...governed(`relationship.synthetic_${index}`, `关系 ${index}`),
      from_entity: `entity.synthetic_${index % 500}`,
      to_entity: `entity.synthetic_${(index + 1) % 500}`,
      predicate: `links_${index}`,
      cardinality: "N:1",
    }));
    const largePackage = {
      ...ontologyPackage,
      entities,
      relationships,
    } as unknown as StudioWorkbench["package"];

    const projection = buildOntologyGraphProjection(largePackage);
    const impact = graphImpactForNode(projection, "entity.synthetic_0");

    expect(projection.nodes).toHaveLength(503);
    expect(projection.edges).toHaveLength(1502);
    expect(impact.incoming).toHaveLength(3);
    expect(impact.outgoing).toHaveLength(3);
    expect(impact.canonicalDependencyCount).toBe(6);
    expect(impact.affectedNodeIds).toEqual(["entity.synthetic_1", "entity.synthetic_499"]);
  });

  it("routes graph creation to the single typed asset editor", () => {
    render(<OntologyGraphEditor
      ontologyPackage={ontologyPackage}
      createEntityHref="/ontology-studio/semantic/model/?create=entities"
      createRelationshipHref="/ontology-studio/semantic/model/?create=relationships"
    />);
    expect(screen.getByRole("link", { name: "新建对象" }).getAttribute("href"))
      .toBe("/ontology-studio/semantic/model/?create=entities");
    expect(screen.getByRole("link", { name: "新建关系" }).getAttribute("href"))
      .toBe("/ontology-studio/semantic/model/?create=relationships");
    expect((screen.getByLabelText("显示待复核候选") as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("节点类型") as HTMLSelectElement).value).toBe("entity");
    expect(screen.getByText("2 / 5 个正式节点可见")).toBeTruthy();
  });

  it("separates schema, mapping and sample/enum workflows into real data pages", async () => {
    const onApply = vi.fn();
    render(<SchemaCatalogView ontologyPackage={ontologyPackage} onApply={onApply} busy={false} />);
    expect(screen.getByText("1 个数据源")).toBeTruthy();
    expect(screen.getAllByText("trades").length).toBeGreaterThan(0);
    expect(screen.getAllByText("trade_id").length).toBeGreaterThan(0);
    const schemaEditTrigger = screen.getByRole("button", { name: "编辑当前数据源" });
    expect(schemaEditTrigger).toBeTruthy();
    fireEvent.click(schemaEditTrigger);
    expect((screen.getByRole("button", { name: "保存数据源草稿" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(document.activeElement).toBe(schemaEditTrigger));

    cleanup();
    render(<MappingWorkbenchView ontologyPackage={ontologyPackage} onApply={onApply} busy={false} />);
    expect(screen.getByText("1 条字段映射")).toBeTruthy();
    expect(screen.getAllByText("property.trade.market").length).toBeGreaterThan(0);
    expect(screen.getAllByText("成交自关联").length).toBeGreaterThan(0);

    cleanup();
    render(<SampleAndEnumView ontologyPackage={ontologyPackage} intake={{ assets: [] }} onApply={onApply} busy={false} />);
    expect(screen.getByText("1 个枚举字段")).toBeTruthy();
    expect(screen.getByText("MAIN")).toBeTruthy();
    expect(screen.getByText("GEM")).toBeTruthy();
  });

  it("keeps source metrics, canonical metrics and runtime support as separate counts", () => {
    const authoring = {
      contract: "studio-authoring-projection/v1",
      source_mode: "EXACT_TRANSCRIPTION",
      requirements: [],
      metric_candidates: Array.from({ length: 8 }, (_, index) => ({ metric_key: `M-${index + 1}` })),
    } as unknown as StudioAuthoringProjection;
    render(<MemoryRouter><SemanticAssetCatalog
      mode="metrics"
      solutionId="ontology.exchange_analytics.adt"
      ontologyPackage={ontologyPackage}
      authoring={authoring}
      busy={false}
      error={null}
      reviewer="atlas-operator"
      onApply={vi.fn()}
    /></MemoryRouter>);

    expect(screen.getByText("8 条来源指标保留为证据，不会替换下方 3 条 Ontology 指标。")).toBeTruthy();
    expect(document.querySelector(".asset-authority-summary > div:first-child strong")?.textContent).toBe("3");
  });

  it("creates a proposed semantic asset through the common typed editor", async () => {
    const onApply = vi.fn().mockResolvedValue(undefined);
    render(<MemoryRouter initialEntries={["/ontology-studio/solutions/ontology.exchange_analytics.adt/semantic/metrics/?assetType=metrics&assetId=new"]}><SemanticAssetCatalog
      mode="metrics"
      solutionId="ontology.exchange_analytics.adt"
      ontologyPackage={ontologyPackage}
      busy={false}
      error={null}
      reviewer="atlas-operator"
      onApply={onApply}
    /></MemoryRouter>);

    fireEvent.change(screen.getByLabelText(/技术 ID/), { target: { value: "metric.demo_value" } });
    fireEvent.change(screen.getByLabelText("中文名称"), { target: { value: "示例指标" } });
    fireEvent.change(screen.getByLabelText("英文名称"), { target: { value: "Demo metric" } });
    fireEvent.change(screen.getByLabelText("业务定义"), { target: { value: "用于验证统一语义资产入口的指标。" } });
    fireEvent.change(screen.getByLabelText("单位"), { target: { value: "count" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /需求文档/ }));
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));

    await waitFor(() => expect(onApply).toHaveBeenCalledWith(expect.objectContaining({
      action: "UPSERT",
      collection: "metrics",
      object_id: "metric.demo_value",
      payload: expect.objectContaining({ status: "proposed", sources: ["source.requirements"] }),
    })));
  });

  it("keeps typed input open when a semantic save fails", async () => {
    const onApply = vi.fn().mockRejectedValue(new Error("revision conflict"));
    render(<MemoryRouter initialEntries={["/ontology-studio/solutions/ontology.exchange_analytics.adt/semantic/model/?assetType=entities&assetId=new"]}><SemanticAssetCatalog
      mode="business"
      solutionId="ontology.exchange_analytics.adt"
      ontologyPackage={ontologyPackage}
      busy={false}
      error="revision conflict"
      reviewer="atlas-operator"
      onApply={onApply}
    /></MemoryRouter>);

    fireEvent.change(screen.getByLabelText(/技术 ID/), { target: { value: "entity.demo" } });
    fireEvent.change(screen.getByLabelText("中文名称"), { target: { value: "保留输入对象" } });
    fireEvent.change(screen.getByLabelText("英文名称"), { target: { value: "Retained object" } });
    fireEvent.change(screen.getByLabelText("业务定义"), { target: { value: "后端失败后仍应保留的输入。" } });
    fireEvent.change(screen.getByLabelText("业务粒度"), { target: { value: "one object" } });
    fireEvent.change(screen.getByLabelText("生命周期"), { target: { value: "created then retained" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /需求文档/ }));
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));

    await waitFor(() => expect(onApply).toHaveBeenCalledOnce());
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect((screen.getByLabelText("中文名称") as HTMLInputElement).value).toBe("保留输入对象");
    expect(screen.getAllByRole("alert").some((item) => item.textContent?.includes("revision conflict"))).toBe(true);
  });

  it("keeps every malformed JSON field blocking even after another JSON field becomes valid", () => {
    const onApply = vi.fn();
    render(<MemoryRouter initialEntries={["/ontology-studio/solutions/ontology.exchange_analytics.adt/semantic/metrics/?assetType=metrics&assetId=new"]}><SemanticAssetCatalog
      mode="metrics"
      solutionId="ontology.exchange_analytics.adt"
      ontologyPackage={ontologyPackage}
      busy={false}
      error={null}
      reviewer="atlas-operator"
      onApply={onApply}
    /></MemoryRouter>);

    fireEvent.change(screen.getByLabelText(/技术 ID/), { target: { value: "metric.invalid_contract" } });
    fireEvent.change(screen.getByLabelText("中文名称"), { target: { value: "无效公式指标" } });
    fireEvent.change(screen.getByLabelText("英文名称"), { target: { value: "Invalid formula metric" } });
    fireEvent.change(screen.getByLabelText("业务定义"), { target: { value: "验证多个结构化字段不会互相掩盖错误。" } });
    fireEvent.change(screen.getByLabelText("单位"), { target: { value: "count" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /需求文档/ }));
    fireEvent.change(screen.getByLabelText("公式合同"), { target: { value: "{" } });
    fireEvent.change(screen.getByLabelText("确定性查询合同"), { target: { value: "{}" } });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));

    expect(onApply).not.toHaveBeenCalled();
    expect((screen.getByLabelText("公式合同") as HTMLTextAreaElement).value).toBe("{");
    expect(screen.getByRole("alert").textContent).toContain("formula");
  });

  it("uses the server-provided asset digest and authenticated reviewer for confirmation", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const proposed = {
      ...ontologyPackage,
      metrics: [{ ...ontologyPackage.metrics[0], status: "proposed" }, ...ontologyPackage.metrics.slice(1)],
    } as StudioWorkbench["package"];
    const exactChecksum = "f".repeat(64);
    render(<MemoryRouter><SemanticAssetCatalog
      mode="metrics"
      solutionId="ontology.exchange_analytics.adt"
      ontologyPackage={proposed}
      busy={false}
      error={null}
      reviewer="atlas-operator"
      assetChecksums={{ "metrics:metric.eligible_turnover": exactChecksum }}
      onApply={vi.fn()}
      onConfirm={onConfirm}
    /></MemoryRouter>);

    fireEvent.click(screen.getByRole("button", { name: "确认当前摘要" }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({
      action: "CONFIRM",
      object_id: "metric.eligible_turnover",
      payload: expect.objectContaining({ reviewer: "atlas-operator", asset_checksum: exactChecksum }),
    })));
  });

  it("requires explicit acknowledgement before deprecating an asset", () => {
    render(<MemoryRouter><SemanticAssetCatalog
      mode="business"
      solutionId="ontology.exchange_analytics.adt"
      ontologyPackage={ontologyPackage}
      busy={false}
      error={null}
      reviewer="atlas-operator"
      onApply={vi.fn()}
      onDeprecate={vi.fn()}
    /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "弃用" }));
    const destructive = screen.getByRole("button", { name: "检查依赖并弃用" }) as HTMLButtonElement;
    expect(destructive.disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: /我已确认/ }));
    expect(destructive.disabled).toBe(false);
  });
});
