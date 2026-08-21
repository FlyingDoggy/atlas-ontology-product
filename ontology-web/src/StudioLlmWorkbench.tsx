import { useEffect, useMemo, useState } from "react";

import type {
  StudioLlmStatus,
  StudioObservationDisposition,
  StudioObservationList,
  StudioObservationSet,
  StudioSlotValue,
} from "./api";

type ReviewAction = "ACCEPT" | "EDIT" | "REJECT";

function slotValueText(value: StudioSlotValue | null): string {
  if (!value) return "—";
  if (value.kind === "STRING") return value.string_value ?? "";
  if (value.kind === "BOOLEAN") return value.boolean_value ? "true" : "false";
  return (value.string_list_value ?? []).join(", ");
}

function editedSlotValue(original: StudioSlotValue, raw: string): StudioSlotValue {
  if (original.kind === "BOOLEAN") {
    return { kind: "BOOLEAN", string_value: null, boolean_value: raw === "true", string_list_value: null };
  }
  if (original.kind === "STRING_LIST") {
    return {
      kind: "STRING_LIST",
      string_value: null,
      boolean_value: null,
      string_list_value: [...new Set(raw.split(",").map((item) => item.trim()).filter(Boolean))],
    };
  }
  return { kind: "STRING", string_value: raw.trim(), boolean_value: null, string_list_value: null };
}

