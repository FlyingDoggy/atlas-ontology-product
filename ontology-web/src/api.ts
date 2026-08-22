import { z } from "zod";

const sha256 = z.string().regex(/^[0-9a-f]{64}$/);

export const authSessionSchema = z.discriminatedUnion("authenticated", [
  z.object({ authenticated: z.literal(false) }).strict(),
  z.object({
    authenticated: z.literal(true),
    username: z.string().min(1),
    role: z.enum(["operator", "viewer"]),
    expires_at: z.number().int().positive(),
  }).strict(),
]);

export type AuthSession = z.infer<typeof authSessionSchema>;

export const productContextSchema = z
  .object({
    contract: z.literal("product-context/v1"),
    persistence: z.enum(["legacy-compatibility", "postgresql-s3"]),
    subject_checksum: sha256,
    subject: z
      .object({
        contract: z.literal("product-context-subject/v1"),
        context_id: z.string().min(1),
        product_family_id: z.literal("ontology-analytics"),
        solution_id: z.string().min(1),
        solution_version: z.string().min(1),
        scenario_id: z.string().min(1),
        scenario_name_en: z.string().min(1),
        scenario_name_zh: z.string().min(1),
        classification: z.literal("constructed_synthetic"),
        active_runtime: z
          .object({
            environment_id: z.string().min(1),
            release_checksum: sha256,
            snapshot_checksum: sha256,
            certification_profile: z.string().nullable(),
          })
          .strict(),
        navigation: z
          .object({
            studio: z.literal("/ontology-studio/"),
            agent: z.literal("/ontology-agent/"),
          })
          .strict(),
        limitations: z.array(z.string().min(1)).min(1),
      })
      .strict(),
    artifact: z
      .object({
        store: z.literal("s3-compatible"),
        bucket: z.string().min(1),
        key: z.string().min(1),
        version_id: z.string().min(1),
        sha256,
        size_bytes: z.number().int().positive(),
        media_type: z.literal("application/json"),
      })
      .strict()
      .nullable(),
  })
  .strict()
  .superRefine((value, context) => {
    if (value.persistence === "postgresql-s3" && value.artifact === null) {
      context.addIssue({
        code: "custom",
        message: "PostgreSQL/S3 context is missing its exact artifact reference",
        path: ["artifact"],
      });
    }
    if (value.artifact && value.artifact.sha256 !== value.subject_checksum) {
      context.addIssue({
        code: "custom",
        message: "Context and artifact identities do not match",
        path: ["artifact", "sha256"],
      });
    }
  });

export type ProductContext = z.infer<typeof productContextSchema>;

const localizedTextSchema = z
  .object({ en: z.string().min(1), zh: z.string().min(1) })
  .strict();

const ontologyNameSchema = z
  .object({
    en: z.string().min(1).nullish(),
    zh: z.string().min(1).nullish(),
  })
  .strict()
  .refine((value) => Boolean(value.en || value.zh), {
    message: "Ontology name requires at least one language",
  })
  .transform((value) => ({
    en: value.en ?? value.zh!,
    zh: value.zh ?? value.en!,
  }));

export const solutionDirectoryEntrySchema = z.object({
  contract: z.literal("studio-solution-directory-entry/v1"),
  solution_id: z.string().min(1),
  status: z.enum(["ACTIVE", "ARCHIVED", "DELETED"]),
  display_name: localizedTextSchema,
  description: z.string().min(1),
  owner: z.string().min(1),
  creation_mode: z.enum(["INSTALLED", "TEMPLATE", "IMPORT", "BLANK"]),
  template_solution_id: z.string().min(1).nullable(),
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
}).strict();

export type SolutionDirectoryEntry = z.infer<typeof solutionDirectoryEntrySchema>;

const exactJsonArtifactSchema = z
  .object({
    store: z.literal("s3-compatible"),
    bucket: z.string().min(1),
    key: z.string().min(1),
    version_id: z.string().min(1),
    sha256,
    size_bytes: z.number().int().positive(),
    media_type: z.literal("application/json"),
  })
  .strict();

export const solutionCatalogSchema = z
  .object({
    contract: z.literal("studio-solution-catalog/v1"),
    solutions: z
      .array(
        z
          .object({
            solution_id: z.string().min(1),
            solution_version: z.string().regex(/^[0-9]+\.[0-9]+\.[0-9]+$/),
            semantic_source_version: z.string().regex(/^[0-9]+\.[0-9]+\.[0-9]+$/),
            scenario_id: z.string().min(1),
            workspace_id: z.string().min(1),
            studio_adapter_id: z.string().min(1),
            classification: z.literal("constructed_synthetic"),
            display_name: z
              .object({ en: z.string().min(1), zh: z.string().min(1) })
              .strict(),
            directory: solutionDirectoryEntrySchema.optional(),
            components: z
              .array(
                z
                  .object({
                    component_id: z.string().min(1),
                    kind: z.enum([
                      "authoring_profile",
                      "semantic_source",
                      "agent_experience",
                      "reference_evaluation",
                    ]),
                    sha256,
                    media_type: z.enum(["application/json", "application/yaml"]),
                  })
                  .strict(),
              )
              .length(4),
            limitations: z.array(z.string().min(1)).min(1),
            persistence: z.enum(["legacy-compatibility", "postgresql-s3"]),
            subject_checksum: sha256,
            artifact: exactJsonArtifactSchema.nullable(),
            installable: z.boolean().optional(),
            resource_count: z.number().int().nonnegative().optional(),
            bundle_checksum: sha256.nullable().optional(),
          })
          .strict()
          .superRefine((value, context) => {
            if (value.persistence === "postgresql-s3" && value.artifact === null) {
              context.addIssue({
                code: "custom",
                message: "Durable solution registration is missing its exact artifact",
                path: ["artifact"],
              });
            }
            if (value.artifact && value.artifact.sha256 !== value.subject_checksum) {
              context.addIssue({
                code: "custom",
                message: "Solution registration artifact identity does not match",
                path: ["artifact", "sha256"],
              });
            }
          }),
      )
      .min(1),
  })
  .strict();

export type SolutionCatalog = z.infer<typeof solutionCatalogSchema>;
export type StudioSolution = SolutionCatalog["solutions"][number];

const agentSolutionSchema = z
  .object({
    solution_id: z.string().min(1),
    solution_version: z.string().regex(/^[0-9]+\.[0-9]+\.[0-9]+$/),
    semantic_source_version: z.string().regex(/^[0-9]+\.[0-9]+\.[0-9]+$/),
    scenario_id: z.string().min(1),
    workspace_id: z.string().min(1),
    studio_adapter_id: z.string().min(1),
    classification: z.literal("constructed_synthetic"),
    display_name: z.object({ en: z.string().min(1), zh: z.string().min(1) }).strict(),
    directory: solutionDirectoryEntrySchema.optional(),
    components: z.array(
      z.object({
        component_id: z.string().min(1),
        kind: z.enum(["authoring_profile", "semantic_source", "agent_experience", "reference_evaluation"]),
        sha256,
        media_type: z.enum(["application/json", "application/yaml"]),
      }).strict(),
    ).length(4),
    limitations: z.array(z.string().min(1)).min(1),
    persistence: z.enum(["legacy-compatibility", "postgresql-s3"]),
    subject_checksum: sha256,
    artifact: exactJsonArtifactSchema.nullable(),
    installable: z.boolean().optional(),
    resource_count: z.number().int().nonnegative().optional(),
    bundle_checksum: sha256.nullable().optional(),
    runtime: z.object({
      state: z.enum(["ACTIVE", "NOT_ACTIVE"]),
      environment_id: z.string().min(1).nullable(),
      snapshot_checksum: sha256.nullable(),
    }).strict(),
  })
  .strict();

export const agentSolutionCatalogSchema = z.object({
  contract: z.literal("agent-solution-catalog/v1"),
  solutions: z.array(agentSolutionSchema).min(1),
}).strict();

export type AgentSolutionCatalog = z.infer<typeof agentSolutionCatalogSchema>;
export type AgentSolution = AgentSolutionCatalog["solutions"][number];

export const solutionQuestionFamilySchema = z.object({
  family_id: z.string().min(1),
  family_checksum: sha256,
  classification: z.literal("constructed_synthetic"),
  cases: z.array(z.object({
    case_id: z.string().min(1),
    language: z.enum(["en", "zh"]),
    question: z.string().min(1),
    expected_intent: z.string().min(1),
    required_tools: z.array(z.string().min(1)).min(1),
  }).strict()).min(1),
}).strict();

export type SolutionQuestionFamily = z.infer<typeof solutionQuestionFamilySchema>;

export const solutionRuntimeSchema = z.object({
  package_id: z.string().min(1),
  version: z.string().min(1),
  release_checksum: sha256,
  snapshot_checksum: sha256,
  environment_id: z.string().min(1),
  certification_profile: z.string().nullable(),
  default_role: z.string().min(1),
  roles: z.array(z.object({
    role_id: z.string().min(1),
    name: localizedTextSchema,
    access: z.enum(["ALLOWED", "DENIED"]),
  }).strict()).min(1),
}).strict();

export type SolutionRuntime = z.infer<typeof solutionRuntimeSchema>;

export const solutionOntologySchema = z.object({
  package_id: z.string().min(1),
  version: z.string().min(1),
  snapshot_checksum: sha256,
  scenario: z.record(z.string(), z.unknown()),
  metrics: z.array(z.object({
    id: z.string().min(1),
    version: z.string().min(1),
    name: localizedTextSchema,
    definition: z.string().min(1),
    unit: z.string().min(1),
    formula: z.record(z.string(), z.unknown()),
  }).strict()),
  analysis_patterns: z.array(z.object({
    id: z.string().min(1),
    intent: z.string().min(1),
    operation: z.string().min(1),
    output_fields: z.array(z.string()),
  }).strict()),
}).strict();

export type SolutionOntology = z.infer<typeof solutionOntologySchema>;

