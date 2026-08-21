from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright


PROJECT_ROOT = Path(__file__).parents[2]
BASE_URL = os.environ.get("ONTOLOGY_COMMON_URL", "http://127.0.0.1:18080").rstrip("/")
ACCESS_FILE = Path(
    os.environ.get("ONTOLOGY_DEMO_ACCESS_FILE", PROJECT_ROOT / "AWS info" / "demo-access.txt")
)
OUTPUT = Path(
    os.environ.get(
        "ONTOLOGY_TEST_OUTPUT",
        PROJECT_ROOT / "outputs" / "release-0.9-browser",
    )
)
ADT = "ontology.exchange_analytics.adt"
CASH = "ontology.exchange_analytics.cash_trading"


def require(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def access_credentials() -> tuple[str, str]:
    username = os.environ.get("ONTOLOGY_DEMO_USERNAME")
    password = os.environ.get("ONTOLOGY_DEMO_PASSWORD")
    if username and password:
        return username, password
    values: dict[str, str] = {}
    for line in ACCESS_FILE.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip().lower()] = value.strip()
    if not values.get("username") or not values.get("password"):
        raise RuntimeError("Demo access file does not contain Username and Password")
    return values["username"], values["password"]


def wait_for_solution(page: Page, solution_id: str) -> None:
    page.wait_for_load_state("networkidle")
    page.locator(".hero-identity code", has_text=solution_id).wait_for()
    page.locator(".role-control select").wait_for()


def run_request(page: Page) -> dict[str, object]:
    with page.expect_response(
        lambda response: "/api/solutions/" in response.url
        and response.url.endswith("/analyze")
        and response.request.method == "POST",
        timeout=60_000,
    ) as response_info:
        page.locator(".run-analysis").click()
    response = response_info.value
    require(response.status == 200, f"analysis returned HTTP {response.status}")
    payload = response.json()
    require(isinstance(payload, dict), "analysis response is not an object")
    return payload


def run_answer(page: Page, expected_badge: str) -> dict[str, object]:
    payload = run_request(page)
    page.locator(".answer-result").wait_for(timeout=60_000)
    page.locator(".answer-badges b", has_text="ANSWERED").wait_for()
    page.locator(".llm-state", has_text=expected_badge).wait_for()
    return payload


OUTPUT.mkdir(parents=True, exist_ok=True)
username, password = access_credentials()
console_errors: list[str] = []
failed_product_responses: list[tuple[int, str]] = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 1100})
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
        lambda response: failed_product_responses.append((response.status, response.url))
        if response.status >= 400
        and any(segment in response.url for segment in ("/api/", "/control/", "/agent-control/"))
        else None,
    )

    page.goto(f"{BASE_URL}/ontology-agent/", wait_until="networkidle")
    require(urlparse(page.url).path == "/login/", "unauthenticated product did not open login page")
    page.locator("#username").fill(username)
    page.locator("#password").fill(password)
    page.locator("#submit-button").click()
    page.wait_for_url(lambda value: urlparse(value).path == "/ontology-agent/")

    wait_for_solution(page, ADT)
    adt_roles = page.locator(".role-control select option").all_text_contents()
    require(page.locator(".role-control select").input_value() == "MarketAnalyst", "ADT default role is not package-owned")
    require(any("ExecutiveViewer" in role for role in adt_roles), "ADT permitted role is missing")
    require(any("ExternalUser" in role and "拒绝演示" in role for role in adt_roles), "ADT denied role is missing")
    require(not any("MarketSurveillanceDemo" in role for role in adt_roles), "Cash role leaked into ADT")
    adt_payload = run_answer(page, "QWEN GROUNDED")
    require(adt_payload["llm"]["model_called"] is True, "ADT registered question did not call Qwen")
    require(page.locator("details summary", has_text="条证据").count() == 1, "ADT evidence disclosure is missing")
    page.screenshot(path=str(OUTPUT / "01-adt-qwen-grounded.png"), full_page=True)

    question = page.get_by_label("业务问题")
    question.fill(question.input_value() + " Please.")
    edited_payload = run_request(page)
    page.locator(".answer-boundary", has_text="REFUSED").wait_for()
    require(edited_payload["status"] == "REFUSED", "edited question was not bounded")
    require(edited_payload["llm"]["model_called"] is False, "unregistered question was sent to Qwen")
    require(edited_payload["llm"]["status"] == "DETERMINISTIC_ONLY", "unregistered path was not deterministic")
    require(edited_payload["facts"] == {}, "refused question released facts")
    require(edited_payload["evidence"] == [], "refused question released evidence")
    require(
        page.locator(".analysis-boundary", has_text="不会外发给模型").count() == 1,
        "edited question is not visibly contained",
    )
    page.screenshot(path=str(OUTPUT / "02-adt-unregistered-deterministic.png"), full_page=True)

    page.get_by_label("切换解决方案").click()
    page.locator(".solution-switcher-list a", has_text="现金市场订单与成交活动监控").click()
    page.wait_for_url(lambda value: urlparse(value).path == "/ontology-agent/" and CASH in value)
    wait_for_solution(page, CASH)
    require(
        page.locator(".role-control select").input_value() == "MarketSurveillanceDemo",
        "Cash default role is not package-owned",
    )
    require(page.locator(".question-family button").count() == 4, "Cash question family was not loaded")
    cash_payload = run_answer(page, "QWEN GROUNDED")
    require(cash_payload["llm"]["model_called"] is True, "Cash registered question did not call Qwen")
    page.screenshot(path=str(OUTPUT / "03-cash-qwen-grounded.png"), full_page=True)

    page.locator("a.product-switch").click()
    page.wait_for_url(lambda value: urlparse(value).path == "/ontology-studio/" and CASH in value)
    page.wait_for_load_state("networkidle")
    page.get_by_role("heading", name="概览", exact=True).wait_for()
    page.locator(".studio-sidebar-context", has_text="现金市场订单与成交活动监控").wait_for()
    require(
        page.locator("a.product-switch").get_attribute("href")
        == f"/ontology-agent/?solution={CASH}",
        "Studio-to-Agent link did not preserve the selected solution",
    )
    page.screenshot(path=str(OUTPUT / "04-cash-studio-linked.png"), full_page=True)

    require(not failed_product_responses, f"Product HTTP failures: {failed_product_responses}")
    require(not console_errors, f"Browser errors: {console_errors}")
    browser.close()

print(
    json.dumps(
        {
            "status": "PASS",
            "release": "0.9.0-solution-aware-llm.1",
            "checks": [
                "FORM_LOGIN",
                "PACKAGE_OWNED_ROLES",
                "ADT_QWEN_GROUNDED",
                "UNREGISTERED_ZERO_EGRESS_VISIBLE",
                "CASH_QWEN_GROUNDED",
                "CROSS_PRODUCT_SOLUTION_LINK",
                "NO_BROWSER_ERRORS",
            ],
            "screenshots": str(OUTPUT),
        },
        ensure_ascii=False,
        indent=2,
    )
)
