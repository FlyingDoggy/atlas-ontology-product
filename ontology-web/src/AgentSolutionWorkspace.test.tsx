import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentSolution } from "./api";
import { AgentSolutionWorkspace } from "./App";
import { LegacyUiLocalizer, UiLocaleProvider } from "./i18n";

const analyzeSolutionMock = vi.hoisted(() => vi.fn());
const fetchAnalyticConversationMock = vi.hoisted(() => vi.fn());

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    analyzeSolution: analyzeSolutionMock,
    fetchAnalyticConversation: fetchAnalyticConversationMock,
  };
});

const digest = "a".repeat(64);
const solution = {
  solution_id: "ontology.exchange_analytics.cash_trading",
  solution_version: "1.2.1",
  semantic_source_version: "0.2.1",
  scenario_id: "scenario.cash_trading",
  workspace_id: "workspace.cash_trading.reference",
  studio_adapter_id: "studio-adapter.cash-trading@1",
  classification: "constructed_synthetic",
  display_name: { en: "Cash Market Order and Trading Activity Monitoring", zh: "现金市场订单与成交活动监控" },
  components: ["authoring_profile", "semantic_source", "agent_experience", "reference_evaluation"].map((kind) => ({
    component_id: `component.${kind}`,
    kind,
    sha256: digest,
    media_type: "application/json",
  })),
  limitations: ["Constructed-synthetic data"],
  persistence: "postgresql-s3",
  subject_checksum: digest,
  artifact: {
    store: "s3-compatible",
    bucket: "ontology-artifacts",
    key: `solution/${digest}.json`,
    version_id: "v1",
    sha256: digest,
    size_bytes: 100,
    media_type: "application/json",
  },
  runtime: { state: "ACTIVE", environment_id: "cash-demo", snapshot_checksum: digest },
} as AgentSolution;

function renderWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  queryClient.setQueryData(["solution-questions", solution.solution_id], {
    family_id: "cash.questions",
    family_checksum: digest,
    classification: "constructed_synthetic",
    cases: [{
      case_id: "q1",
      language: "en",
      question: "What was the order rejection rate?",
      expected_intent: "metric_query",
      required_tools: ["cash.query_metric"],
    }],
  });
  queryClient.setQueryData(["solution-runtime", solution.solution_id], {
    package_id: solution.solution_id,
    version: "0.2.1",
    release_checksum: digest,
    snapshot_checksum: digest,
    environment_id: "cash-demo",
    certification_profile: "cash-demo",
    default_role: "MarketSurveillanceDemo",
    roles: [{
      role_id: "MarketSurveillanceDemo",
      name: { en: "Market Surveillance", zh: "市场监察" },
      access: "ALLOWED",
    }],
  });
  queryClient.setQueryData(["solution-ontology", solution.solution_id], {
    package_id: solution.solution_id,
    version: "0.2.1",
    snapshot_checksum: digest,
    scenario: {},
    metrics: [],
    analysis_patterns: [],
  });
  const root = document.createElement("div");
  root.id = "root";
  document.body.appendChild(root);
  return render(
    <QueryClientProvider client={queryClient}>
      <UiLocaleProvider>
        <LegacyUiLocalizer />
        <AgentSolutionWorkspace solution={solution} />
      </UiLocaleProvider>
    </QueryClientProvider>,
    { container: root },
  );
}

beforeEach(() => {
  window.localStorage.setItem("atlas-ui-locale", "en");
  window.sessionStorage.clear();
  analyzeSolutionMock.mockReset();
  fetchAnalyticConversationMock.mockReset();
  fetchAnalyticConversationMock.mockImplementation((_solutionId: string, conversationId: string) => Promise.resolve({
    contract: "analytic-conversation-transcript/v1",
    conversation_id: conversationId,
    solution_id: solution.solution_id,
    turns: [],
  }));
  analyzeSolutionMock.mockResolvedValue({
    status: "CLARIFY",
    answer: "请说明要查看的指标或 Ontology 定义。",
    conversation_id: "conversation." + "1".repeat(32),
    turn_id: "turn." + "2".repeat(32),
    turn_index: 1,
    parent_execution_id: null,
    execution_id: null,
    snapshot_checksum: digest,
    plan: null,
    steps: [],
    facts: {},
    evidence: [],
    boundary_code: "METRIC_NOT_RESOLVED",
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
      profile_checksum: null,
      activation_id: "cash-trading.deepagent.v1",
    },
  });
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
  document.getElementById("root")?.remove();
});

