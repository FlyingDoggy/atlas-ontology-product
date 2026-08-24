import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, Link, RouterProvider } from "react-router-dom";

import { constructionRunListSchema, type ConstructionReviewDecision, type ConstructionRunList } from "./api";
import { ConstructionReviewCenter, ConstructionRunsView } from "./StudioConstructionViews";


const digest = "a".repeat(64);

function runList(): ConstructionRunList {
  return {
    contract: "construction-run-list/v1",
    workspace_id: "workspace.adt.reference",
    engine_configured: true,
    runs: [{
      decision: null,
      run: {
        contract: "construction-run/v1",
        run_id: `construction-run.${"b".repeat(32)}`,
        attempt_id: `construction-attempt.${"c".repeat(32)}`,
        lease_epoch: 1,
        workspace_id: "workspace.adt.reference",
        solution_id: "ontology.exchange_analytics.adt",
        base_revision: 4,
        base_draft_checksum: digest,
        source_set_digest: digest,
        profile_ref: "construction-profile.source-and-semantica/v1",
        status: "NEEDS_REVIEW",
        engine_status: "COMPLETED",
        selected_sources: [{
          contract: "construction-source-settlement/v1",
          source_id: "asset.metric_logic",
          source_checksum: digest,
          locator: "input/metric_logic.md",
          source_kind: "metric_transcription",
          outcome: "SETTLED",
          detail: "Exact source settled.",
        }],
        stage_receipts: [{
          contract: "construction-stage-receipt/v1",
          stage: "STRUCTURED_EXTRACTION",
          status: "PASS",
          input_digest: digest,
          output_digest: digest,
          item_count: 2,
          implementation: "test",
          detail: "two candidates",
        }, {
          contract: "construction-stage-receipt/v1",
          stage: "PACKAGED_CASE_COMPILATION",
          status: "PASS",
          input_digest: digest,
          output_digest: digest,
          item_count: 1,
          implementation: "packaged-profile-test",
          detail: "packaged profile matched",
        }],
        candidates: [
          {
            contract: "construction-candidate/v1",
            candidate_id: `candidate.${"d".repeat(32)}`,
            occurrence_key: digest,
            revision_digest: digest,
            candidate_type: "METRIC",
            label: "平均每日成交额",
            definition: "同期合资格成交额除以交易日数",
            support_class: "DIRECT_EXACT",
            risk_class: "HIGH",
            review_status: "UNREVIEWED",
            compile_eligible: true,
            canonical_target: "metric.average_daily_turnover",
            proposal: { metric_key: "M-03" },
            proposed_operation: {
              action: "UPSERT",
              collection: "metrics",
              object_id: "metric.average_daily_turnover",
              payload: { id: "metric.average_daily_turnover" },
            },
            source_anchors: [{
              contract: "source-anchor/v1",
              source_id: "asset.metric_logic",
              source_checksum: digest,
              locator_kind: "MARKDOWN_TABLE_ROW",
              locator: "row=M-03;line=9",
              line_number: 9,
              snippet_checksum: digest,
            }],
            impact_refs: ["metric.average_daily_turnover"],
            limitations: [],
            draft_diff: {
              contract: "candidate-draft-diff/v1",
              change_type: "UPDATE",
              before: { id: "metric.average_daily_turnover", definition: "Old" },
              after: { id: "metric.average_daily_turnover", definition: "New" },
              changed_paths: ["definition"],
            },
          },
          {
            contract: "construction-candidate/v1",
            candidate_id: `candidate.${"e".repeat(32)}`,
            occurrence_key: "f".repeat(64),
            revision_digest: "f".repeat(64),
            candidate_type: "METRIC",
            label: "订单取消率",
            definition: "取消订单占全部订单比例",
            support_class: "DIRECT_EXACT",
            risk_class: "HIGH",
            review_status: "UNREVIEWED",
            compile_eligible: false,
            canonical_target: null,
            proposal: { metric_key: "M-06" },
            proposed_operation: null,
            source_anchors: [],
            impact_refs: [],
            limitations: ["No supported Formula/Query compiler mapping exists yet."],
            draft_diff: {
              contract: "candidate-draft-diff/v1",
              change_type: "NON_COMPILABLE",
              before: null,
              after: null,
              changed_paths: [],
            },
          },
        ],
        machine_findings: [{
          contract: "reviewer-finding/v1",
          finding_id: "finding.model.missing_formula",
          finding_type: "MISSING_COVERAGE",
          severity: "ERROR",
          summary: "缺少公式合同",
          detail: "候选没有可编译公式。",
          candidate_ids: [`candidate.${"e".repeat(32)}`],
          evidence_fragment_ids: [],
          finding_authority: "DETERMINISTIC",
          blocks_release: true,
          recommendation: "补齐公式后重新构建。",
        }],
        started_at: "2026-08-21T01:00:00Z",
        completed_at: "2026-08-21T01:00:01Z",
        run_checksum: digest,
      },
    }],
  };
}

