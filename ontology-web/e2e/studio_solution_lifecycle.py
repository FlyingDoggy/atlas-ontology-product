from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


BASE_URL = os.environ["ONTOLOGY_E2E_BASE_URL"].rstrip("/")
ACCESS_FILE = Path(os.environ["ONTOLOGY_DEMO_ACCESS_FILE"])
EVIDENCE_DIR = Path(os.environ["ONTOLOGY_E2E_EVIDENCE_DIR"])


def credentials() -> tuple[str, str]:
    values: dict[str, str] = {}
    for raw_line in ACCESS_FILE.read_text(encoding="utf-8").splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip().lower()] = value.strip()
    return values["username"], values["password"]


def open_row_menu(row) -> None:
    details = row.locator("details")
    if details.get_attribute("open") is None:
        details.locator("summary").click()


def main() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    username, password = credentials()
    suffix = time.strftime("%H%M%S")
    original_name = f"目录生命周期验证 {suffix}"
    updated_name = f"目录生命周期验证（已更新）{suffix}"
    browser_errors: list[str] = []
    failed_product_responses: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1536, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.set_default_navigation_timeout(60_000)
        page.on(
            "console",
            lambda message: browser_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
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

        page.goto(f"{BASE_URL}/ontology-studio/solutions/")
        page.wait_for_load_state("networkidle")
        if urlparse(page.url).path == "/login/":
            page.get_by_label("用户名", exact=True).fill(username)
            page.get_by_label("密码", exact=True).fill(password)
            page.locator("#submit-button").click()
            page.wait_for_url(lambda value: urlparse(value).path != "/login/")
            page.goto(
                f"{BASE_URL}/ontology-studio/solutions/", wait_until="networkidle"
            )
        page.get_by_role("heading", name="全部解决方案", exact=True).wait_for()

        page.get_by_role("button", name="新建解决方案").click()
        dialog = page.get_by_role("dialog", name="新建解决方案")
        dialog.get_by_label("中文名称").fill(original_name)
        dialog.get_by_label("英文名称").fill(f"Directory lifecycle verification {suffix}")
        dialog.get_by_label("业务场景描述").fill("验证模板克隆与 Solution Directory 生命周期的临时测试方案。")
        dialog.get_by_label("负责人").fill("Release Verification")
        with page.expect_response(
            lambda response: response.url.endswith("/control/solutions")
            and response.request.method == "POST"
        ) as create_response:
            dialog.get_by_role("button", name="创建 Draft Solution").click()
        created = create_response.value
        assert created.status == 201, f"create returned HTTP {created.status}"
        payload = created.json()
        solution_id = payload["solution"]["solution_id"]
        assert solution_id.startswith("ontology.custom.")
        page.get_by_role("heading", name="概览", exact=True).wait_for()
        assert solution_id in page.url
        page.screenshot(path=str(EVIDENCE_DIR / "01-created-solution.png"), full_page=True)

        page.goto(
            f"{BASE_URL}/ontology-studio/solutions/?solution={solution_id}",
            wait_until="networkidle",
        )
        row = page.locator(".solution-directory-table article", has_text=solution_id)
        row.wait_for()
        open_row_menu(row)
        row.get_by_role("button", name="编辑信息").click()
        edit_dialog = page.get_by_role("dialog", name="编辑解决方案信息")
        edit_dialog.get_by_label("中文名称").fill(updated_name)
        edit_dialog.get_by_label("负责人").fill("Ontology Release Team")
        with page.expect_response(
            lambda response: f"/control/solutions/{solution_id}/metadata" in response.url
            and response.request.method == "PATCH"
        ) as update_response:
            edit_dialog.get_by_role("button", name="保存信息").click()
        assert update_response.value.status == 200
        row = page.locator(".solution-directory-table article", has_text=solution_id)
        row.get_by_text(updated_name, exact=True).wait_for()

        open_row_menu(row)
        with page.expect_response(
            lambda response: response.url.endswith(f"/control/solutions/{solution_id}/archive")
            and response.request.method == "POST"
        ) as archive_response:
            row.get_by_role("button", name="归档").click()
        assert archive_response.value.status == 200
        row = page.locator(".solution-directory-table article", has_text=solution_id)
        row.get_by_text("已归档", exact=True).wait_for()
        page.screenshot(path=str(EVIDENCE_DIR / "02-archived-solution.png"), full_page=True)

        open_row_menu(row)
        with page.expect_response(
            lambda response: response.url.endswith(f"/control/solutions/{solution_id}/restore")
            and response.request.method == "POST"
        ) as restore_response:
            row.get_by_role("button", name="恢复").click()
        assert restore_response.value.status == 200
        row = page.locator(".solution-directory-table article", has_text=solution_id)
        row.get_by_text("使用中", exact=True).wait_for()

        open_row_menu(row)
        with page.expect_response(
            lambda response: response.url.endswith(f"/control/solutions/{solution_id}/archive")
            and response.request.method == "POST"
        ) as second_archive_response:
            row.get_by_role("button", name="归档").click()
        assert second_archive_response.value.status == 200
        row = page.locator(".solution-directory-table article", has_text=solution_id)
        row.get_by_text("已归档", exact=True).wait_for()

        open_row_menu(row)
        row.get_by_role("button", name="永久移除").click()
        delete_dialog = page.get_by_role("dialog", name="永久移除解决方案")
        delete_dialog.get_by_label("输入完整名称以确认").fill(updated_name)
        with page.expect_response(
            lambda response: response.url.endswith(f"/control/solutions/{solution_id}")
            and response.request.method == "DELETE"
        ) as delete_response:
            delete_dialog.get_by_role("button", name="永久移除").click()
        deleted = delete_response.value
        assert deleted.status == 200
        assert deleted.json()["audit_artifacts_retained"] is True
        page.locator(".solution-directory-table article", has_text=solution_id).wait_for(
            state="detached"
        )

        assert not browser_errors, f"Browser errors: {browser_errors}"
        assert not failed_product_responses, (
            f"Unexpected product HTTP failures: {failed_product_responses}"
        )
        browser.close()

    print(f"studio_solution_lifecycle: PASS ({solution_id})")


if __name__ == "__main__":
    main()
