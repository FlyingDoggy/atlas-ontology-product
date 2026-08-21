"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const baseUrl = process.env.ONTOLOGY_E2E_BASE_URL.replace(/\/$/, "");
const accessFile = process.env.ONTOLOGY_DEMO_ACCESS_FILE;
const evidenceDir = process.env.ONTOLOGY_E2E_EVIDENCE_DIR;
const solutionId = "ontology.exchange_analytics.cash_trading";
const workspaceId = "workspace.cash_trading.reference";

function credentials() {
  const values = {};
  for (const rawLine of fs.readFileSync(accessFile, "utf8").split(/\r?\n/)) {
    const separator = rawLine.indexOf(":");
    if (separator < 0) continue;
    values[rawLine.slice(0, separator).trim().toLowerCase()] = rawLine
      .slice(separator + 1)
      .trim();
  }
  if (!values.username || !values.password) throw new Error("Demo credentials are incomplete");
  return [values.username, values.password];
}

async function getJson(context, route) {
  const response = await context.request.get(`${baseUrl}${route}`);
  if (!response.ok()) throw new Error(`GET ${route} returned ${response.status()}`);
  return response.json();
}

async function waitForJob(context, jobId, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const payload = await getJson(
      context,
      `/control/workspaces/${workspaceId}/construction-jobs`,
    );
    const job = payload.jobs.find((item) => item.job_id === jobId);
    if (job && ["SUCCEEDED", "FAILED", "CANCELLED", "STALE"].includes(job.status)) {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  throw new Error(`Construction job ${jobId} did not reach a terminal state`);
}

async function main() {
  fs.mkdirSync(evidenceDir, { recursive: true });
  const [username, password] = credentials();
  const browserErrors = [];
  const failedProductResponses = [];
  const constructionHistoryReads = [];
  const reviewDraftReads = [];
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1050 } });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);
  page.setDefaultNavigationTimeout(60_000);
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(String(error)));
  page.on("request", (request) => {
    if (request.method() !== "GET") return;
    const requestPath = new URL(request.url()).pathname;
    const viewPath = new URL(page.url()).pathname;
    if (requestPath.endsWith(`/control/workspaces/${workspaceId}/construction-runs`)) {
      constructionHistoryReads.push(viewPath);
    }
    if (requestPath.includes(`/control/workspaces/${workspaceId}/construction-runs/`)
      && requestPath.endsWith("/review-draft")) {
      reviewDraftReads.push(viewPath);
    }
  });
  page.on("response", (response) => {
    if (
      response.status() >= 400
      && ["/api/", "/control/", "/agent-control/"].some((part) => response.url().includes(part))
    ) failedProductResponses.push(`${response.status()} ${response.url()}`);
  });

  try {
    await page.goto(
      `${baseUrl}/ontology-studio/solutions/${solutionId}/`,
      { waitUntil: "networkidle" },
    );
    if (new URL(page.url()).pathname === "/login/") {
      await page.getByLabel("用户名", { exact: true }).fill(username);
      await page.getByLabel("密码", { exact: true }).fill(password);
      await page.locator("#submit-button").click();
      await page.waitForURL((value) => new URL(value).pathname !== "/login/");
      await page.goto(
        `${baseUrl}/ontology-studio/solutions/${solutionId}/`,
        { waitUntil: "networkidle" },
      );
    }

    await page.getByRole("heading", { name: "概览", exact: true }).waitFor();
    const navigation = page.getByRole("navigation", { name: "Ontology Studio" });
    if ((await navigation.getByRole("link").count()) !== 6) {
      throw new Error("Studio does not expose exactly six primary modules");
    }
    const lineage = page.getByRole("region", { name: "Ontology 版本与权威链路" });
    await lineage.waitFor();
    await lineage.getByText("Reviewed Baseline", { exact: true }).waitFor();
    await lineage.getByText("Agent Active", { exact: true }).waitFor();
    await lineage.getByText("与审核基线一致", { exact: true }).waitFor();
    await page.screenshot({
      path: path.join(evidenceDir, "01-reviewed-active-lineage.png"),
      fullPage: true,
    });

    await page.goto(
      `${baseUrl}/ontology-studio/solutions/${solutionId}/inputs/sources/`,
      { waitUntil: "networkidle" },
    );
    await page.getByRole("heading", { name: "来源材料与证据版本" }).waitFor();
    const loadButton = page.getByRole("button", {
      name: /^(载入 4 份参考材料|参考材料已载入)$/,
    });
    await loadButton.waitFor();
    if (await loadButton.isEnabled()) {
      const installResponsePromise = page.waitForResponse(
        (response) => response.url().endsWith(
          `/control/workspaces/${workspaceId}/sources/install-reference-pack`,
        ) && response.request().method() === "POST",
      );
      await loadButton.click();
      const installResponse = await installResponsePromise;
      if (installResponse.status() !== 200) {
        throw new Error(`Reference source pack returned ${installResponse.status()}`);
      }
    }
    await page.getByRole("button", { name: "参考材料已载入" }).waitFor();
    await page.getByText("已载入 Source Library", { exact: true }).waitFor();
    const sourceLibrary = await getJson(
      context,
      `/control/workspaces/${workspaceId}/sources`,
    );
    const expectedSourceIds = new Set([
      "asset.requirements",
      "asset.metric_logic",
      "asset.cash_data_model",
      "asset.cash_data_dictionary",
      "asset.cash_sample_data",
      "asset.cash_provenance_email",
    ]);
    const currentSourceIds = new Set(sourceLibrary.current.map((item) => item.source_id));
    for (const sourceId of expectedSourceIds) {
      if (!currentSourceIds.has(sourceId)) throw new Error(`Missing exact source ${sourceId}`);
    }
    await page.screenshot({
      path: path.join(evidenceDir, "02-exact-source-pack.png"),
      fullPage: true,
    });

    await page.goto(
      `${baseUrl}/ontology-studio/solutions/${solutionId}/inputs/runs/`,
      { waitUntil: "networkidle" },
    );
    await page.getByRole("heading", { name: "自动构建运行" }).waitFor();
    const enqueueResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith(
        `/control/workspaces/${workspaceId}/construction-jobs`,
      ) && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "开始自动构建" }).click();
    const enqueueResponse = await enqueueResponsePromise;
    if (enqueueResponse.status() !== 200) {
      throw new Error(`Construction enqueue returned ${enqueueResponse.status()}`);
    }
    const enqueuedJob = await enqueueResponse.json();
    const terminalJob = await waitForJob(context, enqueuedJob.job_id);
    if (terminalJob.status !== "SUCCEEDED" || !terminalJob.result_run_id) {
      throw new Error(`Construction ended in ${terminalJob.status}: ${terminalJob.error_code}`);
    }
    await page.reload({ waitUntil: "networkidle" });
    await page.getByText("构建完成", { exact: true }).waitFor();
    await page.getByText(
      /^(Semantica 提议引擎已连接|Semantica 已连接 · 案例编译档已匹配)$/,
    ).waitFor();

    const runs = await getJson(
      context,
      `/control/workspaces/${workspaceId}/construction-runs`,
    );
    const record = runs.runs.find((item) => item.run.run_id === terminalJob.result_run_id);
    if (!record) throw new Error("Completed construction run is not queryable");
    const run = record.run;
    const compiledStage = run.stage_receipts.find(
      (item) => item.stage === "PACKAGED_CASE_COMPILATION",
    );
    if (!compiledStage || compiledStage.status !== "PASS" || compiledStage.item_count <= 100) {
      throw new Error("Packaged compilation profile did not produce its typed candidate set");
    }
    const compiledCandidates = run.candidates.filter(
      (item) => item.proposal?.contract === "packaged-case-candidate/v1",
    );
    if (compiledCandidates.length !== compiledStage.item_count) {
      throw new Error("Packaged stage receipt disagrees with its candidate set");
    }
    const typedCandidates = run.candidates.filter((item) => item.proposed_operation !== null);
    const typedTargets = new Set(typedCandidates.map(
      (item) => `${item.proposed_operation.collection}|${item.proposed_operation.object_id}`,
    ));
    if (typedCandidates.length !== 164 || typedTargets.size !== 164) {
      throw new Error(`Expected 164 unique typed operations, received ${typedCandidates.length}/${typedTargets.size}`);
    }
    const candidateTypes = new Set(typedCandidates.map((item) => item.candidate_type));
    const requiredTypes = [
      "ACTOR", "PROCESS", "OBJECT", "LINK", "PROPERTY",
      "DIMENSION", "METRIC", "RULE", "DATA_SOURCE", "MAPPING", "JOIN",
      "ANALYSIS_PATTERN", "POLICY", "QUESTION",
    ];
    for (const candidateType of requiredTypes) {
      if (!candidateTypes.has(candidateType)) throw new Error(`Missing ${candidateType} candidates`);
    }
    if (compiledCandidates.some((item) => item.support_class === "DIRECT_EXACT")) {
      throw new Error("Product-owned construction profile was mislabeled as direct customer fact");
    }
    await page.screenshot({
      path: path.join(evidenceDir, "03-full-ontology-construction.png"),
      fullPage: true,
    });

    await page.goto(
      `${baseUrl}/ontology-studio/solutions/${solutionId}/semantic/metrics/`,
      { waitUntil: "networkidle" },
    );
    await page.getByRole("heading", { name: "指标与业务规则" }).waitFor();
    if ((await page.locator('.catalog-table [role="listitem"]').count()) !== 8) {
      throw new Error("Cash Trading metric catalog does not contain all 8 source metrics");
    }
    await page.getByText("2 个 Agent 已支持", { exact: true }).waitFor();
    await page.screenshot({
      path: path.join(evidenceDir, "04-eight-metric-catalog.png"),
      fullPage: true,
    });

    await page.goto(
      `${baseUrl}/ontology-studio/solutions/${solutionId}/semantic/graph/`,
      { waitUntil: "networkidle" },
    );
    await page.getByRole("heading", { name: "知识图谱编辑器" }).waitFor();
    await page.getByLabel("Ontology graph canvas").waitFor();
    await page.getByRole("button", { name: "新建对象" }).waitFor();
    await page.getByRole("button", { name: "新建关系" }).waitFor();
    await page.screenshot({
      path: path.join(evidenceDir, "05-cash-knowledge-graph.png"),
      fullPage: true,
    });

    await page.goto(
      `${baseUrl}/ontology-studio/solutions/${solutionId}/`,
      { waitUntil: "networkidle" },
    );
    const agentLink = page.getByRole("link", { name: "进入 Agent 查询" });
    if ((await agentLink.getAttribute("href")) !== `/ontology-agent/?solution=${solutionId}`) {
      throw new Error("Reviewed solution did not preserve identity in the Agent link");
    }
    await agentLink.click();
    await page.waitForURL((value) => (
      new URL(value).pathname === "/ontology-agent/" && new URL(value).searchParams.get("solution") === solutionId
    ));
    await page.getByRole("heading", { name: "从业务问题走到可追溯答案" }).waitFor();
    await page.locator(".question-family button").first().click();
    const analysisResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith(`/api/solutions/${solutionId}/analyze`)
        && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "运行受治理分析" }).click();
    const analysisResponse = await analysisResponsePromise;
    if (analysisResponse.status() !== 200) {
      throw new Error(`Cash Agent analysis returned ${analysisResponse.status()}`);
    }
    const analysis = await analysisResponse.json();
    if (analysis.status !== "ANSWERED" || Object.keys(analysis.facts ?? {}).length === 0) {
      throw new Error("Cash Agent did not return governed facts");
    }
    await page.locator(".answer-result").waitFor();
    await page.screenshot({
      path: path.join(evidenceDir, "06-cash-agent-answer.png"),
      fullPage: true,
    });

    if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
    if (failedProductResponses.length) {
      throw new Error(`Failed product responses: ${failedProductResponses.join(" | ")}`);
    }
    const constructionViews = constructionHistoryReads.filter((viewPath) => !(
      viewPath.endsWith("/inputs/runs/")
      || viewPath.endsWith("/semantic/graph/")
      || viewPath.endsWith("/quality/review/")
    ));
    if (constructionViews.length) {
      throw new Error(`Heavy construction history leaked into unrelated views: ${constructionViews.join(", ")}`);
    }
    if (reviewDraftReads.length) {
      throw new Error(`Review drafts were loaded outside the review center: ${reviewDraftReads.join(", ")}`);
    }
    console.log(JSON.stringify({
      status: "PASS",
      release: "0.16.2",
      sourceFiles: 4,
      logicalSources: expectedSourceIds.size,
      packagedCandidates: compiledCandidates.length,
      typedOperations: typedCandidates.length,
      candidateTypes: [...candidateTypes].sort(),
      metricCatalog: 8,
      agentSupportedMetrics: 2,
      activeOntologyVersion: "0.2.0",
      scopedConstructionReads: constructionHistoryReads.length,
      constructionRunId: run.run_id,
      evidenceDir,
    }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
