import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { Link, Navigate, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import remarkGfm from "remark-gfm";

import {
  fetchProductContext,
  fetchAuthSession,
  fetchAgentRuntimeStatus,
  fetchAgentSolutionCatalog,
  fetchSolutionCatalog,
  fetchAnalyticConversation,
  fetchSolutionOntology,
  fetchSolutionQuestions,
  fetchSolutionRuntime,
  fetchStudioWorkbench,
  fetchConstructionRuns,
  fetchConstructionJobs,
  fetchConstructionDecision,
  fetchStudioBuildTasks,
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
  enqueueConstructionJob,
  cancelConstructionJob,
  retryConstructionJob,
  saveConstructionReviewDraft,
  reviewConstructionRun,
  registerStudioSource,
  registerStudioSourceBatch,
  installStudioReferenceSourcePack,
  importStudioInstalledSources,
  prepareAgentRuntime,
  validateDraft,
  verifyAgentRuntime,
  ProductApiError,
  type DraftOperationValue,
  type ProductContext,
  type PackageDraftOperation,
  type AgentSolution,
  type SolutionAnalysis,
  type ConstructionDisposition,
  type StudioWorkbench,
  type AgentRuntimeStatus,
  type SolutionRuntime,
  type SolutionCatalog,
  type StudioSourceLibrary,
  type StudioBuildTask,
  type StudioSolution,
  type WorkspaceEditor,
  type AuthSession,
} from "./api";
import { formatDisplayValue } from "./display";
import { LanguageSwitch, LegacyUiLocalizer, useUiLocale } from "./i18n";
import { StudioWorkbenchView, type WorkbenchTab } from "./StudioWorkbench";
import {
  StudioNavigation,
  StudioSubnavigation,
  studioPageDefinition,
  studioBuildRouteFromPath,
  studioBuildReviewHref,
  studioBuildResultHref,
  studioPageFromPath,
  studioPageHref,
  studioSolutionIdFromPath,
  studioSubpageFromPath,
  type StudioPageId,
  type StudioSubpageId,
} from "./StudioNavigation";
import { StudioSolutionDirectory } from "./StudioSolutionDirectory";
import {
  MappingWorkbenchView,
  OntologyGraphEditor,
  RequirementsCatalogView,
  SampleAndEnumView,
  SchemaCatalogView,
  SqlContractCatalogView,
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
      "基于当前已激活的 Runtime Snapshot 查询、分析并追踪证据。",
    companion: "进入 Ontology Studio",
  },
  studio: {
    eyebrow: "ONTOLOGY STUDIO",
    title: "构建和治理业务语义",
    summary:
      "登记来源材料，构建并复核 Ontology Solution，再发布给 Analytic Agent 使用。",
    companion: "进入 Analytic Agent",
  },
} as const;

