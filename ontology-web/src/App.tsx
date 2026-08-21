import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation, useSearchParams } from "react-router-dom";

import {
  fetchProductContext,
  fetchAuthSession,
  fetchAgentRuntimeStatus,
  fetchAgentSolutionCatalog,
  fetchSolutionCatalog,
  fetchSolutionOntology,
  fetchSolutionQuestions,
  fetchSolutionRuntime,
  fetchStudioWorkbench,
  fetchStudioLlmStatus,
  fetchStudioObservations,
  fetchConstructionRuns,
  fetchConstructionJobs,
  fetchConstructionReviewDraft,
  fetchStudioSourceLibrary,
  fetchStudioSourcePreview,
  fetchWorkspaceEditor,
  activateAgentRuntime,
  analyzeSolution,
  applyDraftOperations,
  applyPackageOperations,
  publishDraft,
  rollbackAgentRuntime,
  generateStudioObservations,
  reviewStudioObservations,
  enqueueConstructionJob,
  cancelConstructionJob,
  retryConstructionJob,
  saveConstructionReviewDraft,
  reviewConstructionRun,
  registerStudioSource,
  installStudioReferenceSourcePack,
  importStudioInstalledSources,
  prepareAgentRuntime,
  validateDraft,
  verifyAgentRuntime,
  submitSemanticChangeRequest,
  ProductApiError,
  type DraftOperationValue,
  type ProductContext,
  type PackageDraftOperation,
  type AgentSolution,
  type SolutionAnalysis,
  type SolutionOntology,
  type SemanticChangeRequestInput,
  type StudioObservationDisposition,
  type ConstructionDisposition,
  type StudioWorkbench,
  type AgentRuntimeStatus,
  type SolutionRuntime,
  type SolutionCatalog,
  type StudioSourceLibrary,
  type StudioSolution,
  type WorkspaceEditor,
  type AuthSession,
} from "./api";
import { formatDisplayValue } from "./display";
import { StudioWorkbenchView, type WorkbenchTab } from "./StudioWorkbench";
import {
  StudioNavigation,
  StudioSubnavigation,
  studioPageDefinition,
  studioPageFromPath,
  studioPageHref,
  studioSolutionIdFromPath,
  studioSubpageFromPath,
  type StudioPageId,
  type StudioSubpageId,
} from "./StudioNavigation";
import { StudioSolutionDirectory } from "./StudioSolutionDirectory";
import { SemanticChangeRequestPanel } from "./SemanticChangeRequestPanel";
import { AgentExecutionEvidence } from "./AgentExecutionEvidence";
import { StudioLlmWorkbench } from "./StudioLlmWorkbench";
import {
  MappingWorkbenchView,
  OntologyGraphEditor,
  RequirementsCatalogView,
  SampleAndEnumView,
  SchemaCatalogView,
  SourceLibraryView,
  StudioVersionLineage,
} from "./StudioProductViews";
import { ConstructionReviewCenter, ConstructionRunsView } from "./StudioConstructionViews";
import { studioQueryScope } from "./studioQueryScope";
import { SemanticAssetCatalog, semanticAssetHref } from "./SemanticAssetCatalog";

type ProductKind = "agent" | "studio";

const phaseLabels = {
  agent: {
    eyebrow: "ONTOLOGY ANALYTIC AGENT",
    title: "当前生效的分析语境",
    summary:
      "每次分析都从同一个已验证上下文出发。这里展示的是后端确认的版本、环境和边界，不是浏览器自行推断的状态。",
    companion: "进入 Ontology Studio",
  },
  studio: {
    eyebrow: "ONTOLOGY STUDIO",
    title: "业务语义的配置入口",
    summary:
      "Studio 从独立 solution registration 读取 authoring、semantic、experience 与 reference components；ADT 是当前安装的场景适配器，不是浏览器里的固定业务逻辑。",
    companion: "进入 Analytic Agent",
  },
} as const;

