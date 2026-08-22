import { useEffect, useMemo, useState } from "react";
import { Link, useBlocker, useNavigate } from "react-router-dom";

import type {
  ConstructionCandidate,
  ConstructionDisposition,
  ConstructionJobList,
  ConstructionReviewDecision,
  ConstructionReviewDraft,
  ConstructionReviewResult,
  ConstructionRunList,
  PackageDraftOperation,
  StudioSourceVersion,
} from "./api";
import { studioBuildResultHref, studioBuildReviewHref, studioPageHref } from "./StudioNavigation";

function useUnsavedReviewGuard(dirty: boolean) {
  const blocker = useBlocker(dirty);
  useEffect(() => {
    if (!dirty) return undefined;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
    };
  }, [dirty]);
  return blocker;
}

function reviewDispositionDigest(dispositions: ConstructionDisposition[]): string {
  return JSON.stringify([...dispositions].sort((left, right) => left.candidate_id.localeCompare(right.candidate_id)));
}


const stageLabels: Record<string, string> = {
  SOURCE_SETTLEMENT: "来源结算",
  STRUCTURED_EXTRACTION: "结构化提取",
  BUILDER_AGENT: "候选构建",
  PACKAGED_CASE_COMPILATION: "兼容资产编译",
  SEMANTICA_PROPOSAL: "语义候选生成",
  CANDIDATE_PRECHECK: "候选预检",
  REVIEWER_AGENT: "机器复核",
};

const candidateTypeLabels: Record<ConstructionCandidate["candidate_type"], string> = {
  SOURCE: "来源",
  GAP: "缺口",
  REQUIREMENT: "需求",
  ACTOR: "角色",
  PROCESS: "流程",
  OBJECT: "对象",
  LINK: "关系",
  PROPERTY: "属性",
  DIMENSION: "维度",
  METRIC: "指标",
  RULE: "规则",
  DATA_SOURCE: "数据源",
  MAPPING: "映射",
  JOIN: "关联合同",
  SQL_CONTRACT: "SQL 合同",
  ANALYSIS_PATTERN: "分析模式",
  POLICY: "策略",
  QUESTION: "问题",
};

const supportLabels: Record<ConstructionCandidate["support_class"], string> = {
  DIRECT_EXACT: "直接证据",
  DERIVED_DETERMINISTIC: "确定性推导",
  MODEL_INFERRED: "模型推断",
  HEURISTIC: "启发式",
  REVIEWER_AUTHORED: "人工补充",
  SYNTHETIC: "合成内容",
  MISSING: "缺失",
};

const jobProgressLabels: Record<string, string> = {
  JOB_QUEUED: "等待后台执行",
  SETTLING_SOURCES: "正在核对材料版本与证据身份",
  BUILDING_CANDIDATES: "正在提取并构建候选资产",
  PERSISTING_RESULT: "正在保存不可变候选集合",
  JOB_COMPLETED: "候选集合已保存，等待人工复核",
  JOB_FAILED: "执行失败，请查看技术原因",
  JOB_CANCELLED: "任务已取消",
  JOB_STALE: "输入已变化，本次结果不可应用",
};

function shortId(value: string): string {
  return value.length > 22 ? `${value.slice(0, 12)}…${value.slice(-7)}` : value;
}

function elapsed(startedAt: string, completedAt: string | null): string {
  if (!completedAt) return "运行中";
  const milliseconds = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return "—";
  return milliseconds < 1000 ? `${milliseconds} ms` : `${(milliseconds / 1000).toFixed(1)} s`;
}