export const solutionLlmExecutionSchema = z.object({
  contract: z.literal("solution-llm-execution/v1"),
  mode: z.enum(["OFF", "SHADOW", "ACTIVE"]),
  status: z.enum(["DETERMINISTIC_ONLY", "SHADOW_VERIFIED", "GROUNDED", "FALLBACK"]),
  provider: z.literal("qwen"),
  requested_model: z.literal("qwen3.8-max"),
  model_called: z.boolean(),
  provider_call_count: z.number().int().min(0).max(1),
  fallback_used: z.boolean(),
  reason_code: z.string().nullable(),
  profile_checksum: sha256.nullable(),
  activation_id: z.string().nullable(),
}).strict().superRefine((value, context) => {
  if (value.model_called !== (value.provider_call_count === 1)) {
    context.addIssue({ code: "custom", message: "Model call count is inconsistent" });
  }
  if (value.status === "FALLBACK" && !value.fallback_used) {
    context.addIssue({ code: "custom", message: "Fallback status is missing its fallback marker" });
  }
  if (value.status !== "FALLBACK" && value.fallback_used) {
    context.addIssue({ code: "custom", message: "Non-fallback status cannot claim fallback" });
  }
  if (["GROUNDED", "SHADOW_VERIFIED"].includes(value.status) && !value.model_called) {
    context.addIssue({ code: "custom", message: "Grounded status requires one model call" });
  }
});

export const solutionAnalysisSchema = z.object({
  status: z.enum(["ANSWERED", "CLARIFY", "REFUSED", "FAILED"]),
  answer: z.string(),
  execution_id: z.string().nullable(),
  snapshot_checksum: sha256.nullable(),
  plan: z.object({
    plan_id: z.string().min(1),
    intent: z.string().min(1),
    question: z.string().min(1),
    snapshot_checksum: sha256,
    steps: z.array(z.record(z.string(), z.unknown())),
    plan_hash: sha256,
  }).strict().nullable(),
  steps: z.array(z.object({
    step_id: z.string().min(1),
    status: z.enum(["PASS", "FAIL", "SKIPPED"]),
  }).passthrough()),
  facts: z.record(z.string(), z.unknown()),
  evidence: z.array(z.object({
    claim_id: z.string().min(1),
    display_value: z.string(),
    result_path: z.string().min(1),
    dataset_checksum: sha256,
  }).passthrough()),
  boundary_code: z.string().nullable(),
  llm: solutionLlmExecutionSchema,
}).strict().superRefine((value, context) => {
  if (value.status === "ANSWERED") {
    if (!value.execution_id || !value.snapshot_checksum || !value.plan || value.evidence.length === 0) {
      context.addIssue({ code: "custom", message: "Answered result is missing its exact execution evidence" });
    }
    return;
  }
  if (value.plan !== null || value.steps.length > 0 || Object.keys(value.facts).length > 0 || value.evidence.length > 0) {
    context.addIssue({ code: "custom", message: "A boundary response released partial analysis content" });
  }
});

export type SolutionAnalysis = z.infer<typeof solutionAnalysisSchema>;

const editorDescriptorSchema = z
  .object({
    contract: z.literal("studio-editor-descriptor/v1"),
    descriptor_id: z.string().min(1),
    version: z.string().regex(/^[0-9]+\.[0-9]+\.[0-9]+$/),
    workspace_id: z.string().min(1),
    studio_adapter_id: z.string().min(1),
    draft_schema_version: z.string().min(1),
    operations_contract: z.literal("studio-draft-operations/v1"),
    title: localizedTextSchema,
    description: localizedTextSchema,
    semantic_slot_manifest: z
      .object({ locator: z.string().min(1), sha256 })
      .strict(),
    fields: z
      .array(
        z
          .object({
            path: z.string().min(1),
            label: localizedTextSchema,
            help: localizedTextSchema,
            control: z.enum(["TEXTAREA", "SELECT", "CHECKBOX", "MULTI_SELECT"]),
            value_kind: z.enum(["STRING", "BOOLEAN", "STRING_LIST"]),
            required: z.boolean(),
            options: z.array(
              z.object({ value: z.string().min(1), label: localizedTextSchema }).strict(),
            ),
          })
          .strict(),
      )
      .min(1),
  })
  .strict();

const packageCollectionSchema = z.enum([
  "sources", "decisions", "actors", "processes", "entities", "properties", "relationships",
  "dimensions", "rules", "metrics", "data_sources", "bindings", "joins",
  "sql_contracts", "analysis_patterns", "policies", "questions",
]);

export const packageDraftOperationSchema = z.object({
  action: z.enum(["UPSERT", "CONFIRM", "DEPRECATE"]),
  collection: packageCollectionSchema,
  object_id: z.string().min(1),
  payload: z.record(z.string(), z.unknown()).nullable(),
}).strict();

const draftWorkspaceSchema = z
  .object({
    schema_version: z.string().min(1),
    workspace_id: z.string().min(1),
    package_id: z.string().min(1),
    base_version: z.string().min(1),
    target_version: z.string().min(1),
    revision: z.number().int().positive(),
    created_at: z.string().min(1),
    updated_at: z.string().min(1),
    revision_created_at: z.string().nullable(),
    solution_intent: z.string().optional().default(""),
    authoring_language: z.enum(["en", "zh"]).nullable().optional(),
    language_policy_digest: sha256.nullable().optional(),
    intake_submission_id: z.string().min(1).nullable().optional().default(null),
    intake_checksum: sha256.nullable().optional().default(null),
    source_anchors: z.array(
      z.record(z.string().min(1), z.string().min(1)).superRefine((anchor, context) => {
        if (!anchor.field || Object.keys(anchor).length < 2) {
          context.addIssue({
            code: "custom",
            message: "Source anchor requires a semantic field and at least one provenance locator",
          });
        }
      }),
    ).default([]),
    modified_fields: z.array(z.string()),
    draft: z.record(z.string(), z.unknown()).default({}),
    package_operations: z.array(packageDraftOperationSchema).default([]),
    draft_checksum: sha256,
    validation: z
      .object({
        status: z.enum(["NOT_RUN", "STALE", "PASS", "FAIL"]),
        revision: z.number().int().positive().nullable(),
        draft_checksum: sha256.nullable(),
        validated_at: z.string().nullable(),
        report: z.record(z.string(), z.unknown()).nullable(),
      })
      .strict(),
    last_published: z
      .object({
        package_id: z.string().min(1),
        version: z.string().min(1),
        checksum: sha256,
      })
      .strict()
      .nullable(),
  })
  .strict();

const governedStatusSchema = z.enum([
  "proposed",
  "needs_clarification",
  "confirmed",
  "rejected",
  "published",
  "deprecated",
]);

const governedObjectSchema = z.object({
  id: z.string().min(1),
  version: z.string().regex(/^[0-9]+\.[0-9]+\.[0-9]+$/),
  status: governedStatusSchema,
  name: ontologyNameSchema,
  definition: z.string().min(1),
  owner: z.string().min(1),
  sources: z.array(z.string().min(1)).min(1),
  decisions: z.array(z.string().min(1)),
  tags: z.array(z.string()),
});

const entitySchema = governedObjectSchema.extend({
  primary_key: z.string().min(1),
  grain: z.string().min(1),
  lifecycle: z.string().min(1),
}).strict();

const propertySchema = governedObjectSchema.extend({
  entity: z.string().min(1),
  data_type: z.enum(["string", "integer", "decimal", "boolean", "date", "datetime", "enum"]),
  required: z.boolean(),
  unit: z.string().nullable(),
  enum_values: z.array(z.string()),
  null_meaning: z.string().min(1),
}).strict();

const relationshipSchema = governedObjectSchema.extend({
  from_entity: z.string().min(1),
  to_entity: z.string().min(1),
  predicate: z.string().min(1),
  cardinality: z.enum(["1:1", "1:N", "N:1", "N:N"]),
}).strict();

const metricSchema = governedObjectSchema.extend({
  metric_type: z.enum(["base", "derived"]),
  base_entity: z.string().min(1),
  result_grain: z.array(z.string()),
  value_type: z.enum(["integer", "decimal", "percentage"]),
  unit: z.string().min(1),
  aggregation_semantics: z.string().min(1),
  formula: z.record(z.string(), z.unknown()),
  query: z.record(z.string(), z.unknown()),
  allowed_dimensions: z.array(z.string()),
  null_policy: z.string().min(1),
  zero_denominator_policy: z.string().min(1),
}).strict();

const ruleSchema = governedObjectSchema.extend({
  rule_type: z.enum(["eligibility", "quality", "calendar", "policy", "alert"]),
  all: z.array(z.record(z.string(), z.unknown())),
  failure_behavior: z.enum(["exclude", "block", "warn"]),
}).strict();

const policySchema = governedObjectSchema.extend({
  allowed_roles: z.array(z.string()),
  denied_roles: z.array(z.string()),
  allowed_grains: z.array(z.string()),
  denied_fields: z.array(z.string()),
  minimum_group_size: z.number().int().positive(),
}).strict();

const dataSourceSchema = governedObjectSchema.extend({
  protocol: z.literal("tabular/v1"),
  tables: z.array(z.object({
    name: z.string().min(1),
    grain: z.string().min(1),
    primary_key: z.array(z.string()),
    fields: z.array(z.object({
      name: z.string().min(1),
      data_type: z.enum(["string", "integer", "decimal", "boolean", "date", "datetime"]),
      nullable: z.boolean(),
      description: z.string(),
      unit: z.string().nullable(),
    }).strict()),
  }).strict()),
}).strict();

const bindingSchema = governedObjectSchema.extend({
  logical_target: z.string().min(1),
  source: z.string().min(1),
  table: z.string().min(1),
  column: z.string().min(1),
  data_type: z.enum(["string", "integer", "decimal", "boolean", "date", "datetime"]),
  unit: z.string().nullable(),
  transformation: z.string().min(1),
}).strict();

const joinSchema = governedObjectSchema.extend({
  left_source: z.string().min(1),
  left_table: z.string().min(1),
  right_source: z.string().min(1),
  right_table: z.string().min(1),
  keys: z.array(z.object({ left_column: z.string().min(1), right_column: z.string().min(1) }).strict()).min(1),
  expected_cardinality: z.enum(["1:1", "N:1"]),
  fanout_policy: z.enum(["block", "deduplicate_reviewed"]),
}).strict();

const sqlContractSchema = governedObjectSchema.extend({
  dialect: z.enum(["ansi", "postgresql", "duckdb", "bigquery", "snowflake", "spark", "other"]),
  statement_source: z.string().min(1),
  statement_locator: z.string().min(1),
  inputs: z.array(z.object({
    source: z.string().min(1),
    table: z.string().min(1),
    alias: z.string().nullable(),
  }).strict()),
  output_fields: z.array(z.string().min(1)),
  implements: z.array(z.string().min(1)),
  parameters: z.array(z.object({
    name: z.string().min(1),
    data_type: z.enum(["string", "integer", "decimal", "boolean", "date", "datetime"]),
    required: z.boolean(),
    description: z.string(),
  }).strict()),
  execution_mode: z.enum(["reference_only", "validated_query", "runtime_tool"]),
  read_only: z.literal(true),
}).strict();

