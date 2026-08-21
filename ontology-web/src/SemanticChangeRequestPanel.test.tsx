import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SolutionAnalysis } from "./api";
import { SemanticChangeRequestPanel } from "./SemanticChangeRequestPanel";

const result = {
  status: "ANSWERED",
  execution_id: `exec.${"a".repeat(32)}`,
  snapshot_checksum: "b".repeat(64),
  evidence: [
    { claim_id: "claim.metric.delta", display_value: "12.0", result_path: "/facts/delta", dataset_checksum: "c".repeat(64) },
  ],
} as unknown as SolutionAnalysis;

afterEach(cleanup);

describe("SemanticChangeRequestPanel", () => {
  it("submits a proposed, evidence-bound request without changing ontology", () => {
    const onSubmit = vi.fn();
    render(<SemanticChangeRequestPanel result={result} busy={false} error={null} submittedId={null} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByRole("button", { name: "反馈语义缺口" }));
    fireEvent.change(screen.getByLabelText("Request type"), { target: { value: "MISSING_RELATIONSHIP" } });
    fireEvent.change(screen.getByLabelText("标题"), { target: { value: "缺少成交与证券关系" } });
    fireEvent.change(screen.getByLabelText("观察"), { target: { value: "当前分析无法从成交穿透到证券类别。" } });
    fireEvent.change(screen.getByLabelText("建议变更"), { target: { value: "请在 Studio 复核 Trade-to-Instrument Link。" } });
    fireEvent.click(screen.getByRole("button", { name: "提交为 Proposed Request" }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      execution_id: result.execution_id,
      snapshot_checksum: result.snapshot_checksum,
      request_type: "MISSING_RELATIONSHIP",
      claim_refs: ["claim.metric.delta"],
    }));
  });
});