function shortDigest(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

function SolutionSwitcher({ selectedId, kind, canOperate }: { selectedId: string; kind: ProductKind; canOperate: boolean }) {
  const { name, t } = useUiLocale();
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
      <summary aria-label={t("切换解决方案", "Switch solution")}>
        <span>Solution</span>
        <strong>{selected ? name(selected.display_name) : t("选择解决方案", "Select solution")}</strong>
        <small>{selected ? `v${selected.solution_version}` : ""}</small>
      </summary>
      <div className="solution-switcher-popover">
        <label><span>搜索解决方案</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="名称或 ID" /></label>
        <div className="solution-switcher-list">
          {visible.map((solution) => (
            <a href={destination(solution.solution_id)} className={solution.solution_id === selectedId ? "is-selected" : ""} key={solution.solution_id}>
              <span>{solution.solution_id === selectedId ? "✓" : ""}</span>
              <div><strong>{name(solution.display_name)}</strong><small>{solution.solution_id}</small></div>
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
  directoryHome = false,
  taskCenter = false,
}: {
  kind: ProductKind;
  solutionId: string;
  session: AuthSession | null;
  directoryHome?: boolean;
  taskCenter?: boolean;
}) {
  const { t } = useUiLocale();
  const otherUrl = directoryHome || taskCenter
    ? "/ontology-agent/"
    : kind === "agent"
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
        <LanguageSwitch />
        {session?.authenticated ? <span className={`access-role is-${session.role}`}><i aria-hidden="true" />{session.role === "operator" ? "配置人员" : "只读访问"}<small>{session.username}</small></span> : <span className="access-role is-loading">正在确认权限</span>}
        {directoryHome || taskCenter
          ? <span className="header-directory-context">{taskCenter ? t("任务中心", "Task Center") : t("解决方案目录", "Solution Catalog")}</span>
          : <SolutionSwitcher selectedId={solutionId} kind={kind} canOperate={session?.authenticated === true && session.role === "operator"} />}
        <a className="product-switch" href={otherUrl}>
          {phaseLabels[kind].companion}
          <span aria-hidden="true">↗</span>
        </a>
      </div>
    </header>
  );
}

const executionLabels: Record<StudioBuildTask["execution_status"], string> = {
  QUEUED: "等待执行",
  RUNNING: "正在构建",
  COMMITTING: "正在保存结果",
  CANCEL_REQUESTED: "正在取消",
  SUCCEEDED: "执行已结束",
  FAILED: "执行失败",
  CANCELLED: "已取消",
  STALE: "输入已过期",
};

const outcomeLabels: Record<NonNullable<StudioBuildTask["result_outcome"]>, string> = {
  TECHNICAL_FAILURE: "技术失败",
  BLOCKED: "产出被阻断",
  REVIEW_READY_WITH_WARNINGS: "可复核（有警告）",
  REVIEW_READY: "可复核",
  NO_APPLICABLE_CHANGES: "无适用变更",
};

const taskProgressLabels: Record<string, string> = {
  JOB_QUEUED: "等待执行",
  SOURCE_VERSIONS_BOUND: "正在锁定来源版本",
  BUILDER_RUNNING: "Builder 正在构建候选",
  MODEL_GATEWAY_RETRY_PENDING: "模型服务波动，准备从检查点继续",
  REVIEWER_RUNNING: "正在执行机器复核",
  IMMUTABLE_RUN_COMMITTING: "正在保存不可变结果",
  IMMUTABLE_RUN_COMMITTED: "构建结果已保存",
  CANCEL_REQUESTED: "正在安全取消",
  CANCELLED_BY_USER: "已取消",
  CONSTRUCTION_FAILED: "构建执行失败",
  MODEL_GATEWAY_UNAVAILABLE: "模型服务持续不可用",
};

const agentActivityLabels: Record<NonNullable<StudioBuildTask["activity"]>["activity_stage"], string> = {
  PREPARING: "准备构建上下文",
  READING_SOURCES: "读取与核对来源证据",
  MODELING: "生成并修订候选语义",
  VALIDATING: "验证候选包并修复问题",
  FINALIZING: "封存候选包",
};

function taskDestination(task: StudioBuildTask): string {
  if (task.destination.type === "RESULT" && task.run_id && task.decision_id) {
    return studioBuildResultHref(task.solution_id, task.run_id, task.decision_id);
  }
  if (task.destination.type === "REVIEW" && task.run_id) {
    return studioBuildReviewHref(task.solution_id, task.run_id);
  }
  if (task.destination.type === "SOLUTION") return studioPageHref("overview", task.solution_id);
  return `/ontology-studio/tasks/${encodeURIComponent(task.task_id)}/`;
}

function StudioTaskCenter({ session }: { session: AuthSession | null }) {
  const location = useLocation();
  const taskId = location.pathname.match(/\/ontology-studio\/tasks\/([^/]+)/)?.[1];
  const [filter, setFilter] = useState<"ATTENTION" | "ACTIVE" | "DONE" | "ALL">("ATTENTION");
  const query = useQuery({
    queryKey: ["studio-build-tasks"],
    queryFn: fetchStudioBuildTasks,
    refetchInterval: (current) => {
      const active = current.state.data?.tasks.some((task) => ["QUEUED", "RUNNING", "COMMITTING", "CANCEL_REQUESTED"].includes(task.execution_status));
      return active ? (document.hidden ? 10_000 : 2_000) : 15_000;
    },
  });
  const tasks = query.data?.tasks ?? [];
  const visible = tasks.filter((task) => {
    if (filter === "ALL") return true;
    if (filter === "ACTIVE") return ["QUEUED", "RUNNING", "COMMITTING", "CANCEL_REQUESTED"].includes(task.execution_status);
    if (filter === "DONE") return task.review_status === "APPLIED" || task.result_outcome === "NO_APPLICABLE_CHANGES";
    return task.review_status === "NEEDS_REVIEW" || task.result_outcome === "BLOCKED" || task.result_outcome === "TECHNICAL_FAILURE";
  });
  const selected = tasks.find((task) => task.task_id === taskId) ?? null;
  if (query.isPending) return <main className="state-screen"><span className="state-pulse" /><p>正在读取任务中心…</p></main>;
  if (query.isError) return <main className="state-screen state-error"><h1>无法读取任务中心</h1><button type="button" onClick={() => query.refetch()}>重新检查</button></main>;
  return (
    <div className="product-shell">
      <Header kind="studio" solutionId={selected?.solution_id ?? "ontology.exchange_analytics.adt"} session={session} taskCenter />
      <main className="studio-task-main">
        <header className="task-center-heading">
          <div><span>TASK CENTER</span><h1>任务中心</h1><p>跨解决方案查看构建进度、业务产出和待处理事项。</p></div>
          <Link className="secondary-action" to="/ontology-studio/solutions/">返回解决方案目录</Link>
        </header>
        <nav className="task-center-filters" aria-label="任务筛选">
          {(["ATTENTION", "ACTIVE", "DONE", "ALL"] as const).map((value) => <button type="button" className={filter === value ? "is-active" : ""} key={value} onClick={() => setFilter(value)}>{value === "ATTENTION" ? "需处理" : value === "ACTIVE" ? "进行中" : value === "DONE" ? "已完成" : "全部"}<b>{tasks.filter((task) => value === "ALL" || (value === "ACTIVE" && ["QUEUED", "RUNNING", "COMMITTING", "CANCEL_REQUESTED"].includes(task.execution_status)) || (value === "DONE" && (task.review_status === "APPLIED" || task.result_outcome === "NO_APPLICABLE_CHANGES")) || (value === "ATTENTION" && (task.review_status === "NEEDS_REVIEW" || task.result_outcome === "BLOCKED" || task.result_outcome === "TECHNICAL_FAILURE"))).length}</b></button>)}
        </nav>
        <div className={`task-center-layout ${selected ? "has-detail" : ""}`}>
          <section className="task-table" aria-label="任务列表">
            <header><span>解决方案 / 任务</span><span>执行</span><span>产出</span><span>进度</span><span /></header>
            {visible.length ? visible.map((task) => <article key={task.task_id} className={selected?.task_id === task.task_id ? "is-selected" : ""}>
              <div><strong>{task.solution_name}</strong><code>{task.task_id}</code><small>{new Date(task.updated_at).toLocaleString("zh-CN", { hour12: false })}</small></div>
              <span className={`task-status is-${task.execution_status.toLowerCase()}`}>{executionLabels[task.execution_status]}</span>
              <span className={`task-outcome is-${(task.result_outcome ?? "pending").toLowerCase()}`}>{task.result_outcome ? outcomeLabels[task.result_outcome] : "尚未形成"}</span>
              <div className="task-progress"><span><i style={{ width: `${Math.min(100, Math.round(task.completed_stages / task.total_stages * 100))}%` }} /></span><small>{task.activity ? agentActivityLabels[task.activity.activity_stage] : taskProgressLabels[task.progress_message] ?? `${task.completed_stages} / ${task.total_stages}`}</small></div>
              <Link className="row-action" to={taskDestination(task)}>{task.review_status === "NEEDS_REVIEW" ? "进入复核" : task.destination.type === "RESULT" ? "查看结果" : "查看任务"}</Link>
            </article>) : <div className="task-empty"><strong>当前筛选下没有任务</strong><p>从任一解决方案的“构建与复核”发起构建后，任务会出现在这里。</p></div>}
          </section>
          {selected ? <aside className="task-detail-panel">
            <Link to="/ontology-studio/tasks/" aria-label="关闭任务详情">×</Link>
            <span>TASK DETAIL</span><h2>{selected.solution_name}</h2><code>{selected.task_id}</code>
            <dl><div><dt>执行状态</dt><dd>{executionLabels[selected.execution_status]}</dd></div><div><dt>业务结果</dt><dd>{selected.result_outcome ? outcomeLabels[selected.result_outcome] : "尚未形成"}</dd></div><div><dt>当前阶段</dt><dd>{selected.activity ? agentActivityLabels[selected.activity.activity_stage] : taskProgressLabels[selected.progress_message] ?? selected.progress_message}</dd></div><div><dt>候选</dt><dd>{selected.activity && selected.execution_status === "RUNNING" ? `${selected.activity.candidate_count} 项草稿候选` : `${selected.candidate_count} 项，其中 ${selected.compilable_count} 项可应用`}</dd></div>{selected.activity ? <><div><dt>模型轮次</dt><dd>{selected.activity.model_turn_count}</dd></div><div><dt>工具调用</dt><dd>{selected.activity.tool_call_count}</dd></div></> : null}<div><dt>阻断项</dt><dd>{selected.blocker_count}</dd></div><div><dt>输出语言</dt><dd>{selected.authoring_language === "zh" ? "中文" : selected.authoring_language === "en" ? "英文" : "尚未锁定"}</dd></div></dl>
            <Link className="primary-action" to={taskDestination(selected)}>{selected.review_status === "NEEDS_REVIEW" ? "进入人工复核" : selected.destination.type === "RESULT" ? "查看复核结果" : "打开任务所在方案"}</Link>
          </aside> : null}
        </div>
      </main>
    </div>
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
        工作区暂时不可用，请稍后重试。
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
  solutionId,
}: {
  workbench: StudioWorkbench;
  runtime: AgentRuntimeStatus | null;
  sourceLibrary: StudioSourceLibrary | null;
  solutionId: string;
}) {
  const validation = workbench.workspace.validation.status;
  const release = workbench.workspace.last_published;
  const active = runtime?.active;
  const packageGroups = [
    {
      label: "业务模型",
      count: workbench.package.entities.length
        + workbench.package.properties.length
        + workbench.package.relationships.length,
      detail: `${workbench.package.entities.length} 对象 · ${workbench.package.properties.length} 属性 · ${workbench.package.relationships.length} 关系`,
      page: "semantic" as const,
      subpage: "model" as const,
    },
    {
      label: "指标与维度",
      count: workbench.package.metrics.length
        + workbench.package.dimensions.length
        + workbench.package.rules.length,
      detail: `${workbench.package.metrics.length} 指标 · ${workbench.package.dimensions.length} 维度 · ${workbench.package.rules.length} 规则`,
      page: "semantic" as const,
      subpage: "metrics" as const,
    },
    {
      label: "数据语义",
      count: workbench.package.data_sources.length
        + workbench.package.bindings.length
        + workbench.package.joins.length,
      detail: `${workbench.package.data_sources.length} 数据源 · ${workbench.package.bindings.length} 映射 · ${workbench.package.joins.length} 关联`,
      page: "data" as const,
      subpage: "mappings" as const,
    },
    {
      label: "分析能力",
      count: workbench.package.analysis_patterns.length
        + workbench.package.questions.length
        + workbench.package.policies.length,
      detail: `${workbench.package.analysis_patterns.length} 模式 · ${workbench.package.questions.length} 问题 · ${workbench.package.policies.length} 策略`,
      page: "semantic" as const,
      subpage: "experience" as const,
    },
    {
      label: "证据与假设",
      count: workbench.package.sources.length + workbench.package.decisions.length,
      detail: `${workbench.package.sources.length} 来源 · ${workbench.package.decisions.length} 决策/假设`,
      page: "inputs" as const,
      subpage: "sources" as const,
    },
  ];
  const packageAssets = packageGroups.reduce((total, group) => total + group.count, 0);
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
  const hasInputs = Boolean(sourceLibrary?.current.length || installedAssets.length);
  const hasDomainAssets = packageAssets > 0;
  const nextPage: StudioPageId = !hasInputs
    ? "inputs"
    : !hasDomainAssets
      ? "construction"
      : validation !== "PASS"
        ? "quality"
        : release === null
          ? "quality"
          : active?.release.version !== release.version
            ? "quality"
            : "semantic";
  const nextSubpage: StudioSubpageId = !hasInputs
    ? "sources"
    : !hasDomainAssets
      ? "runs"
      : validation !== "PASS"
        ? "validation"
        : release === null
          ? "versions"
          : active?.release.version !== release.version
            ? "delivery"
            : "model";
  const nextCopy = !hasInputs
    ? "登记第一份来源材料。"
    : !hasDomainAssets
      ? "使用已登记材料生成待复核候选。"
      : validation !== "PASS"
        ? "验证当前 Draft 并处理阻断问题。"
        : release === null
          ? "创建第一个不可变 Release。"
          : active?.release.version !== release.version
            ? "准备并激活新的 Runtime Snapshot。"
            : "当前运行版本已同步，可继续维护语义模型。";

  const steps: Array<{ page: StudioPageId; subpage?: StudioSubpageId; number: string; title: string; copy: string }> = [
    { page: "inputs", number: "01", title: "登记输入", copy: "维护需求、材料和 exact version" },
    { page: "construction", number: "02", title: "构建与复核", copy: "生成候选、机器复核并人工处置" },
    { page: "semantic", number: "03", title: "维护语义", copy: "管理对象、关系、指标和分析能力" },
    { page: "data", number: "04", title: "绑定数据", copy: "维护 Schema、映射、Join 和 SQL 合同" },
    { page: "quality", number: "05", title: "验证与发布", copy: "检查、审批、激活与回滚" },
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
      <section className="studio-package-inventory" aria-labelledby="package-inventory-title">
        <header>
          <div><span>ONTOLOGY PACKAGE</span><h2 id="package-inventory-title">Package 内容</h2></div>
          <strong>{packageAssets} 项已登记资产</strong>
        </header>
        <div className="studio-asset-summary">
          {packageGroups.map((group) => (
            <Link key={group.label} to={studioPageHref(group.page, solutionId, group.subpage)}>
              <span>{group.label}</span><strong>{group.count}</strong><small>{group.detail}</small><i aria-hidden="true">→</i>
            </Link>
          ))}
        </div>
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
  requestedRunId = null,
  requestedDecisionId = null,
  openMaterialIntake = false,
  readOnly = false,
}: {
  workspaceId: string;
  page: StudioPageId;
  subpage: StudioSubpageId;
  solutionId: string;
  reviewer: string;
  requestedRunId?: string | null;
  requestedDecisionId?: string | null;
  openMaterialIntake?: boolean;
  readOnly?: boolean;
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
  const activeReviewRunId = requestedRunId
    ?? constructionRunsQuery.data?.runs.find((item) => item.decision === null)?.run.run_id
    ?? null;
  const reviewDraftQuery = useQuery({
    queryKey: ["studio-construction-review-draft", workspaceId, activeReviewRunId],
    queryFn: () => fetchConstructionReviewDraft(workspaceId, activeReviewRunId!),
    enabled: queryScope.reviewDraft && Boolean(activeReviewRunId) && !requestedDecisionId,
  });
  const constructionDecisionQuery = useQuery({
    queryKey: ["studio-construction-decision", workspaceId, activeReviewRunId, requestedDecisionId],
    queryFn: () => fetchConstructionDecision(workspaceId, activeReviewRunId!, requestedDecisionId!),
    enabled: queryScope.reviewDraft && Boolean(activeReviewRunId) && Boolean(requestedDecisionId),
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
  const registerSourceBatch = useMutation({
    mutationFn: async ({ items, idempotencyKey }: {
      items: Parameters<typeof registerStudioSourceBatch>[2];
      idempotencyKey: string;
    }) => registerStudioSourceBatch(workspaceId, idempotencyKey, items),
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
  const startConstruction = useMutation({
    mutationFn: async ({ sourceVersionIds, authoringLanguage }: { sourceVersionIds: string[]; authoringLanguage: "en" | "zh" }) => {
      if (!query.data) throw new ProductApiError("Studio workbench 尚未就绪。", 409);
      return enqueueConstructionJob(workspaceId, query.data.workspace.revision, sourceVersionIds, authoringLanguage);
    },
    onSuccess: async () => {
      await Promise.all([
        constructionJobsQuery.refetch(),
        query.refetch(),
      ]);
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
    return <section className="catalog-state is-error" role="alert">工作区读取失败，请刷新后重试。</section>;
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
            solutionId={solutionId}
          />;
  } else if (page === "inputs" && subpage === "requirements") {
    content = <RequirementsCatalogView solutionId={solutionId} ontologyPackage={query.data.package} authoring={query.data.authoring} />;
  } else if (page === "inputs" && subpage === "sources") {
    content = <SourceLibraryView
      ontologyPackage={query.data.package}
      intake={query.data.intake}
      library={sourceLibraryQuery.data ?? null}
      busy={registerSourceBatch.isPending || registerSource.isPending || installReferencePack.isPending || importInstalledSources.isPending}
      error={(registerSourceBatch.error ?? registerSource.error ?? installReferencePack.error ?? importInstalledSources.error ?? sourceLibraryQuery.error) instanceof Error
        ? String((registerSourceBatch.error ?? registerSource.error ?? installReferencePack.error ?? importInstalledSources.error ?? sourceLibraryQuery.error)?.message)
        : null}
      onUpload={async (input) => { await registerSource.mutateAsync(input); }}
      onUploadBatch={async (items, idempotencyKey) => registerSourceBatch.mutateAsync({ items, idempotencyKey })}
      onPreview={(sourceVersionId) => fetchStudioSourcePreview(workspaceId, sourceVersionId)}
      onInstallReferencePack={async () => { await installReferencePack.mutateAsync(); }}
      onImportInstalledSources={async () => { await importInstalledSources.mutateAsync(); }}
      openIntakeOnLoad={openMaterialIntake}
      readOnly={readOnly}
    />;
  } else if (page === "construction" && subpage === "runs") {
    content = <ConstructionRunsView
        runs={constructionRunsQuery.data ?? null}
        jobs={constructionJobsQuery.data ?? null}
        sources={sourceLibraryQuery.data?.current ?? []}
        authoringLanguage={query.data.workspace.authoring_language ?? query.data.package.authoring_policy?.authoring_language ?? null}
        currentRevision={query.data.workspace.revision}
        busy={startConstruction.isPending || cancelConstruction.isPending || retryConstruction.isPending}
        error={(startConstruction.error ?? cancelConstruction.error ?? retryConstruction.error ?? constructionJobsQuery.error ?? constructionRunsQuery.error) instanceof Error ? String((startConstruction.error ?? cancelConstruction.error ?? retryConstruction.error ?? constructionJobsQuery.error ?? constructionRunsQuery.error)?.message) : null}
        onStart={(sourceVersionIds, authoringLanguage) => startConstruction.mutate({ sourceVersionIds, authoringLanguage })}
        onCancel={(jobId) => cancelConstruction.mutate(jobId)}
        onRetry={(jobId) => retryConstruction.mutate(jobId)}
        readOnly={readOnly}
      />;
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
      readOnly={readOnly}
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
      readOnly={readOnly}
    />;
  } else if (page === "semantic" && subpage === "graph") {
    const pendingCandidateRun = constructionRunsQuery.data?.runs.find((item) => item.decision === null)?.run;
    content = <OntologyGraphEditor
      ontologyPackage={query.data.package}
      candidates={pendingCandidateRun?.candidates ?? []}
      reviewHref={studioPageHref("construction", solutionId, "review")}
      createEntityHref={semanticAssetHref(solutionId, "entities")}
      createRelationshipHref={semanticAssetHref(solutionId, "relationships")}
      editAssetHref={(collection, objectId) => semanticAssetHref(solutionId, collection, objectId)}
      readOnly={readOnly}
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
      readOnly={readOnly}
    />;
  } else if (page === "quality" && subpage === "policies") {
    content = <SemanticAssetCatalog
      mode="policies"
      solutionId={solutionId}
      ontologyPackage={query.data.package}
      busy={author.isPending || authorAndValidate.isPending}
      error={(author.error ?? authorAndValidate.error) instanceof Error ? String((author.error ?? authorAndValidate.error)?.message) : null}
      onApply={applyOperation}
      onApplyAndValidate={applyAndValidateOperation}
      onConfirm={applyOperation}
      onDeprecate={applyOperation}
      assetChecksums={query.data.asset_checksums}
      reviewer={reviewer}
      readOnly={readOnly}
    />;
  } else if (page === "construction" && subpage === "review") content = <ConstructionReviewCenter
    runs={constructionRunsQuery.data ?? null}
    reviewDraft={reviewDraftQuery.data ?? null}
    decision={constructionDecisionQuery.data ?? null}
    requestedRunId={requestedRunId}
    requestedDecisionId={requestedDecisionId}
    solutionId={solutionId}
    currentRevision={query.data.workspace.revision}
    busy={reviewConstruction.isPending || saveReviewDraft.isPending}
    error={(reviewConstruction.error ?? saveReviewDraft.error ?? constructionDecisionQuery.error ?? reviewDraftQuery.error ?? constructionRunsQuery.error) instanceof Error ? String((reviewConstruction.error ?? saveReviewDraft.error ?? constructionDecisionQuery.error ?? reviewDraftQuery.error ?? constructionRunsQuery.error)?.message) : null}
    onSave={(runId, dispositions) => saveReviewDraft.mutateAsync({ runId, dispositions })}
    onReview={(runId, dispositions, reviewBatchChecksum) => reviewConstruction.mutateAsync({ runId, dispositions, reviewBatchChecksum })}
    readOnly={readOnly}
  />;
  else if (page === "data" && subpage === "schemas") content = <SchemaCatalogView
    ontologyPackage={query.data.package}
    busy={author.isPending}
    error={author.error instanceof Error ? author.error.message : null}
    onApply={applyOperation}
    readOnly={readOnly}
  />;
  else if (page === "data" && subpage === "mappings") content = <MappingWorkbenchView
    ontologyPackage={query.data.package}
    busy={author.isPending}
    error={author.error instanceof Error ? author.error.message : null}
    onApply={applyOperation}
    readOnly={readOnly}
  />;
  else if (page === "data" && subpage === "sql") content = <SqlContractCatalogView
    ontologyPackage={query.data.package}
    busy={author.isPending}
    error={author.error instanceof Error ? author.error.message : null}
    onApply={applyOperation}
    readOnly={readOnly}
  />;
  else if (page === "data" && subpage === "samples") content = <SampleAndEnumView
    ontologyPackage={query.data.package}
    intake={query.data.intake}
    busy={author.isPending}
    error={author.error instanceof Error ? author.error.message : null}
    onApply={applyOperation}
    readOnly={readOnly}
  />;
  const activeTab: WorkbenchTab | undefined = page === "quality" && subpage === "validation"
        ? "validate"
        : page === "quality" && subpage === "changes"
          ? "evidence"
          : page === "quality" && subpage === "delivery"
            ? "release"
            : undefined;
  if (activeTab) content = <StudioWorkbenchView activeTab={activeTab} navigation="hidden" presentation="page" workbench={query.data} readOnly={readOnly} authoring={{
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
  if (page === "quality" && subpage === "versions") {
    content = <section className="release-version-page">
      <header className="object-page-heading"><div><span>VERSION & APPROVAL</span><h2>版本与审批</h2><p>Draft 修订、精确验证和不可变发布记录在这里汇合；运行准备与激活在“交付与运行”中操作。</p></div><div className="object-page-counts"><strong>{query.data.revisions.length} 个 Draft 修订</strong><span>{query.data.workspace.last_published ? `已发布 v${query.data.workspace.last_published.version}` : "尚未发布"}</span></div></header>
      <div className="release-version-layout"><section><h3>不可变 Draft 修订</h3>{[...query.data.revisions].reverse().map((revision, index) => <article key={`${String(revision.revision)}:${String(revision.record_checksum)}`}><span>r{String(revision.revision)}</span><div><strong>v{String(revision.target_version)}</strong><small>{String(revision.recorded_at)}</small></div><code>{shortDigest(String(revision.draft_checksum))}</code><em>{index === 0 ? "CURRENT" : "HISTORICAL"}</em></article>)}</section><aside><span>LATEST PUBLICATION</span><h3>{query.data.workspace.last_published ? `v${query.data.workspace.last_published.version}` : "尚未发布"}</h3><p>{query.data.workspace.last_published ? "该语义 Release 已冻结；它不会自动成为 Agent Active。" : "当前 Draft 通过精确验证后，才可以发布为不可变语义 Release。"}</p><code>{query.data.workspace.last_published?.checksum ?? query.data.workspace.draft_checksum}</code><Link to={studioPageHref("quality", solutionId, "delivery")}>前往交付与运行 →</Link></aside></div>
    </section>;
  }
  const showDraftControls = !readOnly && page === "quality" && ["validation", "versions"].includes(subpage);
  return <>{showDraftControls ? controls : null}{content}</>;
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

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function AgentQueryResults({ result }: { result: SolutionAnalysis }) {
  const { locale, t } = useUiLocale();
  const rawQueries = Array.isArray(result.facts.queries) ? result.facts.queries : [];
  const queries = rawQueries.map(objectValue).filter((item): item is Record<string, unknown> => item !== null);
  if (queries.length === 0) return null;
  return (
    <section className="agent-query-results" aria-label={t("本次分析结果", "Analysis results")}>
      {queries.map((query, index) => {
        const period = objectValue(query.period);
        const evidence = objectValue(query.evidence);
        const rows = Array.isArray(query.rows) ? query.rows : [];
        const localizedMetricName = locale === "zh" ? query.metric_name_zh : query.metric_name_en;
        const metricName = typeof localizedMetricName === "string"
          ? localizedMetricName
          : typeof query.metric_name === "string"
            ? query.metric_name
            : t(`指标 ${index + 1}`, `Metric ${index + 1}`);
        const metricCode = typeof query.metric_code === "string" ? query.metric_code : "METRIC";
        const queryHash = typeof evidence?.query_hash === "string" ? evidence.query_hash : null;
        return (
          <article key={`${metricCode}:${index}`}>
            <header>
              <div><span>{metricCode}</span><h3>{metricName}</h3></div>
              <code>{typeof query.unit === "string" ? query.unit : ""}</code>
            </header>
            <FactValue value={rows} />
            <details>
              <summary>{t("查看计算口径与证据", "View calculation semantics and evidence")}</summary>
              <dl>
                <div><dt>Ontology metric</dt><dd><code>{String(query.metric_id ?? "—")}</code></dd></div>
                <div><dt>{t("分析期间", "Analysis period")}</dt><dd>{period ? `${String(period.start ?? "—")} — ${String(period.end ?? "—")}` : "—"}</dd></div>
                <div><dt>{t("维度", "Dimensions")}</dt><dd>{stringArray(query.dimensions).join(" · ") || t("整体", "Overall")}</dd></div>
                <div><dt>{t("来源", "Sources")}</dt><dd>{stringArray(evidence?.sources).join(" · ") || "—"}</dd></div>
                <div><dt>{t("口径决策", "Decisions")}</dt><dd>{stringArray(evidence?.decisions).join(" · ") || "—"}</dd></div>
                <div><dt>Query hash</dt><dd><code>{queryHash ? shortDigest(queryHash) : "—"}</code></dd></div>
              </dl>
            </details>
          </article>
        );
      })}
    </section>
  );
}

export function AgentSolutionWorkspace({ solution }: { solution: AgentSolution }) {
  const { locale, name, t } = useUiLocale();
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
  const createConversationId = () => {
    const randomUuid = globalThis.crypto?.randomUUID?.().replaceAll("-", "").toLowerCase();
    if (randomUuid && /^[0-9a-f]{32}$/.test(randomUuid)) return `conversation.${randomUuid}`;
    const bytes = new Uint8Array(16);
    if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes);
    else for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
    return `conversation.${Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")}`;
  };
  const conversationStorageKey = `atlas-agent-conversation:${solution.solution_id}`;
  const [conversationId, setConversationId] = useState(() => {
    const stored = globalThis.sessionStorage?.getItem(conversationStorageKey);
    return stored && /^conversation\.[0-9a-f]{32}$/.test(stored) ? stored : createConversationId();
  });
  const [pendingQuestion, setPendingQuestion] = useState("");
  const conversation = useQuery({
    queryKey: ["analytic-conversation", solution.solution_id, conversationId],
    queryFn: () => fetchAnalyticConversation(solution.solution_id, conversationId),
  });
  const selectedQuestionCase = questions.data?.cases.find((item) => item.case_id === selectedQuestionCaseId);
  const exactQuestionCaseId = selectedQuestionCase?.question === question.trim()
    ? selectedQuestionCase.case_id
    : undefined;
  const analysis = useMutation({
    mutationFn: ({ submitted, questionCaseId }: { submitted: string; questionCaseId?: string }) => analyzeSolution(
      solution.solution_id,
      submitted,
      role || runtime.data?.default_role || "",
      questionCaseId,
      conversationId,
    ),
    onSuccess: (payload, variables) => {
      queryClient.setQueryData(
        ["analytic-conversation", solution.solution_id, conversationId],
        (current: Awaited<ReturnType<typeof fetchAnalyticConversation>> | undefined) => {
          const priorTurns = current?.turns ?? [];
          const nextTurn = {
              turn_id: payload.turn_id!,
              turn_index: payload.turn_index!,
              question: variables.submitted,
              status: payload.status,
              completed_at: new Date().toISOString(),
              analysis: payload,
          };
          return {
            contract: "analytic-conversation-transcript/v1" as const,
            conversation_id: conversationId,
            solution_id: solution.solution_id,
            turns: priorTurns.some((turn) => turn.turn_id === nextTurn.turn_id)
              ? priorTurns
              : [...priorTurns, nextTurn].sort((left, right) => left.turn_index - right.turn_index),
          };
        },
      );
      setPendingQuestion("");
    },
  });

  useEffect(() => {
    const first = questions.data?.cases[0];
    setQuestion(first?.question ?? "");
    setSelectedQuestionCaseId(first?.case_id ?? null);
  }, [solution.solution_id, questions.data?.family_id]);

  useEffect(() => {
    if (runtime.data) {
      setRole(runtime.data.default_role);
    }
  }, [runtime.data]);

  useEffect(() => {
    globalThis.sessionStorage?.setItem(conversationStorageKey, conversationId);
  }, [conversationId, conversationStorageKey]);

  if (questions.isPending || runtime.isPending || ontology.isPending) {
    return <section className="catalog-state">正在加载分析语境…</section>;
  }
  if (questions.isError || runtime.isError || ontology.isError || !questions.data || !runtime.data || !ontology.data) {
    return <section className="catalog-state is-error" role="alert">当前解决方案尚未激活，无法开始分析。</section>;
  }

  const registeredDates = questions.data.cases.flatMap((item) => item.question.match(/20\d{2}-\d{2}-\d{2}/g) ?? []).sort();
  const samplePeriod = registeredDates.length > 0
    ? `${registeredDates[0]} — ${registeredDates[registeredDates.length - 1]}`
    : "已激活样例数据";
  const runAnalysis = () => {
    const submitted = question.trim();
    if (!submitted || analysis.isPending) return;
    const questionCaseId = exactQuestionCaseId;
    setPendingQuestion(submitted);
    setQuestion("");
    setSelectedQuestionCaseId(null);
    analysis.mutate({ submitted, questionCaseId });
  };
  const modelLabel = (result: SolutionAnalysis) => result.llm.status === "GROUNDED"
    ? "DeepAgent · Qwen 3.8 Max"
    : result.llm.status === "FALLBACK"
      ? "DeepAgent fallback"
      : "Ontology runtime";
  const startNewConversation = () => {
    const nextConversationId = createConversationId();
    globalThis.sessionStorage?.setItem(conversationStorageKey, nextConversationId);
    queryClient.setQueryData(
      ["analytic-conversation", solution.solution_id, nextConversationId],
      {
        contract: "analytic-conversation-transcript/v1",
        conversation_id: nextConversationId,
        solution_id: solution.solution_id,
        turns: [],
      },
    );
    setConversationId(nextConversationId);
    setPendingQuestion("");
    analysis.reset();
  };
  const turns = conversation.data?.turns ?? [];

  return (
    <section className="agent-console">
      <header className="agent-console-header">
        <div>
          <span className="agent-console-kicker">ONTOLOGY ANALYTIC AGENT</span>
          <h1>{name(solution.display_name)}</h1>
          <p>{locale === "en" ? solution.solution_id : solution.display_name.en}</p>
        </div>
        <div className="agent-context-strip" aria-label={t("当前分析语境", "Current analysis context")}>
          <div title={`Ontology: v${ontology.data.version}`}><span className="visually-hidden">Ontology</span><strong><span>v{ontology.data.version}</span></strong></div>
          <div title={`${t("数据期间", "Data period")}: ${samplePeriod}`}><span className="visually-hidden">{t("数据期间", "Data period")}</span><strong><span>{samplePeriod}</span></strong></div>
          <div title="Runtime: Active"><span className="visually-hidden">Runtime</span><strong><i /><span>Active</span></strong></div>
          <label><span className="visually-hidden">{t("分析角色", "Analysis role")}</span><select aria-label={t("分析角色", "Analysis role")} value={role || runtime.data.default_role} onChange={(event) => setRole(event.target.value)}>
            {runtime.data.roles.filter((item) => item.access === "ALLOWED").map((item) => (
              <option key={item.role_id} value={item.role_id}>{name(item.name)}</option>
            ))}
          </select></label>
        </div>
      </header>

      <div className="agent-console-layout">
        <aside className="agent-starters" aria-label={t("示例问题", "Suggested questions")}>
          <header><h2>{t("示例问题", "Suggested questions")}</h2><span>{questions.data.cases.length}</span></header>
          <div>
            {questions.data.cases.map((item, index) => (
              <button
                type="button"
                key={item.case_id}
                className={exactQuestionCaseId === item.case_id ? "is-selected" : undefined}
                onClick={() => {
                  setQuestion(item.question);
                  setSelectedQuestionCaseId(item.case_id);
                }}
              ><span>{String(index + 1).padStart(2, "0")}</span>{item.question}</button>
            ))}
          </div>
        </aside>

        <section className="agent-conversation" aria-live="polite">
          <header className="agent-conversation-toolbar">
            <div>
              <strong>{t("当前对话", "Current conversation")}</strong>
              <span>{t(`${turns.length} 轮`, `${turns.length} turn${turns.length === 1 ? "" : "s"}`)}</span>
            </div>
            <button type="button" onClick={startNewConversation}>{t("新建对话", "New conversation")}</button>
          </header>
          {conversation.isPending ? (
            <article className="agent-message is-assistant is-loading"><span>Agent</span><p>{t("正在恢复当前对话…", "Restoring this conversation…")}</p></article>
          ) : null}
          {conversation.isError ? (
            <article className="agent-message is-assistant is-error"><span>Agent</span><p>{t("当前对话无法恢复。你可以新建对话后继续。", "This conversation could not be restored. Start a new conversation to continue.")}</p></article>
          ) : null}
          {!conversation.isPending && !conversation.isError && turns.length === 0 && !pendingQuestion && !analysis.isPending ? (
            <div className="agent-empty-state"><h2>{t("询问 Cash Trading 数据", "Ask about Cash Trading data")}</h2><p>{t("可以直接输入问题，或从左侧选择一个示例。", "Enter a question directly or choose a suggested question on the left.")}</p></div>
          ) : null}
          {turns.map((turn) => (
            <div className="agent-turn" key={turn.turn_id}>
              <article className="agent-message is-user"><span>{t("你", "You")}</span><p data-no-ui-translate>{turn.question}</p></article>
              {turn.analysis ? (
                <article className={`agent-message is-assistant is-${turn.analysis.status.toLowerCase()}`}>
                  <div className="agent-message-heading"><span>Agent</span><small>{modelLabel(turn.analysis)}</small></div>
                  <div className="agent-answer-copy" data-no-ui-translate>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.analysis.answer}</ReactMarkdown>
                  </div>
                  {turn.analysis.status === "ANSWERED" ? <AgentQueryResults result={turn.analysis} /> : null}
                  {turn.analysis.boundary_code ? <code className="agent-boundary-code">{turn.analysis.boundary_code}</code> : null}
                  {turn.analysis.status === "ANSWERED" ? (
                    <details className="agent-run-identity"><summary>{t("本次运行信息", "Run details")}</summary><dl>
                      <div><dt>Package</dt><dd><code>{ontology.data.package_id}@{ontology.data.version}</code></dd></div>
                      <div><dt>Snapshot</dt><dd><code>{turn.analysis.snapshot_checksum ? shortDigest(turn.analysis.snapshot_checksum) : "—"}</code></dd></div>
                      <div><dt>Execution</dt><dd><code>{turn.analysis.execution_id ?? "—"}</code></dd></div>
                      <div><dt>Model</dt><dd>{modelLabel(turn.analysis)}</dd></div>
                    </dl></details>
                  ) : null}
                </article>
              ) : (
                <article className="agent-message is-assistant is-failed"><span>Agent</span><p>{t("这条早期回答无法恢复。", "This earlier response could not be restored.")}</p></article>
              )}
            </div>
          ))}
          {pendingQuestion ? <article className="agent-message is-user"><span>{t("你", "You")}</span><p data-no-ui-translate>{pendingQuestion}</p></article> : null}
          {analysis.isPending ? <article className="agent-message is-assistant is-loading"><span>Agent</span><p>{t("正在分析 Ontology 与样例数据…", "Analyzing the ontology and sample data…")}</p></article> : null}
          {analysis.isError ? <article className="agent-message is-assistant is-error"><span>Agent</span><p data-no-ui-translate>{(analysis.error as Error).message}</p></article> : null}
        </section>
      </div>

      <form className="agent-composer" onSubmit={(event) => { event.preventDefault(); runAnalysis(); }}>
        <label htmlFor="agent-question">{t("输入分析问题", "Enter an analysis question")}</label>
        <div><textarea id="agent-question" value={question} onChange={(event) => {
          setQuestion(event.target.value);
          if (selectedQuestionCase?.question !== event.target.value) setSelectedQuestionCaseId(null);
        }} rows={3} placeholder={t(
          "例如：展示样例期间每日潜在自成交率。",
          "For example: Show the daily potential self-trade rate for the sample period.",
        )} />
        <button type="submit" disabled={!question.trim() || analysis.isPending}>{analysis.isPending ? t("分析中…", "Analyzing…") : t("发送", "Send")}</button></div>
      </form>
    </section>
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
  const { name, t } = useUiLocale();
  const location = useLocation();
  const buildRoute = studioBuildRouteFromPath(location.pathname);
  const page = studioPageFromPath(location.pathname);
  const subpage = studioSubpageFromPath(location.pathname, page);
  const definition = studioPageDefinition(page);
  const referenceMode = solution.directory?.creation_mode === "INSTALLED";
  if (page === "solutions") {
    return (
      <div className="studio-directory-application">
        {!canOperate ? <div className="readonly-role-banner"><strong>只读访问</strong><span>你可以查看解决方案，但新建、修改、删除和发布需要配置人员权限。</span></div> : null}
        <fieldset className="role-gated-content" disabled={!canOperate}>
          <StudioSolutionDirectory
            catalog={catalog}
            selectedSolutionId=""
            openCreateOnLoad={canOperate && new URLSearchParams(location.search).get("new") === "1"}
            openReferenceCopyId={canOperate ? new URLSearchParams(location.search).get("copy") : null}
          />
        </fieldset>
      </div>
    );
  }
  return (
    <div className="studio-application">
      <StudioNavigation
        activePage={page}
        solutionName={name(solution.display_name)}
        solutionVersion={solution.solution_version}
        activeRuntimeVersion={runtime?.version ?? null}
        solutionId={solution.solution_id}
      />
      <section className="studio-page">
        <header className="studio-page-header">
          <div className="studio-breadcrumbs"><Link to="/ontology-studio/solutions/">{t("解决方案目录", "Solution Catalog")}</Link><i>/</i><span>{name(solution.display_name)}</span><i>/</i><span>{definition.label}</span></div>
          <div className="studio-page-title">
            <div><h1>{definition.label}</h1><p>{definition.description}</p></div>
            <div className="studio-page-context"><span>方案 v{solution.solution_version}</span><code>{solution.workspace_id}</code></div>
          </div>
          <StudioSubnavigation page={page} activeSubpage={subpage} solutionId={solution.solution_id} />
        </header>
        {!canOperate ? <div className="readonly-role-banner"><strong>只读访问</strong><span>模型和运行状态可查看；新建、修改、审核、发布与激活已锁定。</span></div> : null}
        {referenceMode ? <div className="reference-solution-banner"><div><strong>参考方案 · 只读</strong><span>浏览已确认的内容与运行结果；要重新构建或修改，请先复制为独立方案。</span></div><div className="reference-solution-actions"><Link to={studioPageHref("semantic", solution.solution_id, "graph")}>查看知识图谱</Link><Link className="is-primary" to={`/ontology-studio/solutions/?copy=${encodeURIComponent(solution.solution_id)}`}>复制为可编辑方案</Link></div></div> : null}
        <fieldset className="role-gated-content studio-page-content" disabled={!canOperate}>
          {page === "overview" || page === "inputs" || page === "construction" || page === "semantic" || page === "data" || page === "quality" ? (
            <StudioPackageWorkbench
              workspaceId={solution.workspace_id}
              page={page}
              subpage={subpage}
              solutionId={solution.solution_id}
              reviewer={reviewer}
              requestedRunId={buildRoute?.runId ?? null}
              requestedDecisionId={buildRoute?.decisionId ?? null}
              openMaterialIntake={new URLSearchParams(location.search).get("intake") === "1"}
              readOnly={referenceMode}
            />
          ) : null}
        </fieldset>
      </section>
    </div>
  );
}

function GenericSolutionView({ kind, solutionId }: { kind: ProductKind; solutionId: string }) {
  const location = useLocation();
  const directoryHome = kind === "studio" && studioPageFromPath(location.pathname) === "solutions";
  const authSession = useQuery({
    queryKey: ["auth-session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
  });
  const agentCatalog = useQuery({
    queryKey: ["agent-solution-catalog", "selected"],
    queryFn: fetchAgentSolutionCatalog,
    enabled: kind === "agent",
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
    enabled: kind === "studio" && Boolean(selectedStudioSolution),
    retry: false,
  });
  if ((kind === "agent" && agentCatalog.isPending) || (kind === "studio" && studioCatalog.isPending)) {
    return <main className="state-screen"><span className="state-pulse" /><p>正在核验 selected solution…</p></main>;
  }
  if ((kind === "agent" && (agentCatalog.isError || !agentCatalog.data)) || (kind === "studio" && (studioCatalog.isError || !studioCatalog.data))) {
    return <main className="state-screen state-error"><span className="error-code">SOLUTION UNAVAILABLE</span><h1>无法打开所选 solution</h1><p>Catalog 或 exact runtime 未通过验证。</p></main>;
  }
  const solution = kind === "studio" ? selectedStudioSolution : selectedSolution;
  if (!solution) {
    return <main className="state-screen state-error"><span className="error-code">SOLUTION NOT INSTALLED</span><h1>所选 solution 不在目录中</h1></main>;
  }

  return (
    <div className="product-shell">
      <Header kind={kind} solutionId={solution.solution_id} session={authSession.data ?? null} directoryHome={directoryHome} />
      {kind === "agent" ? (
        <main className="agent-main"><AgentSolutionWorkspace key={selectedSolution!.solution_id} solution={selectedSolution!} /></main>
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
    ?? "ontology.exchange_analytics.cash_trading";
  return (
    <><LegacyUiLocalizer /><Routes>
      <Route path="/" element={<Navigate to="/ontology-agent/" replace />} />
      <Route path="/ontology-agent/*" element={<GenericSolutionView kind="agent" solutionId={selectedSolution} />} />
      <Route path="/ontology-studio" element={<Navigate to="/ontology-studio/solutions/" replace />} />
      <Route path="/ontology-studio/tasks/*" element={<Navigate to="/ontology-studio/solutions/" replace />} />
      <Route path="/ontology-studio/*" element={<GenericSolutionView kind="studio" solutionId={selectedSolution} />} />
      <Route path="*" element={<Navigate to="/ontology-agent/" replace />} />
    </Routes></>
  );
}

function TaskCenterRoute() {
  const session = useQuery({ queryKey: ["auth-session"], queryFn: fetchAuthSession, staleTime: 60_000 });
  return <StudioTaskCenter session={session.data ?? null} />;
}