const workbenchPackageSchema = z.object({
  package_id: z.string().min(1),
  version: z.string().regex(/^[0-9]+\.[0-9]+\.[0-9]+$/),
  status: governedStatusSchema,
  created_at: z.string().min(1),
  authoring_policy: z.object({
    contract: z.literal("ontology-authoring-policy/v1"),
    authoring_language: z.enum(["en", "zh"]),
    allowed_verbatim_terms: z.array(z.string()),
    policy_digest: sha256,
  }).strict().nullable().optional(),
  scenario: governedObjectSchema.passthrough(),
  actors: z.array(governedObjectSchema.passthrough()),
  processes: z.array(governedObjectSchema.passthrough()),
  sources: z.array(z.object({
    id: z.string().min(1), source_type: z.string().min(1), title: z.string().min(1),
    locator: z.string().min(1), owner: z.string().min(1), captured_on: z.string().min(1),
    trust: z.enum(["primary", "secondary", "assumption"]), notes: z.string(),
  }).strict()),
  decisions: z.array(z.object({
    id: z.string().min(1), question: z.string().min(1), options: z.array(z.string()),
    decision: z.string(), decided_by: z.string(), decided_on: z.string(),
    affects: z.array(z.string()), residual_assumption: z.string(),
  }).strict()),
  entities: z.array(entitySchema),
  properties: z.array(propertySchema),
  relationships: z.array(relationshipSchema),
  dimensions: z.array(governedObjectSchema.passthrough()),
  rules: z.array(ruleSchema),
  metrics: z.array(metricSchema),
  data_sources: z.array(dataSourceSchema),
  bindings: z.array(bindingSchema),
  joins: z.array(joinSchema),
  sql_contracts: z.array(sqlContractSchema).default([]),
  analysis_patterns: z.array(governedObjectSchema.passthrough()),
  policies: z.array(policySchema),
  questions: z.array(governedObjectSchema.passthrough()),
}).strict();

const sourceProjectionAnchorSchema = z.object({
  contract: z.literal("source-anchor/v1"),
  source_id: z.string().min(1),
  source_checksum: sha256,
  locator_kind: z.enum(["MARKDOWN_TABLE_ROW", "TEXT_RANGE", "XLSX_ROW", "XLSX_RANGE"]),
  locator: z.string().min(1),
  line_number: z.number().int().positive(),
  sheet_name: z.string().min(1).nullable().optional(),
  cell_range: z.string().min(1).nullable().optional(),
  snippet_checksum: sha256,
}).strict();

const studioAuthoringProjectionSchema = z.object({
  contract: z.literal("studio-authoring-projection/v1"),
  source_mode: z.enum(["EXACT_TRANSCRIPTION", "CANONICAL_FALLBACK"]),
  requirements: z.array(z.object({
    contract: z.literal("requirement-projection/v1"),
    requirement_key: z.string().regex(/^O-[0-9]{2}$/),
    question: z.string().min(1),
    minimum_output: z.string().min(1),
    presentation: z.string().min(1),
    status: z.enum(["SOURCE_SUPPORTED", "CANONICAL_DRAFT"]),
    support_class: z.enum(["DIRECT_EXACT", "CANONICAL_DRAFT"]),
    source_anchor: sourceProjectionAnchorSchema.nullable(),
  }).strict()),
  metric_candidates: z.array(z.object({
    contract: z.literal("metric-candidate-projection/v1"),
    metric_key: z.string().regex(/^M-[0-9]{2}$/),
    name: z.string().min(1),
    definition: z.string().min(1),
    calculation_logic: z.string().min(1),
    filters_and_scope: z.string().min(1),
    grain_and_dimensions: z.string().min(1),
    unit: z.string().min(1),
    null_and_zero_policy: z.string().min(1),
    primary_sources: z.string().min(1),
    source_status: z.string().min(1),
    support_class: z.enum(["DIRECT_EXACT", "CANONICAL_DRAFT"]),
    compile_status: z.enum(["EXECUTABLE", "SOURCE_CANDIDATE"]),
    canonical_metric_id: z.string().min(1).nullable(),
    ontology_status: z.enum(["REVIEWED", "DRAFT", "UNMAPPED"]),
    runtime_status: z.enum(["SUPPORTED", "NOT_YET_SUPPORTED", "NOT_APPLICABLE"]),
    governance_status: z.enum(["REVIEWED", "REVIEWED_WITH_ASSUMPTIONS", "UNREVIEWED"]),
    source_anchor: sourceProjectionAnchorSchema.nullable(),
  }).strict()),
}).strict();

export const studioWorkbenchSchema = z.object({
  contract: z.literal("studio-workbench/v1"),
  persistence: z.enum(["legacy-compatibility", "postgresql-s3"]),
  package_checksum: sha256,
  asset_checksums: z.record(z.string().min(1), sha256).default({}),
  package: workbenchPackageSchema,
  workspace: draftWorkspaceSchema,
  intake: z.record(z.string(), z.unknown()),
  authoring: studioAuthoringProjectionSchema.optional().default({
    contract: "studio-authoring-projection/v1",
    source_mode: "CANONICAL_FALLBACK",
    requirements: [],
    metric_candidates: [],
  }),
  revisions: z.array(z.record(z.string(), z.unknown())),
  semantic_change_requests: z.array(z.record(z.string(), z.unknown())).default([]),
}).strict().superRefine((value, context) => {
  if (value.workspace.package_id !== value.package.package_id) {
    context.addIssue({ code: "custom", message: "Workbench package/workspace identity mismatch" });
  }
  if (value.workspace.target_version !== value.package.version) {
    context.addIssue({ code: "custom", message: "Workbench candidate version mismatch" });
  }
  const entityIds = new Set(value.package.entities.map((item) => item.id));
  for (const property of value.package.properties) {
    if (!entityIds.has(property.entity)) {
      context.addIssue({ code: "custom", message: `Unknown property entity ${property.entity}` });
    }
  }
  for (const relationship of value.package.relationships) {
    if (!entityIds.has(relationship.from_entity) || !entityIds.has(relationship.to_entity)) {
      context.addIssue({ code: "custom", message: `Unknown relationship endpoint ${relationship.id}` });
    }
  }
});

export type StudioWorkbench = z.infer<typeof studioWorkbenchSchema>;
export type StudioAuthoringProjection = z.infer<typeof studioAuthoringProjectionSchema>;

export const semanticChangeRequestTypeSchema = z.enum([
  "MISSING_CONCEPT",
  "WRONG_DEFINITION",
  "MISSING_RELATIONSHIP",
  "METRIC_LOGIC",
  "DATA_BINDING",
  "ANALYSIS_CAPABILITY",
  "OTHER",
]);

export const semanticChangeRequestSchema = z.object({
  contract: z.literal("semantic-change-request/v1"),
  request_id: z.string().regex(/^scr\.[0-9a-f]{32}$/),
  classification: z.literal("constructed_synthetic"),
  solution_id: z.string().min(1),
  environment_id: z.string().min(1),
  snapshot_checksum: sha256,
  execution_id: z.string().regex(/^exec\.[0-9a-f]{32}$/),
  question: z.string().min(1),
  request_type: semanticChangeRequestTypeSchema,
  title: z.string().min(3),
  observation: z.string().min(3),
  proposed_change: z.string().min(3),
  claim_refs: z.array(z.string().min(1)).min(1),
  status: z.literal("PROPOSED_UNTRIAGED"),
  created_at: z.string().min(1),
  request_digest: sha256,
}).strict();

export type SemanticChangeRequestType = z.infer<typeof semanticChangeRequestTypeSchema>;
export type SemanticChangeRequest = z.infer<typeof semanticChangeRequestSchema>;
export type SemanticChangeRequestInput = {
  execution_id: string;
  snapshot_checksum: string;
  request_type: SemanticChangeRequestType;
  title: string;
  observation: string;
  proposed_change: string;
  claim_refs: string[];
};

const installedStudioLlmStatusSchema = z.object({
  installed: z.literal(true),
  demo_class: z.literal("STUDIO_LLM_ENGINEERING_DEMO"),
  mode: z.enum(["off", "active-observation-canary"]),
  provider: z.literal("qwen"),
  requested_model: z.literal("qwen3.8-max"),
  workflow: z.literal("CLEARED_INPUT_TO_HUMAN_REVIEWED_DRAFT"),
  slot_count: z.number().int().positive(),
  label: z.string().min(1),
  can_publish: z.literal(false),
}).strict();

const unavailableStudioLlmStatusSchema = z.object({
  installed: z.literal(false),
  demo_class: z.literal("STUDIO_LLM_ENGINEERING_DEMO"),
  mode: z.literal("off"),
  provider: z.null(),
  requested_model: z.null(),
  workflow: z.literal("NOT_INSTALLED"),
  slot_count: z.literal(0),
  label: z.string().min(1),
  can_publish: z.literal(false),
}).strict();

export const studioLlmStatusSchema = z.discriminatedUnion("installed", [
  installedStudioLlmStatusSchema,
  unavailableStudioLlmStatusSchema,
]);

export const studioSlotValueSchema = z.object({
  kind: z.enum(["STRING", "BOOLEAN", "STRING_LIST"]),
  string_value: z.string().nullable().optional(),
  boolean_value: z.boolean().nullable().optional(),
  string_list_value: z.array(z.string()).nullable().optional(),
}).strict().superRefine((value, context) => {
  const populated = [value.string_value, value.boolean_value, value.string_list_value]
    .filter((item) => item !== null && item !== undefined).length;
  if (populated !== 1) context.addIssue({ code: "custom", message: "Studio slot value requires exactly one typed value" });
  if (value.kind === "STRING" && !value.string_value) context.addIssue({ code: "custom", message: "STRING value is missing" });
  if (value.kind === "BOOLEAN" && typeof value.boolean_value !== "boolean") context.addIssue({ code: "custom", message: "BOOLEAN value is missing" });
  if (value.kind === "STRING_LIST" && (!value.string_list_value || value.string_list_value.length === 0)) context.addIssue({ code: "custom", message: "STRING_LIST value is missing" });
});

