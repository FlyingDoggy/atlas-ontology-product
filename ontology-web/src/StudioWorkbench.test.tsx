import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StudioWorkbench } from "./api";
import { StudioWorkbenchView } from "./StudioWorkbench";

const digest = "a".repeat(64);
const governed = (id: string, en: string, zh: string) => ({
  id,
  version: "1.0.0",
  status: "confirmed" as const,
  name: { en, zh },
  definition: `${en} definition`,
  owner: "actor.owner",
  sources: ["source.requirements"],
  decisions: [],
  tags: [],
});

const workbench = {
  contract: "studio-workbench/v1",
  persistence: "postgresql-s3",
  package_checksum: digest,
  package: {
    package_id: "ontology.exchange_analytics.adt",
    version: "1.2.1",
    status: "confirmed",
    created_at: "2026-08-20T00:00:00Z",
    scenario: governed("scenario.adt", "ADT", "ADT"),
    actors: [], processes: [], sources: [{
      id: "source.requirements", source_type: "requirement_transcription",
      title: "ADT requirements and process", locator: "input/requirements_and_process.md",
      owner: "actor.business_owner", captured_on: "2026-08-20", trust: "primary", notes: "Synthetic reference transcription",
    }], decisions: [],
    entities: [{ ...governed("entity.trade", "Trade", "成交"), primary_key: "property.trade.id", grain: "one trade", lifecycle: "executed" }],
    properties: [{ ...governed("property.trade.id", "Trade ID", "成交编号"), entity: "entity.trade", data_type: "string", required: true, unit: null, enum_values: [], null_meaning: "not_allowed" }],
    relationships: [{ ...governed("relationship.trade.market", "Trade market", "成交市场"), from_entity: "entity.trade", to_entity: "entity.trade", predicate: "belongsTo", cardinality: "N:1" }],
    dimensions: [],
    rules: [{
      ...governed("rule.trade.eligible", "Eligible trade", "合资格成交"),
      rule_type: "eligibility", all: [{ property: "property.trade.status", op: "eq", value: "EXECUTED" }],
      failure_behavior: "exclude",
    }],
    metrics: [{
      ...governed("metric.adt", "Average daily turnover", "日均成交额"),
      metric_type: "derived", base_entity: "entity.trade", result_grain: ["dimension.period"],
      value_type: "decimal", unit: "HKD mn/day", aggregation_semantics: "derived_non_additive",
      formula: { op: "divide", args: [{ op: "sum", args: [{ op: "field_ref", ref: "property.trade.value" }] }, { op: "metric_ref", ref: "metric.trading_days" }] },
      query: { base_source: "source.trade", required_joins: [], filters: ["rule.trade.eligible"] },
      allowed_dimensions: ["dimension.period"], null_policy: "fail_validation", zero_denominator_policy: "refuse",
    }],
    data_sources: [{
      ...governed("source.trade", "Trade source", "成交数据源"),
      protocol: "tabular/v1",
      tables: [{ name: "trade_fact", grain: "one trade", primary_key: ["trade_id"], fields: [{ name: "executed_value", data_type: "decimal", nullable: false, description: "Executed amount", unit: "HKD" }] }],
    }],
    bindings: [{
      ...governed("binding.trade.value", "Trade value binding", "成交额映射"),
      logical_target: "property.trade.value", source: "source.trade", table: "trade_fact",
      column: "executed_value", data_type: "decimal", unit: "HKD", transformation: "identity",
    }],
    joins: [{
      ...governed("join.trade.market", "Trade market join", "成交市场关联"),
      left_source: "source.trade", left_table: "trade_fact", right_source: "source.trade", right_table: "market_dim",
      keys: [{ left_column: "market_id", right_column: "market_id" }], expected_cardinality: "N:1", fanout_policy: "block",
    }],
    analysis_patterns: [], policies: [{
      ...governed("policy.analyst", "Analyst access", "分析师权限"),
      allowed_roles: ["role.market_analyst"], denied_roles: ["role.external"],
      allowed_grains: ["aggregate"], denied_fields: ["property.trade.participant_id"], minimum_group_size: 5,
    }], questions: [],
  },
  workspace: {
    schema_version: "adt-draft-workspace/v1", workspace_id: "workspace.adt.reference",
    package_id: "ontology.exchange_analytics.adt", base_version: "1.2.0", target_version: "1.2.1",
    revision: 1, created_at: "2026-08-20T00:00:00Z", updated_at: "2026-08-20T00:00:00Z",
    revision_created_at: "2026-08-20T00:00:00Z", intake_submission_id: "submission.reference.adt.v1",
    intake_checksum: digest, source_anchors: [{ field: "metric_definition", asset_id: "asset.requirements", locator: "section:M-03" }], modified_fields: [], draft: {}, package_operations: [], draft_checksum: digest,
    validation: { status: "NOT_RUN", revision: null, draft_checksum: null, validated_at: null, report: null },
    last_published: null,
  },
  intake: {
    schema_version: "adt-intake-submission/v1",
    assets: [{
      asset_id: "asset.requirements", kind: "requirement_transcription",
      locator: "input/requirements_and_process.md", checksum: digest,
      disclosure_status: "CLEARED_SYNTHETIC", processing_mode: "TRANSCRIBED",
    }],
    gaps: [{ gap_id: "gap.production.schema", status: "OPEN", description: "Production physical schema is unavailable", blocks_synthetic_reference: false }],
  },
  revisions: [{
    schema_version: "adt-draft-revision/v1", workspace_id: "workspace.adt.reference",
    revision: 1, target_version: "1.2.1", recorded_at: "2026-08-20T00:00:00Z",
    draft: {}, draft_checksum: digest, modified_fields: [], record_checksum: "b".repeat(64),
  }],
  semantic_change_requests: [{
    contract: "semantic-change-request/v1", request_id: `scr.${"c".repeat(32)}`,
    request_type: "MISSING_RELATIONSHIP", title: "Missing instrument relationship",
    observation: "Agent could not traverse to instrument class.", proposed_change: "Review a Trade-to-Instrument link.",
    status: "PROPOSED_UNTRIAGED", created_at: "2026-08-20T02:00:00Z",
    execution_id: `exec.${"d".repeat(32)}`, snapshot_checksum: digest,
    claim_refs: ["claim.metric.delta"],
  }],
} as unknown as StudioWorkbench;

