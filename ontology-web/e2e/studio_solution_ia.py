from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("ONTOLOGY_E2E_BASE_URL", "http://127.0.0.1:8780")
ACCESS_FILE = Path(os.environ["ONTOLOGY_DEMO_ACCESS_FILE"])
EVIDENCE_DIR = Path(
    os.environ.get("ONTOLOGY_E2E_EVIDENCE_DIR", "test-artifacts/studio-solution-ia")
)


def credentials() -> tuple[str, str]:
    values: dict[str, str] = {}
    for raw_line in ACCESS_FILE.read_text(encoding="utf-8").splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip().lower()] = value.strip()
    return values["username"], values["password"]


def main() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    username, password = credentials()
    console_errors: list[str] = []
    failed_responses: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1536, "height": 1000})
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.on(
            "response",
            lambda response: failed_responses.append(f"{response.status} {response.url}")
            if response.status >= 400
            else None,
        )

        page.goto(f"{BASE_URL}/ontology-studio/")
        page.wait_for_load_state("networkidle")
        if urlparse(page.url).path == "/login/":
            page.get_by_label("用户名", exact=True).fill(username)
            page.get_by_label("密码", exact=True).fill(password)
            page.locator("#submit-button").click()
            page.wait_for_url(lambda value: urlparse(value).path != "/login/")
            page.goto(f"{BASE_URL}/ontology-studio/", wait_until="networkidle")
        page.get_by_role("heading", name="概览", exact=True).wait_for()
        navigation = page.get_by_role("navigation", name="Ontology Studio")
        assert navigation.get_by_role("link").count() == 6
        for label in ("概览", "输入与证据", "语义模型", "数据", "质量与治理", "版本与发布"):
            assert navigation.get_by_role("link", name=label, exact=False).is_visible()
        assert navigation.get_by_role("link", name="解决方案", exact=True).count() == 0
        page.screenshot(path=str(EVIDENCE_DIR / "01-workspace-overview.png"), full_page=True)

        page.get_by_label("切换解决方案").click()
        page.get_by_placeholder("名称或 ID").fill("现金")
        assert page.locator(".solution-switcher-list a").count() == 1
        page.screenshot(path=str(EVIDENCE_DIR / "02-solution-switcher.png"), full_page=True)

        page.goto(f"{BASE_URL}/ontology-studio/solutions/")
        page.wait_for_load_state("networkidle")
        page.get_by_role("heading", name="全部解决方案", exact=True).wait_for()
        assert page.locator(".solution-directory-table article").count() >= 2
        page.get_by_role("button", name="新建解决方案").click()
        page.get_by_role("dialog", name="新建解决方案").wait_for()
        assert page.get_by_text("从模板创建", exact=True).is_visible()
        assert page.get_by_role("button", name="创建 Draft Solution").is_visible()
        page.screenshot(path=str(EVIDENCE_DIR / "03-create-solution.png"), full_page=True)
        page.get_by_role("button", name="关闭").click()

        page.get_by_role("link", name="打开", exact=True).first.click()
        page.get_by_role("heading", name="概览", exact=True).wait_for()
        navigation.get_by_role("link", name="质量与治理", exact=False).click()
        page.get_by_role("navigation", name="质量与治理子页面").wait_for()
        page.get_by_role("link", name="复核中心", exact=False).click()
        page.get_by_role("heading", name="候选复核中心").wait_for()
        page.screenshot(path=str(EVIDENCE_DIR / "04-quality-subnavigation.png"), full_page=True)

        browser.close()

    unexpected = [item for item in failed_responses if "/favicon" not in item]
    assert not console_errors, f"Browser errors: {console_errors}"
    assert not unexpected, f"Failed responses: {unexpected}"
    print("studio_solution_ia: PASS")


if __name__ == "__main__":
    main()
