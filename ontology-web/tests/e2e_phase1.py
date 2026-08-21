from __future__ import annotations

import json
from pathlib import Path
import subprocess

from playwright.sync_api import expect, sync_playwright


BASE_URL = "http://127.0.0.1:18080"
ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "test-artifacts"


def issue_test_session() -> str:
    command = (
        "from ontology_agent.demo_auth import AuthSettings,DemoAuthService;"
        "print(DemoAuthService(AuthSettings.from_env()).issue_session())"
    )
    result = subprocess.run(
        [
            "docker",
            "exec",
            "ontology-common-product-auth-1",
            "python",
            "-c",
            command,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if not token or "\n" in token:
        raise AssertionError("Auth service did not issue one test session")
    return token


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        anonymous = browser.new_page(viewport={"width": 1440, "height": 1000})
        anonymous.goto(f"{BASE_URL}/ontology-agent/")
        anonymous.wait_for_load_state("networkidle")
        assert "/login/" in anonymous.url
        expect(anonymous.get_by_role("heading", name="进入工作区")).to_be_visible()
        anonymous.close()

        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_cookies(
            [
                {
                    "name": "atlas_demo_session",
                    "value": issue_test_session(),
                    "url": BASE_URL,
                    "httpOnly": True,
                    "sameSite": "Lax",
                }
            ]
        )
        page = context.new_page()
        console_errors: list[str] = []
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.goto(f"{BASE_URL}/ontology-agent/")
        page.wait_for_load_state("networkidle")

        expect(
            page.get_by_role("heading", name="当前生效的分析语境")
        ).to_be_visible(timeout=10_000)
        expect(page.get_by_text("PostgreSQL", exact=True)).to_be_visible()
        expect(page.get_by_text("S3-compatible · exact version", exact=True)).to_be_visible()
        expect(page.get_by_text("上下文工件已按 exact version 回读", exact=True)).to_be_visible()
        expect(
            page.get_by_role("main").get_by_text("ADT参考分析", exact=True)
        ).to_be_visible()
        assert page.get_by_text("legacy compatibility 模式", exact=False).count() == 0
        page.screenshot(path=ARTIFACT_DIR / "phase1-agent.png", full_page=True)

        api_response = context.request.get(f"{BASE_URL}/api/product/context")
        assert api_response.ok
        payload = api_response.json()
        assert payload["persistence"] == "postgresql-s3"
        assert payload["artifact"]["sha256"] == payload["subject_checksum"]
        assert payload["subject"]["classification"] == "constructed_synthetic"

        page.get_by_role("link", name="进入 Ontology Studio").click()
        page.wait_for_load_state("networkidle")
        assert page.url.endswith("/ontology-studio/")
        expect(page.get_by_role("heading", name="业务语义的配置入口")).to_be_visible()
        expect(page.get_by_role("heading", name="已安装的场景组件")).to_be_visible()
        expect(page.get_by_role("heading", name="ADT参考分析").first).to_be_visible()
        expect(page.get_by_text("Authoring profile", exact=True).last).to_be_visible()
        expect(page.get_by_text("Semantic source", exact=True).last).to_be_visible()
        expect(page.get_by_text("Agent experience", exact=True).last).to_be_visible()
        expect(page.get_by_text("Reference & control", exact=True).last).to_be_visible()
        catalog_response = context.request.get(f"{BASE_URL}/control/solutions")
        assert catalog_response.ok
        catalog = catalog_response.json()
        assert catalog["contract"] == "studio-solution-catalog/v1"
        assert len(catalog["solutions"]) >= 1
        solution = max(
            catalog["solutions"],
            key=lambda item: tuple(int(part) for part in item["solution_version"].split(".")),
        )
        assert solution["solution_id"] == payload["subject"]["solution_id"]
        assert solution["semantic_source_version"] == payload["subject"]["solution_version"]
        assert solution["persistence"] == "postgresql-s3"
        assert solution["artifact"]["sha256"] == solution["subject_checksum"]
        expect(page.get_by_role("heading", name="ADT 语义草稿")).to_be_visible()
        expect(page.get_by_text("PostgreSQL + S3", exact=True)).to_be_visible()
        expect(page.get_by_text("指标定义", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="保存草稿")).to_be_visible()
        expect(page.get_by_role("button", name="验证当前版本")).to_be_visible()
        expect(page.get_by_role("button", name="发布语义版本")).to_be_visible()
        editor_response = context.request.get(
            f"{BASE_URL}/control/workspaces/{solution['workspace_id']}/editor"
        )
        assert editor_response.ok
        editor = editor_response.json()
        assert editor["contract"] == "studio-workspace-editor/v1"
        assert editor["persistence"] == "postgresql-s3"
        assert editor["descriptor"]["workspace_id"] == editor["workspace"]["workspace_id"]
        assert len(editor["descriptor"]["fields"]) == 5
        page.screenshot(path=ARTIFACT_DIR / "phase1-studio.png", full_page=True)

        if console_errors:
            raise AssertionError(
                "Browser console errors: " + json.dumps(console_errors, ensure_ascii=False)
            )
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
