"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const baseUrl = process.env.ONTOLOGY_E2E_BASE_URL.replace(/\/$/, "");
const accessFile = process.env.ONTOLOGY_DEMO_ACCESS_FILE;
const evidenceDir = process.env.ONTOLOGY_E2E_EVIDENCE_DIR;

function credentials() {
  const values = {};
  for (const rawLine of fs.readFileSync(accessFile, "utf8").split(/\r?\n/)) {
    const separator = rawLine.indexOf(":");
    if (separator < 0) continue;
    values[rawLine.slice(0, separator).trim().toLowerCase()] = rawLine
      .slice(separator + 1)
      .trim();
  }
  return [values.username, values.password];
}

async function openRowMenu(row) {
  const details = row.locator("details");
  if ((await details.getAttribute("open")) === null) {
    await details.locator("summary").click();
  }
}

async function main() {
  fs.mkdirSync(evidenceDir, { recursive: true });
  const [username, password] = credentials();
  const suffix = new Date().toISOString().replace(/\D/g, "").slice(8, 14);
  const solutionName = `现金市场构建验证 ${suffix}`;
  const browserErrors = [];
  const failedProductResponses = [];
  let solutionId = null;
  let workspaceId = null;

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1536, height: 1000 } });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);
  page.setDefaultNavigationTimeout(60_000);
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(String(error)));
  page.on("response", (response) => {
    if (
      response.status() >= 400
      && ["/api/", "/control/", "/agent-control/"].some((part) => response.url().includes(part))
    ) failedProductResponses.push(`${response.status()} ${response.url()}`);
  });

  try {
    await page.goto(`${baseUrl}/ontology-studio/solutions/`, { waitUntil: "networkidle" });
    if (new URL(page.url()).pathname === "/login/") {
      await page.getByLabel("用户名", { exact: true }).fill(username);
      await page.getByLabel("密码", { exact: true }).fill(password);
      await page.locator("#submit-button").click();
      await page.waitForURL((value) => new URL(value).pathname !== "/login/");
      await page.goto(`${baseUrl}/ontology-studio/solutions/`, { waitUntil: "networkidle" });
    }

    await page.getByRole("heading", { name: "全部解决方案", exact: true }).waitFor();

    // The installed Cash reference has its own durable External Reviewer source library.
    // Prove that its source-backed catalogs are plural before testing an
    // isolated template clone.  The clone starts from the canonical package;
    // its construction may reference installed template inputs without
    // duplicating source ownership, upload history, runs or review decisions.
    const cashReference = "ontology.exchange_analytics.cash_trading";
    await page.goto(`${baseUrl}/ontology-studio/solutions/${cashReference}/inputs/requirements/`, { waitUntil: "networkidle" });
    let catalogRows = page.locator('.catalog-table [role="listitem"]');
    await catalogRows.first().waitFor();
    if ((await catalogRows.count()) !== 7) throw new Error("Cash reference requirement denominator is not 7");
    await page.goto(`${baseUrl}/ontology-studio/solutions/${cashReference}/semantic/metrics/`, { waitUntil: "networkidle" });
    catalogRows = page.locator('.catalog-table [role="listitem"]');
    await catalogRows.first().waitFor();
    if ((await catalogRows.count()) !== 8) throw new Error("Cash reference metric denominator is not 8");
    await page.screenshot({ path: path.join(evidenceDir, "00-cash-reference-multi-metric.png"), fullPage: true });

    await page.goto(`${baseUrl}/ontology-studio/solutions/`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "新建解决方案" }).click();
    const dialog = page.getByRole("dialog", { name: "新建解决方案" });
    await dialog.locator(".solution-form-field select").selectOption(
      "ontology.exchange_analytics.cash_trading",
    );
    await dialog.getByLabel("中文名称").fill(solutionName);
    await dialog.getByLabel("英文名称").fill(`Cash construction verification ${suffix}`);
    await dialog.getByLabel("业务场景描述").fill(
      "验证模板化新 Solution 无需修改公共产品代码即可完成自动构建与人工复核。",
    );
    await dialog.getByLabel("负责人").fill("Ontology Product Team");
    const createPromise = page.waitForResponse(
      (response) => response.url().endsWith("/control/solutions") && response.request().method() === "POST",
    );
    await dialog.getByRole("button", { name: "创建 Draft Solution" }).click();
    const createResponse = await createPromise;
    if (createResponse.status() !== 201) throw new Error(`create returned ${createResponse.status()}`);
    const created = (await createResponse.json()).solution;
    solutionId = created.solution_id;
    workspaceId = created.workspace_id;
    if (!solutionId.startsWith("ontology.custom.") || !workspaceId.startsWith("workspace.custom.")) {
      throw new Error("custom solution identities were not allocated");
    }

    await page.getByRole("heading", { name: "概览", exact: true }).waitFor();
    if (!page.url().includes(solutionId)) throw new Error("solution route lost exact identity");
    const navigation = page.getByRole("navigation", { name: "Ontology Studio" });
    if ((await navigation.getByRole("link").count()) !== 6) throw new Error("Studio must expose exactly six primary modules");
    // The route shell and page heading render before the exact package is
    // materialized.  Evidence must show the product state, not its loading
    // placeholder, so wait on a semantic completion marker.
    await page.getByRole("region", { name: "工作区状态" }).waitFor();
    await page.screenshot({ path: path.join(evidenceDir, "01-custom-solution-overview.png"), fullPage: true });

    await page.goto(`${baseUrl}/ontology-studio/solutions/${solutionId}/inputs/requirements/`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "业务需求与分析流程" }).waitFor();
    const requirementRows = page.locator('.catalog-table [role="listitem"]');
    await requirementRows.first().waitFor();
    if ((await requirementRows.count()) !== 5) throw new Error("isolated template requirement denominator is not 5");

    await page.goto(`${baseUrl}/ontology-studio/solutions/${solutionId}/semantic/metrics/`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "指标与业务规则" }).waitFor();
    const metricRows = page.locator('.catalog-table [role="listitem"]');
    await metricRows.first().waitFor();
    if ((await metricRows.count()) !== 5) throw new Error("isolated template metric denominator is not 5");
    await page.screenshot({ path: path.join(evidenceDir, "02-multi-metric-catalog.png"), fullPage: true });

    await page.goto(`${baseUrl}/ontology-studio/solutions/${solutionId}/inputs/runs/`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "自动构建运行" }).waitFor();
    const enqueuePromise = page.waitForResponse(
      (response) => response.url().endsWith(`/control/workspaces/${workspaceId}/construction-jobs`)
        && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "开始自动构建" }).click();
    const enqueueResponse = await enqueuePromise;
    if (enqueueResponse.status() !== 200) throw new Error(`enqueue returned ${enqueueResponse.status()}`);
    await page.getByText("构建完成", { exact: true }).waitFor({ timeout: 90_000 });
    await page.getByText("19 个候选待复核", { exact: true }).waitFor();
    await page.screenshot({ path: path.join(evidenceDir, "03-construction-completed.png"), fullPage: true });

    await page.goto(`${baseUrl}/ontology-studio/solutions/${solutionId}/quality/review/`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "候选复核中心" }).waitFor();
    const actionSelects = page.locator('select[aria-label^="复核动作 "]');
    if ((await actionSelects.count()) !== 19) throw new Error("review denominator is not 19 candidates");
    for (let index = 0; index < 19; index += 1) await actionSelects.nth(index).selectOption("DEFER");
    await page.getByRole("button", { name: "保存复核进度" }).click();
    await page.getByText("所有候选均已保存 disposition", { exact: true }).waitFor();
    await page.getByRole("button", { name: "完成本轮复核并应用" }).click();
    await page.getByRole("button", { name: "本轮已完成" }).waitFor();
    await page.screenshot({ path: path.join(evidenceDir, "04-human-review-completed.png"), fullPage: true });

    await page.goto(`${baseUrl}/ontology-studio/solutions/${solutionId}/semantic/graph/`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "知识图谱编辑器" }).waitFor();
    await page.getByLabel("Ontology graph canvas").waitFor();
    if (!(await page.getByRole("button", { name: "新建对象" }).isVisible())) throw new Error("Graph object authoring is unavailable");
    if (!(await page.getByRole("button", { name: "新建关系" }).isVisible())) throw new Error("Graph link authoring is unavailable");
    await page.screenshot({ path: path.join(evidenceDir, "05-graph-editor.png"), fullPage: true });
  } finally {
    if (solutionId) {
      await page.goto(`${baseUrl}/ontology-studio/solutions/?solution=${solutionId}`, { waitUntil: "networkidle" });
      let row = page.locator(".solution-directory-table article", { hasText: solutionId });
      await row.waitFor();
      await openRowMenu(row);
      const archivePromise = page.waitForResponse(
        (response) => response.url().endsWith(`/control/solutions/${solutionId}/archive`)
          && response.request().method() === "POST",
      );
      await row.getByRole("button", { name: "归档" }).click();
      const archiveResponse = await archivePromise;
      if (archiveResponse.status() !== 200) throw new Error(`archive returned ${archiveResponse.status()}`);
      row = page.locator(".solution-directory-table article", { hasText: solutionId });
      await openRowMenu(row);
      await row.getByRole("button", { name: "永久移除" }).click();
      const deleteDialog = page.getByRole("dialog", { name: "永久移除解决方案" });
      await deleteDialog.getByLabel("输入完整名称以确认").fill(solutionName);
      const deletePromise = page.waitForResponse(
        (response) => response.url().endsWith(`/control/solutions/${solutionId}`)
          && response.request().method() === "DELETE",
      );
      await deleteDialog.getByRole("button", { name: "永久移除" }).click();
      const deleteResponse = await deletePromise;
      if (deleteResponse.status() !== 200 || !(await deleteResponse.json()).audit_artifacts_retained) {
        throw new Error("delete did not retain audit artifacts");
      }
    }
    await browser.close();
  }

  if (browserErrors.length) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
  if (failedProductResponses.length) throw new Error(`Failed product responses: ${failedProductResponses.join(" | ")}`);
  console.log(`semantic_construction_e2e: PASS (${solutionId}, template -> run -> review -> graph -> cleanup)`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
