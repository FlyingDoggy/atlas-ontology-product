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

type DialogState =
  | {
      kind: "create";
      initialMode: "BLANK" | "TEMPLATE";
      template?: StudioSolution;
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

function dateLabel(value?: string): string {
  if (!value) return "已安装";
  return new Intl.DateTimeFormat("zh-CN", {
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
  onCreate: (input: CreateStudioSolutionInput) => void;
  onUpdate: (solution: StudioSolution, input: {
    display_name: { en: string; zh: string };
    description: string;
    owner: string;
  }) => void;
  onDelete: (solution: StudioSolution) => void;
}) {
  const [creationMode, setCreationMode] = useState<"BLANK" | "TEMPLATE">(
    state?.kind === "create" ? state.initialMode : "BLANK",
  );
  const [templateId, setTemplateId] = useState(
    state?.kind === "create"
      ? state.template?.solution_id ?? solutions[0]?.solution_id ?? ""
      : solutions[0]?.solution_id ?? "",
  );
  const selectedTemplate = solutions.find((item) => item.solution_id === templateId)
    ?? (state?.kind === "create" ? state.template : solutions[0]);
  const editing = state?.kind === "edit" ? state.solution : null;
  const [nameZh, setNameZh] = useState(
    editing?.display_name.zh
    ?? (state?.kind === "create" && state.initialMode === "TEMPLATE" && state.template
      ? `${state.template.display_name.zh}副本`
      : ""),
  );
  const [nameEn, setNameEn] = useState(
    editing?.display_name.en
    ?? (state?.kind === "create" && state.initialMode === "TEMPLATE" && state.template
      ? `${state.template.display_name.en} Copy`
      : ""),
  );
  const [description, setDescription] = useState(
    editing?.directory?.description
    ?? (state?.kind === "create" && state.initialMode === "TEMPLATE" && state.template
      ? `基于“${state.template.display_name.zh}”结构创建的独立本体解决方案。`
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
      creation_mode: creationMode,
      template_solution_id: creationMode === "TEMPLATE" ? templateId : null,
    });
  };
  const title = state.kind === "create"
    ? "新建解决方案"
    : state.kind === "edit"
      ? "编辑解决方案信息"
      : "永久移除解决方案";

  return (
    <div className="solution-dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onClose();
    }}>
      <section className="solution-dialog" role="dialog" aria-modal="true" aria-labelledby="solution-dialog-title">
        <header>
          <div><span>SOLUTION DIRECTORY</span><h2 id="solution-dialog-title">{title}</h2></div>
          <button type="button" aria-label="关闭" onClick={onClose} disabled={busy}>×</button>
        </header>
        <form onSubmit={submit}>
          {state.kind === "create" ? (
            <>
              <fieldset className="creation-methods">
                <legend>创建基础</legend>
                <label className={creationMode === "BLANK" ? "is-selected" : ""}>
                  <input
                    type="radio"
                    name="creation-mode"
                    value="BLANK"
                    checked={creationMode === "BLANK"}
                    onChange={() => setCreationMode("BLANK")}
                  />
                  <strong>空白创建</strong>
                  <small>创建不含任何业务对象、指标或规则的独立 Draft。</small>
                </label>
                <label className={creationMode === "TEMPLATE" ? "is-selected" : ""}>
                  <input
                    type="radio"
                    name="creation-mode"
                    value="TEMPLATE"
                    checked={creationMode === "TEMPLATE"}
                    onChange={() => setCreationMode("TEMPLATE")}
                    disabled={!solutions.some((item) => solutionStatus(item) === "ACTIVE")}
                  />
                  <strong>从模板创建</strong>
                  <small>复制已安装模板的结构；源材料、运行记录和发布历史不会继承。</small>
                </label>
              </fieldset>
              {creationMode === "TEMPLATE" ? (
                <>
                  <label className="solution-form-field">
                    <span>模板</span>
                    <select value={templateId} onChange={(event) => setTemplateId(event.target.value)} required>
                      {solutions.filter((item) => solutionStatus(item) === "ACTIVE").map((item) => (
                        <option value={item.solution_id} key={item.solution_id}>{item.display_name.zh}</option>
                      ))}
                    </select>
                  </label>
                  {selectedTemplate ? <p className="template-contract">模板版本 v{selectedTemplate.solution_version} · {selectedTemplate.resource_count ?? 0} 项资源 · {selectedTemplate.components.length} 个核心组件</p> : null}
                </>
              ) : null}
            </>
          ) : null}
          {state.kind !== "delete" ? (
            <div className="solution-form-grid">
              <label className="solution-form-field"><span>中文名称</span><input value={nameZh} onChange={(event) => setNameZh(event.target.value)} required /></label>
              <label className="solution-form-field"><span>英文名称</span><input value={nameEn} onChange={(event) => setNameEn(event.target.value)} required /></label>
              <label className="solution-form-field is-wide"><span>业务场景描述</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} required /></label>
              <label className="solution-form-field is-wide"><span>负责人</span><input value={owner} onChange={(event) => setOwner(event.target.value)} required /></label>
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
            <button type="button" className="secondary" onClick={onClose} disabled={busy}>取消</button>
            <button
              type="submit"
              className={state.kind === "delete" ? "danger" : "primary"}
              disabled={busy || (state.kind === "delete" && confirmation !== state.solution.display_name.zh)}
            >
              {busy ? "正在处理…" : state.kind === "create" ? "创建 Draft Solution" : state.kind === "edit" ? "保存信息" : "永久移除"}
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
}: {
  catalog: SolutionCatalog;
  selectedSolutionId: string;
  openCreateOnLoad?: boolean;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const solutions = useMemo(() => latestSolutions(catalog), [catalog]);
  const selected = solutions.find((item) => item.solution_id === selectedSolutionId) ?? solutions[0];
  const [dialog, setDialog] = useState<DialogState>(
    openCreateOnLoad
      ? { kind: "create", initialMode: "BLANK", template: selected }
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
    mutationFn: createStudioSolution,
    onSuccess: async (solution) => {
      await invalidate();
      setDialog(null);
      navigate(studioPageHref("overview", solution.solution_id));
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
          <p>在一个目录中切换业务场景、创建独立 Draft，并管理每个本体解决方案的生命周期。</p>
        </div>
        <button type="button" className="primary" onClick={() => setDialog({ kind: "create", initialMode: "BLANK", template: selected })}>新建解决方案</button>
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
                <strong>{solution.display_name.zh}</strong>
                <span>{solution.display_name.en}</span>
                <code>{solution.solution_id}</code>
              </div>
              <div><span className={`directory-status is-${status.toLowerCase()}`}>{status === "ACTIVE" ? "使用中" : "已归档"}</span></div>
              <div><strong>v{solution.solution_version}</strong><small>{solution.directory?.creation_mode === "TEMPLATE" ? "模板创建" : solution.directory?.creation_mode === "BLANK" ? "空白创建" : solution.directory?.creation_mode === "IMPORT" ? "导入创建" : "已安装"}</small></div>
              <div><strong>{runtime?.state === "ACTIVE" ? "Active" : "未激活"}</strong><small>{runtime?.environment_id ?? "—"}</small></div>
              <div><strong>{dateLabel(solution.directory?.updated_at)}</strong><small>{solution.directory?.owner ?? "Ontology Product Team"}</small></div>
              <div className="directory-row-actions">
                {status === "ACTIVE" ? <Link to={studioPageHref("overview", solution.solution_id)}>打开</Link> : null}
                <details>
                  <summary aria-label={`管理${solution.display_name.zh}`}>•••</summary>
                  <div>
                    {status === "ACTIVE" ? (
                      <>
                        <button type="button" onClick={() => setDialog({ kind: "edit", solution })}>编辑信息</button>
                        <button type="button" onClick={() => setDialog({ kind: "create", initialMode: "TEMPLATE", template: solution })}>复制为新方案</button>
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
        key={dialog ? `${dialog.kind}-${dialog.kind === "create" ? `${dialog.initialMode}-${dialog.template?.solution_id ?? "blank"}` : dialog.solution.solution_id}` : "closed"}
        state={dialog}
        solutions={solutions}
        busy={isBusy}
        error={dialog && actionError instanceof Error ? actionError.message : null}
        onClose={() => !isBusy && setDialog(null)}
        onCreate={(input) => create.mutate(input)}
        onUpdate={(solution, input) => update.mutate({ solution, input })}
        onDelete={(solution) => remove.mutate(solution.solution_id)}
      />
    </div>
  );
}
