from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("ONTOLOGY_WEB_URL", "http://127.0.0.1:8781")
OUTPUT = Path(os.environ.get("ONTOLOGY_TEST_OUTPUT", "/tmp/atlas-react-cash-e2e"))
SOLUTION = "ontology.exchange_analytics.cash_trading"
AUTH_CONTAINER = os.environ.get("ONTOLOGY_AUTH_CONTAINER")
OUTPUT.mkdir(parents=True, exist_ok=True)


def issue_test_session(container: str) -> str:
    command = (
        "from ontology_agent.demo_auth import AuthSettings,DemoAuthService;"
        "print(DemoAuthService(AuthSettings.from_env()).issue_session())"
    )
    result = subprocess.run(
        ["docker", "exec", container, "python", "-c", command],
        check=True,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if not token or "\n" in token:
        raise AssertionError("Auth service did not issue one test session")
    return token

errors: list[str] = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1500, "height": 1000})
    if AUTH_CONTAINER:
        context.add_cookies(
            [
                {
                    "name": "atlas_demo_session",
                    "value": issue_test_session(AUTH_CONTAINER),
                    "url": BASE_URL,
                    "httpOnly": True,
                    "sameSite": "Lax",
                }
            ]
        )
    page = context.new_page()
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))

    page.goto(
        f"{BASE_URL}/ontology-agent/?solution={SOLUTION}",
        wait_until="networkidle",
    )
    page.get_by_role("heading", name="从业务问题走到可追溯答案").wait_for()
    catalog_response = context.request.get(f"{BASE_URL}/control/solutions")
    assert catalog_response.ok
    catalog = catalog_response.json()
    cash_catalog = next(
        item for item in catalog["solutions"] if item["solution_id"] == SOLUTION
    )
    assert cash_catalog["persistence"] == "postgresql-s3"
    assert cash_catalog["artifact"]["sha256"] == cash_catalog["subject_checksum"]

    runtime_response = context.request.get(
        f"{BASE_URL}/api/solutions/{SOLUTION}/runtime/active"
    )
    assert runtime_response.ok
    runtime = runtime_response.json()
    assert runtime["package_id"] == SOLUTION
    assert runtime["environment_id"] == "cash-trading-poc"
    assert runtime["snapshot_checksum"]
    assert "现金市场订单与成交活动监控" in page.locator(".solution-switcher > summary").inner_text()
    assert page.locator(".question-family button").count() == 4
    page.locator(".question-family button").first.click()
    page.get_by_role("button", name="运行受治理分析").click()
    page.locator(".answer-result").wait_for()
    assert "200" in page.locator(".answer-result").inner_text()
    assert "20" in page.locator(".answer-result").inner_text()
    page.screenshot(path=str(OUTPUT / "react-cash-agent.png"), full_page=True)

    page.locator(".role-control select").select_option("ExternalUser")
    page.get_by_role("button", name="运行受治理分析").click()
    page.locator(".answer-boundary").wait_for()
    assert "没有释放部分 facts 或 evidence" in page.locator(".answer-boundary").inner_text()

    page.locator(".product-switch").click()
    page.wait_for_url(f"**/ontology-studio/?solution={SOLUTION}")
    page.get_by_role("heading", name="概览", exact=True).wait_for()
    page.get_by_role("link", name="输入与证据", exact=False).click()
    page.get_by_role("heading", name="现金交易语义草稿").wait_for()
    assert page.locator(".editor-field").count() == 5
    page.get_by_role("link", name="全部解决方案", exact=True).last.click()
    page.get_by_role("heading", name="全部解决方案", exact=True).wait_for()
    assert page.locator(".solution-directory-table article").count() >= 2
    page.screenshot(path=str(OUTPUT / "react-cash-studio.png"), full_page=True)

    browser.close()

assert not errors, "browser errors: " + " | ".join(errors)
print(json.dumps({
    "status": "PASS",
    "solution": SOLUTION,
    "checks": [
        "REACT_SOLUTION_SWITCH",
        "AGENT_ACTIVE_SNAPSHOT_QUERY",
        "ANSWER_FACTS_AND_EVIDENCE",
        "NO_PARTIAL_REFUSAL",
        "STUDIO_AGENT_LINK",
        "DESCRIPTOR_DRIVEN_CASH_EDITOR",
        "TWO_SOLUTION_CATALOG",
        "POSTGRESQL_S3_CATALOG_READBACK",
        "ACTIVE_RUNTIME_READBACK",
    ],
    "screenshots": str(OUTPUT),
}, ensure_ascii=False, indent=2))
