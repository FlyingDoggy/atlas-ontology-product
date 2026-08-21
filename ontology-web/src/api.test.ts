import { describe, expect, it } from "vitest";

import {
  productContextSchema,
  solutionAnalysisSchema,
  solutionCatalogSchema,
  solutionQuestionFamilySchema,
  solutionRuntimeSchema,
  studioWorkbenchSchema,
  agentRuntimeStatusSchema,
  preparedRuntimeSchema,
  activeRuntimeVerificationSchema,
  semanticChangeRequestSchema,
  studioLlmStatusSchema,
  studioObservationSetSchema,
  workspaceEditorSchema,
} from "./api";

const digest = "a".repeat(64);

function validContext() {
  return {
    contract: "product-context/v1",
    persistence: "postgresql-s3",
    subject_checksum: digest,
    subject: {
      contract: "product-context-subject/v1",
      context_id: "context.adt.reference",
      product_family_id: "ontology-analytics",
      solution_id: "ontology.exchange_analytics.adt",
      solution_version: "1.2.0",
      scenario_id: "scenario.adt_reference",
      scenario_name_en: "ADT Reference Analysis",
      scenario_name_zh: "ADT参考分析",
      classification: "constructed_synthetic",
      active_runtime: {
        environment_id: "adt-poc",
        release_checksum: "b".repeat(64),
        snapshot_checksum: "c".repeat(64),
        certification_profile: "adt-golden-v1",
      },
      navigation: {
        studio: "/ontology-studio/",
        agent: "/ontology-agent/",
      },
      limitations: ["Synthetic only"],
    },
    artifact: {
      store: "s3-compatible",
      bucket: "ontology-artifacts",
      key: `product-context/sha256/${digest}.json`,
      version_id: "version-1",
      sha256: digest,
      size_bytes: 512,
      media_type: "application/json",
    },
  };
}

describe("productContextSchema", () => {
  it("accepts an exact PostgreSQL/S3 context", () => {
    expect(productContextSchema.parse(validContext()).persistence).toBe(
      "postgresql-s3",
    );
  });

  it("rejects an artifact identity mismatch", () => {
    const value = validContext();
    value.artifact.sha256 = "d".repeat(64);
    expect(productContextSchema.safeParse(value).success).toBe(false);
  });

  it("rejects unknown browser-side authority fields", () => {
    const value = { ...validContext(), browser_calculated_status: "ACTIVE" };
    expect(productContextSchema.safeParse(value).success).toBe(false);
  });
});

describe("Studio runtime lifecycle contracts", () => {
  const release = { package_id: "ontology.exchange_analytics.adt", version: "1.2.1", checksum: digest };
  const snapshot = { environment_id: "adt-poc", release, checksum: "b".repeat(64) };

  it("accepts one exact prepared snapshot and its certification evidence", () => {
    const parsed = preparedRuntimeSchema.parse({
      snapshot,
      readiness: {
        status: "READY",
        checks: [{ check_id: "GOLDEN_SUITE", category: "data", status: "PASS", message: "8/8 passed", details: { case_count: 8 } }],
        certification_profile: "adt-golden-v1",
        certification_checksum: "c".repeat(64),
      },
      idempotent: false,
    });
    expect(parsed.snapshot.release.checksum).toBe(digest);
  });

  it("rejects a verification report whose case_count does not match its cases", () => {
    const invalid = {
      status: "PASS", snapshot, suite_id: "adt.tracer.v1.suite", case_count: 2,
      cases: [{ case_id: "answered.1", status: "PASS", defects: [], execution_id: "execution.1" }],
      oracle: "constructed-synthetic", oracle_defects: {},
    };
    expect(activeRuntimeVerificationSchema.safeParse(invalid).success).toBe(false);
  });

  it("keeps the active pointer distinct from a merely published release", () => {
    const parsed = agentRuntimeStatusSchema.parse({
      environment_id: "adt-poc", package_id: release.package_id,
      state_authority: "postgresql-s3", active: snapshot,
      rollback_target: null,
    });
    expect(parsed.active?.checksum).toBe(snapshot.checksum);
  });

  it("accepts a newly created Solution before any runtime is active", () => {
    const parsed = agentRuntimeStatusSchema.parse({
      environment_id: "solution-blank",
      package_id: "ontology.custom.blank",
      state_authority: "postgresql-s3",
      active: null,
      rollback_target: null,
    });

    expect(parsed.active).toBeNull();
    expect(parsed.rollback_target).toBeNull();
  });

  it("persists a distinct rollback target in runtime status", () => {
    const previous = {
      ...snapshot,
      release: { ...snapshot.release, version: "1.1.0", checksum: "b".repeat(64) },
      checksum: "c".repeat(64),
    };
    const parsed = agentRuntimeStatusSchema.parse({
      environment_id: "adt-poc", package_id: release.package_id,
      state_authority: "postgresql-s3", active: snapshot,
      rollback_target: previous,
    });
    expect(parsed.rollback_target?.release.version).toBe("1.1.0");
  });
});