export function ConstructionRunsView({
  runs,
  jobs,
  sources,
  authoringLanguage = null,
  currentRevision,
  busy,
  error,
  onStart,
  onCancel,
  onRetry,
  readOnly = false,
}: {
  runs: ConstructionRunList | null;
  jobs: ConstructionJobList | null;
  sources: StudioSourceVersion[];
  authoringLanguage?: "en" | "zh" | null;
  currentRevision: number;
  busy: boolean;
  error: string | null;
  onStart: (sourceVersionIds: string[], authoringLanguage: "en" | "zh") => void;
  onCancel: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  readOnly?: boolean;
}) {
  const latest = runs?.runs[0]?.run ?? null;
  const latestJob = jobs?.jobs[0] ?? null;
  const activeJob = latestJob && ["QUEUED", "RUNNING", "COMMITTING", "CANCEL_REQUESTED"].includes(latestJob.status) ? latestJob : null;
  const jobProgress = latestJob ? Math.min(100, Math.round((latestJob.completed_stages / latestJob.total_stages) * 100)) : 0;
  const runSyncPending = latestJob?.status === "SUCCEEDED"
    && Boolean(latestJob.result_run_id)
    && latest?.run_id !== latestJob.result_run_id;
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>(() => sources.map((source) => source.source_version_id));
  const [selectedLanguage, setSelectedLanguage] = useState<"en" | "zh">(
    authoringLanguage ?? "en",
  );
  const sourceIdentity = sources.map((source) => source.source_version_id).join("|");
  useEffect(() => {
    setSelectedSourceIds(sources.map((source) => source.source_version_id));
  }, [sourceIdentity]);
  const isCurrent = latest?.base_revision === currentRevision;
  const packagedProfileReady = latest?.stage_receipts.some((item) => item.stage === "PACKAGED_CASE_COMPILATION" && item.status === "PASS") ?? false;
  const counts = useMemo(() => {
    const values = latest?.candidates ?? [];
    return {
      total: values.length,
      compilable: values.filter((item) => item.compile_eligible).length,
      unsupported: values.filter((item) => !item.compile_eligible).length,
    };
  }, [latest]);
  return (
    <section className="construction-page" aria-labelledby="construction-runs-title">
      <header className="object-page-heading">
        <div>
          <span>CONSTRUCTION RUNS</span>
          <h2 id="construction-runs-title">自动构建运行</h2>
          <p>把选定来源结算为可追踪候选；构建结果不会直接修改 Draft，也不会自动发布。</p>
        </div>
        <div className="construction-primary-action">
          <span className={runs?.engine_configured || packagedProfileReady ? "status-good" : "status-warn"}>
            {runs?.engine_configured
              ? packagedProfileReady
                ? "Semantica 已连接 · 案例编译档已匹配"
                : "Semantica 提议引擎已连接"
              : packagedProfileReady
                ? "案例编译档已匹配"
                : "当前使用来源投影"}
          </span>
          {!readOnly ? <button type="button" onClick={() => onStart(selectedSourceIds, authoringLanguage ?? selectedLanguage)} disabled={busy || Boolean(activeJob) || (sources.length > 0 && selectedSourceIds.length === 0)}>
            {busy ? "正在处理…" : activeJob ? "构建任务运行中" : "开始自动构建"}
          </button> : null}
        </div>
      </header>

      <section className="construction-source-selection" aria-labelledby="construction-source-selection-title">
        <header><div><span>INPUT SELECTION</span><h3 id="construction-source-selection-title">选择本次构建使用的材料版本</h3><p>构建任务只读取本次选定的来源版本。</p></div><strong>{sources.length ? `${selectedSourceIds.length} / ${sources.length}` : "工作区来源"}</strong></header>
        {sources.length ? <div>{sources.map((source) => <label key={source.source_version_id}><input type="checkbox" checked={selectedSourceIds.includes(source.source_version_id)} disabled={readOnly || Boolean(activeJob)} onChange={(event) => setSelectedSourceIds((current) => event.target.checked ? [...current, source.source_version_id] : current.filter((id) => id !== source.source_version_id))} /><span><strong>{source.title}</strong><small>{source.kind} · {source.original_name}</small><code>{source.source_version_id}</code></span></label>)}</div> : <p className="construction-fixed-source-note">当前 Solution 尚无可选来源版本。{readOnly ? "复制参考方案后可登记材料并重新构建。" : "构建将读取工作区已登记材料；如需锁定特定版本，请先到“来源材料”登记。"}</p>}
      </section>

      <section className="construction-language-policy" aria-labelledby="construction-language-title">
        <div>
          <span>ONTOLOGY LANGUAGE</span>
          <h3 id="construction-language-title">Ontology 输出语言</h3>
          <p>只控制名称、定义和业务说明。ID、SQL、字段名及原始证据保持不变。</p>
        </div>
        {authoringLanguage ? (
          <div className="language-policy-locked">
            <strong>{authoringLanguage === "en" ? "English" : "简体中文"}</strong>
            <small>已写入当前 Solution，后续构建沿用</small>
          </div>
        ) : (
          <label>
            <span>首次构建请选择</span>
            <select value={selectedLanguage} onChange={(event) => setSelectedLanguage(event.target.value as "en" | "zh")} disabled={busy || Boolean(activeJob)}>
              <option value="en">English</option>
              <option value="zh">简体中文</option>
            </select>
          </label>
        )}
      </section>

      {latestJob ? <section className={`construction-job-banner is-${latestJob.status.toLowerCase()}`} aria-live="polite">
        <div><span>构建任务</span><strong>{latestJob.status === "QUEUED" ? "已排队" : latestJob.status === "RUNNING" ? "正在后台构建" : latestJob.status === "COMMITTING" ? "正在保存候选集合" : latestJob.status === "CANCEL_REQUESTED" ? "正在取消" : latestJob.status === "SUCCEEDED" ? "执行已结束" : latestJob.status === "STALE" ? "输入已变化，结果未应用" : latestJob.status === "CANCELLED" ? "已取消" : "执行失败"}</strong><code>{shortId(latestJob.job_id)} · {latestJob.selected_source_version_ids.length ? `${latestJob.selected_source_version_ids.length} 个来源版本` : "工作区来源"}</code></div>
        <div className="construction-job-progress"><span><i style={{ width: `${jobProgress}%` }} /></span><b>{jobProgress}%</b><small>{jobProgressLabels[latestJob.progress_message] ?? latestJob.progress_message}</small></div>
        <div className="construction-job-actions"><Link to={`/ontology-studio/tasks/${encodeURIComponent(latestJob.job_id)}/`}>查看任务</Link>{latestJob.status === "SUCCEEDED" && latestJob.result_run_id ? <Link className="is-primary" to={studioBuildReviewHref(latestJob.solution_id, latestJob.result_run_id)}>进入人工复核</Link> : null}{!readOnly && activeJob && ["QUEUED", "RUNNING"].includes(activeJob.status) ? <button type="button" disabled={busy} onClick={() => onCancel(activeJob.job_id)}>取消任务</button> : null}{!readOnly && ["FAILED", "CANCELLED", "STALE"].includes(latestJob.status) ? <button type="button" disabled={busy || latestJob.base_revision !== currentRevision} onClick={() => onRetry(latestJob.job_id)}>重试同一输入</button> : null}</div>
      </section> : null}

      {latest ? (
        <>
          <div className="construction-summary-strip">
            <div><span>运行状态</span><strong>{latest.status === "NEEDS_REVIEW" ? "等待人工复核" : latest.status}</strong></div>
            <div><span>来源结算</span><strong>{latest.selected_sources.length} 个来源已结算</strong></div>
            <div><span>候选集合</span><strong>{counts.total} 个候选待复核</strong></div>
            <div><span>机器复核</span><strong>{latest.machine_findings.length} 个发现</strong></div>
            <div><span>可编译 / 待补能力</span><strong>{counts.compilable} / {counts.unsupported}</strong></div>
            <div><span>耗时</span><strong>{elapsed(latest.started_at, latest.completed_at)}</strong></div>
          </div>
          {!isCurrent ? (
            <div className="construction-stale-banner" role="alert">
              该运行绑定 Draft r{latest.base_revision}，当前是 r{currentRevision}；结果只能查看，不能应用。
            </div>
          ) : null}
          <div className="construction-grid">
            <section className="construction-panel">
              <header><div><span>STAGE RECEIPTS</span><h3>运行阶段</h3></div><code>{shortId(latest.run_id)}</code></header>
              <ol className="construction-stages">
                {latest.stage_receipts.map((receipt, index) => (
                  <li key={receipt.stage} className={`is-${receipt.status.toLowerCase()}`}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <div><strong>{stageLabels[receipt.stage] ?? receipt.stage}</strong><p>{receipt.detail}</p><small>{receipt.item_count} items · {receipt.implementation}</small></div>
                    <b>{receipt.status}</b>
                  </li>
                ))}
              </ol>
            </section>
            <section className="construction-panel">
              <header><div><span>SELECTED EXACT SOURCES</span><h3>本次使用的材料</h3></div><b>{latest.selected_sources.length}</b></header>
              <div className="construction-source-list">
                {latest.selected_sources.map((source) => (
                  <article key={source.source_id}>
                    <div><strong>{source.source_id}</strong><small>{source.source_kind}</small></div>
                    <code>{source.locator}</code>
                    <span className={source.outcome === "SETTLED" ? "status-good" : "status-warn"}>{source.outcome}</span>
                  </article>
                ))}
              </div>
            </section>
          </div>
          <section className="construction-history">
            <header><span>RUN HISTORY</span><h3>最近运行</h3></header>
            <div className="catalog-table-head"><span>运行</span><span>基线</span><span>引擎</span><span>候选</span><span>决策</span></div>
            {runs?.runs.map((record) => (
              <div className="construction-history-row" key={record.run.run_id}>
                <code>{shortId(record.run.run_id)}</code>
                <span>Draft r{record.run.base_revision}</span>
                <span>{record.run.engine_status === "COMPLETED" ? "Semantica" : record.run.stage_receipts.some((item) => item.stage === "PACKAGED_CASE_COMPILATION" && item.status === "PASS") ? "案例编译档" : "来源投影"}</span>
                <strong>{record.run.candidates.length}</strong>
                <span>{record.decision?.status ?? "待复核"}</span>
              </div>
            ))}
          </section>
        </>
      ) : error ? (
        <div className="construction-empty is-error" role="alert">
          <span>CONSTRUCTION DATA ERROR</span>
          <h3>构建结果读取失败</h3>
          <p>{error}</p>
        </div>
      ) : runSyncPending || runs === null ? (
        <div className="construction-empty" aria-live="polite">
          <span>LOADING CONSTRUCTION RUN</span>
          <h3>{runSyncPending ? "正在同步候选集合" : "正在读取构建记录"}</h3>
          <p>{runSyncPending ? "后台任务已完成，系统正在读取与校验不可变运行结果。" : "正在核对运行记录、来源结算和候选合同。"}</p>
        </div>
      ) : (
        <div className="construction-empty">
          <span>NO CONSTRUCTION RUN</span>
          <h3>材料已登记，尚未生成候选</h3>
          <p>启动后会逐一结算来源，生成带证据的候选集合，并送到复核中心。</p>
        </div>
      )}
      {error && latest ? <p className="operator-error" role="alert">{error}</p> : null}
    </section>
  );
}


