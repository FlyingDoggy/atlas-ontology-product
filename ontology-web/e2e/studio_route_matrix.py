from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


BASE_URL = os.environ["ONTOLOGY_E2E_BASE_URL"].rstrip("/")
ACCESS_FILE = Path(os.environ["ONTOLOGY_DEMO_ACCESS_FILE"])
SOLUTION_ID = "ontology.exchange_analytics.cash_trading"

ROUTES = (
    ("", "概览", "工作区概览"),
    ("inputs/requirements/", "输入与证据", "业务需求"),
    ("inputs/sources/", "输入与证据", "来源材料"),
    ("construction/runs/", "构建与复核", "构建任务"),
    ("construction/review/", "构建与复核", "复核队列"),
    ("semantic/model/", "语义模型", "业务模型"),
    ("semantic/metrics/", "语义模型", "指标与规则"),
    ("semantic/graph/", "语义模型", "知识图谱"),
    ("semantic/experience/", "语义模型", "分析能力"),
    ("data/schemas/", "数据", "数据源与 Schema"),
    ("data/mappings/", "数据", "映射与关联"),
    ("data/sql/", "数据", "SQL 合同"),
    ("data/samples/", "数据", "样例与枚举"),
    ("quality/policies/", "质量与发布", "访问与披露策略"),
    ("quality/validation/", "质量与发布", "验证结果"),
    ("quality/changes/", "质量与发布", "问题与变更"),
    ("quality/versions/", "质量与发布", "版本与审批"),
    ("quality/delivery/", "质量与发布", "交付与运行"),
)

GLOBAL_ROUTES = (
    ("/ontology-studio/solutions/", "全部解决方案"),
)


def credentials() -> tuple[str, str]:
    values: dict[str, str] = {}
    for raw_line in ACCESS_FILE.read_text(encoding="utf-8").splitlines():
        if ":" in raw_line:
            key, value = raw_line.split(":", 1)
            values[key.strip().lower()] = value.strip()
    return values["username"], values["password"]


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.set_default_timeout(45_000)
    browser_errors: list[str] = []
    failed_responses: list[str] = []
    page.on("console", lambda message: browser_errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: browser_errors.append(str(error)))
    page.on(
        "response",
        lambda response: failed_responses.append(f"{response.status} {response.url}")
        if response.status >= 400 and any(segment in response.url for segment in ("/api/", "/control/", "/agent-control/"))
        else None,
    )

    root = f"/ontology-studio/solutions/{SOLUTION_ID}/"
    page.goto(f"{BASE_URL}{root}", wait_until="domcontentloaded", timeout=60_000)
    if urlparse(page.url).path == "/login/":
        username, password = credentials()
        page.get_by_label("用户名", exact=True).fill(username)
        page.get_by_label("密码", exact=True).fill(password)
        page.locator("#submit-button").click()
        page.wait_for_url(lambda value: urlparse(value).path != "/login/")

    checked: list[str] = []
    for path, heading in GLOBAL_ROUTES:
        page.goto(
            f"{BASE_URL}{path}", wait_until="domcontentloaded", timeout=60_000
        )
        page.get_by_role("heading", name=heading, exact=True, level=1).wait_for()
        assert "读取失败" not in page.locator("body").inner_text(), path
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
        assert not overflow, f"horizontal overflow: {path}"
        checked.append(path)

    page.goto(
        f"{BASE_URL}/ontology-studio/tasks/legacy-task-id/",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    page.wait_for_url(f"{BASE_URL}/ontology-studio/solutions/")
    page.get_by_role("heading", name="全部解决方案", exact=True, level=1).wait_for()
    assert page.get_by_role("link", name=re.compile("任务中心")).count() == 0
    checked.append("task-center-redirect")

    for suffix, page_title, subpage_title in ROUTES:
        page.goto(
            f"{BASE_URL}{root}{suffix}",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        page.get_by_role("heading", name=page_title, exact=True, level=1).wait_for()
        current = page.locator('.studio-subnavigation a[aria-current="page"]')
        if suffix:
            assert current.count() == 1, f"missing current subpage navigation: {suffix}"
            assert re.search(re.escape(subpage_title), current.inner_text())
        else:
            assert current.count() == 0
        assert page.locator(".studio-page-content").locator(":scope > *").count() > 0
        assert "读取失败" not in page.locator("body").inner_text(), suffix or "overview"
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
        if overflow:
            offenders = page.evaluate("""
                [...document.querySelectorAll('body *')]
                  .filter((element) => element.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
                  .slice(0, 8)
                  .map((element) => ({
                    tag: element.tagName,
                    className: String(element.className).slice(0, 120),
                    right: Math.round(element.getBoundingClientRect().right),
                    width: Math.round(element.getBoundingClientRect().width),
                  }))
            """)
            raise AssertionError(f"horizontal overflow: {suffix or 'overview'} {offenders}")
        checked.append(suffix or "overview")

    browser.close()

assert not browser_errors, f"Browser errors: {browser_errors}"
assert not failed_responses, f"Failed product responses: {failed_responses}"
print(f"studio_route_matrix: PASS ({len(checked)} routes)")
