from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from playwright.sync_api import expect, sync_playwright


BASE_URL = os.environ.get("ONTOLOGY_WEB_URL", "http://127.0.0.1:18083")
SOLUTION = "ontology.exchange_analytics.cash_trading"
WORKSPACE = "workspace.cash_trading.reference"
AUTH_CONTAINER = os.environ.get("ONTOLOGY_AUTH_CONTAINER", "ontology-ui-qa-auth-1")
CHROME = os.environ.get(
    "ONTOLOGY_CHROME_EXECUTABLE",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)
OUTPUT = Path(
    os.environ.get(
        "ONTOLOGY_TEST_OUTPUT",
        str(Path(__file__).resolve().parents[1] / "demo-materials/cash-trading-e2e/screenshots"),
    )
)


def issue_session() -> str:
    supplied = os.environ.get("ONTOLOGY_SESSION_TOKEN", "").strip()
    if supplied:
        return supplied
    command = (
        "from ontology_agent.demo_auth import AuthSettings,DemoAuthService;"
        "print(DemoAuthService(AuthSettings.from_env()).issue_session())"
    )
    result = subprocess.run(
        ["docker", "exec", AUTH_CONTAINER, "python", "-c", command],
        check=True,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if not token or "\n" in token:
        raise AssertionError("Auth service did not issue one local QA session")
    return token


def goto_ready(page, route: str, selector: str, timeout: int = 45_000) -> None:
    page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded", timeout=timeout)
    page.locator(selector).wait_for(state="visible", timeout=timeout)
    page.wait_for_timeout(600)


def assert_package_contract(request) -> dict[str, object]:
    response = request.get(
        f"{BASE_URL}/control/workspaces/{WORKSPACE}/workbench",
        timeout=60_000,
    )
    assert response.ok, response.text()
    workbench = response.json()
    package = workbench["package"]
    expected = {
        "entities": 9,
        "properties": 83,
        "relationships": 14,
        "dimensions": 8,
        "metrics": 22,
        "data_sources": 9,
        "bindings": 80,
        "joins": 8,
    }
    actual = {key: len(package[key]) for key in expected}
    assert actual == expected, actual
    assert package["package_id"] == SOLUTION
    assert package["status"] == "confirmed"
    assert len(package["sources"]) >= 7
    assert len(package["decisions"]) >= 17
    assert len(package["questions"]) >= 8
    return {
        "package_id": package["package_id"],
        "version": package["version"],
        "checksum": workbench["package_checksum"],
        "counts": actual,
    }


def analyze(request, question: str, case_id: str, expected_metric: str, expected_tokens: list[str]) -> dict[str, object]:
    response = request.post(
        f"{BASE_URL}/api/solutions/{SOLUTION}/analyze",
        data={
            "question": question,
            "role": "MarketSurveillanceDemo",
            "question_case_id": case_id,
        },
        timeout=180_000,
    )
    assert response.ok, response.text()
    payload = response.json()
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["status"] == "ANSWERED", payload
    assert payload["llm"]["status"] == "GROUNDED", payload["llm"]
    assert expected_metric in serialized, serialized
    for token in expected_tokens:
        assert token in serialized, f"{token!r} missing from {serialized}"
    assert payload.get("execution_id")
    assert payload.get("snapshot_checksum")
    return {
        "question": question,
        "metric": expected_metric,
        "answer": payload["answer"],
        "llm": payload["llm"],
        "execution_id": payload["execution_id"],
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=CHROME)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        context.add_cookies(
            [
                {
                    "name": "atlas_demo_session",
                    "value": issue_session(),
                    "url": BASE_URL,
                    "httpOnly": True,
                    "sameSite": "Lax",
                }
            ]
        )
        page = context.new_page()
        page.on(
            "console",
            lambda message: errors.append(f"console:{message.text}")
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: errors.append(f"page:{error}"))

        package_summary = assert_package_contract(context.request)

        goto_ready(page, "/ontology-studio/solutions/", ".solution-directory")
        page.get_by_placeholder("名称或 Solution ID").fill(SOLUTION)
        expect(page.get_by_text("现金市场订单与成交活动监控", exact=True)).to_be_visible()
        page.screenshot(path=OUTPUT / "01-solution-directory.png", full_page=False)
        page.get_by_role("button", name="新建解决方案").click()
        expect(page.get_by_role("dialog", name="新建解决方案")).to_be_visible()
        expect(page.get_by_text("构建所需材料", exact=True)).to_be_visible()
        page.screenshot(path=OUTPUT / "02-build-entry.png", full_page=False)
        page.get_by_role("button", name="关闭").click()

        goto_ready(
            page,
            f"/ontology-studio/solutions/{SOLUTION}/overview/",
            ".studio-package-inventory",
        )
        expect(page.get_by_role("heading", name="Package 内容")).to_be_visible()
        expect(page.get_by_text("业务模型", exact=True).last).to_be_visible()
        page.screenshot(path=OUTPUT / "03-package-overview.png", full_page=False)

        goto_ready(
            page,
            f"/ontology-studio/solutions/{SOLUTION}/semantic/model/",
            ".semantic-asset-catalog",
        )
        expect(page.get_by_role("heading", name="业务模型", exact=True).last).to_be_visible()
        expect(page.locator(".asset-category-nav")).to_contain_text("对象")
        expect(page.locator(".asset-category-nav")).to_contain_text("9")
        page.screenshot(path=OUTPUT / "04-business-model.png", full_page=False)

        goto_ready(
            page,
            f"/ontology-studio/solutions/{SOLUTION}/semantic/metrics/",
            ".semantic-asset-catalog",
        )
        expect(page.locator(".asset-category-nav")).to_contain_text("指标")
        expect(page.locator(".asset-category-nav")).to_contain_text("22")
        page.screenshot(path=OUTPUT / "05-metrics-and-rules.png", full_page=False)

        goto_ready(
            page,
            f"/ontology-studio/solutions/{SOLUTION}/semantic/graph/",
            ".ontology-graph-workspace",
        )
        page.locator(".react-flow__node").first.wait_for(timeout=45_000)
        expect(page.get_by_role("heading", name="知识图谱", exact=True).last).to_be_visible()
        page.screenshot(path=OUTPUT / "06-knowledge-graph.png", full_page=False)

        goto_ready(
            page,
            f"/ontology-studio/solutions/{SOLUTION}/inputs/sources/",
            ".source-library-page",
        )
        expect(page.get_by_role("heading", name="来源材料与证据版本")).to_be_visible()
        source_rows = page.locator(".source-library-row")
        fallback_rows = page.locator(".source-library-table article")
        assert source_rows.count() >= 4 or fallback_rows.count() >= 4
        if source_rows.count():
            source_rows.first.click()
            page.locator(".source-preview-drawer").wait_for(timeout=30_000)
            page.locator(".drawer-loading").wait_for(state="detached", timeout=30_000)
            expect(page.locator(".source-preview-content")).not_to_be_empty()
        page.screenshot(path=OUTPUT / "07-source-preview.png", full_page=False)

        live_results = [
            analyze(
                context.request,
                "What was the order rejection rate from 2026-08-03 to 2026-08-07?",
                "cash.metric.m01.rejection-rate.en.v2",
                "metric.order_rejection_rate",
                ["16.666667"],
            ),
            analyze(
                context.request,
                "What were p50, p95 and p99 trade capture latency from 2026-08-03 to 2026-08-07?",
                "cash.metric.m03.latency.en.v2",
                "metric.trade_capture_latency_ms",
                ["15", "9"],
            ),
            analyze(
                context.request,
                "Show the daily potential self-trade rate from 2026-08-03 to 2026-08-07.",
                "cash.metric.m08.self-trade-trend.en.v2",
                "metric.potential_self_trade_rate",
                ["10.0", "triage"],
            ),
        ]

        goto_ready(
            page,
            f"/ontology-agent/?solution={SOLUTION}",
            ".agent-console",
        )
        expect(page.get_by_role("heading", name="现金市场订单与成交活动监控")).to_be_visible()
        expect(page.locator(".agent-starters button")).to_have_count(8)
        first_question = page.locator(".agent-starters button").first
        first_question.click()
        page.get_by_role("button", name="发送").click()
        page.locator(".agent-answer-copy").wait_for(timeout=180_000)
        expect(page.locator(".agent-query-results")).to_be_visible()
        expect(page.get_by_text("DeepAgent · Qwen 3.8 Max", exact=True).first).to_be_visible()
        page.screenshot(path=OUTPUT / "08-agent-answer.png", full_page=False)

        if errors:
            raise AssertionError("Browser errors: " + " | ".join(errors))
        browser.close()

    print(
        json.dumps(
            {
                "status": "PASS",
                "package": package_summary,
                "live_agent_checks": live_results,
                "screenshots": str(OUTPUT),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