type ReviewAction = "UNREVIEWED" | "ACCEPT" | "EDIT" | "REJECT" | "DEFER";

function ConstructionReviewResultView({
  decision,
  solutionId,
}: {
  decision: ConstructionReviewDecision;
  solutionId: string;
}) {
  const appliedCount = decision.applied.length;
  return (
    <section className="review-result" aria-labelledby="review-result-title">
      <header>
        <span>复核应用结果</span>
        <h2 id="review-result-title">
          {decision.status === "REVIEWED_NO_CHANGE" ? "本轮已完成，Draft 无变更" : `已生成 Draft r${decision.resulting_revision}`}
        </h2>
        <p>系统已按人工处置应用类型化变更并完成服务端确认；发布和运行激活仍是后续独立步骤。</p>
      </header>
      <div className="review-result-summary">
        <div><span>已应用</span><strong>{appliedCount}</strong><small>已写入并确认的语义资产</small></div>
        <div><span>暂缓</span><strong>{decision.deferred_candidate_ids.length}</strong><small>保留在后续补充队列</small></div>
        <div><span>拒绝</span><strong>{decision.rejected_candidate_ids.length}</strong><small>未写入当前 Draft</small></div>
        <div><span>新修订</span><strong>r{decision.resulting_revision}</strong><small>{shortId(decision.resulting_draft_checksum)}</small></div>
      </div>
      {decision.server_blockers.length ? (
        <div className="review-result-blockers" role="status">
          <strong>仍需处理的发布阻断项</strong>
          {decision.server_blockers.map((item) => <code key={item}>{item}</code>)}
        </div>
      ) : null}
      {decision.applied.length ? (
        <section className="review-result-assets">
          <header><h3>本轮应用的资产</h3><span>{decision.applied.length} 项</span></header>
          <div className="catalog-table-head"><span>资产</span><span>变化</span><span>确认</span><span>最终摘要</span></div>
          {decision.applied.map((asset) => (
            <article key={asset.candidate_id}>
              <div><strong>{asset.object_id}</strong><small>{asset.collection}</small></div>
              <span>{asset.change_type === "CREATE" ? "新增" : asset.change_type === "UPDATE" ? "更新" : asset.change_type === "NO_CHANGE" ? "无字段变化" : "已应用"}</span>
              <b>{asset.confirmation_status === "CONFIRMED" ? "已确认" : "精确登记"}</b>
              <code>{shortId(asset.final_confirmed_asset_digest)}</code>
            </article>
          ))}
        </section>
      ) : null}
      <nav className="review-result-destinations" aria-label="检查复核结果">
        <Link to={studioPageHref("semantic", solutionId, "model")}>查看业务模型</Link>
        <Link to={studioPageHref("semantic", solutionId, "metrics")}>查看指标与规则</Link>
        <Link to={studioPageHref("data", solutionId, "mappings")}>查看映射与关联</Link>
        <Link to={studioPageHref("quality", solutionId, "validation")}>验证新 Draft</Link>
      </nav>
      <footer><span>Decision</span><code>{decision.decision_id}</code><span>Checksum</span><code>{shortId(decision.decision_checksum)}</code></footer>
    </section>
  );
}