export function StudioLlmWorkbench({
  status,
  observationSets,
  currentRevision,
  busy,
  error,
  onGenerate,
  onReview,
}: {
  status: StudioLlmStatus | null;
  observationSets: StudioObservationList["observation_sets"];
  currentRevision: number;
  busy: "generate" | "review" | null;
  error: string | null;
  onGenerate: () => void;
  onReview: (dispositions: StudioObservationDisposition[]) => void;
}) {
  const activeRecord = observationSets.find((item) => item.decision === null) ?? observationSets[0] ?? null;
  const hasPendingSet = observationSets.some((item) => item.decision === null);
  const activeSet = activeRecord?.observation_set ?? null;
  const initialActions = useMemo(() => Object.fromEntries(
    (activeSet?.observations ?? []).map((item) => [item.observation_id, item.status === "MISSING" ? "REJECT" : "ACCEPT"]),
  ) as Record<string, ReviewAction>, [activeSet]);
  const initialInputs = useMemo(() => Object.fromEntries(
    (activeSet?.observations ?? []).map((item) => [item.observation_id, slotValueText(item.value)]),
  ), [activeSet]);
  const [actions, setActions] = useState<Record<string, ReviewAction>>(initialActions);
  const [editedInputs, setEditedInputs] = useState<Record<string, string>>(initialInputs);

  useEffect(() => {
    setActions(initialActions);
    setEditedInputs(initialInputs);
  }, [activeSet?.observation_set_id, initialActions, initialInputs]);

  function submit(set: StudioObservationSet) {
    onReview(set.observations.map((observation) => {
      const action = actions[observation.observation_id] ?? (observation.status === "MISSING" ? "REJECT" : "ACCEPT");
      if (action === "EDIT" && observation.value) {
        return {
          observation_id: observation.observation_id,
          action,
          reason_code: "REVIEWER_CORRECTION",
          edited_value: editedSlotValue(observation.value, editedInputs[observation.observation_id] ?? ""),
        };
      }
      if (action === "REJECT") {
        return {
          observation_id: observation.observation_id,
          action,
          reason_code: observation.status === "MISSING" ? "KEEP_MISSING" : "NOT_SUPPORTED",
          edited_value: null,
        };
      }
      return {
        observation_id: observation.observation_id,
        action: "ACCEPT",
        reason_code: "SOURCE_SUPPORTED",
        edited_value: null,
      };
    }));
  }

  return (
    <section className="studio-llm-workbench" aria-labelledby="studio-llm-heading">
      <header>
        <div>
          <span>BOUNDED LLM CO-AUTHORING</span>
          <h2 id="studio-llm-heading">材料观察与人工复核</h2>
          <p>LLM 只读取获准的字段投影并形成候选观察；唯一能修改 Draft 的动作是下面这次人工 disposition。</p>
        </div>
        <dl>
          <div><dt>Provider / model</dt><dd>{status?.installed ? `${status.provider} · ${status.requested_model}` : "Not installed"}</dd></div>
          <div><dt>Mode</dt><dd>{status?.mode ?? "unavailable"}</dd></div>
          <div><dt>Draft</dt><dd>r{currentRevision}</dd></div>
          <div><dt>Publish authority</dt><dd>{status?.can_publish ? "MODEL" : "HUMAN ONLY"}</dd></div>
        </dl>
      </header>
      <div className="studio-llm-boundary">
        <div><b>{status?.label ?? "当前 solution 未安装 Studio LLM profile"}</b><p>{hasPendingSet ? "当前 Draft 已有一组待复核 Observation；完成或拒绝前不会再次外发模型请求。" : status?.installed ? "即使五个槽位全部有值，也必须逐条复核；生成 observation 本身不会改变 revision。" : "该 package 仍可使用确定性的完整 Studio 工作台；需要模型协作时安装 package-owned LLM profile。"}</p></div>
        <button type="button" disabled={!status?.installed || status.mode === "off" || hasPendingSet || busy !== null} onClick={onGenerate}>
          {busy === "generate" ? "正在分析获准材料…" : "生成一组候选 Observation"}
        </button>
      </div>

      {activeSet ? (
        <div className="observation-review">
          <div className="observation-review-heading">
            <div><span>OBSERVATION SET</span><code>{activeSet.observation_set_id}</code></div>
            <div><span>BASE REVISION</span><b>r{activeSet.base_revision}</b></div>
            <div><span>MODEL RESPONSE</span><b>{activeSet.response_model}</b></div>
            <div><span>STATE</span><b>{activeRecord?.decision?.status ?? "AWAITING REVIEW"}</b></div>
          </div>
          <ol>
            {activeSet.observations.map((observation, index) => {
              const action = actions[observation.observation_id] ?? (observation.status === "MISSING" ? "REJECT" : "ACCEPT");
              const sourceField = observation.source_anchor && typeof observation.source_anchor.field === "string"
                ? observation.source_anchor.field
                : null;
              return (
                <li key={observation.observation_id} className={observation.status === "MISSING" ? "is-missing" : ""}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div className="observation-subject">
                    <code>{observation.slot_id}</code>
                    <strong>{slotValueText(observation.value)}</strong>
                    <small>{sourceField ? `SOURCE ANCHOR · ${sourceField}` : "MISSING SOURCE"}</small>
                  </div>
                  <label>Human disposition
                    <select
                      aria-label={`Disposition ${observation.slot_id}`}
                      value={action}
                      disabled={Boolean(activeRecord?.decision) || observation.status === "MISSING"}
                      onChange={(event) => setActions((current) => ({ ...current, [observation.observation_id]: event.target.value as ReviewAction }))}
                    >
                      {observation.status === "PROPOSED" ? <><option value="ACCEPT">Accept supported value</option><option value="EDIT">Edit as reviewer</option><option value="REJECT">Reject</option></> : <option value="REJECT">Keep missing</option>}
                    </select>
                  </label>
                  {action === "EDIT" && observation.value ? (
                    <label className="observation-edit">Reviewer value
                      {observation.value.kind === "BOOLEAN" ? (
                        <select aria-label={`Edited value ${observation.slot_id}`} value={editedInputs[observation.observation_id]} onChange={(event) => setEditedInputs((current) => ({ ...current, [observation.observation_id]: event.target.value }))}><option value="true">true</option><option value="false">false</option></select>
                      ) : (
                        <textarea aria-label={`Edited value ${observation.slot_id}`} rows={2} value={editedInputs[observation.observation_id]} onChange={(event) => setEditedInputs((current) => ({ ...current, [observation.observation_id]: event.target.value }))} />
                      )}
                    </label>
                  ) : null}
                </li>
              );
            })}
          </ol>
          <footer>
            <p>提交后形成 immutable Decision，并以 observation set 的 base revision 做 CAS；过期 Draft 会被拒绝。</p>
            <button type="button" disabled={Boolean(activeRecord?.decision) || busy !== null || activeSet.base_revision !== currentRevision} onClick={() => submit(activeSet)}>
              {busy === "review" ? "应用中…" : activeRecord?.decision ? "本组已复核" : "应用人工复核到 Draft"}
            </button>
          </footer>
        </div>
      ) : (
        <div className="observation-empty"><span>NO OBSERVATION SET</span><p>当前还没有调用模型；Draft 保持不变。</p></div>
      )}
      {error ? <p className="operator-error" role="alert">{error}</p> : null}
    </section>
  );
}
