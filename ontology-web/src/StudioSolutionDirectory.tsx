import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  archiveStudioSolution,
  createStudioSolution,
  deleteStudioSolution,
  fetchAgentSolutionCatalog,
  restoreStudioSolution,
  updateStudioSolution,
  type SolutionCatalog,
  type CreateStudioSolutionInput,
  type StudioSolution,
} from "./api";
import { studioPageHref } from "./StudioNavigation";
import { useUiLocale, type UiLocale } from "./i18n";

type DialogState =
  | {
      kind: "create";
      initialMode: "DOCUMENT_BUILD" | "BLANK" | "REFERENCE_COPY";
      reference?: StudioSolution;
    }
  | { kind: "edit"; solution: StudioSolution }
  | { kind: "delete"; solution: StudioSolution }
  | null;

function latestSolutions(catalog: SolutionCatalog): StudioSolution[] {
  const latest = new Map<string, StudioSolution>();
  for (const solution of catalog.solutions) {
    const current = latest.get(solution.solution_id);
    if (!current || current.solution_version.localeCompare(
      solution.solution_version,
      undefined,
      { numeric: true },
    ) < 0) latest.set(solution.solution_id, solution);
  }
  return [...latest.values()].sort((left, right) =>
    (right.directory?.updated_at ?? "").localeCompare(left.directory?.updated_at ?? "")
    || left.display_name.zh.localeCompare(right.display_name.zh, "zh-CN")
  );
}

function solutionStatus(solution: StudioSolution): "ACTIVE" | "ARCHIVED" {
  return solution.directory?.status === "ARCHIVED" ? "ARCHIVED" : "ACTIVE";
}

function isReferenceSolution(solution: StudioSolution): boolean {
  return solution.directory?.creation_mode === "INSTALLED";
}

