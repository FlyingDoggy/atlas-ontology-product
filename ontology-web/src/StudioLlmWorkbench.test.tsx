import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StudioLlmStatus, StudioObservationSet } from "./api";
import { StudioLlmWorkbench } from "./StudioLlmWorkbench";

const digest = "a".repeat(64);
afterEach(cleanup);
const status: StudioLlmStatus = {
  installed: true,
  demo_class: "STUDIO_LLM_ENGINEERING_DEMO",
  mode: "active-observation-canary",
  provider: "qwen",
  requested_model: "qwen3.8-max",
  workflow: "CLEARED_INPUT_TO_HUMAN_REVIEWED_DRAFT",
  slot_count: 5,
  label: "PROPOSED observations · not published ontology",
  can_publish: false,
};

function observationSet(): StudioObservationSet {
  const slots = [
    ["metric.definition", "STRING", "Current metric definition"],
    ["eligibility.include_status", "STRING", "TRADED"],
    ["eligibility.exclude_cancelled", "BOOLEAN", true],
    ["metric.allowed_dimensions", "STRING_LIST", ["participant", "instrument"]],
    ["mapping.amount", "MISSING", null],
  ] as const;
  return {
    contract: "studio-observation-set/v1",
    observation_set_id: `observation-set.${"1".repeat(32)}`,
    run_id: `studio-run.${"2".repeat(32)}`,
    workspace_id: "workspace.adt.reference",
    base_revision: 4,
    base_draft_checksum: digest,
    intake_checksum: digest,
    profile_digest: digest,
    slot_manifest_digest: digest,
    egress_decision_digest: digest,
    projection_digest: digest,
    requested_model: "qwen3.8-max",
    response_model: "qwen3.8-max",
    provider_request_id: "provider.1",
    created_at: "2026-08-20T00:00:00Z",
    projection: { contract: "studio-cleared-input-projection/v1" },
    observations: slots.map(([slotId, kind, value], index) => ({
      observation_id: `observation.${"3".repeat(32)}.${String(index + 1).padStart(2, "0")}`,
      slot_id: slotId,
      status: kind === "MISSING" ? "MISSING" as const : "PROPOSED" as const,
      support_code: kind === "MISSING" ? "MISSING_SOURCE" as const : "DIRECT_SOURCE" as const,
      value: kind === "MISSING" ? null : {
        kind,
        string_value: kind === "STRING" ? value as string : null,
        boolean_value: kind === "BOOLEAN" ? value as boolean : null,
        string_list_value: kind === "STRING_LIST" ? [...value as readonly string[]] : null,
      },
      source_anchor: kind === "MISSING" ? null : { field: slotId, asset_id: "asset.requirements" },
      source_fragment_checksum: kind === "MISSING" ? null : digest,
    })),
    observation_set_checksum: digest,
  };
}

describe("StudioLlmWorkbench", () => {
  it("shows a clean disabled capability state when the selected package has no LLM profile", () => {
    render(<StudioLlmWorkbench
      status={{
        installed: false,
        demo_class: "STUDIO_LLM_ENGINEERING_DEMO",
        mode: "off",
        provider: null,
        requested_model: null,
        workflow: "NOT_INSTALLED",
        slot_count: 0,
        label: "当前 solution 未安装 Studio LLM profile",
        can_publish: false,
      }}
      observationSets={[]}
      currentRevision={1}
      busy={null}
      error={null}
      onGenerate={vi.fn()}
      onReview={vi.fn()}
    />);

    expect(screen.getByText("当前 solution 未安装 Studio LLM profile")).toBeTruthy();
    expect(screen.getByText("Not installed")).toBeTruthy();
    expect(screen.getByRole("button", { name: "生成一组候选 Observation" }).hasAttribute("disabled")).toBe(true);
  });

  it("keeps Qwen observations visibly proposed and requires an ordered human disposition", () => {
    const onReview = vi.fn();
    render(<StudioLlmWorkbench
      status={status}
      observationSets={[{ observation_set: observationSet(), decision: null }]}
      currentRevision={4}
      busy={null}
      error={null}
      onGenerate={vi.fn()}
      onReview={onReview}
    />);

    expect(screen.getByText("qwen3.8-max")).toBeTruthy();
    expect(screen.getByText("PROPOSED observations · not published ontology")).toBeTruthy();
    expect(screen.getByText("mapping.amount")).toBeTruthy();
    expect(screen.getByText("MISSING SOURCE")).toBeTruthy();
    expect(screen.getByRole("button", { name: "生成一组候选 Observation" }).hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByLabelText("Disposition metric.definition"), { target: { value: "EDIT" } });
    fireEvent.change(screen.getByLabelText("Edited value metric.definition"), { target: { value: "Human-corrected metric definition" } });
    fireEvent.click(screen.getByRole("button", { name: "应用人工复核到 Draft" }));

    expect(onReview).toHaveBeenCalledOnce();
    expect(onReview.mock.calls[0][0]).toHaveLength(5);
    expect(onReview.mock.calls[0][0][0]).toMatchObject({
      action: "EDIT",
      reason_code: "REVIEWER_CORRECTION",
      edited_value: { kind: "STRING", string_value: "Human-corrected metric definition" },
    });
    expect(onReview.mock.calls[0][0][4]).toMatchObject({
      action: "REJECT",
      reason_code: "KEEP_MISSING",
      edited_value: null,
    });
  });
});