function shortDigest(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

function SolutionSwitcher({ selectedId, kind, canOperate }: { selectedId: string; kind: ProductKind; canOperate: boolean }) {
  const agentQuery = useQuery({
    queryKey: ["agent-solution-catalog", "header"],
    queryFn: fetchAgentSolutionCatalog,
    enabled: kind === "agent",
  });
  const studioQuery = useQuery({
    queryKey: ["studio-solution-catalog", "header"],
    queryFn: fetchSolutionCatalog,
    enabled: kind === "studio",
  });
  const [search, setSearch] = useState("");
  const catalog = kind === "studio" ? studioQuery.data : agentQuery.data;
  if (!catalog) return <span className="solution-switcher-loading">SOLUTION CATALOG</span>;
  const latest = new Map<string, AgentSolution | StudioSolution>();
  for (const solution of catalog.solutions) {
    const current = latest.get(solution.solution_id);
    if (!current || current.solution_version.localeCompare(solution.solution_version, undefined, { numeric: true }) < 0) {
      latest.set(solution.solution_id, solution);
    }
  }
  const values = [...latest.values()];
  const selected = latest.get(selectedId) ?? values[0];
  const visible = values.filter((solution) => `${solution.display_name.zh} ${solution.display_name.en} ${solution.solution_id}`.toLowerCase().includes(search.toLowerCase()));
  const destination = (solutionId: string) => {
    const base = kind === "studio"
      ? studioPageHref("overview", solutionId)
      : "/ontology-agent/";
    return kind === "studio" || solutionId === "ontology.exchange_analytics.adt"
      ? base
      : `${base}?solution=${encodeURIComponent(solutionId)}`;
  };
  return (
    <details className="solution-switcher">
      <summary aria-label="切换解决方案">
        <span>Solution</span>
        <strong>{selected?.display_name.zh ?? "选择解决方案"}</strong>
        <small>{selected ? `v${selected.solution_version}` : ""}</small>
      </summary>
      <div className="solution-switcher-popover">
        <label><span>搜索解决方案</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="名称或 ID" /></label>
        <div className="solution-switcher-list">
          {visible.map((solution) => (
            <a href={destination(solution.solution_id)} className={solution.solution_id === selectedId ? "is-selected" : ""} key={solution.solution_id}>
              <span>{solution.solution_id === selectedId ? "✓" : ""}</span>
              <div><strong>{solution.display_name.zh}</strong><small>{solution.display_name.en}</small></div>
              <code>v{solution.solution_version}</code>
            </a>
          ))}
        </div>
        {kind === "studio" ? (
          <footer>
            <a href="/ontology-studio/solutions/">查看全部解决方案</a>
            {canOperate ? <a className="is-primary" href="/ontology-studio/solutions/?new=1">新建</a> : null}
          </footer>
        ) : null}
      </div>
    </details>
  );
}

function Header({
  kind,
  solutionId,
  session,
}: {
  kind: ProductKind;
  solutionId: string;
  session: AuthSession | null;
}) {
  const otherUrl = kind === "agent"
    ? studioPageHref("overview", solutionId)
    : `/ontology-agent/?solution=${encodeURIComponent(solutionId)}`;
  return (
    <header className="product-header">
      <a
        className="brand"
        href={kind === "studio"
          ? "/ontology-studio/solutions/"
          : solutionId === "ontology.exchange_analytics.adt"
            ? "/ontology-agent/"
            : `/ontology-agent/?solution=${encodeURIComponent(solutionId)}`}
        aria-label={kind === "studio" ? "Atlas Ontology Studio 首页" : "Atlas Ontology Agent 首页"}
      >
        <span className="brand-mark" aria-hidden="true">
          A
        </span>
        <span className="brand-wordmark">
          <strong>Atlas</strong>
          <small>Ontology analytics</small>
        </span>
      </a>
      <div className="header-actions">
        {session?.authenticated ? <span className={`access-role is-${session.role}`}><i aria-hidden="true" />{session.role === "operator" ? "配置人员" : "只读访问"}<small>{session.username}</small></span> : <span className="access-role is-loading">正在确认权限</span>}
        <SolutionSwitcher selectedId={solutionId} kind={kind} canOperate={session?.authenticated === true && session.role === "operator"} />
        <a className="product-switch" href={otherUrl}>
          {phaseLabels[kind].companion}
          <span aria-hidden="true">↗</span>
        </a>
      </div>
    </header>
  );
}

function SemanticSpine({ context }: { context: ProductContext }) {
  const steps = [
    {
      label: "Solution",
      value: context.subject.solution_id,
      state: "registered",
    },
    {
      label: "Semantic release",
      value: shortDigest(context.subject.active_runtime.release_checksum),
      state: "verified",
    },
    {
      label: "Runtime snapshot",
      value: shortDigest(context.subject.active_runtime.snapshot_checksum),
      state: "active",
    },
    {
      label: "Product context",
      value: shortDigest(context.subject_checksum),
      state: context.persistence === "postgresql-s3" ? "durable" : "compatibility",
    },
  ];
  return (
    <aside className="semantic-spine" aria-label="Active context lineage">
      <div className="spine-heading">
        <span>ACTIVE LINEAGE</span>
        <b>04 / 04</b>
      </div>
      <ol>
        {steps.map((step, index) => (
          <li key={step.label} className={index === steps.length - 1 ? "is-current" : ""}>
            <span className="spine-node" aria-hidden="true">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div>
              <span className="spine-label">{step.label}</span>
              <strong>{step.value}</strong>
              <small>{step.state}</small>
            </div>
          </li>
        ))}
      </ol>
    </aside>
  );
}

function ContextFacts({ context }: { context: ProductContext }) {
  const facts = [
    ["Environment", context.subject.active_runtime.environment_id],
    ["Solution version", context.subject.solution_version],
    ["Scenario contract", context.subject.scenario_id],
    [
      "Certification",
      context.subject.active_runtime.certification_profile ?? "Not declared",
    ],
    ["State store", context.persistence === "postgresql-s3" ? "PostgreSQL" : "Legacy compatibility"],
    ["Artifact store", context.artifact ? "S3-compatible · exact version" : "Legacy compatibility"],
  ];
  return (
    <section className="context-facts" aria-labelledby="facts-heading">
      <div className="section-heading">
        <span>CONTEXT DOSSIER</span>
        <h2 id="facts-heading">可核验的运行边界</h2>
      </div>
      <dl>
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {context.artifact ? (
        <div className="artifact-proof">
          <span className="proof-mark" aria-hidden="true">✓</span>
          <div>
            <strong>上下文工件已按 exact version 回读</strong>
            <p>
              {context.artifact.bucket} / {shortDigest(context.artifact.version_id)} ·{" "}
              {context.artifact.size_bytes} bytes
            </p>
          </div>
        </div>
      ) : (
        <div className="artifact-proof is-compatibility">
          <span className="proof-mark" aria-hidden="true">!</span>
          <div>
            <strong>当前仍在 legacy compatibility 模式</strong>
            <p>新部署必须完成 PostgreSQL + S3 context import 后再对外验证。</p>
          </div>
        </div>
      )}
    </section>
  );
}

function Limitations({ context }: { context: ProductContext }) {
  return (
    <section className="limitations" aria-labelledby="limitations-heading">
      <span className="section-index">BOUNDARY / 01</span>
      <h2 id="limitations-heading">这份上下文能说明什么</h2>
      <p>
        它证明产品正在读取一个明确的 ADT synthetic solution 与 active runtime；它不证明 HKEX
        业务口径、生产安全或企业级可用性。
      </p>
      <ul>
        {context.subject.limitations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

const componentLabels = {
  authoring_profile: "Authoring profile",
  semantic_source: "Semantic source",
  agent_experience: "Agent experience",
  reference_evaluation: "Reference & control",
} as const;

function StudioSolutionCatalog({
  catalog,
  activeSolutionId,
  selectedSolutionId,
}: {
  catalog: SolutionCatalog;
  activeSolutionId: string;
  selectedSolutionId: string;
}) {
  const latestBySolution = new Map<string, SolutionCatalog["solutions"][number]>();
  const historyCount = new Map<string, number>();
  for (const solution of catalog.solutions) {
    historyCount.set(solution.solution_id, (historyCount.get(solution.solution_id) ?? 0) + 1);
    const current = latestBySolution.get(solution.solution_id);
    if (
      !current ||
      current.solution_version.localeCompare(solution.solution_version, undefined, { numeric: true }) < 0
    ) {
      latestBySolution.set(solution.solution_id, solution);
    }
  }
  const visibleSolutions = [...latestBySolution.values()];
  return (
    <section className="solution-catalog" aria-labelledby="solution-catalog-heading">
      <div className="solution-catalog-heading">
        <div>
          <span>SOLUTION CATALOG</span>
          <h2 id="solution-catalog-heading">已安装的场景组件</h2>
        </div>
        <code>{catalog.contract}</code>
      </div>
      <div className="solution-list">
        {visibleSolutions.map((solution) => (
          <article className={solution.solution_id === selectedSolutionId ? "is-selected" : ""} key={`${solution.solution_id}@${solution.solution_version}`}>
            <div className="solution-identity">
              <div>
                <span className="solution-state">
                  {solution.solution_id === selectedSolutionId
                    ? "OPEN WORKSPACE"
                    : solution.solution_id === activeSolutionId
                      ? "ACTIVE RUNTIME"
                      : "INSTALLED"}
                </span>
                <h3>{solution.display_name.zh}</h3>
                <p>{solution.display_name.en}</p>
              </div>
              <code>REG {solution.solution_version}</code>
            </div>
            <div className="solution-open-actions">
              <a href={studioPageHref("overview", solution.solution_id)}>Open in Studio</a>
              <a href={`/ontology-agent/?solution=${encodeURIComponent(solution.solution_id)}`}>Open in Agent</a>
            </div>
            <dl className="solution-meta">
              <div><dt>Workspace</dt><dd>{solution.workspace_id}</dd></div>
              <div><dt>Studio adapter</dt><dd>{solution.studio_adapter_id}</dd></div>
              <div><dt>Semantic source</dt><dd>{solution.semantic_source_version}</dd></div>
              <div><dt>Registry</dt><dd>{solution.persistence === "postgresql-s3" ? "PostgreSQL + exact S3" : "Compatibility"}</dd></div>
              <div><dt>Registration</dt><dd>{shortDigest(solution.subject_checksum)}</dd></div>
            </dl>
            <ol className="component-strip" aria-label="Solution components">
              {solution.components.map((component, index) => (
                <li key={component.component_id}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <strong>{componentLabels[component.kind]}</strong>
                    <code>{shortDigest(component.sha256)}</code>
                  </div>
                </li>
              ))}
            </ol>
            <p className="catalog-boundary">
              Catalog registration only · release and activation authority remain separate
              {(historyCount.get(solution.solution_id) ?? 1) > 1
                ? ` · ${(historyCount.get(solution.solution_id) ?? 1) - 1} prior exact registration retained`
                : ""}.
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

function pathValue(draft: Record<string, unknown>, path: string): DraftOperationValue {
  let current: unknown = draft;
  for (const segment of path.split(".")) {
    if (!current || typeof current !== "object" || Array.isArray(current)) {
      return "";
    }
    current = (current as Record<string, unknown>)[segment];
  }
  if (typeof current === "string" || typeof current === "boolean") {
    return current;
  }
  if (Array.isArray(current) && current.every((item) => typeof item === "string")) {
    return current;
  }
  return "";
}

function valuesFromEditor(editor: WorkspaceEditor): Record<string, DraftOperationValue> {
  return Object.fromEntries(
    editor.descriptor.fields.map((field) => [
      field.path,
      pathValue(editor.workspace.draft, field.path),
    ]),
  );
}

function sameValue(left: DraftOperationValue, right: DraftOperationValue): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function StudioWorkspaceEditor({ workspaceId }: { workspaceId: string }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["studio-workspace-editor", workspaceId],
    queryFn: () => fetchWorkspaceEditor(workspaceId),
  });
  const [values, setValues] = useState<Record<string, DraftOperationValue>>({});
  const editor = query.data;
  const baseline = useMemo(() => (editor ? valuesFromEditor(editor) : {}), [editor]);

  useEffect(() => {
    if (editor) setValues(valuesFromEditor(editor));
  }, [editor]);

  const save = useMutation({
    mutationFn: async () => {
      if (!editor) return;
      const operations = editor.descriptor.fields
        .filter((field) => !sameValue(values[field.path] ?? "", baseline[field.path] ?? ""))
        .map((field) => ({ path: field.path, value: values[field.path] ?? "" }));
      if (operations.length) {
        await applyDraftOperations(workspaceId, editor.workspace.revision, operations);
      }
    },
    onSuccess: async () => {
      await query.refetch();
      await queryClient.invalidateQueries({ queryKey: ["studio-workbench", workspaceId] });
    },
  });
  const validate = useMutation({
    mutationFn: async () => {
      if (editor) await validateDraft(workspaceId, editor.workspace.revision);
    },
    onSuccess: async () => {
      await query.refetch();
      await queryClient.invalidateQueries({ queryKey: ["studio-workbench", workspaceId] });
    },
  });
  const publish = useMutation({
    mutationFn: async () => {
      if (editor) await publishDraft(workspaceId, editor.workspace.revision);
    },
    onSuccess: async () => {
      await query.refetch();
      await queryClient.invalidateQueries({ queryKey: ["studio-workbench", workspaceId] });
    },
  });

  if (query.isPending) {
    return <section className="catalog-state">正在打开可验证的 Studio workspace…</section>;
  }
  if (query.isError || !editor) {
    return (
      <section className="catalog-state is-error" role="alert">
        Workspace editor 不可用；Studio 不会退回浏览器内置表单。
      </section>
    );
  }

  const dirty = editor.descriptor.fields.some(
    (field) => !sameValue(values[field.path] ?? "", baseline[field.path] ?? ""),
  );
  const exactValidation =
    editor.workspace.validation.status === "PASS" &&
    editor.workspace.validation.revision === editor.workspace.revision &&
    editor.workspace.validation.draft_checksum === editor.workspace.draft_checksum;
  const actionError = save.error ?? validate.error ?? publish.error;

  function updateValue(path: string, value: DraftOperationValue) {
    setValues((current) => ({ ...current, [path]: value }));
  }

  return (
    <section className="workspace-editor" aria-labelledby="workspace-editor-heading">
      <div className="workspace-editor-heading">
        <div>
          <span>AUTHORING WORKSPACE</span>
          <h2 id="workspace-editor-heading">{editor.descriptor.title.zh}</h2>
          <p>{editor.descriptor.description.zh}</p>
        </div>
        <dl>
          <div><dt>Revision</dt><dd>r{editor.workspace.revision}</dd></div>
          <div><dt>Target</dt><dd>{editor.workspace.target_version}</dd></div>
          <div><dt>State</dt><dd>{editor.workspace.validation.status}</dd></div>
          <div><dt>Authority</dt><dd>{editor.persistence === "postgresql-s3" ? "PostgreSQL + S3" : "Compatibility"}</dd></div>
        </dl>
      </div>
      <div className="editor-fields">
        {editor.descriptor.fields.map((field) => {
          const value = values[field.path];
          return (
            <div className={`editor-field control-${field.control.toLowerCase()}`} key={field.path}>
              <div className="field-copy">
                <label htmlFor={`field-${field.path}`}>{field.label.zh}</label>
                <p>{field.help.zh}</p>
                <code>{field.path}</code>
              </div>
              {field.control === "TEXTAREA" ? (
                <textarea
                  id={`field-${field.path}`}
                  value={typeof value === "string" ? value : ""}
                  onChange={(event) => updateValue(field.path, event.target.value)}
                  rows={4}
                />
              ) : field.control === "SELECT" ? (
                <select
                  id={`field-${field.path}`}
                  value={typeof value === "string" ? value : ""}
                  onChange={(event) => updateValue(field.path, event.target.value)}
                >
                  {field.options.map((option) => (
                    <option key={option.value} value={option.value}>{option.label.zh}</option>
                  ))}
                </select>
              ) : field.control === "CHECKBOX" ? (
                <label className="toggle" htmlFor={`field-${field.path}`}>
                  <input
                    id={`field-${field.path}`}
                    type="checkbox"
                    checked={typeof value === "boolean" ? value : false}
                    onChange={(event) => updateValue(field.path, event.target.checked)}
                  />
                  <span aria-hidden="true" />
                  {value === true ? "已启用" : "未启用"}
                </label>
              ) : (
                <div className="multi-select" id={`field-${field.path}`}>
                  {field.options.map((option) => {
                    const selected = Array.isArray(value) && value.includes(option.value);
                    return (
                      <label key={option.value}>
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => {
                            const current = Array.isArray(value) ? value : [];
                            updateValue(
                              field.path,
                              selected
                                ? current.filter((item) => item !== option.value)
                                : [...current, option.value],
                            );
                          }}
                        />
                        {option.label.zh}
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="editor-actions">
        <div>
          <span className={`validation-state is-${editor.workspace.validation.status.toLowerCase()}`}>
            {exactValidation ? "EXACT VALIDATION PASS" : `VALIDATION ${editor.workspace.validation.status}`}
          </span>
          <code>{shortDigest(editor.workspace.draft_checksum)}</code>
          {actionError ? <p role="alert">{(actionError as Error).message}</p> : null}
        </div>
        <div className="action-buttons">
          <button type="button" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "保存中…" : "保存草稿"}
          </button>
          <button type="button" disabled={dirty || validate.isPending} onClick={() => validate.mutate()}>
            {validate.isPending ? "验证中…" : "验证当前版本"}
          </button>
          <button className="primary" type="button" disabled={dirty || !exactValidation || publish.isPending} onClick={() => publish.mutate()}>
            {publish.isPending ? "发布中…" : "发布语义版本"}
          </button>
        </div>
      </div>
      <p className="editor-boundary">
        表单来自 exact Authoring Profile；保存不会激活 Agent runtime，发布也不会自动切换 active snapshot。
      </p>
    </section>
  );
}

function StudioDraftControlBar({
  workbench,
  validating,
  publishing,
  error,
  onValidate,
  onPublish,
}: {
  workbench: StudioWorkbench;
  validating: boolean;
  publishing: boolean;
  error: string | null;
  onValidate: () => void;
  onPublish: () => void;
}) {
  const exactValidation = workbench.workspace.validation.status === "PASS"
    && workbench.workspace.validation.revision === workbench.workspace.revision
    && workbench.workspace.validation.draft_checksum === workbench.workspace.draft_checksum;
  return <section className="studio-draft-control" aria-label="当前 Draft 发布控制">
    <div className="draft-control-identity">
      <span>WORKING DRAFT</span>
      <strong>r{workbench.workspace.revision} · 目标 v{workbench.workspace.target_version}</strong>
      <code>{shortDigest(workbench.workspace.draft_checksum)}</code>
    </div>
    <ol className="draft-control-states">
      <li className="is-current"><span>1</span><b>Draft</b></li>
      <li className={exactValidation ? "is-complete" : ""}><span>2</span><b>{exactValidation ? "已验证" : "待验证"}</b></li>
      <li className={workbench.workspace.last_published?.version === workbench.workspace.target_version ? "is-complete" : ""}><span>3</span><b>已发布</b></li>
      <li><span>4</span><b>运行激活</b></li>
    </ol>
    <div className="draft-control-actions">
      <button type="button" disabled={validating || publishing} onClick={onValidate}>{validating ? "验证中…" : "验证当前 Draft"}</button>
      <button type="button" className="is-primary" disabled={!exactValidation || publishing || validating} onClick={onPublish}>{publishing ? "发布中…" : "发布语义版本"}</button>
    </div>
    {error ? <p role="alert">{error}</p> : null}
  </section>;
}

function StudioOverviewPanel({
  workbench,
  runtime,
  sourceLibrary,
  llmInstalled,
  solutionId,
}: {
  workbench: StudioWorkbench;
  runtime: AgentRuntimeStatus | null;
  sourceLibrary: StudioSourceLibrary | null;
  llmInstalled: boolean;
  solutionId: string;
}) {
  const validation = workbench.workspace.validation.status;
  const release = workbench.workspace.last_published;
  const active = runtime?.active;
  const packageAssets = [
    workbench.package.entities,
    workbench.package.relationships,
    workbench.package.metrics,
    workbench.package.rules,
    workbench.package.bindings,
    workbench.package.analysis_patterns,
  ].reduce((total, items) => total + items.length, 0);
  const intakeGaps = Array.isArray(workbench.intake.gaps) ? workbench.intake.gaps.length : 0;
  const referencePack = workbench.intake.reference_source_pack && typeof workbench.intake.reference_source_pack === "object"
    ? workbench.intake.reference_source_pack as Record<string, unknown>
    : {};
  const registrations = Array.isArray(referencePack.registrations)
    ? referencePack.registrations.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    : [];
  const expectedSourceIds = new Set(registrations.map((item) => String(item.source_id ?? "")).filter(Boolean));
  const installedAssets = [
    ...(Array.isArray(workbench.intake.assets) ? workbench.intake.assets : []),
    ...(Array.isArray(workbench.intake.source_files) ? workbench.intake.source_files : []),
  ].filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
  const installedAssetSourceIds = new Set(
    installedAssets
      .map((item) => String(item.asset_id ?? item.file_id ?? ""))
      .filter(Boolean),
  );
  const lineageSourceIds = expectedSourceIds.size ? expectedSourceIds : installedAssetSourceIds;
  const installedSourceIds = new Set(sourceLibrary?.current.map((item) => item.source_id) ?? []);
  const reviewedBaseline = workbench.intake.reviewed_baseline && typeof workbench.intake.reviewed_baseline === "object"
    ? workbench.intake.reviewed_baseline as Record<string, unknown>
    : {};
  const reviewedMetricSet = Array.isArray(reviewedBaseline.metric_set) ? reviewedBaseline.metric_set : [];
  const nextPage: StudioPageId = validation !== "PASS"
    ? "quality"
    : release === null
      ? "inputs"
      : active?.release.version !== release.version
        ? "release"
        : "semantic";
  const nextSubpage: StudioSubpageId = validation !== "PASS"
    ? "validation"
    : release === null
      ? "versions"
      : active?.release.version !== release.version
        ? "delivery"
        : "model";
  const nextCopy = validation !== "PASS"
    ? "先运行验证，确认当前语义版本是否完整。"
    : release === null
      ? "当前草稿已验证，可以检查并发布语义版本。"
      : active?.release.version !== release.version
        ? "已有新发布版本，准备并激活对应运行快照。"
        : "工作区与运行版本一致，可以继续维护业务模型。";

  const steps: Array<{ page: StudioPageId; subpage?: StudioSubpageId; number: string; title: string; copy: string }> = [
    { page: "inputs", number: "01", title: "整理输入", copy: "复核需求、指标、证据与缺口" },
    { page: "semantic", number: "02", title: "维护语义", copy: "管理对象、关系、指标与策略" },
    { page: "data", number: "03", title: "绑定数据", copy: "连接字段、表与关联关系" },
    { page: "quality", number: "04", title: "验证与复核", copy: "执行检查并处置候选观察" },
    { page: "release", number: "05", title: "发布版本", copy: "审批、认证、激活与回滚" },
  ];

  return (
    <div className="studio-overview">
      <section className="studio-next-action">
        <div><span>建议下一步</span><h2>{nextCopy}</h2></div>
        <Link to={studioPageHref(nextPage, solutionId, nextSubpage)}>继续处理 <span aria-hidden="true">→</span></Link>
      </section>
      <StudioVersionLineage
        sourcePack={{
          physicalFileCount: Number(referencePack.physical_file_count ?? 0)
            || installedAssets.length
            || sourceLibrary?.current.length
            || 0,
          logicalSourceCount: lineageSourceIds.size || sourceLibrary?.current.length || 0,
          installedSourceCount: lineageSourceIds.size
            ? [...lineageSourceIds].filter((sourceId) => installedSourceIds.has(sourceId)).length
            : sourceLibrary?.current.length ?? 0,
        }}
        draft={{
          revision: workbench.workspace.revision,
          targetVersion: workbench.workspace.target_version,
          validation,
        }}
        reviewed={{
          version: typeof reviewedBaseline.semantic_version === "string" ? reviewedBaseline.semantic_version : null,
          status: typeof reviewedBaseline.review_status === "string" ? reviewedBaseline.review_status : null,
          metricCount: reviewedMetricSet.length,
        }}
        active={active ? { version: active.release.version, environmentId: runtime?.environment_id ?? active.environment_id } : null}
        solutionId={solutionId}
      />
      <section className="studio-flow-panel">
        <div className="studio-panel-heading"><div><span>建模流程</span><h2>从业务定义到可用运行版本</h2></div><p>每一步都是独立页面，状态通过同一个工作区衔接。</p></div>
        <ol className="studio-flow-list">
          {steps.map((step) => (
            <li key={step.page}>
              <Link to={studioPageHref(step.page, solutionId, step.subpage)}>
                <span>{step.number}</span><div><strong>{step.title}</strong><small>{step.copy}</small></div><i aria-hidden="true">→</i>
              </Link>
            </li>
          ))}
        </ol>
      </section>
      <section className="studio-asset-summary">
        <div><span>语义资产</span><strong>{packageAssets}</strong><small>核心对象、关系、指标、规则、映射与分析模式</small></div>
        <div><span>待处理变更</span><strong>{workbench.semantic_change_requests.length}</strong><small>来自分析端的语义变更请求</small></div>
        <div><span>输入缺口</span><strong>{intakeGaps}</strong><small>已记录且需要后续确认的材料缺口</small></div>
        <div><span>AI 辅助</span><strong>{llmInstalled ? "可用" : "未安装"}</strong><small>观察只进入人工复核，不会直接改写模型</small></div>
      </section>
    </div>
  );
}

function StudioPackageWorkbench({
  workspaceId,
  page,
  subpage,
  solutionId,
  reviewer,
}: {
  workspaceId: string;
  page: StudioPageId;
  subpage: StudioSubpageId;
  solutionId: string;
  reviewer: string;
}) {
  const queryClient = useQueryClient();
  const queryScope = studioQueryScope(page, subpage);
  const query = useQuery({
    queryKey: ["studio-workbench", workspaceId],
    queryFn: () => fetchStudioWorkbench(workspaceId),
  });
  const runtimeQuery = useQuery({
    queryKey: ["studio-runtime-status", query.data?.package.package_id],
    queryFn: () => fetchAgentRuntimeStatus(query.data!.package.package_id),
    enabled: Boolean(query.data) && queryScope.runtime,
  });
  const llmStatusQuery = useQuery({
    queryKey: ["studio-llm-status", workspaceId],
    queryFn: () => fetchStudioLlmStatus(workspaceId),
    enabled: Boolean(query.data) && queryScope.llmStatus,
  });
  const llmObservationsQuery = useQuery({
    queryKey: ["studio-llm-observations", workspaceId],
    queryFn: () => fetchStudioObservations(workspaceId),
    enabled: queryScope.llmObservations
      && llmStatusQuery.data?.installed === true
      && llmStatusQuery.data.mode === "active-observation-canary",
  });
  const constructionRunsQuery = useQuery({
    queryKey: ["studio-construction-runs", workspaceId],
    queryFn: () => fetchConstructionRuns(workspaceId),
    enabled: Boolean(query.data) && queryScope.constructionRuns,
  });
  const constructionJobsQuery = useQuery({
    queryKey: ["studio-construction-jobs", workspaceId],
    queryFn: () => fetchConstructionJobs(workspaceId),
    enabled: Boolean(query.data) && queryScope.constructionJobs,
    refetchInterval: (state) => state.state.data?.jobs.some((job) =>
      ["QUEUED", "RUNNING", "COMMITTING", "CANCEL_REQUESTED"].includes(job.status)
    ) ? 1000 : false,
  });
  const activeReviewRunId = constructionRunsQuery.data?.runs.find((item) => item.decision === null)?.run.run_id ?? null;
  const reviewDraftQuery = useQuery({
    queryKey: ["studio-construction-review-draft", workspaceId, activeReviewRunId],
    queryFn: () => fetchConstructionReviewDraft(workspaceId, activeReviewRunId!),
    enabled: queryScope.reviewDraft && Boolean(activeReviewRunId),
  });
  const sourceLibraryQuery = useQuery({
    queryKey: ["studio-source-library", workspaceId],
    queryFn: () => fetchStudioSourceLibrary(workspaceId),
    enabled: Boolean(query.data) && queryScope.sourceLibrary,
  });
  const [prepared, setPrepared] = useState<Awaited<ReturnType<typeof prepareAgentRuntime>> | null>(null);
  const [rollbackTarget, setRollbackTarget] = useState<Awaited<ReturnType<typeof activateAgentRuntime>>["previous"]>(null);
  const [verification, setVerification] = useState<Awaited<ReturnType<typeof verifyAgentRuntime>> | null>(null);
  useEffect(() => {
    setRollbackTarget(runtimeQuery.data?.rollback_target ?? null);
  }, [runtimeQuery.data?.rollback_target]);
  useEffect(() => {
    const release = query.data?.workspace.last_published;
    if (!release || (prepared && prepared.snapshot.release.checksum !== release.checksum)) {
      setPrepared(null);
      setVerification(null);
    }
  }, [prepared, query.data?.workspace.last_published]);
  const prepare = useMutation({
    mutationFn: async () => {
      const release = query.data?.workspace.last_published;
      if (!release) throw new ProductApiError("请先发布 exact semantic release。", 409);
      return prepareAgentRuntime(release);
    },
    onSuccess: (value) => {
      setPrepared(value);
      setVerification(null);
    },
  });
  const activate = useMutation({
    mutationFn: async () => {
      if (!prepared) throw new ProductApiError("请先准备并认证 runtime。", 409);
      return activateAgentRuntime(prepared.snapshot, runtimeQuery.data?.active ?? null);
    },
    onSuccess: async (receipt) => {
      setRollbackTarget(receipt.previous);
      setVerification(null);
      await runtimeQuery.refetch();
    },
  });
  const rollback = useMutation({
    mutationFn: async () => {
      const current = runtimeQuery.data?.active;
      if (!rollbackTarget || !current) throw new ProductApiError("没有可回滚的 previous snapshot。", 409);
      return rollbackAgentRuntime(rollbackTarget, current);
    },
    onSuccess: async (receipt) => {
      setRollbackTarget(receipt.previous);
      setPrepared(null);
      setVerification(null);
      await runtimeQuery.refetch();
    },
  });
  const verify = useMutation({
    mutationFn: async () => {
      const active = runtimeQuery.data?.active;
      if (!active) throw new ProductApiError("当前没有可验证的 active runtime。", 409);
      return verifyAgentRuntime(active);
    },
    onSuccess: setVerification,
  });
  const author = useMutation({
    mutationFn: async (operation: PackageDraftOperation) => {
      if (!query.data) throw new ProductApiError("Studio workbench 尚未就绪。", 409);
      return applyPackageOperations(
        workspaceId,
        query.data.workspace.revision,
        [operation],
      );
    },
    onSuccess: async () => {
      await query.refetch();
      await queryClient.invalidateQueries({ queryKey: ["studio-workspace-editor", workspaceId] });
    },
  });
  const authorAndValidate = useMutation({
    mutationFn: async (operation: PackageDraftOperation) => {
      if (!query.data) throw new ProductApiError("Studio workbench 尚未就绪。", 409);
      const saved = await applyPackageOperations(
        workspaceId,
        query.data.workspace.revision,
        [operation],
      );
      return validateDraft(workspaceId, saved.revision);
    },
    onSuccess: async () => {
      await query.refetch();
      await queryClient.invalidateQueries({ queryKey: ["studio-workspace-editor", workspaceId] });
    },
  });
  const validateWorkspace = useMutation({
    mutationFn: async () => {
      if (!query.data) throw new ProductApiError("Studio workbench 尚未就绪。", 409);
      return validateDraft(workspaceId, query.data.workspace.revision);
    },
    onSuccess: async () => {
      await query.refetch();
      await queryClient.invalidateQueries({ queryKey: ["studio-workspace-editor", workspaceId] });
    },
  });
  const publishWorkspace = useMutation({
    mutationFn: async () => {
      if (!query.data) throw new ProductApiError("Studio workbench 尚未就绪。", 409);
      return publishDraft(workspaceId, query.data.workspace.revision);
    },
    onSuccess: async () => {
      await query.refetch();
      await runtimeQuery.refetch();
      await queryClient.invalidateQueries({ queryKey: ["studio-workspace-editor", workspaceId] });
    },
  });
  const registerSource = useMutation({
    mutationFn: async (input: Parameters<typeof registerStudioSource>[1]) => {
      return registerStudioSource(workspaceId, input);
    },
    onSuccess: async () => {
      await sourceLibraryQuery.refetch();
    },
  });
  const installReferencePack = useMutation({
    mutationFn: async () => installStudioReferenceSourcePack(workspaceId),
    onSuccess: async () => {
      await Promise.all([
        sourceLibraryQuery.refetch(),
        query.refetch(),
      ]);
    },
  });
  const importInstalledSources = useMutation({
    mutationFn: async () => importStudioInstalledSources(workspaceId),
    onSuccess: async () => {
      await Promise.all([
        sourceLibraryQuery.refetch(),
        query.refetch(),
      ]);
    },
  });
  const generateObservations = useMutation({
    mutationFn: async () => {
      if (!query.data) throw new ProductApiError("Studio workbench 尚未就绪。", 409);
      return generateStudioObservations(workspaceId, query.data.workspace.revision);
    },
    onSuccess: async () => {
      await llmObservationsQuery.refetch();
      await query.refetch();
    },
  });
  const reviewObservations = useMutation({
    mutationFn: async (dispositions: StudioObservationDisposition[]) => {
      if (!query.data) throw new ProductApiError("Studio workbench 尚未就绪。", 409);
      const record = llmObservationsQuery.data?.observation_sets.find((item) => item.decision === null)
        ?? llmObservationsQuery.data?.observation_sets[0];
      if (!record) throw new ProductApiError("没有可复核的 observation set。", 409);
      return reviewStudioObservations(
        workspaceId,
        record.observation_set.observation_set_id,
        query.data.workspace.revision,
        dispositions,
      );
    },
    onSuccess: async () => {
      await Promise.all([
        query.refetch(),
        llmObservationsQuery.refetch(),
        queryClient.invalidateQueries({ queryKey: ["studio-workspace-editor", workspaceId] }),
      ]);
    },
  });
  const startConstruction = useMutation({
    mutationFn: async (sourceVersionIds: string[]) => {
      if (!query.data) throw new ProductApiError("Studio workbench 尚未就绪。", 409);
      return enqueueConstructionJob(workspaceId, query.data.workspace.revision, sourceVersionIds);
    },
    onSuccess: async () => {
      await constructionJobsQuery.refetch();
    },
  });
  const cancelConstruction = useMutation({
    mutationFn: async (jobId: string) => cancelConstructionJob(workspaceId, jobId),
    onSuccess: async () => { await constructionJobsQuery.refetch(); },
  });
  const retryConstruction = useMutation({
    mutationFn: async (jobId: string) => retryConstructionJob(workspaceId, jobId),
    onSuccess: async () => { await constructionJobsQuery.refetch(); },
  });
  const latestJobStatus = constructionJobsQuery.data?.jobs[0]?.status;
  useEffect(() => {
    if (["SUCCEEDED", "FAILED", "CANCELLED", "STALE"].includes(latestJobStatus ?? "")) {
      void queryClient.refetchQueries({
        queryKey: ["studio-construction-runs", workspaceId],
        exact: true,
        type: "active",
      });
    }
  }, [latestJobStatus, queryClient, workspaceId]);
  const reviewConstruction = useMutation({
    mutationFn: async ({ runId, dispositions, reviewBatchChecksum }: { runId: string; dispositions: ConstructionDisposition[]; reviewBatchChecksum: string | null }) => {
      const run = constructionRunsQuery.data?.runs.find((item) => item.run.run_id === runId)?.run;
      if (!run) throw new ProductApiError("候选运行已不存在，请刷新后重试。", 409);
      return reviewConstructionRun(workspaceId, runId, run.base_revision, dispositions, reviewBatchChecksum);
    },
    onSuccess: async () => {
      await Promise.all([
        query.refetch(),
        constructionRunsQuery.refetch(),
        queryClient.invalidateQueries({ queryKey: ["studio-workspace-editor", workspaceId] }),
      ]);
    },
  });
  const saveReviewDraft = useMutation({
    mutationFn: async ({ runId, dispositions }: { runId: string; dispositions: ConstructionDisposition[] }) => {
      const expectedReviewRevision = reviewDraftQuery.data?.review_revision ?? 0;
      return saveConstructionReviewDraft(
        workspaceId,
        runId,
        expectedReviewRevision,
        dispositions,
      );
    },
    onSuccess: async () => { await reviewDraftQuery.refetch(); },
  });
  if (query.isPending) {
    return <section className="catalog-state">正在 materialize exact ontology package…</section>;
  }
  if (query.isError || !query.data) {
    return <section className="catalog-state is-error" role="alert">语义工作台不可用；Studio 不会回退到浏览器 hard-code 模型。</section>;
  }
  const busy = prepare.isPending
    ? "prepare" as const
    : activate.isPending
      ? "activate" as const
      : rollback.isPending
        ? "rollback" as const
      : verify.isPending
        ? "verify" as const
        : runtimeQuery.isFetching
          ? "refresh" as const
          : null;
  const actionError = prepare.error ?? activate.error ?? rollback.error ?? verify.error ?? runtimeQuery.error;
  const llmWorkbench = <StudioLlmWorkbench
      status={llmStatusQuery.data ?? null}
      observationSets={llmObservationsQuery.data?.observation_sets ?? []}
      currentRevision={query.data.workspace.revision}
      busy={generateObservations.isPending ? "generate" : reviewObservations.isPending ? "review" : null}
      error={(
        generateObservations.error
        ?? reviewObservations.error
        ?? (llmStatusQuery.data?.installed === true && llmStatusQuery.data.mode === "active-observation-canary" ? llmObservationsQuery.error : null)
      ) instanceof Error ? String((
        generateObservations.error
        ?? reviewObservations.error
        ?? llmObservationsQuery.error
      )?.message) : null}
      onGenerate={() => generateObservations.mutate()}
      onReview={(dispositions) => reviewObservations.mutate(dispositions)}
    />;
  const workspaceActionError = author.error
    ?? authorAndValidate.error
    ?? validateWorkspace.error
    ?? publishWorkspace.error;
  const controls = <StudioDraftControlBar
    workbench={query.data}
    validating={validateWorkspace.isPending || authorAndValidate.isPending}
    publishing={publishWorkspace.isPending}
    error={workspaceActionError instanceof Error ? workspaceActionError.message : null}
    onValidate={() => validateWorkspace.mutate()}
    onPublish={() => publishWorkspace.mutate()}
  />;
  const applyOperation = async (operation: PackageDraftOperation) => { await author.mutateAsync(operation); };
  const applyAndValidateOperation = async (operation: PackageDraftOperation) => { await authorAndValidate.mutateAsync(operation); };
  let content: ReactNode = null;
  if (page === "overview") {
    content = sourceLibraryQuery.isPending || runtimeQuery.isPending
      ? <section className="catalog-state" aria-live="polite">正在核验来源版本与运行权威链路…</section>
      : sourceLibraryQuery.isError || runtimeQuery.isError
        ? <section className="catalog-state is-error" role="alert">概览无法确认完整权威链路；系统不会把未读取状态显示为 0。</section>
        : <StudioOverviewPanel
            workbench={query.data}
            runtime={runtimeQuery.data ?? null}
            sourceLibrary={sourceLibraryQuery.data ?? null}
            llmInstalled={llmStatusQuery.data?.installed === true}
            solutionId={solutionId}
          />;
  } else if (page === "inputs" && subpage === "requirements") {
    content = <RequirementsCatalogView solutionId={solutionId} ontologyPackage={query.data.package} authoring={query.data.authoring} />;
  } else if (page === "inputs" && subpage === "sources") {
    content = <SourceLibraryView
      ontologyPackage={query.data.package}
      intake={query.data.intake}
      library={sourceLibraryQuery.data ?? null}
      busy={registerSource.isPending || installReferencePack.isPending || importInstalledSources.isPending}
      error={(registerSource.error ?? installReferencePack.error ?? importInstalledSources.error ?? sourceLibraryQuery.error) instanceof Error
        ? String((registerSource.error ?? installReferencePack.error ?? importInstalledSources.error ?? sourceLibraryQuery.error)?.message)
        : null}
      onUpload={async (input) => { await registerSource.mutateAsync(input); }}
      onPreview={(sourceVersionId) => fetchStudioSourcePreview(workspaceId, sourceVersionId)}
      onInstallReferencePack={async () => { await installReferencePack.mutateAsync(); }}
      onImportInstalledSources={async () => { await importInstalledSources.mutateAsync(); }}
    />;
  } else if (page === "inputs" && subpage === "runs") {
    content = <>
      <ConstructionRunsView
        runs={constructionRunsQuery.data ?? null}
        jobs={constructionJobsQuery.data ?? null}
        sources={sourceLibraryQuery.data?.current ?? []}
        currentRevision={query.data.workspace.revision}
        busy={startConstruction.isPending || cancelConstruction.isPending || retryConstruction.isPending}
        error={(startConstruction.error ?? cancelConstruction.error ?? retryConstruction.error ?? constructionJobsQuery.error ?? constructionRunsQuery.error) instanceof Error ? String((startConstruction.error ?? cancelConstruction.error ?? retryConstruction.error ?? constructionJobsQuery.error ?? constructionRunsQuery.error)?.message) : null}
        onStart={(sourceVersionIds) => startConstruction.mutate(sourceVersionIds)}
        onCancel={(jobId) => cancelConstruction.mutate(jobId)}
        onRetry={(jobId) => retryConstruction.mutate(jobId)}
      />
      <details className="auxiliary-construction-tool">
        <summary>AI 辅助字段提取</summary>
        {llmWorkbench}
      </details>
    </>;
  } else if (page === "semantic" && subpage === "model") {
    content = <SemanticAssetCatalog
      mode="business"
      solutionId={solutionId}
      ontologyPackage={query.data.package}
      candidates={constructionRunsQuery.data?.runs.find((item) => item.decision === null)?.run.candidates ?? []}
      busy={author.isPending || authorAndValidate.isPending}
      error={(author.error ?? authorAndValidate.error) instanceof Error ? String((author.error ?? authorAndValidate.error)?.message) : null}
      onApply={applyOperation}
      onApplyAndValidate={applyAndValidateOperation}
      onConfirm={applyOperation}
      onDeprecate={applyOperation}
      assetChecksums={query.data.asset_checksums}
      reviewer={reviewer}
    />;
  } else if (page === "semantic" && subpage === "metrics") {
    content = <SemanticAssetCatalog
      mode="metrics"
      solutionId={solutionId}
      ontologyPackage={query.data.package}
      authoring={query.data.authoring}
      candidates={constructionRunsQuery.data?.runs.find((item) => item.decision === null)?.run.candidates ?? []}
      busy={author.isPending || authorAndValidate.isPending}
      error={(author.error ?? authorAndValidate.error) instanceof Error ? String((author.error ?? authorAndValidate.error)?.message) : null}
      onApply={applyOperation}
      onApplyAndValidate={applyAndValidateOperation}
      onConfirm={applyOperation}
      onDeprecate={applyOperation}
      assetChecksums={query.data.asset_checksums}
      reviewer={reviewer}
    />;
  } else if (page === "semantic" && subpage === "graph") {
    const pendingCandidateRun = constructionRunsQuery.data?.runs.find((item) => item.decision === null)?.run;
    content = <OntologyGraphEditor
      ontologyPackage={query.data.package}
      candidates={pendingCandidateRun?.candidates ?? []}
      reviewHref={studioPageHref("quality", solutionId, "review")}
      createEntityHref={semanticAssetHref(solutionId, "entities")}
      createRelationshipHref={semanticAssetHref(solutionId, "relationships")}
      editAssetHref={(collection, objectId) => semanticAssetHref(solutionId, collection, objectId)}
    />;
  } else if (page === "semantic" && subpage === "experience") {
    content = <SemanticAssetCatalog
      mode="experience"
      solutionId={solutionId}
      ontologyPackage={query.data.package}
      candidates={constructionRunsQuery.data?.runs.find((item) => item.decision === null)?.run.candidates ?? []}
      busy={author.isPending || authorAndValidate.isPending}
      error={(author.error ?? authorAndValidate.error) instanceof Error ? String((author.error ?? authorAndValidate.error)?.message) : null}
      onApply={applyOperation}
      onApplyAndValidate={applyAndValidateOperation}
      onConfirm={applyOperation}
      onDeprecate={applyOperation}
      assetChecksums={query.data.asset_checksums}
      reviewer={reviewer}
    />;
  } else if (page === "quality" && subpage === "policies") {
    content = <SemanticAssetCatalog
      mode="policies"
      solutionId={solutionId}
      ontologyPackage={query.data.package}
      busy={false}
      error={null}
      onApply={applyOperation}
      assetChecksums={query.data.asset_checksums}
      reviewer={reviewer}
    />;
  } else if (page === "quality" && subpage === "review") content = <ConstructionReviewCenter
    runs={constructionRunsQuery.data ?? null}
    reviewDraft={reviewDraftQuery.data ?? null}
    currentRevision={query.data.workspace.revision}
    busy={reviewConstruction.isPending || saveReviewDraft.isPending}
    error={(reviewConstruction.error ?? saveReviewDraft.error ?? reviewDraftQuery.error ?? constructionRunsQuery.error) instanceof Error ? String((reviewConstruction.error ?? saveReviewDraft.error ?? reviewDraftQuery.error ?? constructionRunsQuery.error)?.message) : null}
    onSave={(runId, dispositions) => saveReviewDraft.mutateAsync({ runId, dispositions })}
    onReview={(runId, dispositions, reviewBatchChecksum) => reviewConstruction.mutate({ runId, dispositions, reviewBatchChecksum })}
  />;
  else if (page === "data" && subpage === "schemas") content = <SchemaCatalogView
    ontologyPackage={query.data.package}
    busy={author.isPending}
    error={author.error instanceof Error ? author.error.message : null}
    onApply={applyOperation}
  />;
  else if (page === "data" && subpage === "mappings") content = <MappingWorkbenchView
    ontologyPackage={query.data.package}
    busy={author.isPending}
    error={author.error instanceof Error ? author.error.message : null}
    onApply={applyOperation}
  />;
  else if (page === "data" && subpage === "samples") content = <SampleAndEnumView
    ontologyPackage={query.data.package}
    intake={query.data.intake}
    busy={author.isPending}
    error={author.error instanceof Error ? author.error.message : null}
    onApply={applyOperation}
  />;
  const activeTab: WorkbenchTab | undefined = page === "quality" && subpage === "validation"
        ? "validate"
        : page === "quality" && subpage === "changes"
          ? "evidence"
          : page === "release" && subpage === "delivery"
            ? "release"
            : undefined;
  if (activeTab) content = <StudioWorkbenchView activeTab={activeTab} navigation="hidden" presentation="page" workbench={query.data} authoring={{
    busy: author.isPending,
    error: author.error instanceof Error ? author.error.message : null,
    onApply: applyOperation,
  }} lifecycle={{
    status: runtimeQuery.data ?? null,
    prepared,
    rollbackTarget,
    verification,
    busy,
    error: actionError instanceof Error ? actionError.message : null,
    onRefresh: () => {
      void query.refetch();
      void runtimeQuery.refetch();
    },
    onPrepare: () => prepare.mutate(),
    onActivate: () => activate.mutate(),
    onVerify: () => verify.mutate(),
    onRollback: () => rollback.mutate(),
  }} />;
  if (page === "release" && subpage === "versions") {
    content = <section className="release-version-page">
      <header className="object-page-heading"><div><span>VERSION & APPROVAL</span><h2>版本与审批</h2><p>Draft 修订、精确验证和不可变发布记录在这里汇合；运行准备与激活在“交付与运行”中操作。</p></div><div className="object-page-counts"><strong>{query.data.revisions.length} 个 Draft 修订</strong><span>{query.data.workspace.last_published ? `已发布 v${query.data.workspace.last_published.version}` : "尚未发布"}</span></div></header>
      <div className="release-version-layout"><section><h3>不可变 Draft 修订</h3>{[...query.data.revisions].reverse().map((revision, index) => <article key={`${String(revision.revision)}:${String(revision.record_checksum)}`}><span>r{String(revision.revision)}</span><div><strong>v{String(revision.target_version)}</strong><small>{String(revision.recorded_at)}</small></div><code>{shortDigest(String(revision.draft_checksum))}</code><em>{index === 0 ? "CURRENT" : "HISTORICAL"}</em></article>)}</section><aside><span>LATEST PUBLICATION</span><h3>{query.data.workspace.last_published ? `v${query.data.workspace.last_published.version}` : "尚未发布"}</h3><p>{query.data.workspace.last_published ? "该语义 Release 已冻结；它不会自动成为 Agent Active。" : "当前 Draft 通过精确验证后，才可以发布为不可变语义 Release。"}</p><code>{query.data.workspace.last_published?.checksum ?? query.data.workspace.draft_checksum}</code><Link to={studioPageHref("release", solutionId, "delivery")}>前往交付与运行 →</Link></aside></div>
    </section>;
  }
  return <>{controls}{content}</>;
}

function SolutionLineage({
  solution,
  runtime,
  answerStatus,
}: {
  solution: AgentSolution | StudioSolution;
  runtime?: { version: string; release_checksum: string; snapshot_checksum: string };
  answerStatus?: string;
}) {
  const steps = [
    ["Solution registration", shortDigest(solution.subject_checksum), "installed"],
    ["Semantic package", runtime?.version ?? solution.semantic_source_version, "versioned"],
    ["Runtime snapshot", runtime ? shortDigest(runtime.snapshot_checksum) : "Not active", runtime ? "active" : "blocked"],
    ["Supported answer", answerStatus ?? "Ask a question", answerStatus === "ANSWERED" ? "committed" : "bounded"],
  ];
  return (
    <aside className="semantic-spine" aria-label="Selected solution lineage">
      <div className="spine-heading"><span>SOLUTION LINEAGE</span><b>04 / 04</b></div>
      <ol>
        {steps.map(([stepLabel, value, stepState], index) => (
          <li key={stepLabel} className={index === steps.length - 1 ? "is-current" : ""}>
            <span className="spine-node">{String(index + 1).padStart(2, "0")}</span>
            <div><span className="spine-label">{stepLabel}</span><strong>{value}</strong><small>{stepState}</small></div>
          </li>
        ))}
      </ol>
    </aside>
  );
}

function FactValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span>—</span>;
    const rows = value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item));
    if (rows.length === value.length) {
      const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
      return (
        <div className="analysis-table-wrap">
          <table><thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}</tr></thead>
            <tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{formatDisplayValue(row[column])}</td>)}</tr>)}</tbody>
          </table>
        </div>
      );
    }
    return <ul>{value.map((item, index) => <li key={index}>{String(item)}</li>)}</ul>;
  }
  if (value && typeof value === "object") {
    return (
      <div className="fact-grid">
        {Object.entries(value).map(([key, item]) => (
          item && typeof item === "object"
            ? <section className="fact-group" key={key}><h4>{key.replaceAll("_", " ")}</h4><FactValue value={item} /></section>
            : <div className="fact-cell" key={key}><span>{key.replaceAll("_", " ")}</span><strong>{formatDisplayValue(item)}</strong></div>
        ))}
      </div>
    );
  }
  return <strong>{formatDisplayValue(value)}</strong>;
}

function OntologyInventory({ ontology }: { ontology: SolutionOntology }) {
  return (
    <section className="ontology-inventory" aria-labelledby="ontology-inventory-heading">
      <div className="section-heading">
        <span>ACTIVE ONTOLOGY PACKAGE</span>
        <h2 id="ontology-inventory-heading">指标与分析模式</h2>
      </div>
      <div className="inventory-columns">
        <div>
          <h3>{ontology.metrics.length} governed metrics</h3>
          {ontology.metrics.map((metric) => (
            <article key={metric.id}><code>{metric.id}</code><strong>{metric.name.zh}</strong><p>{metric.definition}</p><small>{metric.unit}</small></article>
          ))}
        </div>
        <div>
          <h3>{ontology.analysis_patterns.length} bounded patterns</h3>
          {ontology.analysis_patterns.map((pattern) => (
            <article key={pattern.id}><code>{pattern.id}</code><strong>{pattern.intent.replaceAll("_", " ")}</strong><p>{pattern.operation}</p><small>{pattern.output_fields.join(" · ")}</small></article>
          ))}
        </div>
      </div>
    </section>
  );
}

function AgentSolutionWorkspace({ solution }: { solution: AgentSolution }) {
  const queryClient = useQueryClient();
  const questions = useQuery({
    queryKey: ["solution-questions", solution.solution_id],
    queryFn: () => fetchSolutionQuestions(solution.solution_id),
  });
  const runtime = useQuery({
    queryKey: ["solution-runtime", solution.solution_id],
    queryFn: () => fetchSolutionRuntime(solution.solution_id),
  });
  const ontology = useQuery({
    queryKey: ["solution-ontology", solution.solution_id],
    queryFn: () => fetchSolutionOntology(solution.solution_id),
  });
  const [question, setQuestion] = useState("");
  const [selectedQuestionCaseId, setSelectedQuestionCaseId] = useState<string | null>(null);
  const [role, setRole] = useState("");
  const [result, setResult] = useState<SolutionAnalysis | null>(null);
  const [submittedRequestId, setSubmittedRequestId] = useState<string | null>(null);
  const selectedQuestionCase = questions.data?.cases.find((item) => item.case_id === selectedQuestionCaseId);
  const modelEligibleCaseId = selectedQuestionCase?.question === question.trim()
    ? selectedQuestionCase.case_id
    : undefined;
  const analysis = useMutation({
    mutationFn: () => analyzeSolution(
      solution.solution_id,
      question.trim(),
      role || runtime.data?.default_role || "",
      modelEligibleCaseId,
    ),
    onSuccess: (payload) => {
      setResult(payload);
      setSubmittedRequestId(null);
    },
  });
  const semanticChange = useMutation({
    mutationFn: (input: SemanticChangeRequestInput) => submitSemanticChangeRequest(
      solution.solution_id,
      input,
    ),
    onSuccess: async (request) => {
      setSubmittedRequestId(request.request_id);
      await queryClient.invalidateQueries({ queryKey: ["studio-workbench", solution.workspace_id] });
    },
  });

  useEffect(() => {
    const first = questions.data?.cases[0];
    if (first && !question) {
      setQuestion(first.question);
      setSelectedQuestionCaseId(first.case_id);
    }
  }, [questions.data, question]);

  useEffect(() => {
    if (runtime.data) {
      setRole(runtime.data.default_role);
      setResult(null);
    }
  }, [runtime.data]);

  if (questions.isPending || runtime.isPending || ontology.isPending) {
    return <section className="catalog-state">正在核验 selected solution 的 runtime、ontology 与问题清单…</section>;
  }
  if (questions.isError || runtime.isError || ontology.isError || !questions.data || !runtime.data || !ontology.data) {
    return <section className="catalog-state is-error" role="alert">Selected solution 尚未形成可读取的 active runtime；Agent 不会退回其他 solution。</section>;
  }

  return (
    <>
      <section className="hero solution-hero">
        <div className="hero-copy">
          <div className="eyebrow-row"><span>ONTOLOGY ANALYTIC AGENT</span><span className="active-chip"><i /> ACTIVE</span></div>
          <p className="scenario-kicker">{solution.display_name.en}</p>
          <h1>从业务问题走到可追溯答案</h1>
          <p className="hero-summary">自然语言负责表达意图；Ontology 限定可执行语义；确定性工具计算事实；active snapshot 与证据决定什么可以展示。</p>
          <div className="hero-identity"><span>{solution.display_name.zh}</span><code>{solution.solution_id}</code></div>
        </div>
        <SolutionLineage solution={solution} runtime={runtime.data} answerStatus={result?.status} />
      </section>
      <section className="analysis-workspace">
        <div className="question-panel">
          <div className="section-heading"><span>GOVERNED QUESTION</span><h2>选择示例或输入业务问题</h2></div>
          <label className="role-control">分析角色
            <select value={role || runtime.data.default_role} onChange={(event) => setRole(event.target.value)}>
              {runtime.data.roles.map((item) => (
                <option key={item.role_id} value={item.role_id}>
                  {item.name.zh} · {item.role_id}{item.access === "DENIED" ? "（拒绝演示）" : ""}
                </option>
              ))}
            </select>
          </label>
          <div className="question-family">
            {questions.data.cases.map((item) => (
              <button
                type="button"
                key={item.case_id}
                className={modelEligibleCaseId === item.case_id ? "is-selected" : undefined}
                onClick={() => {
                  setQuestion(item.question);
                  setSelectedQuestionCaseId(item.case_id);
                }}
              >
                <span>{item.expected_intent}</span>{item.question}
              </button>
            ))}
          </div>
          <textarea aria-label="业务问题" value={question} onChange={(event) => setQuestion(event.target.value)} rows={4} />
          <button className="run-analysis" type="button" disabled={!question.trim() || analysis.isPending} onClick={() => { setResult(null); analysis.mutate(); }}>
            {analysis.isPending ? "分析中…" : "运行受治理分析"}
          </button>
          <p className="analysis-boundary">
            {modelEligibleCaseId
              ? "当前为登记问题：Qwen 只负责受约束的意图 grounding；事实仍由 Ontology 工具确定性计算。"
              : "当前为开放输入：不会外发给模型；Agent 仅在封闭语义内确定性匹配、澄清或拒绝。"}
          </p>
        </div>
        <div className="answer-panel">
          {analysis.isError ? <div className="answer-boundary"><span>FAILED</span><h2>{(analysis.error as Error).message}</h2></div> : null}
          {!analysis.isError && !result ? <div className="answer-placeholder"><span>SUPPORTED ANSWER</span><h2>答案会连同事实、计划和证据显示在这里。</h2></div> : null}
          {result && result.status !== "ANSWERED" ? (
            <div className="answer-boundary"><span>{result.status}</span><code>{result.boundary_code}</code><h2>{result.answer}</h2><p>没有释放部分 facts 或 evidence。</p></div>
          ) : null}
          {result?.status === "ANSWERED" ? (
            <div className="answer-result">
              <header>
                <span>COMMITTED ANALYSIS</span>
                <div className="answer-badges">
                  <b>ANSWERED</b>
                  <b className={`llm-state is-${result.llm.status.toLowerCase()}`}>
                    {result.llm.status === "GROUNDED" ? "QWEN GROUNDED" : null}
                    {result.llm.status === "SHADOW_VERIFIED" ? "QWEN SHADOW" : null}
                    {result.llm.status === "DETERMINISTIC_ONLY" ? "DETERMINISTIC" : null}
                    {result.llm.status === "FALLBACK" ? "SAFE FALLBACK" : null}
                  </b>
                </div>
                <h2>{result.answer}</h2>
              </header>
              <FactValue value={result.facts} />
              {result.llm.status === "FALLBACK" ? <p className="fallback-note">模型路径未通过，本答案已从原始请求重新执行确定性分析，不包含部分模型输出。</p> : null}
              <AgentExecutionEvidence result={result} />
              <SemanticChangeRequestPanel
                result={result}
                busy={semanticChange.isPending}
                error={semanticChange.error instanceof Error ? semanticChange.error.message : null}
                submittedId={submittedRequestId}
                onSubmit={(request) => semanticChange.mutate(request)}
              />
            </div>
          ) : null}
        </div>
      </section>
      <OntologyInventory ontology={ontology.data} />
    </>
  );
}

function StudioAboutPage({
  solution,
  runtime,
}: {
  solution: AgentSolution | StudioSolution;
  runtime: SolutionRuntime | null;
}) {
  return (
    <div className="studio-about">
      <section className="studio-about-card">
        <div className="studio-panel-heading"><div><span>产品与工作区</span><h2>{solution.display_name.zh}</h2></div><code>{solution.solution_id}</code></div>
        <dl>
          <div><dt>Solution version</dt><dd>{solution.solution_version}</dd></div>
          <div><dt>Semantic source</dt><dd>{solution.semantic_source_version}</dd></div>
          <div><dt>Scenario</dt><dd>{solution.scenario_id}</dd></div>
          <div><dt>Workspace</dt><dd>{solution.workspace_id}</dd></div>
          <div><dt>Registry</dt><dd>{solution.persistence}</dd></div>
          <div><dt>Registration</dt><dd>{shortDigest(solution.subject_checksum)}</dd></div>
          <div><dt>Runtime</dt><dd>{runtime ? `${runtime.version} · ${runtime.environment_id}` : "未激活"}</dd></div>
        </dl>
      </section>
      <section className="studio-about-card is-note">
        <div className="studio-panel-heading"><div><span>数据与版本说明</span><h2>当前参考数据的适用范围</h2></div></div>
        <p>当前安装的数据集为构造型参考数据，用于展示从材料整理、语义建模到分析运行的完整流程；它不代表 HKEX 的最终业务口径或生产结论。</p>
        <ul>{solution.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>
    </div>
  );
}

function StudioApplication({
  solution,
  runtime,
  catalog,
  canOperate,
  reviewer,
}: {
  solution: AgentSolution | StudioSolution;
  runtime: SolutionRuntime | null;
  catalog: SolutionCatalog;
  canOperate: boolean;
  reviewer: string;
}) {
  const location = useLocation();
  const page = studioPageFromPath(location.pathname);
  const subpage = studioSubpageFromPath(location.pathname, page);
  const definition = studioPageDefinition(page);
  if (page === "solutions") {
    return (
      <div className="studio-directory-application">
        {!canOperate ? <div className="readonly-role-banner"><strong>只读访问</strong><span>你可以查看解决方案，但新建、修改、删除和发布需要配置人员权限。</span></div> : null}
        <fieldset className="role-gated-content" disabled={!canOperate}>
          <StudioSolutionDirectory
            catalog={catalog}
            selectedSolutionId={solution.solution_id}
            openCreateOnLoad={canOperate && new URLSearchParams(location.search).get("new") === "1"}
          />
        </fieldset>
      </div>
    );
  }
  return (
    <div className="studio-application">
      <StudioNavigation
        activePage={page}
        solutionName={solution.display_name.zh}
        solutionVersion={solution.solution_version}
        activeRuntimeVersion={runtime?.version ?? null}
        solutionId={solution.solution_id}
      />
      <section className="studio-page">
        <header className="studio-page-header">
          <div className="studio-breadcrumbs"><Link to="/ontology-studio/solutions/">解决方案目录</Link><i>/</i><span>{solution.display_name.zh}</span><i>/</i><span>{definition.label}</span></div>
          <div className="studio-page-title">
            <div><h1>{definition.label}</h1><p>{definition.description}</p></div>
            <div className="studio-page-context"><span>方案 v{solution.solution_version}</span><code>{solution.workspace_id}</code></div>
          </div>
          <StudioSubnavigation page={page} activeSubpage={subpage} solutionId={solution.solution_id} />
        </header>
        {!canOperate ? <div className="readonly-role-banner"><strong>只读访问</strong><span>模型和运行状态可查看；新建、修改、审核、发布与激活已锁定。</span></div> : null}
        <fieldset className="role-gated-content studio-page-content" disabled={!canOperate}>
          {page === "overview" || page === "semantic" || page === "data" || page === "quality" || page === "release" || page === "inputs" ? (
            <StudioPackageWorkbench workspaceId={solution.workspace_id} page={page} subpage={subpage} solutionId={solution.solution_id} reviewer={reviewer} />
          ) : null}
        </fieldset>
      </section>
    </div>
  );
}

function GenericSolutionView({ kind, solutionId }: { kind: ProductKind; solutionId: string }) {
  const authSession = useQuery({
    queryKey: ["auth-session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
  });
  const agentCatalog = useQuery({
    queryKey: ["agent-solution-catalog", "selected"],
    queryFn: fetchAgentSolutionCatalog,
  });
  const selectedSolution = agentCatalog.data
    ? [...agentCatalog.data.solutions]
        .filter((item) => item.solution_id === solutionId)
        .sort((left, right) => left.solution_version.localeCompare(right.solution_version, undefined, { numeric: true }))
        .at(-1)
    : undefined;
  const studioCatalog = useQuery({
    queryKey: ["studio-solution-catalog"],
    queryFn: fetchSolutionCatalog,
    enabled: kind === "studio",
  });
  const selectedStudioSolution = studioCatalog.data
    ? [...studioCatalog.data.solutions]
        .filter((item) => item.solution_id === solutionId)
        .sort((left, right) => left.solution_version.localeCompare(right.solution_version, undefined, { numeric: true }))
        .at(-1)
    : undefined;
  const studioRuntime = useQuery({
    queryKey: ["solution-runtime", solutionId, "studio-lineage"],
    queryFn: () => fetchSolutionRuntime(solutionId),
    enabled: kind === "studio" && selectedSolution?.runtime.state === "ACTIVE",
  });
  if (agentCatalog.isPending || (kind === "studio" && (studioCatalog.isPending || (selectedSolution?.runtime.state === "ACTIVE" && studioRuntime.isPending)))) {
    return <main className="state-screen"><span className="state-pulse" /><p>正在核验 selected solution…</p></main>;
  }
  if (agentCatalog.isError || !agentCatalog.data || (kind === "studio" && (studioCatalog.isError || !studioCatalog.data))) {
    return <main className="state-screen state-error"><span className="error-code">SOLUTION UNAVAILABLE</span><h1>无法打开所选 solution</h1><p>Catalog 或 exact runtime 未通过验证。</p></main>;
  }
  const solution = kind === "studio" ? selectedStudioSolution : selectedSolution;
  if (!solution) {
    return <main className="state-screen state-error"><span className="error-code">SOLUTION NOT INSTALLED</span><h1>所选 solution 不在目录中</h1></main>;
  }

  return (
    <div className="product-shell">
      <Header kind={kind} solutionId={solution.solution_id} session={authSession.data ?? null} />
      {kind === "agent" ? (
        <main className="agent-main"><AgentSolutionWorkspace solution={selectedSolution!} /></main>
      ) : (
        <main className="studio-main"><StudioApplication solution={solution} runtime={studioRuntime.data ?? null} catalog={studioCatalog.data!} canOperate={authSession.data?.authenticated === true && authSession.data.role === "operator"} reviewer={authSession.data?.authenticated ? authSession.data.username : "unknown"} /></main>
      )}
      <footer className="product-footer"><span>Atlas semantic products</span><span>{kind === "studio" ? "Ontology Studio" : "Ontology Analytic Agent"}</span></footer>
    </div>
  );
}

function ProductView({ kind }: { kind: ProductKind }) {
  const authSession = useQuery({ queryKey: ["auth-session"], queryFn: fetchAuthSession, staleTime: 60_000 });
  const query = useQuery({
    queryKey: ["product-context"],
    queryFn: fetchProductContext,
  });
  const catalogQuery = useQuery({
    queryKey: ["studio-solution-catalog"],
    queryFn: fetchSolutionCatalog,
    enabled: kind === "studio",
  });

  if (query.isPending) {
    return (
      <main className="state-screen" aria-live="polite">
        <span className="state-pulse" aria-hidden="true" />
        <p>正在核验产品上下文…</p>
      </main>
    );
  }
  if (query.isError) {
    const error = query.error as ProductApiError;
    return (
      <main className="state-screen state-error">
        <span className="error-code">CONTEXT UNAVAILABLE</span>
        <h1>无法确认当前运行语境</h1>
        <p>{error.message}</p>
        <button type="button" onClick={() => query.refetch()}>
          重新检查
        </button>
      </main>
    );
  }

  const context = query.data;
  const labels = phaseLabels[kind];
  return (
    <div className="product-shell">
      <Header kind={kind} solutionId={context.subject.solution_id} session={authSession.data ?? null} />
      <main>
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow-row">
              <span>{labels.eyebrow}</span>
              <span className="active-chip">
                <i aria-hidden="true" /> ACTIVE
              </span>
            </div>
            <p className="scenario-kicker">{context.subject.scenario_name_en}</p>
            <h1>{labels.title}</h1>
            <p className="hero-summary">{labels.summary}</p>
            <div className="hero-identity">
              <span>{context.subject.scenario_name_zh}</span>
              <code>{context.subject.context_id}</code>
            </div>
          </div>
          <SemanticSpine context={context} />
        </section>
        {kind === "studio" ? (
          catalogQuery.isPending ? (
            <section className="catalog-state" aria-live="polite">
              正在核验 solution registration…
            </section>
          ) : catalogQuery.isError ? (
            <section className="catalog-state is-error" role="alert">
              Solution catalog 不可用；Studio 不会用浏览器状态代替后端登记。
            </section>
          ) : (
            <StudioSolutionCatalog
              catalog={catalogQuery.data}
              activeSolutionId={context.subject.solution_id}
              selectedSolutionId={context.subject.solution_id}
            />
          )
        ) : null}
        {kind === "studio" && catalogQuery.data ? (
          <StudioWorkspaceEditor
            workspaceId={
              [...catalogQuery.data.solutions]
                .filter((solution) => solution.solution_id === context.subject.solution_id)
                .sort((left, right) => left.solution_version.localeCompare(right.solution_version, undefined, { numeric: true }))
                .at(-1)?.workspace_id ?? catalogQuery.data.solutions[0].workspace_id
            }
          />
        ) : null}
        <div className="content-grid">
          <ContextFacts context={context} />
          <Limitations context={context} />
        </div>
      </main>
      <footer className="product-footer">
        <span>Atlas semantic products</span>
        <span>{kind === "studio" ? "Ontology Studio" : "Ontology Analytic Agent"}</span>
      </footer>
    </div>
  );
}

export function App() {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const selectedSolution = studioSolutionIdFromPath(location.pathname)
    ?? searchParams.get("solution")
    ?? "ontology.exchange_analytics.adt";
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/ontology-agent/" replace />} />
      <Route path="/ontology-agent/*" element={<GenericSolutionView kind="agent" solutionId={selectedSolution} />} />
      <Route path="/ontology-studio" element={<Navigate to="/ontology-studio/solutions/" replace />} />
      <Route path="/ontology-studio/*" element={<GenericSolutionView kind="studio" solutionId={selectedSolution} />} />
      <Route path="*" element={<Navigate to="/ontology-agent/" replace />} />
    </Routes>
  );
}