describe("AgentSolutionWorkspace", () => {
  it("submits the original question, clears the composer, and never UI-translates conversation content", async () => {
    renderWorkspace();
    const input = await screen.findByLabelText(/输入分析问题|Enter an analysis question/);
    expect(input.getAttribute("placeholder")).toBe(
      "For example: Show the daily potential self-trade rate for the sample period.",
    );
    fireEvent.change(input, { target: { value: "你都能回答什么问题" } });
    fireEvent.click(screen.getByRole("button", { name: /发送|Send/ }));

    await waitFor(() => expect(analyzeSolutionMock).toHaveBeenCalledWith(
      solution.solution_id,
      "你都能回答什么问题",
      "MarketSurveillanceDemo",
      undefined,
      expect.stringMatching(/^conversation\.[0-9a-f]{32}$/),
    ));
    const firstConversationId = analyzeSolutionMock.mock.calls[0][4];
    expect(input).toHaveProperty("value", "");
    expect(await screen.findByText("你都能回答什么问题")).toBeTruthy();
    expect(await screen.findByText("请说明要查看的指标或 Ontology 定义。")).toBeTruthy();
    expect(screen.queryByText(/You都能回答什么questions/)).toBeNull();

    const firstResponse = await analyzeSolutionMock.mock.results[0].value;
    analyzeSolutionMock.mockResolvedValueOnce({
      ...firstResponse,
      status: "CLARIFY",
      answer: "请说明参与者维度的时间范围。",
      conversation_id: firstConversationId,
      turn_id: "turn." + "3".repeat(32),
      turn_index: 2,
    });
    fireEvent.change(input, { target: { value: "按参与者拆开" } });
    fireEvent.click(screen.getByRole("button", { name: /发送|Send/ }));
    await waitFor(() => expect(analyzeSolutionMock).toHaveBeenLastCalledWith(
      solution.solution_id,
      "按参与者拆开",
      "MarketSurveillanceDemo",
      undefined,
      firstConversationId,
    ));
    expect(await screen.findByText("按参与者拆开")).toBeTruthy();
    expect(await screen.findByText("请说明参与者维度的时间范围。")).toBeTruthy();
    expect(screen.getByText("你都能回答什么问题")).toBeTruthy();
    expect(screen.getByText("请说明要查看的指标或 Ontology 定义。")).toBeTruthy();
    expect(screen.getByText("2 turns")).toBeTruthy();
  });

  it("restores the complete current conversation after a reload and starts a clean session only on request", async () => {
    const conversationId = "conversation." + "7".repeat(32);
    window.sessionStorage.setItem(`atlas-agent-conversation:${solution.solution_id}`, conversationId);
    const analysis = await analyzeSolutionMock();
    fetchAnalyticConversationMock.mockResolvedValue({
      contract: "analytic-conversation-transcript/v1",
      conversation_id: conversationId,
      solution_id: solution.solution_id,
      turns: [
        {
          turn_id: analysis.turn_id,
          turn_index: 1,
          question: "What can you answer?",
          status: analysis.status,
          completed_at: "2026-08-25T09:00:00Z",
          analysis: { ...analysis, conversation_id: conversationId },
        },
      ],
    });

    renderWorkspace();

    expect(await screen.findByText("What can you answer?")).toBeTruthy();
    expect(await screen.findByText("请说明要查看的指标或 Ontology 定义。")).toBeTruthy();
    expect(fetchAnalyticConversationMock).toHaveBeenCalledWith(solution.solution_id, conversationId);

    fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
    expect(await screen.findByText("Ask about Cash Trading data")).toBeTruthy();
    expect(screen.queryByText("What can you answer?")).toBeNull();
    expect(window.sessionStorage.getItem(`atlas-agent-conversation:${solution.solution_id}`)).toMatch(
      /^conversation\.[0-9a-f]{32}$/,
    );
    expect(window.sessionStorage.getItem(`atlas-agent-conversation:${solution.solution_id}`)).not.toBe(conversationId);
  });
});