function dateLabel(value?: string, locale: UiLocale = "zh"): string {
  if (!value) return "已安装";
  return new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function DirectoryDialog({
  state,
  solutions,
  busy,
  error,
  onClose,
  onCreate,
  onUpdate,
  onDelete,
}: {
  state: DialogState;
  solutions: StudioSolution[];
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onCreate: (input: CreateStudioSolutionInput, openMaterialIntake: boolean) => void;
  onUpdate: (solution: StudioSolution, input: {
    display_name: { en: string; zh: string };
    description: string;
    owner: string;
  }) => void;
  onDelete: (solution: StudioSolution) => void;
}) {
  const { locale, name: displayName, t } = useUiLocale();
  const referenceSolutions = solutions.filter(isReferenceSolution);
  const [creationMode, setCreationMode] = useState<"DOCUMENT_BUILD" | "BLANK" | "REFERENCE_COPY">(
    state?.kind === "create" ? state.initialMode : "DOCUMENT_BUILD",
  );
  const [referenceId, setReferenceId] = useState(
    state?.kind === "create"
      ? state.reference?.solution_id ?? referenceSolutions[0]?.solution_id ?? ""
      : referenceSolutions[0]?.solution_id ?? "",
  );
  const selectedReference = referenceSolutions.find((item) => item.solution_id === referenceId)
    ?? (state?.kind === "create" ? state.reference : referenceSolutions[0]);
  const editing = state?.kind === "edit" ? state.solution : null;
  const [nameZh, setNameZh] = useState(
    editing?.display_name.zh
    ?? (state?.kind === "create" && state.initialMode === "REFERENCE_COPY" && state.reference
      ? `${state.reference.display_name.zh}副本`
      : ""),
  );
  const [nameEn, setNameEn] = useState(
    editing?.display_name.en
    ?? (state?.kind === "create" && state.initialMode === "REFERENCE_COPY" && state.reference
      ? `${state.reference.display_name.en} Copy`
      : ""),
  );
  const [description, setDescription] = useState(
    editing?.directory?.description
    ?? (state?.kind === "create" && state.initialMode === "REFERENCE_COPY" && state.reference
      ? locale === "en"
        ? `Independent editable solution copied from “${state.reference.display_name.en}”.`
        : `基于“${state.reference.display_name.zh}”创建的独立可编辑解决方案。`
      : ""),
  );
  const [owner, setOwner] = useState(
    editing?.directory?.owner ?? "Ontology Product Team",
  );
  const [confirmation, setConfirmation] = useState("");

  if (!state) return null;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (state.kind === "delete") {
      if (confirmation === state.solution.display_name.zh) onDelete(state.solution);
      return;
    }
    const input = {
      display_name: { en: nameEn.trim(), zh: nameZh.trim() },
      description: description.trim(),
      owner: owner.trim(),
    };
    if (state.kind === "edit") onUpdate(state.solution, input);
    else onCreate({
      ...input,
      // The v1 API calls this compatibility operation TEMPLATE. In the product
      // it is deliberately exposed as a Reference Solution copy: ADT/Cash are
      // examples with business facts, not reusable templates.
      creation_mode: creationMode === "REFERENCE_COPY" ? "TEMPLATE" : "BLANK",
      template_solution_id: creationMode === "REFERENCE_COPY" ? referenceId : null,
    }, creationMode === "DOCUMENT_BUILD");
  };
  const title = state.kind === "create"
    ? t("新建解决方案", "Create solution")
    : state.kind === "edit"
      ? t("编辑解决方案信息", "Edit solution details")
      : t("永久移除解决方案", "Delete solution permanently");

  return (
    <div className="solution-dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onClose();
    }}>
      <section className="solution-dialog" role="dialog" aria-modal="true" aria-labelledby="solution-dialog-title">
        <header>
          <div><span>SOLUTION DIRECTORY</span><h2 id="solution-dialog-title">{title}</h2></div>
          <button type="button" aria-label={t("关闭", "Close")} onClick={onClose} disabled={busy}>×</button>
        </header>
        <form onSubmit={submit}>
          {state.kind === "create" ? (
            <>
              <fieldset className="creation-methods">
                <legend>{t("创建方式", "Creation method")}</legend>
                <label className={creationMode === "DOCUMENT_BUILD" ? "is-selected" : ""}>
                  <input
                    type="radio"
                    name="creation-mode"
                    value="DOCUMENT_BUILD"
                    checked={creationMode === "DOCUMENT_BUILD"}
                    onChange={() => setCreationMode("DOCUMENT_BUILD")}
                  />
                  <strong>{t("从材料构建", "Build from source materials")}</strong>
                  <small>{t(
                    "创建独立 Draft，随后批量登记业务材料并启动 Ontology Builder。",
                    "Create an independent Draft, then register business materials in batches and start Ontology Builder.",
                  )}</small>
                </label>
                <label className={creationMode === "BLANK" ? "is-selected" : ""}>
                  <input
                    type="radio"
                    name="creation-mode"
                    value="BLANK"
                    checked={creationMode === "BLANK"}
                    onChange={() => setCreationMode("BLANK")}
                  />
                  <strong>{t("空白创建", "Create from blank")}</strong>
                  <small>{t(
                    "创建不含任何业务对象、指标或规则的独立 Draft。",
                    "Create an independent Draft with no business objects, metrics or rules.",
                  )}</small>
                </label>
                <label className={creationMode === "REFERENCE_COPY" ? "is-selected" : ""}>
                  <input
                    type="radio"
                    name="creation-mode"
                    value="REFERENCE_COPY"
                    checked={creationMode === "REFERENCE_COPY"}
                    onChange={() => setCreationMode("REFERENCE_COPY")}
                    disabled={!referenceSolutions.length}
                  />
                  <strong>{t("复制参考方案", "Copy a reference solution")}</strong>
                  <small>{t(
                    "从已安装参考方案创建独立 Draft；运行记录和发布历史不会继承。",
                    "Create an independent Draft from an installed reference solution. Runtime records and publication history are not inherited.",
                  )}</small>
                </label>
              </fieldset>
              {creationMode === "DOCUMENT_BUILD" ? (
                <section className="document-build-contract" aria-label={t("Ontology 构建材料说明", "Ontology build material guidance")}>
                  <header>
                    <strong>{t("构建所需材料", "Materials required for the build")}</strong>
                    <span>{t("支持一次多选；同一文件可以承担多个用途", "Select multiple files at once; one file can serve multiple purposes")}</span>
                  </header>
                  <ol>
                    <li><b>{t("需求与分析流程", "Requirements and analysis flow")}</b><span>{t("业务过程、分析问题、使用角色和期望输出", "Business processes, analysis questions, user roles and expected outputs")}</span></li>
                    <li><b>{t("指标逻辑", "Metric logic")}</b><span>{t("指标定义、公式、维度、过滤和异常处理", "Metric definitions, formulas, dimensions, filters and exception handling")}</span></li>
                    <li><b>{t("数据模型与字典", "Data model and dictionary")}</b><span>{t("表、字段、主键、枚举、关系和样例数据", "Tables, fields, primary keys, enumerations, relationships and sample data")}</span></li>
                    <li><b>{t("现有 SQL（可选）", "Existing SQL (optional)")}</b><span>{t("用于核对已有计算逻辑，不会直接成为发布权威", "Used to cross-check existing calculations; it does not become publication authority")}</span></li>
                  </ol>
                  <p>{t(
                    "创建后进入“来源材料”：批量上传 → 确认用途 → 选择输出语言 → 启动构建 → 人工复核。",
                    "After creation, open Source Materials: upload in batches → confirm purpose → select the output language → start the build → complete human review.",
                  )}</p>
                </section>
              ) : null}
              {creationMode === "REFERENCE_COPY" ? (
                <>
                  <label className="solution-form-field">
                    <span>{t("参考方案", "Reference solution")}</span>
                    <select value={referenceId} onChange={(event) => setReferenceId(event.target.value)} required>
                      {referenceSolutions.map((item) => (
                        <option value={item.solution_id} key={item.solution_id}>{displayName(item.display_name)}</option>
                      ))}
                    </select>
                  </label>
                  {selectedReference ? <p className="template-contract">{t(
                    `参考版本 v${selectedReference.solution_version} · ${selectedReference.resource_count ?? 0} 项资源 · ${selectedReference.components.length} 个核心组件`,
                    `Reference version v${selectedReference.solution_version} · ${selectedReference.resource_count ?? 0} resources · ${selectedReference.components.length} core components`,
                  )}</p> : null}
                </>
              ) : null}
            </>
          ) : null}
          {state.kind !== "delete" ? (
            <div className="solution-form-grid">
              <label className="solution-form-field"><span>{t("中文名称", "Simplified Chinese name")}</span><input value={nameZh} onChange={(event) => setNameZh(event.target.value)} required /></label>
              <label className="solution-form-field"><span>{t("英文名称", "English name")}</span><input value={nameEn} onChange={(event) => setNameEn(event.target.value)} required /></label>
              <label className="solution-form-field is-wide"><span>{t("业务场景描述", "Business scenario description")}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} required /></label>
              <label className="solution-form-field is-wide"><span>{t("负责人", "Owner")}</span><input value={owner} onChange={(event) => setOwner(event.target.value)} required /></label>
            </div>
          ) : (
            <div className="delete-confirmation">
              <strong>{state.solution.display_name.zh}</strong>
              <p>该操作会从 Solution Directory 中永久移除这个解决方案。已形成的审计工件仍按保留策略保存，但工作区将无法恢复。</p>
              <label className="solution-form-field"><span>输入完整名称以确认</span><input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></label>
            </div>
          )}
          {error ? <p className="solution-action-error" role="alert">{error}</p> : null}
          <footer>
            <button type="button" className="secondary" onClick={onClose} disabled={busy}>{t("取消", "Cancel")}</button>
            <button
              type="submit"
              className={state.kind === "delete" ? "danger" : "primary"}
              disabled={busy || (state.kind === "delete" && confirmation !== state.solution.display_name.zh)}
            >
              {busy
                ? t("正在处理…", "Processing…")
                : state.kind === "create"
                  ? creationMode === "DOCUMENT_BUILD"
                    ? t("创建并登记材料", "Create and register materials")
                    : t("创建 Draft Solution", "Create Draft solution")
                  : state.kind === "edit"
                    ? t("保存信息", "Save details")
                    : t("永久移除", "Delete permanently")}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}