const solutionId = "ontology.exchange_analytics.adt";

function renderReview(element: React.ReactElement, withExit = false) {
  const router = createMemoryRouter([{
    path: "*",
    element: <>{element}{withExit ? <Link to="/ontology-studio/solutions/">离开复核中心</Link> : null}</>,
  }], { initialEntries: [`/ontology-studio/solutions/${solutionId}/construction/review/`] });
  return { router, ...render(<RouterProvider router={router} />) };
}

afterEach(cleanup);

describe("Studio construction product views", () => {
  it("accepts the backend run contract without duplicating job-only source version ids", () => {
    expect(constructionRunListSchema.safeParse(runList()).success).toBe(true);
  });

  it("accepts scenario candidates and explicit Reviewer authority from agentic runs", () => {
    const payload = runList();
    payload.runs[0].run.candidates[0] = {
      ...payload.runs[0].run.candidates[0],
      candidate_type: "SCENARIO",
      canonical_target: "scenario.cash_trading",
      proposed_operation: {
        action: "UPSERT",
        collection: "scenario",
        object_id: "scenario.cash_trading",
        payload: { id: "scenario.cash_trading" },
      },
    };

    expect(constructionRunListSchema.safeParse(payload).success).toBe(true);
  });

  it("never disguises a construction contract failure as an empty result", () => {
    renderReview(<ConstructionReviewCenter solutionId={solutionId} runs={null} reviewDraft={null} currentRevision={4} busy={false} error="Construction runs 未通过客户端合同校验。" onSave={vi.fn().mockResolvedValue(null)} onReview={vi.fn()} />);

    expect(screen.getByRole("alert").textContent).toContain("候选集合读取失败");
    expect(screen.queryByText("没有待复核的候选")).toBeNull();
  });

  it("shows exact stages, sources and candidate denominator", () => {
    render(<ConstructionRunsView runs={runList()} jobs={null} sources={[]} currentRevision={4} busy={false} error={null} onStart={vi.fn()} onCancel={vi.fn()} onRetry={vi.fn()} />);

    expect(screen.getByText("自动构建运行")).toBeTruthy();
    expect(screen.getByText("1 个来源已结算")).toBeTruthy();
    expect(screen.getByText("2 个候选待复核")).toBeTruthy();
    expect(screen.getByText("结构化提取")).toBeTruthy();
    expect(screen.getByText("Semantica 已连接 · 案例编译档已匹配")).toBeTruthy();
  });

  it("starts every candidate undecided and never accepts unsupported items", () => {
    const onReview = vi.fn();
    const onSave = vi.fn().mockResolvedValue(null);
    renderReview(<ConstructionReviewCenter solutionId={solutionId} runs={runList()} reviewDraft={null} currentRevision={4} busy={false} error={null} onSave={onSave} onReview={onReview} />);

    const selects = screen.getAllByLabelText(/复核动作/);
    expect(selects).toHaveLength(2);
    expect((selects[0] as HTMLSelectElement).value).toBe("UNREVIEWED");
    expect((selects[1] as HTMLSelectElement).value).toBe("UNREVIEWED");
    expect((screen.getByRole("button", { name: "完成本轮复核并应用" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(selects[0], { target: { value: "ACCEPT" } });
    fireEvent.change(selects[1], { target: { value: "DEFER" } });
    fireEvent.click(screen.getByRole("button", { name: "保存复核进度" }));

    expect(onSave).toHaveBeenCalledOnce();
    expect(onSave.mock.calls[0][1].map((item: { action: string }) => item.action)).toEqual(["ACCEPT", "DEFER"]);
    expect(onReview).not.toHaveBeenCalled();
  });

  it("shows machine findings and a Candidate-to-Draft comparison without auto-deciding", () => {
    renderReview(<ConstructionReviewCenter solutionId={solutionId} runs={runList()} reviewDraft={null} currentRevision={4} busy={false} error={null} onSave={vi.fn().mockResolvedValue(null)} onReview={vi.fn()} />);

    expect(screen.getByText("Candidate 与当前 Draft")).toBeTruthy();
    expect(screen.getByText("1 处变化")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /订单取消率/ }));
    expect(screen.getByText("缺少公式合同")).toBeTruthy();
    expect(screen.getByText("ERROR · 阻断发布")).toBeTruthy();
    expect((screen.getAllByLabelText(/复核动作/)[1] as HTMLSelectElement).value).toBe("UNREVIEWED");
  });

  it("can fill a conservative batch disposition without submitting a human decision", () => {
    const onReview = vi.fn();
    const onSave = vi.fn().mockResolvedValue(null);
    renderReview(<ConstructionReviewCenter solutionId={solutionId} runs={runList()} reviewDraft={null} currentRevision={4} busy={false} error={null} onSave={onSave} onReview={onReview} />);

    fireEvent.click(screen.getByRole("button", { name: "本页填入保守建议" }));
    const selects = screen.getAllByLabelText(/复核动作/);
    expect((selects[0] as HTMLSelectElement).value).toBe("ACCEPT");
    expect((selects[1] as HTMLSelectElement).value).toBe("DEFER");
    expect(onSave).not.toHaveBeenCalled();
    expect(onReview).not.toHaveBeenCalled();
    expect(screen.getByText("只处理当前 2 项，不保存、不发布、不激活")).toBeTruthy();
  });

  it("turns a human edit into an explicit typed EDIT disposition", () => {
    const onReview = vi.fn();
    const onSave = vi.fn().mockResolvedValue(null);
    renderReview(<ConstructionReviewCenter solutionId={solutionId} runs={runList()} reviewDraft={null} currentRevision={4} busy={false} error={null} onSave={onSave} onReview={onReview} />);
    const selects = screen.getAllByLabelText(/复核动作/);
    fireEvent.change(selects[0], { target: { value: "EDIT" } });
    const operation = screen.getByLabelText("修改 typed operation 平均每日成交额");
    fireEvent.change(operation, { target: { value: JSON.stringify({
      action: "UPSERT",
      collection: "metrics",
      object_id: "metric.average_daily_turnover",
      payload: { id: "metric.average_daily_turnover", definition: "人工确认后的 ADT 定义" },
    }) } });
    fireEvent.change(selects[1], { target: { value: "REJECT" } });
    fireEvent.click(screen.getByRole("button", { name: "保存复核进度" }));

    expect(onSave).toHaveBeenCalledOnce();
    expect(onSave.mock.calls[0][1][0]).toEqual(expect.objectContaining({
      action: "EDIT",
      edited_operation: expect.objectContaining({
        payload: expect.objectContaining({ definition: "人工确认后的 ADT 定义" }),
      }),
    }));
  });

  it("guards unsaved review dispositions when navigating away", () => {
    renderReview(<ConstructionReviewCenter solutionId={solutionId} runs={runList()} reviewDraft={null} currentRevision={4} busy={false} error={null} onSave={vi.fn().mockResolvedValue(null)} onReview={vi.fn()} />, true);
    fireEvent.change(screen.getAllByLabelText(/复核动作/)[0], { target: { value: "ACCEPT" } });
    fireEvent.click(screen.getByRole("link", { name: "离开复核中心" }));

    expect(screen.getByRole("dialog", { name: "离开前是否保留当前修改？" })).toBeTruthy();
    expect((screen.getAllByLabelText(/复核动作/)[0] as HTMLSelectElement).value).toBe("ACCEPT");
    fireEvent.click(screen.getByRole("button", { name: "继续复核" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("adopts the exact save response immediately and does not report a false unsaved state", async () => {
    const onSave = vi.fn().mockImplementation(async (runId: string, dispositions: Array<Record<string, unknown>>) => ({
      contract: "construction-review-draft/v1" as const,
      run_id: runId,
      run_checksum: digest,
      workspace_id: "workspace.adt.reference",
      base_revision: 4,
      review_revision: 1,
      reviewer: "domain-owner.demo",
      dispositions,
      status: "DRAFT" as const,
      submitted_batch_checksum: null,
      final_decision_id: null,
      updated_at: "2026-08-22T05:00:00Z",
      batch_checksum: digest,
    }));
    renderReview(<ConstructionReviewCenter solutionId={solutionId} runs={runList()} reviewDraft={null} currentRevision={4} busy={false} error={null} onSave={onSave} onReview={vi.fn()} />, true);
    const selects = screen.getAllByLabelText(/复核动作/);
    fireEvent.change(selects[0], { target: { value: "ACCEPT" } });
    fireEvent.change(selects[1], { target: { value: "DEFER" } });
    fireEvent.click(screen.getByRole("button", { name: "保存复核进度" }));

    await waitFor(() => expect(screen.getByText("所有候选均已保存复核动作")).toBeTruthy());
    fireEvent.click(screen.getByRole("link", { name: "离开复核中心" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders the authoritative v2 application receipt instead of calling execution complete", () => {
    const decision: ConstructionReviewDecision = {
      contract: "construction-review-decision/v2",
      decision_id: `construction-decision.${"f".repeat(32)}`,
      run_id: runList().runs[0].run.run_id,
      run_checksum: digest,
      workspace_id: "workspace.adt.reference",
      base_revision: 4,
      base_draft_checksum: digest,
      reviewer: "hkex.domain.owner",
      dispositions: [],
      review_batch_checksum: digest,
      request_digest: digest,
      status: "APPLIED_WITH_DEFERRED",
      resulting_revision: 5,
      resulting_draft_checksum: digest,
      applied: [{
        candidate_id: `candidate.${"d".repeat(32)}`,
        collection: "metrics",
        object_id: "metric.average_daily_turnover",
        change_type: "UPDATE",
        changed_paths: ["definition"],
        previous_asset_digest: digest,
        reviewed_content_digest: digest,
        final_confirmed_asset_digest: digest,
        confirmation_status: "CONFIRMED",
      }],
      deferred_candidate_ids: [`candidate.${"e".repeat(32)}`],
      rejected_candidate_ids: [],
      server_blockers: [`DEFERRED_HIGH_RISK:candidate.${"e".repeat(32)}`],
      decided_at: "2026-08-22T05:00:00Z",
      decision_checksum: digest,
    };
    renderReview(<ConstructionReviewCenter solutionId={solutionId} requestedRunId={decision.run_id} requestedDecisionId={decision.decision_id} decision={decision} runs={runList()} reviewDraft={null} currentRevision={5} busy={false} error={null} onSave={vi.fn()} onReview={vi.fn()} />);

    expect(screen.getByText("已生成 Draft r5")).toBeTruthy();
    expect(screen.getByText("metric.average_daily_turnover")).toBeTruthy();
    expect(screen.getByText("已确认")).toBeTruthy();
    expect(screen.getByRole("link", { name: "验证新 Draft" })).toBeTruthy();
  });
});