export function ConstructionReviewCenter({
  runs,
  reviewDraft,
  decision,
  requestedRunId,
  requestedDecisionId,
  solutionId,
  currentRevision,
  busy,
  error,
  onReview,
  onSave,
  readOnly = false,
}: {
  runs: ConstructionRunList | null;
  reviewDraft: ConstructionReviewDraft | null;
  decision?: ConstructionReviewDecision | null;
  requestedRunId?: string | null;
  requestedDecisionId?: string | null;
  solutionId: string;
  currentRevision: number;
  busy: boolean;
  error: string | null;
  onSave: (runId: string, dispositions: ConstructionDisposition[]) => Promise<ConstructionReviewDraft>;
  onReview: (runId: string, dispositions: ConstructionDisposition[], reviewBatchChecksum: string | null) => Promise<ConstructionReviewResult>;
  readOnly?: boolean;
}) {
  const navigate = useNavigate();
  const activeRecord = requestedRunId
    ? runs?.runs.find((item) => item.run.run_id === requestedRunId) ?? null
    : runs?.runs.find((item) => item.decision === null) ?? runs?.runs[0] ?? null;
  const run = activeRecord?.run ?? null;
  const resolvedDecision = decision ?? activeRecord?.decision ?? null;
  const [savedDraft, setSavedDraft] = useState<ConstructionReviewDraft | null>(reviewDraft);
  const [appliedResult, setAppliedResult] = useState<ConstructionReviewResult | null>(null);
  const [workflowPhase, setWorkflowPhase] = useState<"EDITING" | "SAVING" | "SAVED" | "APPLYING" | "APPLIED">(
    resolvedDecision ? "APPLIED" : reviewDraft ? "SAVED" : "EDITING",
  );
  const [selectedId, setSelectedId] = useState<string | null>(run?.candidates[0]?.candidate_id ?? null);
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [riskFilter, setRiskFilter] = useState<string>("ALL");
  const [decisionFilter, setDecisionFilter] = useState<string>("ALL");
  const [page, setPage] = useState(1);
  const [actions, setActions] = useState<Record<string, ReviewAction>>({});
  const [edits, setEdits] = useState<Record<string, PackageDraftOperation>>({});
  const [editTexts, setEditTexts] = useState<Record<string, string>>({});
  const [editErrors, setEditErrors] = useState<Record<string, string>>({});
  const selected = run?.candidates.find((item) => item.candidate_id === selectedId) ?? run?.candidates[0] ?? null;
  const findingsByCandidate = useMemo(() => Object.fromEntries(
    (run?.candidates ?? []).map((candidate) => [
      candidate.candidate_id,
      (run?.machine_findings ?? []).filter((finding) => finding.candidate_ids.includes(candidate.candidate_id)),
    ]),
  ), [run]);
  const selectedFindings = selected ? findingsByCandidate[selected.candidate_id] ?? [] : [];

  useEffect(() => {
    setSelectedId(run?.candidates[0]?.candidate_id ?? null);
    setActions({});
    setEdits({});
    setEditTexts({});
    setEditErrors({});
    setTypeFilter("ALL");
    setRiskFilter("ALL");
    setDecisionFilter("ALL");
    setPage(1);
    setAppliedResult(null);
    setSavedDraft(reviewDraft?.run_id === run?.run_id ? reviewDraft : null);
    setWorkflowPhase(resolvedDecision ? "APPLIED" : reviewDraft?.run_id === run?.run_id ? "SAVED" : "EDITING");
  }, [run?.run_id]);

  useEffect(() => {
    if (!run || !reviewDraft || reviewDraft.run_id !== run.run_id) return;
    setActions(Object.fromEntries(reviewDraft.dispositions.map((item) => [item.candidate_id, item.action])));
    setEdits(Object.fromEntries(reviewDraft.dispositions.flatMap((item) => item.edited_operation ? [[item.candidate_id, item.edited_operation] as const] : [])));
    setEditTexts(Object.fromEntries(reviewDraft.dispositions.flatMap((item) => item.edited_operation ? [[item.candidate_id, JSON.stringify(item.edited_operation, null, 2)] as const] : [])));
    setEditErrors({});
    setSavedDraft(reviewDraft);
    setWorkflowPhase(resolvedDecision ? "APPLIED" : "SAVED");
  }, [reviewDraft?.batch_checksum, run?.run_id]);

  useEffect(() => {
    if (resolvedDecision) setWorkflowPhase("APPLIED");
  }, [resolvedDecision?.decision_id]);

  const filtered = (run?.candidates ?? []).filter((item) => {
    const action = actions[item.candidate_id] ?? "UNREVIEWED";
    return (typeFilter === "ALL" || item.candidate_type === typeFilter)
      && (riskFilter === "ALL" || item.risk_class === riskFilter)
      && (decisionFilter === "ALL" || (decisionFilter === "UNREVIEWED" ? action === "UNREVIEWED" : action !== "UNREVIEWED"));
  });
  const pageSize = 25;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const visibleIdentity = visible.map((candidate) => candidate.candidate_id).join("|");
  const decidedCount = run?.candidates.filter((item) => (actions[item.candidate_id] ?? "UNREVIEWED") !== "UNREVIEWED").length ?? 0;
  const allDecided = Boolean(run && decidedCount === run.candidates.length);
  const stale = Boolean(run && run.base_revision !== currentRevision);
  const hasEditErrors = Object.keys(editErrors).length > 0
    || Boolean(run?.candidates.some((candidate) => actions[candidate.candidate_id] === "EDIT" && !edits[candidate.candidate_id]));

  useEffect(() => { setPage(1); }, [typeFilter, riskFilter, decisionFilter]);
  useEffect(() => {
    if (!visible.length) { setSelectedId(null); return; }
    if (!visible.some((candidate) => candidate.candidate_id === selectedId)) {
      setSelectedId(visible[0].candidate_id);
    }
  }, [visibleIdentity, selectedId]);

  function choose(candidate: ConstructionCandidate, action: ReviewAction) {
    if (action === "ACCEPT" && !candidate.compile_eligible) return;
    if (action === "EDIT" && !candidate.proposed_operation) return;
    if (action === "EDIT" && candidate.proposed_operation) {
      setEdits((current) => current[candidate.candidate_id] ? current : {
        ...current,
        [candidate.candidate_id]: candidate.proposed_operation!,
      });
      setEditTexts((current) => current[candidate.candidate_id] ? current : {
        ...current,
        [candidate.candidate_id]: JSON.stringify(candidate.proposed_operation, null, 2),
      });
    }
    if (action !== "EDIT") {
      setEditErrors((current) => {
        const next = { ...current };
        delete next[candidate.candidate_id];
        return next;
      });
    }
    setActions((current) => ({ ...current, [candidate.candidate_id]: action }));
    setWorkflowPhase("EDITING");
  }

  function fillConservativeRecommendations() {
    if (!run || Boolean(activeRecord?.decision)) return;
    setActions((current) => ({ ...current, ...Object.fromEntries(visible.map((candidate) => [
      candidate.candidate_id,
      candidate.compile_eligible
        && ["DIRECT_EXACT", "DERIVED_DETERMINISTIC"].includes(candidate.support_class)
        && !(findingsByCandidate[candidate.candidate_id] ?? []).some((finding) => finding.blocks_release)
        ? "ACCEPT"
        : "DEFER",
    ])) }));
    setWorkflowPhase("EDITING");
  }

  function updateEditedOperation(candidate: ConstructionCandidate, text: string) {
    setWorkflowPhase("EDITING");
    setEditTexts((current) => ({ ...current, [candidate.candidate_id]: text }));
    try {
      const value = JSON.parse(text) as PackageDraftOperation;
      if (!value || typeof value !== "object" || value.action !== "UPSERT" || !value.payload || value.object_id !== candidate.proposed_operation?.object_id || value.collection !== candidate.proposed_operation?.collection) {
        throw new Error("Typed operation identity cannot change");
      }
      setEdits((current) => ({ ...current, [candidate.candidate_id]: value }));
      setEditErrors((current) => { const next = { ...current }; delete next[candidate.candidate_id]; return next; });
    } catch {
      setEditErrors((current) => ({ ...current, [candidate.candidate_id]: "必须是有效 typed operation JSON；action、collection 与 object_id 不可改写。" }));
    }
  }

  function dispositionsForCurrentState(requireAll: boolean): ConstructionDisposition[] {
    if (!run) return [];
    return run.candidates.flatMap((candidate) => {
      const action = actions[candidate.candidate_id];
      if (action === "UNREVIEWED" || action === undefined) {
        if (requireAll) throw new Error("Candidate is undecided");
        return [];
      }
      return [{
        candidate_id: candidate.candidate_id,
        action,
        note: action === "ACCEPT" ? "已核对来源、定义与影响，接受 typed proposal。" : action === "EDIT" ? "Reviewer 已修改 typed proposal；修改值属于 REVIEWER_AUTHORED。" : action === "DEFER" ? "暂缓，等待补齐编译能力或业务确认。" : "当前证据不足或候选不适用。",
        blocks_release: action !== "REJECT" && (
          (action === "DEFER" && candidate.risk_class === "HIGH")
          || (findingsByCandidate[candidate.candidate_id] ?? []).some((finding) => finding.blocks_release)
        ),
        edited_operation: action === "EDIT" ? edits[candidate.candidate_id] : null,
      }];
    });
  }

  const currentDispositions = dispositionsForCurrentState(false);
  const persistedDigest = reviewDispositionDigest(savedDraft?.dispositions ?? []);
  const currentDigest = reviewDispositionDigest(currentDispositions);
  const progressDirty = currentDigest !== persistedDigest;
  const navigationBlocker = useUnsavedReviewGuard(progressDirty && !resolvedDecision && !appliedResult);

  async function saveProgress() {
    if (!run || !progressDirty || !currentDispositions.length || hasEditErrors) return;
    setWorkflowPhase("SAVING");
    try {
      const saved = await onSave(run.run_id, currentDispositions);
      setSavedDraft(saved);
      setWorkflowPhase("SAVED");
    } catch {
      setWorkflowPhase("EDITING");
    }
  }

  async function submit() {
    if (!run || !allDecided || !savedDraft || progressDirty || hasEditErrors) return;
    setWorkflowPhase("APPLYING");
    try {
      const result = await onReview(run.run_id, dispositionsForCurrentState(true), savedDraft.batch_checksum);
      setAppliedResult(result);
      setWorkflowPhase("APPLIED");
      navigate(studioBuildResultHref(solutionId, run.run_id, result.decision.decision_id), { replace: true });
    } catch {
      setWorkflowPhase("SAVED");
    }
  }

  const finalDecision = appliedResult?.decision ?? resolvedDecision;

  if (runs === null) {
    return error ? (
      <section className="construction-empty is-error" role="alert"><span>REVIEW DATA ERROR</span><h3>候选集合读取失败</h3><p>{error}</p></section>
    ) : (
      <section className="construction-empty" aria-live="polite"><span>LOADING REVIEW DATA</span><h3>正在读取候选集合</h3><p>系统正在校验候选、来源证据和已有复核进度。</p></section>
    );
  }

  if (!run) {
    if (requestedRunId) {
      return <section className="construction-empty is-error" role="alert"><span>构建记录不存在</span><h3>无法打开指定复核任务</h3><p>该链接指向的构建运行不属于当前 Solution，或记录已不可用。</p></section>;
    }
    return <section className="construction-empty"><span>REVIEW CENTER</span><h3>没有待复核的候选</h3><p>先在“输入与证据 → 构建运行”启动一次自动构建。</p></section>;
  }


  if (finalDecision) {
    if (requestedDecisionId && finalDecision.decision_id !== requestedDecisionId) {
      return <section className="construction-empty is-error" role="alert"><span>复核结果不匹配</span><h3>无法确认指定决策</h3><p>结果链接与当前构建记录不一致。</p></section>;
    }
    return <ConstructionReviewResultView decision={finalDecision} solutionId={solutionId} />;
  }

  return (
    <section className="review-center" aria-labelledby="review-center-title">
      <header className="review-center-header">
        <div><span>HUMAN REVIEW CENTER</span><h2 id="review-center-title">候选复核中心</h2><p>每一项默认未决定。模型置信度不能替代来源证据、业务判断或发布权限。</p></div>
        <div className="review-progress"><strong>{decidedCount} / {run.candidates.length}</strong><span>已处理</span></div>
      </header>
      {stale ? <div className="construction-stale-banner" role="alert">该候选集来自 Draft r{run.base_revision}，当前 r{currentRevision}。请归档后重新构建。</div> : null}
      <div className="review-toolbar">
        <label>候选类型
          <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
            <option value="ALL">全部 {run.candidates.length}</option>
            {Object.entries(candidateTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>风险等级<select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)}><option value="ALL">全部风险</option><option value="HIGH">高风险</option><option value="MEDIUM">中风险</option><option value="LOW">低风险</option></select></label>
        <label>处理状态<select value={decisionFilter} onChange={(event) => setDecisionFilter(event.target.value)}><option value="ALL">全部状态</option><option value="UNREVIEWED">未决定</option><option value="DECIDED">已处理</option></select></label>
        <div className="review-toolbar-summary"><span>筛选结果 {filtered.length}</span><span>可编译 {run.candidates.filter((item) => item.compile_eligible).length}</span><span>高风险 {run.candidates.filter((item) => item.risk_class === "HIGH").length}</span>{!readOnly ? <button type="button" disabled={stale || busy || Boolean(activeRecord?.decision) || visible.length === 0} onClick={fillConservativeRecommendations}>本页填入保守建议</button> : null}<small>{readOnly ? "参考方案仅展示已保存的复核记录" : `只处理当前 ${visible.length} 项，不保存、不发布、不激活`}</small></div>
      </div>
      <div className="review-workspace">
        <div className="review-queue" role="list" aria-label="候选队列">
          {visible.map((candidate, index) => {
            const action = actions[candidate.candidate_id] ?? "UNREVIEWED";
            return (
              <article key={candidate.candidate_id} role="listitem" className={selected?.candidate_id === candidate.candidate_id ? "is-selected" : ""}>
                <button type="button" className="review-candidate-main" onClick={() => setSelectedId(candidate.candidate_id)}>
                  <span>{String((currentPage - 1) * pageSize + index + 1).padStart(2, "0")}</span>
                  <div><strong>{candidate.label}</strong><small>{candidateTypeLabels[candidate.candidate_type]} · {supportLabels[candidate.support_class]}</small></div>
                  {(findingsByCandidate[candidate.candidate_id] ?? []).length ? <b className={(findingsByCandidate[candidate.candidate_id] ?? []).some((finding) => finding.severity === "ERROR") ? "finding-error" : "finding-warn"}>{(findingsByCandidate[candidate.candidate_id] ?? []).length} 个发现</b> : null}
                  <em className={`risk-${candidate.risk_class.toLowerCase()}`}>{candidate.risk_class}</em>
                </button>
                <label>复核动作 {candidate.label}
                  <select aria-label={`复核动作 ${candidate.label}`} value={action} disabled={readOnly || Boolean(activeRecord?.decision)} onChange={(event) => choose(candidate, event.target.value as ReviewAction)}>
                    <option value="UNREVIEWED">未决定</option>
                    <option value="ACCEPT" disabled={!candidate.compile_eligible}>接受并应用</option>
                    <option value="EDIT" disabled={!candidate.proposed_operation}>修改后应用</option>
                    <option value="REJECT">拒绝</option>
                    <option value="DEFER">暂缓</option>
                  </select>
                </label>
              </article>
            );
          })}
          <nav className="review-pagination" aria-label="候选分页"><span>第 {currentPage} / {pageCount} 页 · 每页最多 {pageSize} 项</span><div><button type="button" disabled={currentPage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button><button type="button" disabled={currentPage >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>下一页</button></div></nav>
        </div>
        <aside className="review-inspector">
          {selected ? (
            <>
              <span>CANDIDATE INSPECTOR</span>
              <h3>{selected.label}</h3>
              <p>{selected.definition}</p>
              <div className="evidence-lineage-mini">
                <b>{selected.source_anchors.length ? `${selected.source_anchors.length} 个来源锚点` : "无直接来源锚点"}</b>
                <span>→ Run → Candidate → Human Decision → Draft</span>
              </div>
              <dl>
                <div><dt>类型</dt><dd>{candidateTypeLabels[selected.candidate_type]}</dd></div>
                <div><dt>证据等级</dt><dd>{supportLabels[selected.support_class]}</dd></div>
                <div><dt>Canonical target</dt><dd>{selected.canonical_target ?? "尚未映射"}</dd></div>
                <div><dt>可编译</dt><dd>{selected.compile_eligible ? "是；已生成 typed operation" : "否；不能接受"}</dd></div>
                <div><dt>相对 Draft</dt><dd>{selected.draft_diff.change_type === "CREATE" ? "新增" : selected.draft_diff.change_type === "UPDATE" ? "修改" : selected.draft_diff.change_type === "NO_CHANGE" ? "无变化" : selected.draft_diff.change_type === "NON_COMPILABLE" ? "不可编译" : "旧运行未计算"}</dd></div>
              </dl>
              <section className="machine-findings" aria-label="机器复核发现">
                <header><strong>机器复核发现</strong><span>{selectedFindings.length}</span></header>
                {selectedFindings.length ? selectedFindings.map((finding) => <article key={finding.finding_id} className={`is-${finding.severity.toLowerCase()}`}><div><b>{finding.summary}</b><em>{finding.severity}{finding.blocks_release ? " · 阻断发布" : ""}</em></div><p>{finding.detail}</p><small>{finding.recommendation}</small></article>) : <p>本候选暂无机器复核发现；这不等于业务批准。</p>}
              </section>
              <section className="candidate-draft-diff" aria-label="Candidate 与 Draft 对比">
                <header><strong>Candidate 与当前 Draft</strong><span>{selected.draft_diff.changed_paths.length ? `${selected.draft_diff.changed_paths.length} 处变化` : "无字段变化"}</span></header>
                {selected.draft_diff.changed_paths.length ? <p>{selected.draft_diff.changed_paths.join(" · ")}</p> : null}
                {selected.compile_eligible ? <div><section><b>当前 Draft</b><pre>{selected.draft_diff.before ? JSON.stringify(selected.draft_diff.before, null, 2) : "尚不存在"}</pre></section><section><b>候选结果</b><pre>{selected.draft_diff.after ? JSON.stringify(selected.draft_diff.after, null, 2) : "—"}</pre></section></div> : <p>该候选没有可应用的类型化变更。</p>}
              </section>
              {!readOnly && (actions[selected.candidate_id] ?? "UNREVIEWED") === "EDIT" && selected.proposed_operation?.payload ? <section className="typed-candidate-editor"><span>REVIEWER-AUTHORED TYPED EDIT</span><label>完整 typed operation<textarea aria-label={`修改 typed operation ${selected.label}`} rows={16} spellCheck={false} value={editTexts[selected.candidate_id] ?? JSON.stringify(edits[selected.candidate_id] ?? selected.proposed_operation, null, 2)} onChange={(event) => updateEditedOperation(selected, event.target.value)} /></label>{editErrors[selected.candidate_id] ? <p className="operator-error" role="alert">{editErrors[selected.candidate_id]}</p> : <p>允许修改 payload 中的定义、公式、查询与映射字段；action、collection 与 object_id 被锁定，服务端仍会执行完整 typed validation。</p>}</section> : null}
              {selected.source_anchors.map((anchor) => <div className="source-anchor-card" key={anchor.snippet_checksum}><strong>{anchor.source_id}</strong><code>{anchor.locator}</code><small>{anchor.sheet_name && anchor.cell_range ? `${anchor.sheet_name}!${anchor.cell_range}` : `line ${anchor.line_number}`} · {shortId(anchor.snippet_checksum)}</small></div>)}
              {selected.limitations.length ? <div className="candidate-limitations"><strong>限制 / 缺口</strong>{selected.limitations.map((item) => <p key={item}>{item}</p>)}</div> : null}
              <details><summary>技术详情</summary><pre>{JSON.stringify(selected.proposal, null, 2)}</pre></details>
            </>
          ) : null}
        </aside>
      </div>
      <footer className="review-commit-bar">
        <div><strong>{hasEditErrors ? "存在未通过结构校验的人工修改" : allDecided ? progressDirty ? "全部已处理；请先保存复核进度" : "所有候选均已保存复核动作" : `还有 ${run.candidates.length - decidedCount} 项未决定`}</strong><p>{savedDraft ? `服务端复核 r${savedDraft.review_revision} · ${shortId(savedDraft.batch_checksum)}` : "尚未形成服务端复核批次"}；最终提交会再次核对候选、批次和 Draft。</p></div>
        {!readOnly ? <div className="review-commit-actions"><button type="button" disabled={!progressDirty || !currentDispositions.length || hasEditErrors || stale || busy} onClick={() => { void saveProgress(); }}>{workflowPhase === "SAVING" ? "正在保存…" : "保存复核进度"}</button><button type="button" disabled={!allDecided || progressDirty || hasEditErrors || !savedDraft || stale || busy} onClick={() => { void submit(); }}>{workflowPhase === "APPLYING" ? "正在应用…" : "完成本轮复核并应用"}</button></div> : null}
      </footer>
      {navigationBlocker.state === "blocked" ? (
        <div className="eix-modal-backdrop" role="presentation">
          <section className="eix-modal review-leave-dialog" role="dialog" aria-modal="true" aria-labelledby="review-leave-title">
            <header><span>未保存的复核进度</span><h3 id="review-leave-title">离开前是否保留当前修改？</h3></header>
            <p>当前页面包含尚未保存的人工处置。直接离开会丢失这些修改，但不会影响已保存的服务端复核批次。</p>
            <footer><button type="button" onClick={() => navigationBlocker.reset()}>继续复核</button><button className="is-danger" type="button" onClick={() => navigationBlocker.proceed()}>放弃修改并离开</button></footer>
          </section>
        </div>
      ) : null}
      {error ? <p className="operator-error" role="alert">{error}</p> : null}
    </section>
  );
}
