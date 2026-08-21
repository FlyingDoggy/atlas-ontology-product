from __future__ import annotations

import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright


BASE_URL = os.environ["ONTOLOGY_E2E_BASE_URL"].rstrip("/")
ACCESS_FILE = Path(os.environ["ONTOLOGY_DEMO_ACCESS_FILE"])
EVIDENCE_DIR = Path(os.environ["ONTOLOGY_E2E_EVIDENCE_DIR"])
SOLUTION_ID = "ontology.exchange_analytics.cash_trading"


def credentials() -> tuple[str, str]:
    values: dict[str, str] = {}
    for raw_line in ACCESS_FILE.read_text(encoding="utf-8").splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip().lower()] = value.strip()
    return values["username"], values["password"]


def goto(page: Page, route: str) -> None:
    page.goto(f"{BASE_URL}{route}", wait_until="networkidle")
    assert urlparse(page.url).path != "/login/", "authenticated session was lost"


def screenshot(page: Page, name: str) -> None:
    page.screenshot(path=str(EVIDENCE_DIR / name), full_page=True)


def main() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    username, password = credentials()
    console_errors: list[str] = []
    failed_product_responses: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.set_default_navigation_timeout(60_000)
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.on(
            "response",
            lambda response: failed_product_responses.append(
                f"{response.status} {response.url}"
            )
            if response.status >= 400
            and any(
                segment in response.url
                for segment in ("/api/", "/control/", "/agent-control/")
            )
            else None,
        )

        page.goto(
            f"{BASE_URL}/ontology-studio/solutions/{SOLUTION_ID}/",
            wait_until="networkidle",
        )
        if urlparse(page.url).path == "/login/":
            page.get_by_label("用户名", exact=True).fill(username)
            page.get_by_label("密码", exact=True).fill(password)
            page.locator("#submit-button").click()
            page.wait_for_url(lambda value: urlparse(value).path != "/login/")
            goto(page, f"/ontology-studio/solutions/{SOLUTION_ID}/")

        page.get_by_role("heading", name="概览", exact=True).wait_for()
        navigation = page.get_by_role("navigation", name="Ontology Studio")
        assert navigation.get_by_role("link").count() == 6
        page.locator(".access-role.is-operator").filter(has_text="配置人员").wait_for()
        screenshot(page, "01-overview.png")

        # Unified semantic asset catalog and typed authoring entry.
        goto(page, f"/ontology-studio/solutions/{SOLUTION_ID}/semantic/metrics/")
        page.get_by_role("heading", name="指标与规则", exact=True).wait_for()
        assert page.get_by_role("list", name="指标目录").get_by_role("listitem").count() >= 5
        page.get_by_role("link", name="＋ 新增指标").click()
        editor = page.get_by_role("dialog", name="新增指标")
        editor.wait_for()
        editor.get_by_label(re.compile("技术 ID")).fill("metric.visual_qa")
        editor.get_by_label("中文名称").fill("配置体验检查指标")
        editor.get_by_label("英文名称").fill("Configuration UX check")
        editor.get_by_label("业务定义").fill("仅用于验证编辑器的失败保留和结构化合同交互。")
        editor.get_by_label("单位").fill("count")
        editor.get_by_role("checkbox").first.check()
        editor.get_by_label("公式合同").fill("{")
        editor.get_by_label("确定性查询合同").fill("{}")
        editor.get_by_role("button", name="保存草稿").click()
        editor.get_by_role("alert").filter(has_text="formula").wait_for()
        assert editor.get_by_label("公式合同").input_value() == "{"
        screenshot(page, "02-semantic-typed-editor.png")
        page.once("dialog", lambda dialog: dialog.accept())
        editor.get_by_role("button", name="关闭资产编辑器").click()
        editor.wait_for(state="detached")

        # Graph is a first-class projection with the same authoring entry.
        goto(page, f"/ontology-studio/solutions/{SOLUTION_ID}/semantic/graph/")
        page.get_by_role("heading", name="知识图谱", exact=True).wait_for()
        page.get_by_label("Ontology graph canvas").wait_for()
        assert page.get_by_role("link", name="新建对象").is_visible()
        assert page.get_by_role("link", name="新建关系").is_visible()
        screenshot(page, "03-knowledge-graph.png")
        page.get_by_role("link", name="新建关系").click()
        relationship_editor = page.get_by_role("dialog", name="新增关系")
        relationship_editor.wait_for()
        relationship_editor.get_by_role("button", name="关闭资产编辑器").click()

        # Data source, mapping and join editors all expose explicit typed fields.
        goto(page, f"/ontology-studio/solutions/{SOLUTION_ID}/data/schemas/")
        page.get_by_role("heading", name="数据源与 Schema", exact=True).wait_for()
        page.get_by_role("button", name="新增数据源").click()
        data_editor = page.locator(".data-contract-editor")
        data_editor.get_by_label("中文名称").fill("尚未保存的数据源")
        page.once("dialog", lambda dialog: dialog.dismiss())
        data_editor.get_by_role("button", name="取消").click()
        assert data_editor.get_by_label("中文名称").input_value() == "尚未保存的数据源"
        screenshot(page, "04-data-source-editor.png")
        page.once("dialog", lambda dialog: dialog.accept())
        data_editor.get_by_role("button", name="取消").click()

        goto(page, f"/ontology-studio/solutions/{SOLUTION_ID}/data/mappings/")
        page.get_by_role("heading", name="映射与关联", exact=True).wait_for()
        page.get_by_role("button", name="新增映射").click()
        mapping_editor = page.locator(".mapping-inspector form")
        mapping_editor.get_by_label("转换", exact=True).fill("trim_and_uppercase")
        page.once("dialog", lambda dialog: dialog.accept())
        mapping_editor.get_by_role("button", name="取消").click()
        page.get_by_role("button", name="新增 Join").click()
        join_editor = page.locator(".join-editor")
        join_editor.get_by_label("中文名称").fill("待确认关联")
        screenshot(page, "05-mapping-and-join-editor.png")
        page.once("dialog", lambda dialog: dialog.accept())
        join_editor.get_by_role("button", name="取消").click()

        # Exact-source registration protects partially transcribed material.
        goto(page, f"/ontology-studio/solutions/{SOLUTION_ID}/inputs/sources/")
        page.get_by_role("heading", name="来源材料与证据版本", exact=True).wait_for()
        load_pack = page.get_by_role(
            "button", name=re.compile("^(载入 4 份参考材料|参考材料已载入)$")
        )
        if load_pack.is_enabled():
            load_pack.click()
            page.get_by_role("button", name="参考材料已载入").wait_for(timeout=60_000)
        page.get_by_role("button", name="添加或替换材料").click()
        transcription = page.get_by_placeholder(
            "可粘贴 O-xx / M-xx Markdown 表格，或直接上传标准 Excel template。"
        )
        transcription.fill("尚未登记的需求转写；离开前必须明确确认。")
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.get_by_role("button", name="取消").click()
        assert transcription.input_value().startswith("尚未登记")
        screenshot(page, "06-source-registration.png")
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="取消").click()

        # Construction records the exact selected source versions.
        goto(page, f"/ontology-studio/solutions/{SOLUTION_ID}/inputs/runs/")
        page.get_by_role("heading", name="自动构建运行", exact=True).wait_for()
        selected_sources = page.locator('.construction-source-selection input[type="checkbox"]:checked')
        assert selected_sources.count() >= 4
        candidate_summary = page.get_by_text(re.compile(r"\d+ 个候选待复核"))
        if candidate_summary.count() == 0:
            start = page.get_by_role("button", name="开始自动构建")
            with page.expect_response(
                lambda response: response.request.method == "POST"
                and response.url.endswith("/construction-jobs")
                and response.status < 400,
                timeout=30_000,
            ):
                start.click()
            page.get_by_text("构建完成", exact=True).wait_for(timeout=120_000)
            candidate_summary.wait_for(timeout=60_000)
        screenshot(page, "07-construction-run.png")

        # Review remains paged, filtered, source-aware and explicitly human-decided.
        goto(page, f"/ontology-studio/solutions/{SOLUTION_ID}/quality/review/")
        page.get_by_role("heading", name="候选复核中心", exact=True).wait_for()
        queue = page.get_by_role("list", name="候选队列")
        assert 1 <= queue.get_by_role("listitem").count() <= 25
        page.get_by_text(re.compile(r"第 1 / \d+ 页")).wait_for()
        first_action = page.locator('select[aria-label^="复核动作 "]').first
        first_action.select_option("DEFER")
        page.once("dialog", lambda dialog: dialog.dismiss())
        navigation.get_by_role("link", name=re.compile("^语义模型")).click()
        assert urlparse(page.url).path.endswith("/quality/review/")
        first_action.select_option("UNREVIEWED")
        screenshot(page, "08-review-center.png")

        # Desktop floor: no application-level horizontal overflow at 1280px.
        page.set_viewport_size({"width": 1280, "height": 900})
        page.reload(wait_until="networkidle")
        horizontal_overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"
        )
        assert not horizontal_overflow, "Studio shell overflows horizontally at 1280px"
        screenshot(page, "09-review-center-1280.png")

        browser.close()

    unexpected = [item for item in failed_product_responses if "/favicon" not in item]
    assert not console_errors, f"Browser errors: {console_errors}"
    assert not unexpected, f"Failed product responses: {unexpected}"
    print(
        "studio_configuration_ux: PASS "
        f"({len(list(EVIDENCE_DIR.glob('*.png')))} screenshots, {time.strftime('%H:%M:%S')})"
    )


if __name__ == "__main__":
    main()
