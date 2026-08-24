import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SolutionAnalysis } from "./api";
import { AgentExecutionEvidence } from "./AgentExecutionEvidence";

const digest = "a".repeat(64);

const result: SolutionAnalysis = {
  status: "ANSWERED",
  answer: "ADT increased by 3.2%.",
  conversation_id: `conversation.${"1".repeat(32)}`,
  turn_id: `turn.${"2".repeat(32)}`,
  turn_index: 1,
  parent_execution_id: null,
  execution_id: `exec.${"b".repeat(32)}`,
  snapshot_checksum: digest,
  plan: {
    plan_id: "plan.adt.delta",
    intent: "compare_periods",
    question: "Why did ADT change?",
    snapshot_checksum: digest,
    steps: [
      { step_id: "resolve_metric", operation: "Resolve the governed ADT metric" },
      { step_id: "compute_delta", operation: "Compute exact period delta" },
    ],
    plan_hash: "c".repeat(64),
  },
  steps: [
    { step_id: "resolve_metric", status: "PASS" },
    { step_id: "compute_delta", status: "PASS" },
  ],
  facts: { change_pct: 3.2 },
  evidence: [
    {
      claim_id: "claim.adt.change_pct",
      display_value: "3.2%",
      result_path: "$.facts.change_pct",
      dataset_checksum: "d".repeat(64),
    },
  ],
  boundary_code: null,
  llm: {
    contract: "solution-llm-execution/v1",
    mode: "ACTIVE",
    status: "GROUNDED",
    provider: "qwen",
    requested_model: "qwen3.8-max",
    model_called: true,
    provider_call_count: 1,
    fallback_used: false,
    reason_code: null,
    profile_checksum: "e".repeat(64),
    activation_id: "activation.adt.demo",
  },
};

describe("AgentExecutionEvidence", () => {
  it("makes the execution plan, exact evidence and model boundary visible without a JSON dump", () => {
    render(<AgentExecutionEvidence result={result} />);

    expect(screen.getByRole("heading", { name: "执行计划与证据" })).toBeTruthy();
    expect(screen.getByText("resolve_metric")).toBeTruthy();
    expect(screen.getByText("claim.adt.change_pct")).toBeTruthy();
    expect(screen.getByText("QWEN GROUNDED")).toBeTruthy();
    expect(screen.getByText("$.facts.change_pct")).toBeTruthy();
    expect(screen.getByText(/cccccccccc/)).toBeTruthy();
  });
});