export const studioObservationSchema = z.object({
  observation_id: z.string().regex(/^observation\.[0-9a-f]{32}\.[0-9]{2}$/),
  slot_id: z.string().min(1),
  status: z.enum(["PROPOSED", "MISSING"]),
  support_code: z.enum(["DIRECT_SOURCE", "MISSING_SOURCE"]),
  value: studioSlotValueSchema.nullable(),
  source_anchor: z.record(z.string(), z.unknown()).nullable(),
  source_fragment_checksum: sha256.nullable(),
}).strict().superRefine((value, context) => {
  if (value.status === "PROPOSED" && (!value.value || !value.source_anchor || !value.source_fragment_checksum || value.support_code !== "DIRECT_SOURCE")) {
    context.addIssue({ code: "custom", message: "PROPOSED observation requires exact source support" });
  }
  if (value.status === "MISSING" && (value.value || value.source_anchor || value.source_fragment_checksum || value.support_code !== "MISSING_SOURCE")) {
    context.addIssue({ code: "custom", message: "MISSING observation cannot claim source support" });
  }
});

export const studioObservationSetSchema = z.object({
  contract: z.literal("studio-observation-set/v1"),
  observation_set_id: z.string().regex(/^observation-set\.[0-9a-f]{32}$/),
  run_id: z.string().regex(/^studio-run\.[0-9a-f]{32}$/),
  workspace_id: z.string().min(1),
  base_revision: z.number().int().positive(),
  base_draft_checksum: sha256,
  intake_checksum: sha256,
  profile_digest: sha256,
  slot_manifest_digest: sha256,
  egress_decision_digest: sha256,
  projection_digest: sha256,
  requested_model: z.literal("qwen3.8-max"),
  response_model: z.literal("qwen3.8-max"),
  provider_request_id: z.string().min(1),
  created_at: z.string().min(1),
  projection: z.object({ contract: z.literal("studio-cleared-input-projection/v1") }).passthrough(),
  observations: z.array(studioObservationSchema).length(5),
  observation_set_checksum: sha256,
}).strict().superRefine((value, context) => {
  if (new Set(value.observations.map((item) => item.observation_id)).size !== value.observations.length) {
    context.addIssue({ code: "custom", message: "Observation identities must be unique" });
  }
});

const studioReviewDecisionSchema = z.object({
  contract: z.literal("studio-observation-review-decision/v1"),
  decision_id: z.string().min(1),
  observation_set_id: z.string().min(1),
  status: z.enum(["APPLIED", "REVIEWED_NO_CHANGE"]),
  resulting_revision: z.number().int().positive(),
  decision_checksum: sha256,
}).passthrough();

export const studioObservationListSchema = z.object({
  workspace_id: z.string().min(1),
  observation_sets: z.array(z.object({
    observation_set: studioObservationSetSchema,
    decision: studioReviewDecisionSchema.nullable(),
  }).strict()),
}).strict();

export const studioReviewResultSchema = z.object({
  decision: studioReviewDecisionSchema,
  workspace: z.lazy(() => draftWorkspaceSchema),
}).strict();

export type StudioLlmStatus = z.infer<typeof studioLlmStatusSchema>;
export type StudioSlotValue = z.infer<typeof studioSlotValueSchema>;
export type StudioObservation = z.infer<typeof studioObservationSchema>;
export type StudioObservationSet = z.infer<typeof studioObservationSetSchema>;
export type StudioObservationList = z.infer<typeof studioObservationListSchema>;
export type StudioObservationDisposition = {
  observation_id: string;
  action: "ACCEPT" | "EDIT" | "REJECT";
  reason_code: "SOURCE_SUPPORTED" | "REVIEWER_CORRECTION" | "NOT_SUPPORTED" | "KEEP_MISSING";
  edited_value: StudioSlotValue | null;
};

const constructionSourceSettlementSchema = z.object({
  contract: z.literal("construction-source-settlement/v1"),
  source_id: z.string().min(1),
  source_checksum: sha256,
  locator: z.string().min(1),
  source_kind: z.string().min(1),
  outcome: z.enum(["SETTLED", "UNSUPPORTED", "FAILED"]),
  detail: z.string().min(1),
}).strict();

const constructionStageReceiptSchema = z.object({
  contract: z.literal("construction-stage-receipt/v1"),
  stage: z.enum(["SOURCE_SETTLEMENT", "STRUCTURED_EXTRACTION", "BUILDER_AGENT", "PACKAGED_CASE_COMPILATION", "SEMANTICA_PROPOSAL", "CANDIDATE_PRECHECK", "REVIEWER_AGENT"]),
  status: z.enum(["PASS", "WARN", "SKIPPED", "FAIL"]),
  input_digest: sha256,
  output_digest: sha256,
  item_count: z.number().int().nonnegative(),
  implementation: z.string().min(1),
  detail: z.string().min(1),
}).strict();

const candidateDraftDiffSchema = z.object({
  contract: z.literal("candidate-draft-diff/v1"),
  change_type: z.enum(["CREATE", "UPDATE", "NO_CHANGE", "NON_COMPILABLE", "UNKNOWN"]),
  before: z.record(z.string(), z.unknown()).nullable(),
  after: z.record(z.string(), z.unknown()).nullable(),
  changed_paths: z.array(z.string()),
}).strict();

const reviewerFindingSchema = z.object({
  contract: z.literal("reviewer-finding/v1"),
  finding_id: z.string().regex(/^finding\.[A-Za-z0-9][A-Za-z0-9._-]*$/),
  finding_type: z.enum([
    "UNSUPPORTED_CLAIM", "EVIDENCE_CONFLICT", "DUPLICATE_CANDIDATE",
    "BROKEN_REFERENCE", "INCONSISTENT_CONTRACT", "MISSING_COVERAGE",
    "MERGE_SUGGESTION", "DEPRECATION_SUGGESTION", "RELEASE_BLOCKER",
  ]),
  severity: z.enum(["INFO", "WARN", "ERROR"]),
  summary: z.string().min(1),
  detail: z.string().min(1),
  candidate_ids: z.array(z.string().regex(/^candidate\.[0-9a-f]{32}$/)).min(1),
  evidence_fragment_ids: z.array(z.string()),
  blocks_release: z.boolean(),
  recommendation: z.string().min(1),
}).strict();

export const constructionCandidateSchema = z.object({
  contract: z.literal("construction-candidate/v1"),
  candidate_id: z.string().regex(/^candidate\.[0-9a-f]{32}$/),
  occurrence_key: sha256,
  revision_digest: sha256,
  candidate_type: z.enum([
    "SOURCE", "GAP", "REQUIREMENT", "ACTOR", "PROCESS", "OBJECT", "LINK", "PROPERTY",
    "DIMENSION", "METRIC", "RULE", "DATA_SOURCE", "MAPPING", "JOIN", "SQL_CONTRACT",
    "ANALYSIS_PATTERN", "POLICY", "QUESTION",
  ]),
  label: z.string().min(1),
  definition: z.string().min(1),
  support_class: z.enum(["DIRECT_EXACT", "DERIVED_DETERMINISTIC", "MODEL_INFERRED", "HEURISTIC", "REVIEWER_AUTHORED", "SYNTHETIC", "MISSING"]),
  risk_class: z.enum(["LOW", "MEDIUM", "HIGH"]),
  review_status: z.literal("UNREVIEWED"),
  compile_eligible: z.boolean(),
  canonical_target: z.string().nullable(),
  proposal: z.record(z.string(), z.unknown()),
  proposed_operation: packageDraftOperationSchema.nullable(),
  source_anchors: z.array(sourceProjectionAnchorSchema),
  impact_refs: z.array(z.string()),
  limitations: z.array(z.string()),
  draft_diff: candidateDraftDiffSchema,
}).strict().superRefine((value, context) => {
  if (value.compile_eligible !== Boolean(value.proposed_operation)) {
    context.addIssue({ code: "custom", message: "Compile eligibility and operation disagree" });
  }
});

export const constructionRunSchema = z.object({
  contract: z.literal("construction-run/v1"),
  run_id: z.string().regex(/^construction-run\.[0-9a-f]{32}$/),
  attempt_id: z.string().regex(/^construction-attempt\.[0-9a-f]{32}$/),
  lease_epoch: z.number().int().positive(),
  workspace_id: z.string().min(1),
  solution_id: z.string().min(1),
  base_revision: z.number().int().positive(),
  base_draft_checksum: sha256,
  source_set_digest: sha256,
  authoring_language: z.enum(["en", "zh"]).nullable().optional(),
  language_policy_digest: sha256.nullable().optional(),
  profile_ref: z.string().min(1),
  status: z.enum(["QUEUED", "RUNNING", "NEEDS_REVIEW", "FAILED", "CANCEL_REQUESTED", "CANCELLED", "STALE"]),
  engine_status: z.enum(["COMPLETED", "NOT_CONFIGURED", "FAILED"]),
  selected_sources: z.array(constructionSourceSettlementSchema).min(1),
  stage_receipts: z.array(constructionStageReceiptSchema).min(1),
  candidates: z.array(constructionCandidateSchema).min(1),
  machine_findings: z.array(reviewerFindingSchema),
  started_at: z.string().min(1),
  completed_at: z.string().nullable(),
  run_checksum: sha256,
}).strict();

const constructionReviewDecisionSchema = z.object({
  contract: z.enum([
    "construction-review-decision/v1",
    "construction-review-decision/v2",
  ]),
  decision_id: z.string().regex(/^construction-decision\.[0-9a-f]{32}$/),
  run_id: z.string().regex(/^construction-run\.[0-9a-f]{32}$/),
  run_checksum: sha256,
  workspace_id: z.string().min(1),
  base_revision: z.number().int().positive(),
  base_draft_checksum: sha256,
  reviewer: z.string().min(1),
  dispositions: z.array(z.record(z.string(), z.unknown())).min(1),
  review_batch_checksum: sha256.nullable(),
  request_digest: sha256,
  status: z.enum(["APPLIED", "APPLIED_WITH_DEFERRED", "REVIEWED_NO_CHANGE"]),
  resulting_revision: z.number().int().positive(),
  resulting_draft_checksum: sha256,
  applied: z.array(z.object({
    candidate_id: z.string().regex(/^candidate\.[0-9a-f]{32}$/),
    collection: packageCollectionSchema,
    object_id: z.string().min(1),
    change_type: z.enum(["CREATE", "UPDATE", "NO_CHANGE", "UNKNOWN"]),
    changed_paths: z.array(z.string()),
    previous_asset_digest: sha256.nullable(),
    reviewed_content_digest: sha256,
    final_confirmed_asset_digest: sha256,
    confirmation_status: z.enum(["CONFIRMED", "EXACT_REGISTERED"]),
  }).strict()).default([]),
  deferred_candidate_ids: z.array(z.string().regex(/^candidate\.[0-9a-f]{32}$/)).default([]),
  rejected_candidate_ids: z.array(z.string().regex(/^candidate\.[0-9a-f]{32}$/)).default([]),
  server_blockers: z.array(z.string()).default([]),
  decided_at: z.string().min(1),
  decision_checksum: sha256,
}).strict();

