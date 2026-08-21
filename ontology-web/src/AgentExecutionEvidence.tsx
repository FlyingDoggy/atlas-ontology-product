import type { SolutionAnalysis } from "./api";

function text(value: unknown, fallback = "—"): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}

function shortDigest(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

export function AgentExecutionEvidence({ result }: { result: SolutionAnalysis }) {
  if (result.status !== "ANSWERED" || !result.plan || !result.snapshot_checksum) return null;
  const executionByStep = new Map(result.steps.map((item) => [item.step_id, item]));

  return (
    <section className="execution-evidence" aria-labelledby="execution-evidence-heading">
      <header>
        <div>
          <span>TRACEABLE EXECUTION</span>
          <h3 id="execution-evidence-heading">执行计划与证据</h3>
          <p>计划、执行状态和 claim 都绑定到同一个 active snapshot；这里不把模型文字当作计算事实。</p>
        </div>
        <dl>
          <div><dt>Plan</dt><dd>{result.plan.plan_id}</dd></div>
          <div><dt>Plan hash</dt><dd>{shortDigest(result.plan.plan_hash)}</dd></div>
          <div><dt>Snapshot</dt><dd>{shortDigest(result.snapshot_checksum)}</dd></div>
        </dl>
      </header>

      <div className="execution-evidence-grid">
        <section className="execution-steps">
          <h4>Plan → execution</h4>
          <ol>
            {result.plan.steps.map((planned, index) => {
              const stepId = text(planned.step_id, `step.${index + 1}`);
              const executed = executionByStep.get(stepId);
              return (
                <li key={`${stepId}:${index}`}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <code>{stepId}</code>
                    <p>{text(planned.operation, text(planned.description, "Governed plan step"))}</p>
                  </div>
                  <b className={`is-${(executed?.status ?? "SKIPPED").toLowerCase()}`}>{executed?.status ?? "NOT RUN"}</b>
                </li>
              );
            })}
          </ol>
        </section>

        <section className="model-boundary-card">
          <h4>Model boundary</h4>
          <strong>{result.llm.status === "GROUNDED" ? "QWEN GROUNDED" : result.llm.status.replaceAll("_", " ")}</strong>
          <dl>
            <div><dt>Mode</dt><dd>{result.llm.mode}</dd></div>
            <div><dt>Model</dt><dd>{result.llm.requested_model}</dd></div>
            <div><dt>Calls</dt><dd>{result.llm.provider_call_count}</dd></div>
            <div><dt>Fallback</dt><dd>{result.llm.fallback_used ? "YES" : "NO"}</dd></div>
          </dl>
          <p>{result.llm.model_called ? "LLM 参与受约束的语义 grounding；结果事实来自已登记工具。" : "本次执行未调用外部模型。"}</p>
        </section>
      </div>

      <section className="claim-ledger">
        <div><h4>Released claim ledger</h4><span>{result.evidence.length} claims</span></div>
        {result.evidence.map((claim) => (
          <article key={claim.claim_id}>
            <span className="proof-mark" aria-hidden="true">✓</span>
            <div><code>{claim.claim_id}</code><strong>{claim.display_value}</strong></div>
            <div><small>Result path</small><code>{claim.result_path}</code></div>
            <div><small>Dataset</small><code>{shortDigest(claim.dataset_checksum)}</code></div>
          </article>
        ))}
      </section>
    </section>
  );
}
