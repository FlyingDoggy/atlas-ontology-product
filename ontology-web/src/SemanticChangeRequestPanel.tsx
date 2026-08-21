import { useState } from "react";

import type {
  SemanticChangeRequestInput,
  SemanticChangeRequestType,
  SolutionAnalysis,
} from "./api";

const requestTypes: Array<{ id: SemanticChangeRequestType; label: string }> = [
  { id: "MISSING_CONCEPT", label: "缺少业务概念" },
  { id: "WRONG_DEFINITION", label: "定义可能不准确" },
  { id: "MISSING_RELATIONSHIP", label: "缺少 Object / Link" },
  { id: "METRIC_LOGIC", label: "指标逻辑需复核" },
  { id: "DATA_BINDING", label: "数据绑定需复核" },
  { id: "ANALYSIS_CAPABILITY", label: "缺少分析能力" },
  { id: "OTHER", label: "其他语义反馈" },
];

export function SemanticChangeRequestPanel({
  result,
  busy,
  error,
  submittedId,
  onSubmit,
}: {
  result: SolutionAnalysis;
  busy: boolean;
  error: string | null;
  submittedId: string | null;
  onSubmit: (request: SemanticChangeRequestInput) => void;
}) {
  const [open, setOpen] = useState(false);
  const [requestType, setRequestType] = useState<SemanticChangeRequestType>("ANALYSIS_CAPABILITY");
  const [title, setTitle] = useState("");
  const [observation, setObservation] = useState("");
  const [proposedChange, setProposedChange] = useState("");
  const [claimRefs, setClaimRefs] = useState(
    result.evidence.map((item) => item.claim_id),
  );
  if (result.status !== "ANSWERED" || !result.execution_id || !result.snapshot_checksum) return null;

  function submit() {
    if (!result.execution_id || !result.snapshot_checksum) return;
    onSubmit({
      execution_id: result.execution_id,
      snapshot_checksum: result.snapshot_checksum,
      request_type: requestType,
      title,
      observation,
      proposed_change: proposedChange,
      claim_refs: claimRefs,
    });
  }

  if (!open) {
    return <button className="open-scr" type="button" onClick={() => setOpen(true)}>反馈语义缺口</button>;
  }
  return (
    <section className="semantic-change-panel" aria-labelledby="semantic-change-heading">
      <header><div><span>AGENT → STUDIO</span><h3 id="semantic-change-heading">Semantic Change Request</h3><p>这是待分流的 proposed input，不会自动修改 Ontology 或成为业务真相。</p></div><button type="button" onClick={() => setOpen(false)}>关闭</button></header>
      <div className="semantic-change-fields">
        <label>Request type<select aria-label="Request type" value={requestType} onChange={(event) => setRequestType(event.target.value as SemanticChangeRequestType)}>{requestTypes.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label>
        <label>标题<input aria-label="标题" minLength={3} required value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <label className="is-wide">观察<textarea aria-label="观察" minLength={3} required rows={3} value={observation} onChange={(event) => setObservation(event.target.value)} /></label>
        <label className="is-wide">建议变更<textarea aria-label="建议变更" minLength={3} required rows={3} value={proposedChange} onChange={(event) => setProposedChange(event.target.value)} /></label>
      </div>
      <fieldset className="claim-selector"><legend>绑定本次执行证据</legend>{result.evidence.map((item) => <label key={item.claim_id}><input type="checkbox" checked={claimRefs.includes(item.claim_id)} onChange={() => setClaimRefs((current) => current.includes(item.claim_id) ? current.filter((id) => id !== item.claim_id) : [...current, item.claim_id])} /><code>{item.claim_id}</code><span>{item.display_value}</span></label>)}</fieldset>
      <footer><div><code>{result.execution_id}</code><code>{result.snapshot_checksum.slice(0, 12)}…</code></div><button type="button" disabled={busy || title.trim().length < 3 || observation.trim().length < 3 || proposedChange.trim().length < 3 || claimRefs.length === 0} onClick={submit}>{busy ? "提交中…" : "提交为 Proposed Request"}</button></footer>
      {submittedId ? <p className="scr-success">已进入 Studio inbox：<code>{submittedId}</code></p> : null}
      {error ? <p className="operator-error" role="alert">{error}</p> : null}
    </section>
  );
}