export const constructionRunListSchema = z.object({
  contract: z.literal("construction-run-list/v1"),
  workspace_id: z.string().min(1),
  engine_configured: z.boolean(),
  runs: z.array(z.object({
    run: constructionRunSchema,
    decision: constructionReviewDecisionSchema.nullable(),
  }).strict()),
}).strict();

const constructionReviewResultSchema = z.object({
  decision: constructionReviewDecisionSchema,
  workspace: draftWorkspaceSchema,
}).strict();

export type ConstructionCandidate = z.infer<typeof constructionCandidateSchema>;
export type ReviewerFinding = z.infer<typeof reviewerFindingSchema>;
export type ConstructionRun = z.infer<typeof constructionRunSchema>;
export type ConstructionRunList = z.infer<typeof constructionRunListSchema>;
export type ConstructionReviewDecision = z.infer<typeof constructionReviewDecisionSchema>;
export type ConstructionReviewResult = z.infer<typeof constructionReviewResultSchema>;
export type ConstructionDisposition = {
  candidate_id: string;
  action: "ACCEPT" | "EDIT" | "REJECT" | "DEFER";
  note: string;
  blocks_release: boolean;
  edited_operation?: PackageDraftOperation | null;
};

export const constructionJobSchema = z.object({
  contract: z.literal("construction-job/v1"),
  job_id: z.string().regex(/^construction-job\.[0-9a-f]{32}$/),
  run_id: z.string().regex(/^construction-run\.[0-9a-f]{32}$/),
  workspace_id: z.string().min(1),
  solution_id: z.string().min(1),
  base_revision: z.number().int().positive(),
  base_draft_checksum: sha256,
  source_set_digest: sha256,
  selected_source_version_ids: z.array(z.string().regex(/^source-version\.[0-9a-f]{32}$/)),
  authoring_language: z.enum(["en", "zh"]).nullable().optional(),
  language_policy_digest: sha256.nullable().optional(),
  profile_ref: z.string().min(1),
  status: z.enum(["QUEUED", "RUNNING", "COMMITTING", "CANCEL_REQUESTED", "SUCCEEDED", "FAILED", "CANCELLED", "STALE"]),
  attempt_id: z.string().regex(/^construction-attempt\.[0-9a-f]{32}$/).nullable(),
  lease_epoch: z.number().int().nonnegative(),
  lease_owner: z.string().nullable(),
  lease_expires_at: z.string().nullable(),
  result_run_id: z.string().regex(/^construction-run\.[0-9a-f]{32}$/).nullable(),
  error_code: z.string().nullable(),
  current_stage: z.enum(["QUEUED", "SOURCE_SETTLEMENT", "BUILDING_CANDIDATES", "PERSISTING_RESULT", "COMPLETED", "FAILED", "CANCELLED", "STALE"]).default("QUEUED"),
  completed_stages: z.number().int().nonnegative().default(0),
  total_stages: z.number().int().positive().default(6),
  progress_message: z.string().min(1).default("JOB_QUEUED"),
  created_at: z.string().min(1),
  started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  updated_at: z.string().min(1),
}).strict();

export const constructionJobListSchema = z.object({
  contract: z.literal("construction-job-list/v1"),
  workspace_id: z.string().min(1),
  jobs: z.array(constructionJobSchema),
}).strict();

export type ConstructionJob = z.infer<typeof constructionJobSchema>;
export type ConstructionJobList = z.infer<typeof constructionJobListSchema>;

export const studioBuildTaskSchema = z.object({
  contract: z.literal("studio-build-task-summary/v1"),
  task_id: z.string().regex(/^construction-job\.[0-9a-f]{32}$/),
  solution_id: z.string().min(1),
  solution_name: z.string().min(1),
  workspace_id: z.string().min(1),
  authoring_language: z.enum(["en", "zh"]).nullable(),
  language_policy_digest: sha256.nullable(),
  execution_status: z.enum(["QUEUED", "RUNNING", "COMMITTING", "CANCEL_REQUESTED", "SUCCEEDED", "FAILED", "CANCELLED", "STALE"]),
  attempt_id: z.string().regex(/^construction-attempt\.[0-9a-f]{32}$/).nullable(),
  lease_epoch: z.number().int().nonnegative(),
  current_stage: z.string().min(1),
  completed_stages: z.number().int().nonnegative(),
  total_stages: z.number().int().positive(),
  progress_message: z.string().min(1),
  result_outcome: z.enum(["TECHNICAL_FAILURE", "BLOCKED", "REVIEW_READY_WITH_WARNINGS", "REVIEW_READY", "NO_APPLICABLE_CHANGES"]).nullable(),
  outcome_policy_version: z.literal("studio-build-outcome/v1"),
  reason_codes: z.array(z.string()),
  run_id: z.string().regex(/^construction-run\.[0-9a-f]{32}$/).nullable(),
  run_checksum: sha256.nullable(),
  review_status: z.enum(["NOT_READY", "NEEDS_REVIEW", "APPLIED"]),
  decision_id: z.string().regex(/^construction-decision\.[0-9a-f]{32}$/).nullable(),
  candidate_count: z.number().int().nonnegative(),
  compilable_count: z.number().int().nonnegative(),
  blocker_count: z.number().int().nonnegative(),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  completed_at: z.string().nullable(),
  destination: z.object({
    type: z.enum(["TASK", "REVIEW", "RESULT", "SOLUTION"]),
    solution_id: z.string().min(1),
    run_id: z.string().regex(/^construction-run\.[0-9a-f]{32}$/).nullable(),
    decision_id: z.string().regex(/^construction-decision\.[0-9a-f]{32}$/).nullable(),
  }).strict(),
}).strict();

export const studioBuildTaskListSchema = z.object({
  contract: z.literal("studio-build-task-list/v1"),
  tasks: z.array(studioBuildTaskSchema),
}).strict();

export type StudioBuildTask = z.infer<typeof studioBuildTaskSchema>;
export type StudioBuildTaskList = z.infer<typeof studioBuildTaskListSchema>;

export const constructionReviewDraftSchema = z.object({
  contract: z.literal("construction-review-draft/v1"),
  run_id: z.string().regex(/^construction-run\.[0-9a-f]{32}$/),
  run_checksum: sha256,
  workspace_id: z.string().min(1),
  base_revision: z.number().int().positive(),
  review_revision: z.number().int().positive(),
  reviewer: z.string().min(1),
  dispositions: z.array(z.object({
    candidate_id: z.string().regex(/^candidate\.[0-9a-f]{32}$/),
    action: z.enum(["ACCEPT", "EDIT", "REJECT", "DEFER"]),
    note: z.string().min(1),
    blocks_release: z.boolean(),
    edited_operation: packageDraftOperationSchema.nullable(),
  }).strict()),
  status: z.enum(["DRAFT", "FINAL"]),
  submitted_batch_checksum: sha256.nullable(),
  final_decision_id: z.string().regex(/^construction-decision\.[0-9a-f]{32}$/).nullable(),
  updated_at: z.string().min(1),
  batch_checksum: sha256,
}).strict();

export const constructionReviewDraftResponseSchema = z.object({
  contract: z.literal("construction-review-draft-response/v1"),
  workspace_id: z.string().min(1),
  run_id: z.string().min(1),
  review_draft: constructionReviewDraftSchema.nullable(),
}).strict();

export type ConstructionReviewDraft = z.infer<typeof constructionReviewDraftSchema>;

export const sourceKindSchema = z.enum([
  "requirement_transcription",
  "metric_transcription",
  "data_model",
  "data_dictionary",
  "sql",
  "other",
]);

const sourceArtifactSchema = z.object({
  store: z.literal("s3-compatible"),
  bucket: z.string().min(1),
  key: z.string().min(1),
  version_id: z.string().min(1),
  sha256,
  size_bytes: z.number().int().positive(),
  media_type: z.string().min(1),
}).strict();

export const studioSourceVersionSchema = z.object({
  contract: z.literal("studio-source-version/v1"),
  persistence: z.enum(["local-compatibility", "postgresql-s3"]),
  source_version_id: z.string().regex(/^source-version\.[0-9a-f]{32}$/),
  workspace_id: z.string().min(1),
  source_id: z.string().min(1),
  kind: sourceKindSchema,
  title: z.string().min(1),
  original_name: z.string().min(1),
  media_type: z.string().min(1),
  processing_mode: z.enum([
    "TRANSCRIBED",
    "STRUCTURED_TRANSCRIPTION",
    "REGISTERED_NOT_PARSED",
  ]),
  content_checksum: sha256,
  size_bytes: z.number().int().positive(),
  registered_at: z.iso.datetime({ offset: true }),
  artifact: sourceArtifactSchema.nullable(),
  subject_checksum: sha256,
  is_current: z.boolean().optional(),
}).strict().superRefine((value, context) => {
  if (value.persistence === "postgresql-s3" && value.artifact === null) {
    context.addIssue({ code: "custom", message: "Durable source is missing exact S3 identity" });
  }
  if (value.artifact && (
    value.artifact.sha256 !== value.content_checksum
    || value.artifact.size_bytes !== value.size_bytes
    || value.artifact.media_type !== value.media_type
  )) {
    context.addIssue({ code: "custom", message: "Source metadata and exact artifact disagree" });
  }
});

export const studioSourceLibrarySchema = z.object({
  contract: z.literal("studio-source-library/v1"),
  workspace_id: z.string().min(1),
  current: z.array(studioSourceVersionSchema),
  versions: z.array(studioSourceVersionSchema),
}).strict();

export type StudioSourceKind = z.infer<typeof sourceKindSchema>;
export type StudioSourceVersion = z.infer<typeof studioSourceVersionSchema>;
export type StudioSourceLibrary = z.infer<typeof studioSourceLibrarySchema>;