describe("Agent to Studio semantic change contract", () => {
  it("accepts a proposed request that remains untriaged and snapshot-bound", () => {
    const parsed = semanticChangeRequestSchema.parse({
      contract: "semantic-change-request/v1",
      request_id: `scr.${"a".repeat(32)}`,
      classification: "constructed_synthetic",
      solution_id: "ontology.exchange_analytics.adt",
      environment_id: "adt-poc",
      snapshot_checksum: digest,
      execution_id: `exec.${"b".repeat(32)}`,
      question: "Why did ADT change?",
      request_type: "MISSING_RELATIONSHIP",
      title: "Missing instrument link",
      observation: "The analysis cannot traverse to instrument class.",
      proposed_change: "Review a Trade-to-Instrument relationship.",
      claim_refs: ["claim.metric.delta"],
      status: "PROPOSED_UNTRIAGED",
      created_at: "2026-08-20T00:00:00Z",
      request_digest: digest,
    });
    expect(parsed.status).toBe("PROPOSED_UNTRIAGED");
  });
});

describe("Studio LLM co-authoring contracts", () => {
  it("labels the model path as proposed observations rather than ontology authority", () => {
    const parsed = studioLlmStatusSchema.parse({
      installed: true,
      demo_class: "STUDIO_LLM_ENGINEERING_DEMO",
      mode: "active-observation-canary",
      provider: "qwen",
      requested_model: "qwen3.8-max",
      workflow: "CLEARED_INPUT_TO_HUMAN_REVIEWED_DRAFT",
      slot_count: 5,
      label: "PROPOSED observations · not published ontology",
      can_publish: false,
    });
    expect(parsed.can_publish).toBe(false);
  });

  it("treats an uninstalled Studio LLM profile as a normal typed capability state", () => {
    const parsed = studioLlmStatusSchema.parse({
      installed: false,
      demo_class: "STUDIO_LLM_ENGINEERING_DEMO",
      mode: "off",
      provider: null,
      requested_model: null,
      workflow: "NOT_INSTALLED",
      slot_count: 0,
      label: "当前 solution 未安装 Studio LLM profile",
      can_publish: false,
    });
    expect(parsed.installed).toBe(false);
  });

  it("requires the exact five-slot observation denominator", () => {
    const value = {
      contract: "studio-observation-set/v1",
      observation_set_id: `observation-set.${"1".repeat(32)}`,
      run_id: `studio-run.${"2".repeat(32)}`,
      workspace_id: "workspace.adt.reference",
      base_revision: 1,
      base_draft_checksum: digest,
      intake_checksum: digest,
      profile_digest: digest,
      slot_manifest_digest: digest,
      egress_decision_digest: digest,
      projection_digest: digest,
      requested_model: "qwen3.8-max",
      response_model: "qwen3.8-max",
      provider_request_id: "provider.request.1",
      created_at: "2026-08-20T00:00:00Z",
      projection: { contract: "studio-cleared-input-projection/v1" },
      observations: Array.from({ length: 5 }, (_, index) => ({
        observation_id: `observation.${"3".repeat(32)}.${String(index + 1).padStart(2, "0")}`,
        slot_id: `slot.${index + 1}`,
        status: "PROPOSED",
        support_code: "DIRECT_SOURCE",
        value: { kind: "STRING", string_value: `value-${index + 1}`, boolean_value: null, string_list_value: null },
        source_anchor: { field: `slot.${index + 1}`, asset_id: "asset.1" },
        source_fragment_checksum: digest,
      })),
      observation_set_checksum: digest,
    };
    expect(studioObservationSetSchema.parse(value).observations).toHaveLength(5);
    expect(studioObservationSetSchema.safeParse({ ...value, observations: value.observations.slice(0, 4) }).success).toBe(false);
  });
});

