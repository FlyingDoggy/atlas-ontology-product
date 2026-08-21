from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("ONTOLOGY_E2E_BASE_URL", "http://127.0.0.1:18081")
AUTH_ENV_FILE = Path(os.environ["ONTOLOGY_E2E_AUTH_ENV_FILE"])
EVIDENCE_DIR = Path(os.environ["ONTOLOGY_E2E_EVIDENCE_DIR"])


def _env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _session(settings: dict[str, str]) -> str:
    issued_at = int(time.time())
    ttl = int(settings.get("ONTOLOGY_AUTH_SESSION_TTL_SECONDS", "28800"))
    payload = {
        "v": 1,
        "sub": settings["ONTOLOGY_AUTH_USERNAME"],
        "iat": issued_at,
        "exp": issued_at + ttl,
        "nonce": secrets.token_urlsafe(12),
    }
    encoded = _b64(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        settings["ONTOLOGY_AUTH_SESSION_SECRET"].encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded}.{_b64(signature)}"


def main() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    settings = _env_file(AUTH_ENV_FILE)
    browser_errors: list[str] = []
    failed_responses: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1536, "height": 1000})
        page = context.new_page()
        page.on("console", lambda message: browser_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        page.on(
            "response",
            lambda response: failed_responses.append(f"{response.status} {response.url}")
            if response.status >= 400
            else None,
        )

        # Reconnaissance: prove the unauthenticated page is the real responsive login surface.
        page.goto(f"{BASE_URL}/ontology-agent/")
        page.wait_for_load_state("networkidle")
        assert page.url.startswith(f"{BASE_URL}/login/")
        assert page.get_by_label("用户名", exact=True).is_visible()
        assert page.get_by_label("密码", exact=True).is_visible()
        page.screenshot(path=str(EVIDENCE_DIR / "01-login.png"), full_page=True)

        context.add_cookies(
            [
                {
                    "name": "atlas_demo_session",
                    "value": _session(settings),
                    "url": BASE_URL,
                    "httpOnly": True,
                    "secure": settings.get("ONTOLOGY_AUTH_SECURE_COOKIE", "true").lower() == "true",
                    "sameSite": "Lax",
                }
            ]
        )

        # Agent: active package -> governed analysis -> visible evidence -> proposed SCR.
        page.goto(f"{BASE_URL}/ontology-agent/")
        page.wait_for_load_state("networkidle")
        page.get_by_role("heading", name="从业务问题走到可追溯答案").wait_for()
        assert page.get_by_role("link", name=re.compile("进入 Ontology Studio")).is_visible()
        page.get_by_role("button", name="运行受治理分析").click()
        page.get_by_text("COMMITTED ANALYSIS").wait_for(timeout=60_000)
        page.get_by_role("heading", name="执行计划与证据").wait_for()
        assert page.get_by_text(re.compile("QWEN (GROUNDED|SHADOW)")).first.is_visible()
        page.screenshot(path=str(EVIDENCE_DIR / "02-agent-answer.png"), full_page=True)

        page.get_by_role("button", name="反馈语义缺口").click()
        page.get_by_label("标题").fill("Browser verified semantic exploration gap")
        page.get_by_label("观察").fill("The current answer needs a governed continuation into segment concentration.")
        page.get_by_label("建议变更").fill("Review a package-owned concentration analysis pattern and its output contract.")
        page.get_by_role("button", name="提交为 Proposed Request").click()
        page.get_by_text("已进入 Studio inbox").wait_for(timeout=15_000)

        # Studio: hierarchical navigation, package workbench, model observation,
        # human review, feedback inbox, authoring and lifecycle.
        page.get_by_role("link", name=re.compile("进入 Ontology Studio")).click()
        page.wait_for_load_state("networkidle")
        page.get_by_role("heading", name="概览", exact=True).wait_for()
        page.get_by_role("navigation", name="Ontology Studio").wait_for()
        assert page.get_by_role("link", name=re.compile("输入与证据")).is_visible()
        assert page.get_by_role("link", name=re.compile("语义模型")).is_visible()
        assert page.get_by_role("link", name=re.compile("^数据")).is_visible()
        assert page.get_by_role("link", name=re.compile("版本与发布")).is_visible()
        page.screenshot(path=str(EVIDENCE_DIR / "03-studio-overview.png"), full_page=True)

        page.get_by_role("link", name=re.compile("质量与治理")).click()
        page.get_by_role("link", name=re.compile("AI 辅助复核")).click()
        page.get_by_role("heading", name="材料观察与人工复核").wait_for()

        generate = page.get_by_role("button", name="生成一组候选 Observation")
        if generate.is_enabled():
            generate.click()
        else:
            page.get_by_text(re.compile("已有一组待复核 Observation")).wait_for()
        page.get_by_text("OBSERVATION SET", exact=True).wait_for(timeout=60_000)
        review = page.get_by_role("button", name="应用人工复核到 Draft")
        review.click(timeout=20_000)
        page.get_by_role("button", name="本组已复核").wait_for(timeout=20_000)

        page.get_by_role("link", name=re.compile("问题与变更")).click()
        page.get_by_text("Browser verified semantic exploration gap").first.wait_for()
        page.screenshot(path=str(EVIDENCE_DIR / "04-studio-feedback.png"), full_page=True)

        page.get_by_role("link", name=re.compile("语义模型")).click()
        page.get_by_role("heading", name="语义模型工作台").wait_for()
        page.get_by_role("button", name="打开完整合同编辑器").click()
        page.get_by_role("heading", name="完整 Ontology 合同编辑器").wait_for()
        assert page.get_by_label("Contract collection").locator("option").count() == 14
        page.get_by_role("button", name="关闭").click()

        page.get_by_role("link", name=re.compile("输入与证据")).click()
        page.get_by_role("heading", name="ADT 语义草稿", exact=True).wait_for()
        with page.expect_response(
            lambda response: "/control/workspaces/" in response.url
            and response.url.endswith("/validate")
            and response.request.method == "POST"
        ) as validation_response:
            page.get_by_role("button", name="验证当前版本").click()
        validation = validation_response.value
        assert validation.ok, (
            f"workspace validation failed: HTTP {validation.status} "
            f"{validation.text()}"
        )
        page.get_by_text("EXACT VALIDATION PASS", exact=True).wait_for(timeout=20_000)

        with page.expect_response(
            lambda response: "/control/workspaces/" in response.url
            and response.url.endswith("/publish")
            and response.request.method == "POST"
        ) as publish_response:
            page.get_by_role("button", name="发布语义版本").click()
        publication = publish_response.value
        assert publication.ok, (
            f"workspace publication failed: HTTP {publication.status} "
            f"{publication.text()}"
        )

        page.get_by_role("link", name=re.compile("版本与发布")).click()
        page.get_by_role("heading", name="发布、认证、激活与验证").wait_for()
        assert page.get_by_role("link", name=re.compile("在 Agent 中打开")).is_visible()

        with page.expect_response(
            lambda response: response.url.endswith("/agent-control/runtime/prepare")
            and response.request.method == "POST"
        ) as prepare_response:
            page.get_by_role("button", name="准备并认证").click()
        assert prepare_response.value.ok
        page.get_by_text("PREPARED", exact=True).wait_for(timeout=30_000)

        activate = page.get_by_role("button", name="激活准备版本")
        if activate.is_enabled():
            with page.expect_response(
                lambda response: response.url.endswith("/agent-control/runtime/activate")
                and response.request.method == "POST"
            ) as activate_response:
                activate.click()
            assert activate_response.value.ok
        page.get_by_role("button", name=re.compile("回滚到上一版本")).wait_for(timeout=30_000)

        with page.expect_response(
            lambda response: response.url.endswith("/agent-control/runtime/verify-active")
            and response.request.method == "POST"
        ) as verify_response:
            page.get_by_role("button", name="验证当前 Active").click()
        assert verify_response.value.ok
        page.get_by_text("VERIFIED PASS", exact=True).wait_for(timeout=60_000)

        page.reload()
        page.wait_for_load_state("networkidle")
        page.get_by_role("heading", name="版本与发布", exact=True).wait_for()
        page.get_by_role("button", name=re.compile("回滚到上一版本")).wait_for()
        page.screenshot(path=str(EVIDENCE_DIR / "05-studio-lifecycle.png"), full_page=True)

        # Second-solution falsification: the same product shell must run a package that is
        # not ADT, while honestly showing that Studio LLM co-authoring is not installed.
        cash_solution = "ontology.exchange_analytics.cash_trading"
        page.goto(f"{BASE_URL}/ontology-agent/?solution={cash_solution}")
        page.wait_for_load_state("networkidle")
        page.get_by_role("heading", name="从业务问题走到可追溯答案").wait_for()
        page.locator(".hero-identity").get_by_text("现金市场订单与成交活动监控", exact=True).wait_for()
        page.get_by_role("button", name="运行受治理分析").click()
        page.get_by_text("COMMITTED ANALYSIS").wait_for(timeout=60_000)
        page.get_by_role("heading", name="执行计划与证据").wait_for()
        page.screenshot(path=str(EVIDENCE_DIR / "06-cash-agent.png"), full_page=True)

        page.goto(f"{BASE_URL}/ontology-studio/?solution={cash_solution}")
        page.wait_for_load_state("networkidle")
        page.get_by_role("heading", name="概览", exact=True).wait_for()
        page.locator(".studio-sidebar-context > strong").get_by_text(
            "现金市场订单与成交活动监控", exact=True
        ).wait_for()
        page.get_by_role("link", name=re.compile("质量与治理")).click()
        page.get_by_role("link", name=re.compile("AI 辅助复核")).click()
        page.get_by_text(
            "当前 solution 未安装可用的 Studio LLM profile", exact=True
        ).wait_for()
        assert not page.get_by_role("button", name="生成一组候选 Observation").is_enabled()
        page.get_by_role("link", name=re.compile("语义模型")).click()
        page.get_by_role("heading", name="语义模型工作台").wait_for()
        page.get_by_role("button", name="打开完整合同编辑器").click()
        assert page.get_by_label("Contract collection").locator("option").count() == 14
        page.get_by_role("button", name="关闭").click()
        page.get_by_role("link", name=re.compile("版本与发布")).click()
        page.get_by_role("heading", name="发布、认证、激活与验证").wait_for()
        page.screenshot(path=str(EVIDENCE_DIR / "07-cash-studio.png"), full_page=True)

        browser.close()

    unexpected = [item for item in failed_responses if "/favicon" not in item]
    assert not browser_errors, f"Browser errors: {browser_errors}"
    assert not unexpected, f"Failed responses: {unexpected}"
    print("candidate_smoke: PASS")


if __name__ == "__main__":
    main()