export const sourceIntakeBatchReceiptSchema = z.object({
  contract: z.literal("source-intake-batch-receipt/v1"),
  batch_id: z.string().regex(/^source-batch\.[0-9a-f]{32}$/),
  workspace_id: z.string().min(1),
  idempotency_key: z.string().min(8),
  request_digest: sha256,
  physical_files: z.array(z.object({
    client_file_id: z.string().min(1),
    original_name: z.string().min(1),
    content_checksum: sha256,
    size_bytes: z.number().int().positive(),
    declared_media_type: z.string().min(1),
    detected_media_type: z.string().min(1),
    parser_id: z.string().nullable(),
    parser_version: z.string().nullable(),
    capability: z.enum(["TEXT_EXTRACTED", "XLSX_TABULAR_EXTRACTED", "ARCHIVED_ONLY"]),
    reason_code: z.string().min(1),
    selected_ranges: z.array(z.string()),
    truncated: z.boolean(),
  }).strict()),
  registrations: z.array(z.object({
    client_file_id: z.string().min(1),
    source_version_id: z.string().regex(/^source-version\.[0-9a-f]{32}$/),
    source_id: z.string().min(1),
    kind: sourceKindSchema,
    capability: z.enum(["TEXT_EXTRACTED", "XLSX_TABULAR_EXTRACTED", "ARCHIVED_ONLY"]),
  }).strict()),
  failures: z.array(z.object({
    client_file_id: z.string().min(1),
    reason_code: z.string().min(1),
    detail: z.string().min(1),
    retryable: z.boolean(),
  }).strict()),
  completed_at: z.iso.datetime({ offset: true }),
  subject_checksum: sha256,
}).strict();

export type SourceIntakeBatchReceipt = z.infer<typeof sourceIntakeBatchReceiptSchema>;
export type SourceIntakeBatchItemInput = {
  clientFileId: string;
  file: File;
  registrations: Array<{ kind: StudioSourceKind; title: string }>;
};

const referenceSourcePackInstallSchema = z.object({
  contract: z.literal("ontology-reference-source-pack-install/v1"),
  pack_id: z.string().min(1),
  workspace_id: z.string().min(1),
  physical_file_count: z.number().int().positive(),
  registered_source_count: z.number().int().positive(),
  source_version_ids: z.array(z.string().regex(/^source-version\.[0-9a-f]{32}$/)),
  source_content_checksums: z.array(sha256),
  manifest_checksum: sha256,
  subject_checksum: sha256,
}).strict();

export type ReferenceSourcePackInstall = z.infer<typeof referenceSourcePackInstallSchema>;

export const studioSourcePreviewSchema = z.object({
  contract: z.literal("studio-source-preview/v1"),
  source_version_id: z.string().regex(/^source-version\.[0-9a-f]{32}$/),
  content_checksum: sha256,
  parser_build: z.literal("ontology-studio/source-preview@1"),
  status: z.enum(["PARSED", "REGISTERED_NOT_PARSED"]),
  text_lines: z.array(z.object({
    line_number: z.number().int().positive(),
    text: z.string(),
    snippet_checksum: sha256,
  }).strict()),
  sheets: z.array(z.object({
    sheet_name: z.string().min(1),
    used_range: z.string().min(1),
    cells: z.array(z.object({
      cell: z.string().regex(/^[A-Z]+[1-9][0-9]*$/),
      display_value: z.union([z.string(), z.number(), z.boolean()]).nullable(),
      raw_formula: z.string().nullable(),
      snippet_checksum: sha256,
    }).strict()),
    truncated: z.boolean(),
  }).strict()),
  limitation: z.string().nullable(),
}).strict();

export type StudioSourcePreview = z.infer<typeof studioSourcePreviewSchema>;

const runtimeReleaseRefSchema = z.object({
  package_id: z.string().min(1),
  version: z.string().regex(/^[0-9]+\.[0-9]+\.[0-9]+$/),
  checksum: sha256,
}).strict();

export const runtimeSnapshotRefSchema = z.object({
  environment_id: z.string().min(1),
  release: runtimeReleaseRefSchema,
  checksum: sha256,
}).strict();

const runtimeCheckSchema = z.object({
  check_id: z.string().min(1),
  category: z.enum(["structure", "source", "semantic", "binding", "data", "shacl"]),
  status: z.enum(["PASS", "FAIL", "WARN"]),
  message: z.string(),
  details: z.record(z.string(), z.unknown()),
}).strict();

export const agentRuntimeStatusSchema = z.object({
  environment_id: z.string().min(1),
  package_id: z.string().min(1),
  state_authority: z.enum(["legacy-filesystem", "postgresql-s3"]),
  active: runtimeSnapshotRefSchema.nullable(),
  rollback_target: runtimeSnapshotRefSchema.nullable(),
}).strict().superRefine((value, context) => {
  for (const [label, ref] of [
    ["Active", value.active],
    ["Rollback target", value.rollback_target],
  ] as const) {
    if (ref && (
      ref.environment_id !== value.environment_id
      || ref.release.package_id !== value.package_id
    )) {
      context.addIssue({ code: "custom", message: `${label} runtime identity mismatch` });
    }
  }
  if (value.rollback_target && !value.active) {
    context.addIssue({ code: "custom", message: "Rollback target requires an active runtime" });
  }
  if (
    value.rollback_target
    && value.active
    && value.rollback_target.checksum === value.active.checksum
  ) {
    context.addIssue({ code: "custom", message: "Rollback target cannot equal the active runtime" });
  }
});

export const preparedRuntimeSchema = z.object({
  snapshot: runtimeSnapshotRefSchema,
  readiness: z.object({
    status: z.literal("READY"),
    checks: z.array(runtimeCheckSchema),
    certification_profile: z.string().nullable(),
    certification_checksum: sha256.nullable(),
  }).strict(),
  idempotent: z.boolean(),
}).strict();

export const activationReceiptSchema = z.object({
  environment_id: z.string().min(1),
  active: runtimeSnapshotRefSchema,
  previous: runtimeSnapshotRefSchema.nullable(),
  idempotent: z.boolean(),
}).strict().superRefine((value, context) => {
  if (value.environment_id !== value.active.environment_id) {
    context.addIssue({ code: "custom", message: "Activation environment mismatch" });
  }
});

export const activeRuntimeVerificationSchema = z.object({
  status: z.enum(["PASS", "FAIL"]),
  snapshot: runtimeSnapshotRefSchema,
  suite_id: z.string().min(1),
  case_count: z.number().int().nonnegative(),
  cases: z.array(z.object({
    case_id: z.string().min(1),
    status: z.enum(["PASS", "FAIL"]),
    defects: z.array(z.string()),
    execution_id: z.string().nullable(),
  }).strict()),
  oracle: z.string().min(1),
  oracle_defects: z.record(z.string(), z.unknown()),
}).strict().superRefine((value, context) => {
  if (value.case_count !== value.cases.length) {
    context.addIssue({ code: "custom", message: "Verification case_count mismatch" });
  }
  if (value.status === "PASS" && value.cases.some((item) => item.status !== "PASS")) {
    context.addIssue({ code: "custom", message: "PASS verification contains a failed case" });
  }
});

export type RuntimeReleaseRef = z.infer<typeof runtimeReleaseRefSchema>;
export type RuntimeSnapshotRef = z.infer<typeof runtimeSnapshotRefSchema>;
export type AgentRuntimeStatus = z.infer<typeof agentRuntimeStatusSchema>;
export type PreparedRuntime = z.infer<typeof preparedRuntimeSchema>;
export type ActivationReceipt = z.infer<typeof activationReceiptSchema>;
export type ActiveRuntimeVerification = z.infer<typeof activeRuntimeVerificationSchema>;

export const workspaceEditorSchema = z
  .object({
    contract: z.literal("studio-workspace-editor/v1"),
    persistence: z.enum(["legacy-compatibility", "postgresql-s3"]),
    descriptor: editorDescriptorSchema,
    workspace: draftWorkspaceSchema,
  })
  .strict()
  .superRefine((value, context) => {
    if (value.descriptor.workspace_id !== value.workspace.workspace_id) {
      context.addIssue({
        code: "custom",
        message: "Editor descriptor and workspace identities do not match",
        path: ["descriptor", "workspace_id"],
      });
    }
    if (value.descriptor.draft_schema_version !== value.workspace.schema_version) {
      context.addIssue({
        code: "custom",
        message: "Editor descriptor and draft schemas do not match",
        path: ["descriptor", "draft_schema_version"],
      });
    }
  });

export type WorkspaceEditor = z.infer<typeof workspaceEditorSchema>;
export type DraftWorkspace = z.infer<typeof draftWorkspaceSchema>;
export type DraftOperationValue = string | boolean | string[];
export type PackageDraftOperation = z.infer<typeof packageDraftOperationSchema>;

export class ProductApiError extends Error {
  readonly status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ProductApiError";
    this.status = status;
  }
}