export function StudioSolutionDirectory({
  catalog,
  selectedSolutionId,
  openCreateOnLoad = false,
  openReferenceCopyId = null,
}: {
  catalog: SolutionCatalog;
  selectedSolutionId: string;
  openCreateOnLoad?: boolean;
  openReferenceCopyId?: string | null;
}) {
  const { locale, name: displayName, t } = useUiLocale();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const solutions = useMemo(() => latestSolutions(catalog), [catalog]);
  const selected = solutions.find((item) => item.solution_id === selectedSolutionId) ?? solutions[0];
  const requestedReference = solutions.find((item) => item.solution_id === openReferenceCopyId && isReferenceSolution(item));
  const [dialog, setDialog] = useState<DialogState>(
    requestedReference
      ? { kind: "create", initialMode: "REFERENCE_COPY", reference: requestedReference }
      : openCreateOnLoad
      ? { kind: "create", initialMode: "DOCUMENT_BUILD", reference: isReferenceSolution(selected) ? selected : solutions.find(isReferenceSolution) }
      : null,
  );
  const [filter, setFilter] = useState<"ALL" | "ACTIVE" | "ARCHIVED">("ALL");
  const [search, setSearch] = useState("");
  const agentCatalog = useQuery({
    queryKey: ["agent-solution-catalog", "directory"],
    queryFn: fetchAgentSolutionCatalog,
  });
  const runtimeBySolution = new Map(
    agentCatalog.data?.solutions.map((item) => [item.solution_id, item.runtime]) ?? [],
  );
  const filtered = solutions.filter((solution) => {
    const status = solutionStatus(solution);
    const text = `${solution.display_name.zh} ${solution.display_name.en} ${solution.solution_id}`.toLowerCase();
    return (filter === "ALL" || status === filter) && text.includes(search.trim().toLowerCase());
  });
  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["studio-solution-catalog"] }),
      queryClient.invalidateQueries({ queryKey: ["agent-solution-catalog"] }),
    ]);
  };
  const create = useMutation({
    mutationFn: ({ input }: { input: CreateStudioSolutionInput; openMaterialIntake: boolean }) => createStudioSolution(input),
    onSuccess: async (solution, variables) => {
      await invalidate();
      setDialog(null);
      navigate(variables.openMaterialIntake
        ? `${studioPageHref("inputs", solution.solution_id, "sources")}?intake=1`
        : studioPageHref("overview", solution.solution_id));
    },
  });
  const update = useMutation({
    mutationFn: ({ solution, input }: { solution: StudioSolution; input: Parameters<typeof updateStudioSolution>[1] }) => updateStudioSolution(solution.solution_id, input),
    onSuccess: async () => { await invalidate(); setDialog(null); },
  });
  const archive = useMutation({
    mutationFn: archiveStudioSolution,
    onSuccess: invalidate,
  });
  const restore = useMutation({
    mutationFn: restoreStudioSolution,
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: deleteStudioSolution,
    onSuccess: async () => { await invalidate(); setDialog(null); },
  });
  const actionError = create.error ?? update.error ?? archive.error ?? restore.error ?? remove.error;
  const isBusy = create.isPending || update.isPending || archive.isPending || restore.isPending || remove.isPending;

  return (
    <div className="solution-directory">
      <header className="solution-directory-hero">
        <div>
          <span>ONTOLOGY SOLUTIONS</span>
          <h1>全部解决方案</h1>
          <p>创建、复制和管理 Ontology Solution。</p>
        </div>
        <button type="button" className="primary" onClick={() => setDialog({ kind: "create", initialMode: "DOCUMENT_BUILD", reference: isReferenceSolution(selected) ? selected : solutions.find(isReferenceSolution) })}>{t("新建解决方案", "Create solution")}</button>
      </header>
      <section className="solution-directory-toolbar" aria-label="解决方案筛选">
        <div className="solution-directory-tabs">
          {(["ALL", "ACTIVE", "ARCHIVED"] as const).map((status) => (
            <button type="button" className={filter === status ? "is-active" : ""} onClick={() => setFilter(status)} key={status}>
              {status === "ALL" ? "全部" : status === "ACTIVE" ? "使用中" : "已归档"}
              <span>{status === "ALL" ? solutions.length : solutions.filter((item) => solutionStatus(item) === status).length}</span>
            </button>
          ))}
        </div>
        <label className="solution-search"><span>搜索</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="名称或 Solution ID" /></label>
      </section>
      {actionError && !dialog ? <p className="solution-action-error" role="alert">{actionError instanceof Error ? actionError.message : "操作未完成"}</p> : null}
      <section className="solution-directory-table" aria-label="Solution Directory">
        <header><span>解决方案</span><span>状态</span><span>工作版本</span><span>运行状态</span><span>最近更新</span><span aria-label="操作" /></header>
        {filtered.map((solution) => {
          const status = solutionStatus(solution);
          const runtime = runtimeBySolution.get(solution.solution_id);
          return (
            <article key={solution.solution_id} className={solution.solution_id === selectedSolutionId ? "is-current" : ""}>
              <div className="directory-solution-name">
                <strong>{displayName(solution.display_name)}</strong>
                <span>{solution.solution_id}</span>
                <code>{solution.solution_id}</code>
              </div>
              <div><span className={`directory-status is-${status.toLowerCase()}`}>{status === "ACTIVE" ? "使用中" : "已归档"}</span></div>
              <div><strong>v{solution.solution_version}</strong><small>{solution.directory?.creation_mode === "TEMPLATE" ? "参考方案副本" : solution.directory?.creation_mode === "BLANK" ? "空白创建" : solution.directory?.creation_mode === "IMPORT" ? "导入创建" : "参考方案"}</small></div>
              <div><strong>{runtime?.state === "ACTIVE" ? "已激活" : "未激活"}</strong><small>{runtime?.state === "ACTIVE" ? "Runtime 已绑定" : "—"}</small></div>
              <div><strong>{dateLabel(solution.directory?.updated_at, locale)}</strong><small>{solution.directory?.owner ?? "Ontology Product Team"}</small></div>
              <div className="directory-row-actions">
                {status === "ACTIVE" ? <Link to={studioPageHref("overview", solution.solution_id)}>打开</Link> : null}
                <details>
                  <summary aria-label={locale === "en" ? `Manage ${displayName(solution.display_name)}` : `管理${displayName(solution.display_name)}`}>•••</summary>
                  <div>
                    {status === "ACTIVE" ? (
                      isReferenceSolution(solution) ? <>
                        <button type="button" onClick={() => setDialog({ kind: "create", initialMode: "REFERENCE_COPY", reference: solution })}>复制为可编辑方案</button>
                        {runtime?.state === "ACTIVE" ? <a href={`/ontology-agent/?solution=${encodeURIComponent(solution.solution_id)}`}>在 Agent 中打开</a> : null}
                      </> : <>
                        <button type="button" onClick={() => setDialog({ kind: "edit", solution })}>编辑信息</button>
                        {runtime?.state === "ACTIVE" ? <a href={`/ontology-agent/?solution=${encodeURIComponent(solution.solution_id)}`}>在 Agent 中打开</a> : null}
                        <button type="button" onClick={() => archive.mutate(solution.solution_id)} disabled={isBusy}>归档</button>
                      </>
                    ) : (
                      <>
                        <button type="button" onClick={() => restore.mutate(solution.solution_id)} disabled={isBusy}>恢复</button>
                        <button type="button" className="danger" onClick={() => setDialog({ kind: "delete", solution })}>永久移除</button>
                      </>
                    )}
                  </div>
                </details>
              </div>
            </article>
          );
        })}
        {filtered.length === 0 ? <div className="solution-directory-empty"><strong>没有匹配的解决方案</strong><p>调整搜索条件，或创建一个新的 Solution。</p></div> : null}
      </section>
      <aside className="solution-directory-note">
        <strong>版本内容保持不可变</strong>
        <p>编辑发生在 Draft；归档只隐藏日常工作入口。永久移除不会擦除依法需要保留的发布与审计工件。</p>
      </aside>
      <DirectoryDialog
        key={dialog ? `${dialog.kind}-${dialog.kind === "create" ? `${dialog.initialMode}-${dialog.reference?.solution_id ?? "blank"}` : dialog.solution.solution_id}` : "closed"}
        state={dialog}
        solutions={solutions}
        busy={isBusy}
        error={dialog && actionError instanceof Error ? actionError.message : null}
        onClose={() => !isBusy && setDialog(null)}
        onCreate={(input, openMaterialIntake) => create.mutate({ input, openMaterialIntake })}
        onUpdate={(solution, input) => update.mutate({ solution, input })}
        onDelete={(solution) => remove.mutate(solution.solution_id)}
      />
    </div>
  );
}