afterEach(cleanup);

describe("StudioWorkbenchView", () => {
  it("supports a route-controlled page without rendering a second navigation rail", () => {
    render(
      <StudioWorkbenchView
        workbench={workbench}
        activeTab="bindings"
        navigation="hidden"
        presentation="page"
      />,
    );

    expect(screen.getByRole("heading", { name: "逻辑字段到物理数据" })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Studio 工作区" })).toBeNull();
  });

  it("shows package-owned objects, properties and links", () => {
    render(<StudioWorkbenchView workbench={workbench} />);

    expect(screen.getByRole("heading", { name: "业务对象与关系" })).toBeTruthy();
    expect(screen.getByText("Trade")).toBeTruthy();
    expect(screen.getByText("Trade ID")).toBeTruthy();
    expect(screen.getByText("belongsTo")).toBeTruthy();
  });

  it("shows physical mappings and join contracts in the binding workspace", () => {
    render(<StudioWorkbenchView workbench={workbench} />);
    fireEvent.click(screen.getByRole("button", { name: /数据绑定/ }));

    expect(screen.getByRole("heading", { name: "逻辑字段到物理数据" })).toBeTruthy();
    expect(screen.getByText("property.trade.value")).toBeTruthy();
    expect(screen.getByText("trade_fact.executed_value")).toBeTruthy();
    expect(screen.getByText("N:1")).toBeTruthy();
  });

  it("exposes metric formulas, business rules and access policies as first-class ontology", () => {
    render(<StudioWorkbenchView workbench={workbench} />);

    fireEvent.click(screen.getByRole("button", { name: /指标 1/ }));
    expect(screen.getByRole("heading", { name: "指标语义与公式" })).toBeTruthy();
    expect(screen.getByText("Average daily turnover")).toBeTruthy();
    expect(screen.getByText("derived_non_additive")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /规则 1/ }));
    expect(screen.getByRole("heading", { name: "业务规则与失败行为" })).toBeTruthy();
    expect(screen.getByText("Eligible trade")).toBeTruthy();
    expect(screen.getByText("exclude")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /策略 1/ }));
    expect(screen.getByRole("heading", { name: "权限与披露策略" })).toBeTruthy();
    expect(screen.getByText("role.market_analyst")).toBeTruthy();
    expect(screen.getByText("property.trade.participant_id")).toBeTruthy();
  });

  it("shows exact backend validation checks instead of a browser PASS flag", () => {
    const validated = structuredClone(workbench) as StudioWorkbench;
    validated.workspace.validation = {
      status: "PASS",
      revision: 1,
      draft_checksum: digest,
      validated_at: "2026-08-20T01:00:00Z",
      report: {
        status: "PASS",
        checks: [{
          check_id: "RELATIONSHIP_REFERENCES",
          category: "semantic",
          status: "PASS",
          message: "Relationship endpoints resolve to package entities",
          details: { relationship_count: 1 },
        }],
      },
    };
    render(<StudioWorkbenchView workbench={validated} />);
    fireEvent.click(screen.getByRole("button", { name: /验证Checks/ }));

    expect(screen.getByRole("heading", { name: "精确验证结果" })).toBeTruthy();
    expect(screen.getByText("RELATIONSHIP_REFERENCES")).toBeTruthy();
    expect(screen.getByText("Relationship endpoints resolve to package entities")).toBeTruthy();
  });

  it("keeps source evidence, intake gaps, anchors and immutable revision history together", () => {
    render(<StudioWorkbenchView workbench={workbench} />);
    fireEvent.click(screen.getByRole("button", { name: /来源与历史/ }));

    expect(screen.getByRole("heading", { name: "来源证据与修订轨迹" })).toBeTruthy();
    expect(screen.getByText("ADT requirements and process")).toBeTruthy();
    expect(screen.getByText("Production physical schema is unavailable")).toBeTruthy();
    expect(screen.getByText("metric_definition")).toBeTruthy();
    expect(screen.getAllByText("r1")).toHaveLength(2);
    expect(screen.getByText("Missing instrument relationship")).toBeTruthy();
    expect(screen.getByText("PROPOSED_UNTRIAGED")).toBeTruthy();
  });

  it("keeps publish, prepare, activate and verify as separate operator actions", () => {
    const published = structuredClone(workbench) as StudioWorkbench;
    published.workspace.last_published = {
      package_id: published.package.package_id,
      version: published.package.version,
      checksum: digest,
    };
    const oldRelease = { package_id: published.package.package_id, version: "1.2.0", checksum: "c".repeat(64) };
    const oldSnapshot = { environment_id: "adt-poc", release: oldRelease, checksum: "d".repeat(64) };
    const nextSnapshot = {
      environment_id: "adt-poc",
      release: { package_id: published.package.package_id, version: published.package.version, checksum: digest },
      checksum: "e".repeat(64),
    };
    const onPrepare = vi.fn();
    const onActivate = vi.fn();
    const onVerify = vi.fn();
    const onRollback = vi.fn();
    render(<StudioWorkbenchView workbench={published} lifecycle={{
      status: { environment_id: "adt-poc", package_id: published.package.package_id, state_authority: "postgresql-s3", active: oldSnapshot, rollback_target: nextSnapshot },
      prepared: {
        snapshot: nextSnapshot,
        readiness: { status: "READY", checks: [], certification_profile: "adt-golden-v1", certification_checksum: "f".repeat(64) },
        idempotent: false,
      },
      rollbackTarget: nextSnapshot,
      verification: null, busy: null, error: null, onRefresh: vi.fn(), onPrepare, onActivate, onVerify, onRollback,
    }} />);
    fireEvent.click(screen.getByRole("button", { name: /发布与运行/ }));

    expect(screen.getByRole("heading", { name: "发布、认证、激活与验证" })).toBeTruthy();
    expect(screen.getByText("PREPARED")).toBeTruthy();
    expect(screen.getByText("ACTIVE")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "准备并认证" }));
    fireEvent.click(screen.getByRole("button", { name: "激活准备版本" }));
    fireEvent.click(screen.getByRole("button", { name: "验证当前 Active" }));
    fireEvent.click(screen.getByRole("button", { name: /回滚到上一版本/ }));
    expect(onPrepare).toHaveBeenCalledOnce();
    expect(onActivate).toHaveBeenCalledOnce();
    expect(onVerify).toHaveBeenCalledOnce();
    expect(onRollback).toHaveBeenCalledOnce();
  });

  it("authors a typed relationship contract without browser-side package mutation", () => {
    const onApply = vi.fn();
    render(<StudioWorkbenchView workbench={workbench} authoring={{ busy: false, error: null, onApply }} />);
    fireEvent.click(screen.getByRole("button", { name: "新增关系" }));
    fireEvent.change(screen.getByLabelText("Link ID"), { target: { value: "relationship.trade.instrument" } });
    fireEvent.change(screen.getByLabelText("English name"), { target: { value: "Trade instrument" } });
    fireEvent.change(screen.getByLabelText("中文名称"), { target: { value: "成交证券" } });
    fireEvent.change(screen.getByLabelText("Predicate"), { target: { value: "referencesInstrument" } });
    fireEvent.click(screen.getByRole("button", { name: "保存关系草稿" }));

    expect(onApply).toHaveBeenCalledOnce();
    expect(onApply.mock.calls[0][0]).toMatchObject({
      action: "UPSERT",
      collection: "relationships",
      object_id: "relationship.trade.instrument",
      payload: {
        from_entity: "entity.trade",
        to_entity: "entity.trade",
        predicate: "referencesInstrument",
        cardinality: "N:1",
      },
    });
  });

  it("opens one typed editor over every governed package collection", () => {
    render(<StudioWorkbenchView workbench={workbench} authoring={{ busy: false, error: null, onApply: vi.fn() }} />);
    fireEvent.click(screen.getByRole("button", { name: "打开完整合同编辑器" }));
    expect(screen.getByRole("heading", { name: "完整 Ontology 合同编辑器" })).toBeTruthy();
    expect(screen.getByLabelText("Contract collection")).toBeTruthy();
    expect(screen.getByRole("option", { name: "Physical bindings · 1" })).toBeTruthy();
  });
});