describe("solutionCatalogSchema", () => {
  function catalog() {
    const kinds = [
      "authoring_profile",
      "semantic_source",
      "agent_experience",
      "reference_evaluation",
    ] as const;
    return {
      contract: "studio-solution-catalog/v1",
      solutions: [
        {
          solution_id: "ontology.exchange_analytics.adt",
          solution_version: "1.3.0",
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
          components: kinds.map((kind) => ({
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
        },
      ],
    };
  }

  it("accepts a closed four-component durable registration", () => {
    const parsed = solutionCatalogSchema.parse(catalog());
    expect(parsed.solutions).toHaveLength(1);
    expect(parsed.solutions[0].directory?.status).toBe("ACTIVE");
  });

  it("rejects a durable registration without its exact artifact", () => {
    const value = catalog();
    const invalid = {
      ...value,
      solutions: [{ ...value.solutions[0], artifact: null }],
    };
    expect(solutionCatalogSchema.safeParse(invalid).success).toBe(false);
  });
});

describe("workspaceEditorSchema", () => {
  function editor() {
    return {
      contract: "studio-workspace-editor/v1",
      persistence: "postgresql-s3",
      descriptor: {
        contract: "studio-editor-descriptor/v1",
        descriptor_id: "editor.adt.reference",
        version: "1.0.0",
        workspace_id: "workspace.adt.reference",
        studio_adapter_id: "studio-adapter.adt.reference@1",
        draft_schema_version: "adt-draft-workspace/v1",
        operations_contract: "studio-draft-operations/v1",
        title: { en: "ADT draft", zh: "ADT 草稿" },
        description: { en: "Review", zh: "复核" },
        semantic_slot_manifest: {
          locator: "llm/studio/semantic-slot-manifest.json",
          sha256: digest,
        },
        fields: [
          {
            path: "metric_definition",
            label: { en: "Definition", zh: "定义" },
            help: { en: "Reviewed definition", zh: "已复核定义" },
            control: "TEXTAREA",
            value_kind: "STRING",
            required: true,
            options: [],
          },
        ],
      },
      workspace: {
        schema_version: "adt-draft-workspace/v1",
        workspace_id: "workspace.adt.reference",
        package_id: "ontology.exchange_analytics.adt",
        base_version: "1.2.0",
        target_version: "1.2.1",
        revision: 1,
        created_at: "2026-08-20T00:00:00Z",
        updated_at: "2026-08-20T00:00:00Z",
        revision_created_at: "2026-08-20T00:00:00Z",
        intake_submission_id: "submission.reference.adt.v1",
        intake_checksum: digest,
        source_anchors: [],
        modified_fields: [],
        draft: { metric_definition: "Synthetic ADT" },
        draft_checksum: digest,
        validation: {
          status: "NOT_RUN",
          revision: null,
          draft_checksum: null,
          validated_at: null,
          report: null,
        },
        last_published: null,
      },
    };
  }

  it("accepts a descriptor-bound durable workspace", () => {
    expect(workspaceEditorSchema.parse(editor()).workspace.revision).toBe(1);
  });

  it("rejects descriptor/workspace schema drift", () => {
    const value = editor();
    value.descriptor.draft_schema_version = "wrong/v1";
    expect(workspaceEditorSchema.safeParse(value).success).toBe(false);
  });

  it("accepts package-owned provenance vocabulary while retaining the semantic field", () => {
    const value = editor();
    const workspace = value.workspace as Omit<typeof value.workspace, "source_anchors"> & {
      source_anchors: Array<Record<string, string>>;
    };
    workspace.source_anchors = [{
      field: "self_trade_definition",
      source: "governance/assumption-register.json",
      anchor: "CT-ASM-005..CT-ASM-007",
    }];
    expect(workspaceEditorSchema.safeParse(value).success).toBe(true);
    workspace.source_anchors = [{ source: "missing-field.json" }];
    expect(workspaceEditorSchema.safeParse(value).success).toBe(false);
  });
});

describe("studioWorkbenchSchema", () => {
  function governed(id: string, en: string, zh: string) {
    return {
      id,
      version: "1.0.0",
      status: "confirmed",
      name: { en, zh },
      definition: `${en} definition`,
      owner: "actor.owner",
      sources: ["source.requirements"],
      decisions: [],
      tags: [],
    };
  }

  function workbench() {
    return {
      contract: "studio-workbench/v1",
      persistence: "postgresql-s3",
      package_checksum: digest,
      package: {
        package_id: "ontology.exchange_analytics.adt",
        version: "1.2.1",
        status: "confirmed",
        created_at: "2026-08-20T00:00:00Z",
        scenario: {
          ...governed("scenario.adt", "ADT", "ADT"),
          timezone: "Asia/Hong_Kong",
          market_id: "SYNTH-CASH",
          data_window_start: "2025-07-01",
          data_window_end: "2025-12-31",
          periods: [],
          default_role: "MarketAnalyst",
        },
        actors: [], processes: [], sources: [], decisions: [],
        entities: [{
          ...governed("entity.trade", "Trade", "成交"),
          primary_key: "property.trade.id",
          grain: "one trade",
          lifecycle: "executed",
        }],
        properties: [{
          ...governed("property.trade.id", "Trade ID", "成交编号"),
          entity: "entity.trade",
          data_type: "string",
          required: true,
          unit: null,
          enum_values: [],
          null_meaning: "not_allowed",
        }],
        relationships: [{
          ...governed("relationship.trade.market", "Trade market", "成交市场"),
          from_entity: "entity.trade",
          to_entity: "entity.trade",
          predicate: "belongsTo",
          cardinality: "N:1",
        }],
        dimensions: [], rules: [], metrics: [], data_sources: [], bindings: [], joins: [],
        analysis_patterns: [], policies: [], questions: [],
      },
      workspace: {
        schema_version: "adt-draft-workspace/v1",
        workspace_id: "workspace.adt.reference",
        package_id: "ontology.exchange_analytics.adt",
        base_version: "1.2.0",
        target_version: "1.2.1",
        revision: 1,
        created_at: "2026-08-20T00:00:00Z",
        updated_at: "2026-08-20T00:00:00Z",
        revision_created_at: "2026-08-20T00:00:00Z",
        intake_submission_id: "submission.reference.adt.v1",
        intake_checksum: digest,
        source_anchors: [], modified_fields: [], draft: {}, draft_checksum: digest,
        validation: { status: "NOT_RUN", revision: null, draft_checksum: null, validated_at: null, report: null },
        last_published: null,
      },
      intake: { schema_version: "adt-intake-submission/v1", assets: [], gaps: [] },
      revisions: [],
    };
  }

  it("accepts one exact package-driven Studio workbench", () => {
    const parsed = studioWorkbenchSchema.parse(workbench());
    expect(parsed.package.relationships[0].predicate).toBe("belongsTo");
  });

  it("normalizes a true blank generic workspace without legacy ADT fields", () => {
    const value: Record<string, any> = workbench();
    value.package.package_id = "ontology.custom.blank";
    value.package.version = "0.1.0";
    value.package.entities = [];
    value.package.properties = [];
    value.package.relationships = [];
    value.workspace = {
      schema_version: "generic-draft-workspace/v1",
      workspace_id: "workspace.custom.blank",
      package_id: "ontology.custom.blank",
      base_version: "0.1.0",
      target_version: "0.1.0",
      revision: 1,
      created_at: "2026-08-22T00:00:00Z",
      updated_at: "2026-08-22T00:00:00Z",
      revision_created_at: "2026-08-22T00:00:00Z",
      solution_intent: "Start with zero domain assets.",
      modified_fields: [],
      package_operations: [],
      draft_checksum: digest,
      validation: { status: "NOT_RUN", revision: null, draft_checksum: null, validated_at: null, report: null },
      last_published: null,
    };

    const parsed = studioWorkbenchSchema.parse(value);

    expect(parsed.workspace.draft).toEqual({});
    expect(parsed.workspace.source_anchors).toEqual([]);
    expect(parsed.workspace.intake_submission_id).toBeNull();
  });

  it("rejects a relationship to an entity outside the package", () => {
    const value = workbench();
    value.package.relationships[0].to_entity = "entity.browser_fixture";
    expect(studioWorkbenchSchema.safeParse(value).success).toBe(false);
  });
});

describe("solution-neutral Agent contracts", () => {
  it("accepts a package-owned runtime role catalog", () => {
    const parsed = solutionRuntimeSchema.parse({
      package_id: "ontology.exchange_analytics.adt",
      version: "1.2.0",
      release_checksum: digest,
      snapshot_checksum: digest,
      environment_id: "adt-poc",
      certification_profile: "adt-golden-v1",
      default_role: "MarketAnalyst",
      roles: [
        {
          role_id: "MarketAnalyst",
          name: { en: "Market Analyst", zh: "市场分析师" },
          access: "ALLOWED",
        },
        {
          role_id: "ExternalUser",
          name: { en: "External User", zh: "外部用户" },
          access: "DENIED",
        },
      ],
    });
    expect(parsed.default_role).toBe("MarketAnalyst");
    expect(parsed.roles.map((role) => role.role_id)).toEqual([
      "MarketAnalyst",
      "ExternalUser",
    ]);
  });

  it("accepts a Cash Trading question family without widening the ADT LLM contract", () => {
    const parsed = solutionQuestionFamilySchema.parse({
      family_id: "cash-trading.synthetic.analysis.v1",
      family_checksum: digest,
      classification: "constructed_synthetic",
      cases: [{
        case_id: "cash.self-trade.summary.en.v1",
        language: "en",
        question: "Analyze potential self-trades for 2026-08-03 to 2026-08-07.",
        expected_intent: "anomaly_triage",
        required_tools: ["self_trade_summary"],
      }],
    });
    expect(parsed.cases[0].expected_intent).toBe("anomaly_triage");
  });

  it("rejects partial facts on a refused response", () => {
    const refused = {
      status: "REFUSED",
      answer: "Role denied",
      execution_id: null,
      snapshot_checksum: null,
      plan: null,
      steps: [],
      facts: { leaked_count: 20 },
      evidence: [],
      boundary_code: "ROLE_DENIED",
    };
    expect(solutionAnalysisSchema.safeParse(refused).success).toBe(false);
  });

  it("accepts explicit grounded-model metadata on a complete answer", () => {
    const answered = {
      status: "ANSWERED",
      answer: "20 potential self-trade pairs were identified.",
      execution_id: "execution.cash.001",
      snapshot_checksum: digest,
      plan: {
        plan_id: "plan.cash.001",
        intent: "anomaly_triage",
        question: "Analyze potential self-trades for 2026-08-03 to 2026-08-07.",
        snapshot_checksum: digest,
        steps: [{ tool_id: "self_trade_summary" }],
        plan_hash: digest,
      },
      steps: [{ step_id: "step.1", status: "PASS" }],
      facts: { potential_pair_count: 20 },
      evidence: [{
        claim_id: "claim.cash.001",
        display_value: "20",
        result_path: "$.potential_pair_count",
        dataset_checksum: digest,
      }],
      boundary_code: null,
      llm: {
        contract: "solution-llm-execution/v1",
        mode: "ACTIVE",
        status: "GROUNDED",
        provider: "qwen",
        requested_model: "qwen3.8-max",
        model_called: true,
        provider_call_count: 1,
        fallback_used: false,
        reason_code: null,
        profile_checksum: digest,
        activation_id: "activation.cash.v1",
      },
    };
    expect(solutionAnalysisSchema.parse(answered).llm.status).toBe("GROUNDED");
  });
});