export async function fetchAuthSession(): Promise<AuthSession> {
  let response: Response;
  try {
    response = await fetch("/auth/session", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ProductApiError("无法确认当前登录角色。", 0);
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ProductApiError("无法确认当前登录角色。", response.status);
  const parsed = authSessionSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("登录服务返回了无效角色信息。", 502);
  return parsed.data;
}

export async function fetchProductContext(): Promise<ProductContext> {
  let response: Response;
  try {
    response = await fetch("/api/product/context", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ProductApiError("无法连接分析服务。请确认服务已经启动。", 0);
  }
  if (response.status === 401) {
    const next = encodeURIComponent(window.location.pathname);
    window.location.assign(`/login/?next=${next}`);
    throw new ProductApiError("登录会话已过期。", 401);
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ProductApiError("服务返回了无法识别的内容。", response.status);
  }
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload && "detail" in payload
        ? String(payload.detail)
        : "产品上下文暂不可用。";
    throw new ProductApiError(detail, response.status);
  }
  const parsed = productContextSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("产品上下文未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function fetchSolutionCatalog(): Promise<SolutionCatalog> {
  let response: Response;
  try {
    response = await fetch("/control/solutions", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ProductApiError("无法连接 Studio solution catalog。", 0);
  }
  if (response.status === 401) {
    const next = encodeURIComponent(window.location.pathname);
    window.location.assign(`/login/?next=${next}`);
    throw new ProductApiError("登录会话已过期。", 401);
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ProductApiError("Studio 返回了无法识别的内容。", response.status);
  }
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload && "detail" in payload
        ? String(payload.detail)
        : "Solution catalog 暂不可用。";
    throw new ProductApiError(detail, response.status);
  }
  const parsed = solutionCatalogSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("Solution catalog 未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export type CreateStudioSolutionInput = {
  creation_mode: "TEMPLATE" | "BLANK";
  template_solution_id?: string | null;
  display_name: { en: string; zh: string };
  description: string;
  owner: string;
};

export type UpdateStudioSolutionInput = {
  display_name: { en: string; zh: string };
  description: string;
  owner: string;
};

export async function createStudioSolution(
  input: CreateStudioSolutionInput,
): Promise<StudioSolution> {
  const payload = await requestStudioJson("/control/solutions", {
    method: "POST",
    body: JSON.stringify({
      contract: "studio-solution-create/v1",
      ...input,
    }),
  });
  const parsed = z.object({
    contract: z.literal("studio-solution-create-result/v1"),
    solution: solutionCatalogSchema.shape.solutions.element,
  }).strict().safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("新建 Solution 的结果未通过客户端合同校验。", 0);
  }
  return parsed.data.solution;
}

export async function updateStudioSolution(
  solutionId: string,
  input: UpdateStudioSolutionInput,
): Promise<StudioSolution> {
  const payload = await requestStudioJson(
    `/control/solutions/${encodeURIComponent(solutionId)}/metadata`,
    { method: "PATCH", body: JSON.stringify(input) },
  );
  const parsed = solutionCatalogSchema.shape.solutions.element.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("Solution 元数据未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function archiveStudioSolution(solutionId: string): Promise<StudioSolution> {
  const payload = await requestStudioJson(
    `/control/solutions/${encodeURIComponent(solutionId)}/archive`,
    { method: "POST" },
  );
  const parsed = solutionCatalogSchema.shape.solutions.element.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("归档结果未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function restoreStudioSolution(solutionId: string): Promise<StudioSolution> {
  const payload = await requestStudioJson(
    `/control/solutions/${encodeURIComponent(solutionId)}/restore`,
    { method: "POST" },
  );
  const parsed = solutionCatalogSchema.shape.solutions.element.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("恢复结果未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function deleteStudioSolution(solutionId: string): Promise<void> {
  const payload = await requestStudioJson(
    `/control/solutions/${encodeURIComponent(solutionId)}`,
    { method: "DELETE" },
  );
  const parsed = z.object({
    contract: z.literal("studio-solution-delete-result/v1"),
    solution_id: z.literal(solutionId),
    status: z.literal("DELETED"),
    audit_artifacts_retained: z.literal(true),
  }).strict().safeParse(payload);
  if (!parsed.success) throw new ProductApiError("删除结果未通过客户端合同校验。", 0);
}

async function requestAgentJson(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ProductApiError("无法连接 Ontology Agent。", 0);
  }
  if (response.status === 401) {
    const next = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
    window.location.assign(`/login/?next=${next}`);
    throw new ProductApiError("登录会话已过期。", 401);
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ProductApiError("Agent 返回了无法识别的内容。", response.status);
  }
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload && "detail" in payload
        ? String(payload.detail)
        : "Agent 操作未完成。";
    throw new ProductApiError(detail, response.status);
  }
  return payload;
}

export async function fetchAgentSolutionCatalog(): Promise<AgentSolutionCatalog> {
  const payload = await requestAgentJson("/api/solutions");
  const parsed = agentSolutionCatalogSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("Agent solution catalog 未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function fetchSolutionQuestions(solutionId: string): Promise<SolutionQuestionFamily> {
  const payload = await requestAgentJson(`/api/solutions/${encodeURIComponent(solutionId)}/questions`);
  const parsed = solutionQuestionFamilySchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("问题清单未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function fetchSolutionRuntime(solutionId: string): Promise<SolutionRuntime> {
  const payload = await requestAgentJson(`/api/solutions/${encodeURIComponent(solutionId)}/runtime/active`);
  const parsed = solutionRuntimeSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("Active runtime 未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function fetchSolutionOntology(solutionId: string): Promise<SolutionOntology> {
  const payload = await requestAgentJson(`/api/solutions/${encodeURIComponent(solutionId)}/ontology`);
  const parsed = solutionOntologySchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("Ontology package 未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function analyzeSolution(
  solutionId: string,
  question: string,
  role: string,
  questionCaseId?: string,
): Promise<SolutionAnalysis> {
  const payload = await requestAgentJson(`/api/solutions/${encodeURIComponent(solutionId)}/analyze`, {
    method: "POST",
    body: JSON.stringify({ question, role, question_case_id: questionCaseId }),
  });
  const parsed = solutionAnalysisSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("分析结果未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function submitSemanticChangeRequest(
  solutionId: string,
  input: SemanticChangeRequestInput,
): Promise<SemanticChangeRequest> {
  const payload = await requestAgentJson(
    `/api/solutions/${encodeURIComponent(solutionId)}/semantic-change-requests`,
    {
      method: "POST",
      body: JSON.stringify({
        contract: "semantic-change-request-create/v1",
        ...input,
      }),
    },
  );
  const parsed = semanticChangeRequestSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("Semantic Change Request 未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

async function requestStudioJson(
  path: string,
  init?: RequestInit,
): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ProductApiError("无法连接 Ontology Studio。", 0);
  }
  if (response.status === 401) {
    const next = encodeURIComponent(window.location.pathname);
    window.location.assign(`/login/?next=${next}`);
    throw new ProductApiError("登录会话已过期。", 401);
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ProductApiError("Studio 返回了无法识别的内容。", response.status);
  }
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload && "detail" in payload
        ? String(payload.detail)
        : "Studio 操作未完成。";
    throw new ProductApiError(detail, response.status);
  }
  return payload;
}

async function requestAgentControlJson(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ProductApiError("无法连接 Agent Runtime Control。", 0);
  }
  if (response.status === 401) {
    const next = encodeURIComponent(window.location.pathname);
    window.location.assign(`/login/?next=${next}`);
    throw new ProductApiError("登录会话已过期。", 401);
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ProductApiError("Agent Runtime Control 返回了无法识别的内容。", response.status);
  }
  if (!response.ok) {
    const detail = typeof payload === "object" && payload && "detail" in payload
      ? String(payload.detail)
      : "Agent Runtime 操作未完成。";
    throw new ProductApiError(detail, response.status);
  }
  return payload;
}

export async function fetchWorkspaceEditor(workspaceId: string): Promise<WorkspaceEditor> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/editor`);
  const parsed = workspaceEditorSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("Workspace editor 未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function fetchStudioWorkbench(workspaceId: string): Promise<StudioWorkbench> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/workbench`);
  const parsed = studioWorkbenchSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("Studio Workbench 未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function fetchStudioLlmStatus(workspaceId: string): Promise<StudioLlmStatus> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/llm/status`);
  const parsed = studioLlmStatusSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Studio LLM status 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function fetchStudioObservations(workspaceId: string): Promise<StudioObservationList> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/llm/observations`);
  const parsed = studioObservationListSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Studio observations 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function generateStudioObservations(
  workspaceId: string,
  expectedRevision: number,
): Promise<StudioObservationSet> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/llm/observations`, {
    method: "POST",
    body: JSON.stringify({ expected_revision: expectedRevision }),
  });
  const parsed = studioObservationSetSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Generated observations 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function reviewStudioObservations(
  workspaceId: string,
  observationSetId: string,
  expectedRevision: number,
  dispositions: StudioObservationDisposition[],
): Promise<z.infer<typeof studioReviewResultSchema>> {
  const payload = await requestStudioJson(
    `/control/workspaces/${encodeURIComponent(workspaceId)}/llm/observations/${encodeURIComponent(observationSetId)}/review`,
    {
      method: "POST",
      body: JSON.stringify({ expected_revision: expectedRevision, dispositions }),
    },
  );
  const parsed = studioReviewResultSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Studio review result 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function fetchConstructionRuns(workspaceId: string): Promise<ConstructionRunList> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/construction-runs`);
  const parsed = constructionRunListSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Construction runs 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function fetchConstructionJobs(workspaceId: string): Promise<ConstructionJobList> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/construction-jobs`);
  const parsed = constructionJobListSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Construction jobs 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function fetchStudioBuildTasks(): Promise<StudioBuildTaskList> {
  const payload = await requestStudioJson("/control/construction-tasks");
  const parsed = studioBuildTaskListSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("构建任务未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function fetchStudioBuildTask(taskId: string): Promise<StudioBuildTask> {
  const payload = await requestStudioJson(`/control/construction-tasks/${encodeURIComponent(taskId)}`);
  const parsed = studioBuildTaskSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("构建任务详情未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function enqueueConstructionJob(
  workspaceId: string,
  expectedRevision: number,
  sourceVersionIds: string[] = [],
  authoringLanguage?: "en" | "zh",
): Promise<ConstructionJob> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/construction-jobs`, {
    method: "POST",
    body: JSON.stringify({ expected_revision: expectedRevision, source_version_ids: sourceVersionIds, authoring_language: authoringLanguage }),
  });
  const parsed = constructionJobSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Construction job 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function cancelConstructionJob(
  workspaceId: string,
  jobId: string,
): Promise<ConstructionJob> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/construction-jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
  const parsed = constructionJobSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Cancelled construction job 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function retryConstructionJob(
  workspaceId: string,
  jobId: string,
): Promise<ConstructionJob> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/construction-jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST" });
  const parsed = constructionJobSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Retried construction job 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function startConstructionRun(
  workspaceId: string,
  expectedRevision: number,
  sourceVersionIds: string[] = [],
  authoringLanguage?: "en" | "zh",
): Promise<ConstructionRun> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/construction-runs`, {
    method: "POST",
    body: JSON.stringify({ expected_revision: expectedRevision, source_version_ids: sourceVersionIds, authoring_language: authoringLanguage }),
  });
  const parsed = constructionRunSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Construction run 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function reviewConstructionRun(
  workspaceId: string,
  runId: string,
  expectedRevision: number,
  dispositions: ConstructionDisposition[],
  reviewBatchChecksum: string | null = null,
): Promise<z.infer<typeof constructionReviewResultSchema>> {
  const payload = await requestStudioJson(
    `/control/workspaces/${encodeURIComponent(workspaceId)}/construction-runs/${encodeURIComponent(runId)}/review`,
    {
      method: "POST",
      body: JSON.stringify({
        contract: "construction-review-request/v1",
        expected_revision: expectedRevision,
        reviewer: "domain-owner.demo",
        dispositions,
        review_batch_checksum: reviewBatchChecksum,
      }),
    },
  );
  const parsed = constructionReviewResultSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Construction review 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function fetchConstructionDecision(
  workspaceId: string,
  runId: string,
  decisionId: string,
): Promise<ConstructionReviewDecision> {
  const payload = await requestStudioJson(
    `/control/workspaces/${encodeURIComponent(workspaceId)}/construction-runs/${encodeURIComponent(runId)}/decisions/${encodeURIComponent(decisionId)}`,
  );
  const parsed = constructionReviewDecisionSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("复核应用结果未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function fetchConstructionReviewDraft(
  workspaceId: string,
  runId: string,
): Promise<ConstructionReviewDraft | null> {
  const payload = await requestStudioJson(
    `/control/workspaces/${encodeURIComponent(workspaceId)}/construction-runs/${encodeURIComponent(runId)}/review-draft`,
  );
  const parsed = constructionReviewDraftResponseSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Review draft 未通过客户端合同校验。", 0);
  return parsed.data.review_draft;
}

export async function saveConstructionReviewDraft(
  workspaceId: string,
  runId: string,
  expectedReviewRevision: number,
  dispositions: ConstructionDisposition[],
): Promise<ConstructionReviewDraft> {
  const payload = await requestStudioJson(
    `/control/workspaces/${encodeURIComponent(workspaceId)}/construction-runs/${encodeURIComponent(runId)}/review-draft`,
    {
      method: "PUT",
      body: JSON.stringify({
        contract: "construction-review-draft-save/v1",
        expected_review_revision: expectedReviewRevision,
        reviewer: "domain-owner.demo",
        dispositions,
      }),
    },
  );
  const parsed = constructionReviewDraftSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Saved review draft 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function fetchStudioSourceLibrary(
  workspaceId: string,
): Promise<StudioSourceLibrary> {
  const payload = await requestStudioJson(
    `/control/workspaces/${encodeURIComponent(workspaceId)}/sources`,
  );
  const parsed = studioSourceLibrarySchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("来源材料库未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function fetchStudioSourcePreview(
  workspaceId: string,
  sourceVersionId: string,
): Promise<StudioSourcePreview> {
  const payload = await requestStudioJson(
    `/control/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceVersionId)}/preview`,
  );
  const parsed = studioSourcePreviewSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("来源材料预览未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export type RegisterStudioSourceInput = {
  kind: StudioSourceKind;
  title: string;
  originalName: string;
  mediaType: string;
  body: Blob | string;
};

export async function registerStudioSource(
  workspaceId: string,
  input: RegisterStudioSourceInput,
): Promise<StudioSourceVersion> {
  const search = new URLSearchParams({
    kind: input.kind,
    title: input.title,
    original_name: input.originalName,
  });
  let response: Response;
  try {
    response = await fetch(
      `/control/workspaces/${encodeURIComponent(workspaceId)}/sources?${search}`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json", "Content-Type": input.mediaType },
        body: input.body,
      },
    );
  } catch {
    throw new ProductApiError("无法连接 Ontology Studio 来源材料库。", 0);
  }
  if (response.status === 401) {
    const next = encodeURIComponent(window.location.pathname);
    window.location.assign(`/login/?next=${next}`);
    throw new ProductApiError("登录会话已过期。", 401);
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ProductApiError("来源材料库返回了无法识别的内容。", response.status);
  }
  if (!response.ok) {
    const detail = typeof payload === "object" && payload && "detail" in payload
      ? String(payload.detail)
      : "来源材料登记失败。";
    throw new ProductApiError(detail, response.status);
  }
  const parsed = studioSourceVersionSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("来源材料版本未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function registerStudioSourceBatch(
  workspaceId: string,
  idempotencyKey: string,
  items: SourceIntakeBatchItemInput[],
): Promise<SourceIntakeBatchReceipt> {
  const form = new FormData();
  form.set("manifest_json", JSON.stringify({
    contract: "source-intake-batch/v1",
    idempotency_key: idempotencyKey,
    items: items.map((item) => ({
      client_file_id: item.clientFileId,
      original_name: item.file.name,
      declared_media_type: item.file.type || "application/octet-stream",
      registrations: item.registrations,
    })),
  }));
  for (const item of items) form.append("files", item.file, item.file.name);
  let response: Response;
  try {
    response = await fetch(
      `/control/workspaces/${encodeURIComponent(workspaceId)}/source-intake/batches`,
      { method: "POST", credentials: "same-origin", headers: { Accept: "application/json" }, body: form },
    );
  } catch {
    throw new ProductApiError("无法连接 Ontology Studio 来源材料库。", 0);
  }
  if (response.status === 401) {
    const next = encodeURIComponent(window.location.pathname);
    window.location.assign(`/login/?next=${next}`);
    throw new ProductApiError("登录会话已过期。", 401);
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ProductApiError("批量登记返回了无法识别的内容。", response.status);
  }
  if (!response.ok) {
    const detail = typeof payload === "object" && payload && "detail" in payload
      ? String(payload.detail)
      : "批量材料登记失败。";
    throw new ProductApiError(detail, response.status);
  }
  const parsed = sourceIntakeBatchReceiptSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("批量登记回执未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function installStudioReferenceSourcePack(
  workspaceId: string,
): Promise<ReferenceSourcePackInstall> {
  const payload = await requestStudioJson(
    `/control/workspaces/${encodeURIComponent(workspaceId)}/sources/install-reference-pack`,
    { method: "POST" },
  );
  const parsed = referenceSourcePackInstallSchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("参考材料包安装回执未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function importStudioInstalledSources(
  workspaceId: string,
): Promise<StudioSourceLibrary> {
  const payload = await requestStudioJson(
    `/control/workspaces/${encodeURIComponent(workspaceId)}/sources/import-installed`,
    { method: "POST" },
  );
  const parsed = studioSourceLibrarySchema.safeParse(payload);
  if (!parsed.success) {
    throw new ProductApiError("安装材料版本化结果未通过客户端合同校验。", 0);
  }
  return parsed.data;
}

export async function applyDraftOperations(
  workspaceId: string,
  expectedRevision: number,
  operations: Array<{ path: string; value: DraftOperationValue }>,
): Promise<DraftWorkspace> {
  const payload = await requestStudioJson(
    `/control/workspaces/${encodeURIComponent(workspaceId)}/draft-operations`,
    {
      method: "POST",
      body: JSON.stringify({
        contract: "studio-draft-operations/v1",
        expected_revision: expectedRevision,
        operations,
      }),
    },
  );
  const parsed = draftWorkspaceSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("保存后的工作区未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function applyPackageOperations(
  workspaceId: string,
  expectedRevision: number,
  operations: PackageDraftOperation[],
): Promise<DraftWorkspace> {
  const payload = await requestStudioJson(
    `/control/workspaces/${encodeURIComponent(workspaceId)}/package-operations`,
    {
      method: "POST",
      body: JSON.stringify({
        contract: "studio-package-operations/v1",
        expected_revision: expectedRevision,
        operations,
      }),
    },
  );
  const parsed = draftWorkspaceSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("保存后的工作区未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function validateDraft(
  workspaceId: string,
  expectedRevision: number,
): Promise<DraftWorkspace> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/validate`, {
    method: "POST",
    body: JSON.stringify({ expected_revision: expectedRevision }),
  });
  const parsed = draftWorkspaceSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("验证后的工作区未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function publishDraft(
  workspaceId: string,
  expectedRevision: number,
): Promise<{ workspace: DraftWorkspace; release: { package_id: string; version: string; release_checksum: string; idempotent: boolean; validation_status: string } }> {
  const payload = await requestStudioJson(`/control/workspaces/${encodeURIComponent(workspaceId)}/publish`, {
    method: "POST",
    body: JSON.stringify({ expected_revision: expectedRevision }),
  });
  const parsed = z.object({
    workspace: draftWorkspaceSchema,
    release: z.object({
      package_id: z.string().min(1),
      version: z.string().min(1),
      release_checksum: sha256,
      idempotent: z.boolean(),
      validation_status: z.string().min(1),
    }).strict(),
  }).strict().safeParse(payload);
  if (!parsed.success) throw new ProductApiError("发布回执未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function fetchAgentRuntimeStatus(packageId: string): Promise<AgentRuntimeStatus> {
  const payload = await requestAgentControlJson(`/agent-control/runtime/status/${encodeURIComponent(packageId)}`);
  const parsed = agentRuntimeStatusSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Runtime status 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function prepareAgentRuntime(release: RuntimeReleaseRef): Promise<PreparedRuntime> {
  const payload = await requestAgentControlJson("/agent-control/runtime/prepare", {
    method: "POST",
    body: JSON.stringify({ release, certify_adt: true }),
  });
  const parsed = preparedRuntimeSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Prepared runtime 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function activateAgentRuntime(
  snapshot: RuntimeSnapshotRef,
  expectedCurrent: RuntimeSnapshotRef | null,
): Promise<ActivationReceipt> {
  const payload = await requestAgentControlJson("/agent-control/runtime/activate", {
    method: "POST",
    body: JSON.stringify({
      snapshot,
      expected_current: expectedCurrent,
      require_adt_certification: true,
    }),
  });
  const parsed = activationReceiptSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Activation receipt 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function rollbackAgentRuntime(
  targetSnapshot: RuntimeSnapshotRef,
  expectedCurrent: RuntimeSnapshotRef,
): Promise<ActivationReceipt> {
  const payload = await requestAgentControlJson("/agent-control/runtime/rollback", {
    method: "POST",
    body: JSON.stringify({
      target_snapshot: targetSnapshot,
      expected_current: expectedCurrent,
      require_adt_certification: true,
    }),
  });
  const parsed = activationReceiptSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Rollback receipt 未通过客户端合同校验。", 0);
  return parsed.data;
}

export async function verifyAgentRuntime(snapshot: RuntimeSnapshotRef): Promise<ActiveRuntimeVerification> {
  const payload = await requestAgentControlJson("/agent-control/runtime/verify-active", {
    method: "POST",
    body: JSON.stringify({ expected_snapshot: snapshot }),
  });
  const parsed = activeRuntimeVerificationSchema.safeParse(payload);
  if (!parsed.success) throw new ProductApiError("Runtime verification 未通过客户端合同校验。", 0);
  return parsed.data;
}
