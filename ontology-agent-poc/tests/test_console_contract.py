from __future__ import annotations

from pathlib import Path


CONSOLE_ROOT = Path(__file__).parents[2] / "ontology-console"


def _function(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_live_chat_is_an_api_caller_not_a_browser_evaluator() -> None:
    source = (CONSOLE_ROOT / "app.js").read_text(encoding="utf-8")
    body = _function(
        source,
        "async function submitChat()",
        "function backendIntent",
    )

    assert "api.analyze(question)" in body
    for forbidden in (
        "parseQuestion(",
        "authorizeLogicalPlan(",
        "compilePhysicalPlan(",
        "executePhysicalPlan(",
        "SOURCE_FIXTURES",
    ):
        assert forbidden not in body


def test_dashboard_is_a_projection_of_one_governed_agent_response() -> None:
    source = (CONSOLE_ROOT / "app.js").read_text(encoding="utf-8")
    body = _function(
        source,
        "async function loadAnalysisDashboard()",
        "function unavailableChatView",
    )

    assert "api.analyze(" in body
    for forbidden in (
        "parseQuestion(",
        "authorizeLogicalPlan(",
        "compilePhysicalPlan(",
        "executePhysicalPlan(",
        "SOURCE_FIXTURES",
    ):
        assert forbidden not in body

    rendered = _function(source, "function dashboardView()", "async function loadAnalysisDashboard()")
    assert "payload.facts" in rendered
    assert "payload.evidence" in rendered
    assert "payload.snapshot_checksum" in rendered


def test_browser_publish_cannot_mutate_active_runtime() -> None:
    source = (CONSOLE_ROOT / "app.js").read_text(encoding="utf-8")
    body = _function(source, "function publishDraft()", "function nextVersion")

    assert "studioApi.publishDraft(" in body
    assert "state.published.active" not in body


def test_studio_live_actions_use_the_control_api() -> None:
    source = (CONSOLE_ROOT / "app.js").read_text(encoding="utf-8")
    save = _function(source, "async function saveDraft()", "async function runValidation()")
    validate = _function(
        source,
        "async function runValidation()",
        "function validateContent",
    )

    assert "studioApi.patchDraft(" in save
    assert "studioApi.validateDraft(" in validate
    assert "validateContent(" not in validate


def test_operator_journey_uses_the_agent_control_api() -> None:
    source = (CONSOLE_ROOT / "app.js").read_text(encoding="utf-8")
    prepare = _function(
        source,
        "async function prepareReleasedRuntime()",
        "async function activatePreparedRuntime()",
    )
    activate = _function(
        source,
        "async function activatePreparedRuntime()",
        "async function verifyActiveRuntime()",
    )
    verify = _function(
        source,
        "async function verifyActiveRuntime()",
        "function nextVersion",
    )

    assert "operatorApi.prepare(release)" in prepare
    assert "operatorApi.activate(" in activate
    assert "state.operator.active" in activate
    assert "operatorApi.verifyActive(active)" in verify
    assert "run_golden_suite" not in source


def test_console_has_no_second_live_adt_truth() -> None:
    source = (CONSOLE_ROOT / "app.js").read_text(encoding="utf-8")

    assert "browserAnalysisFallbackCalls: 0" in source
    for retired_truth in (
        "XHKG-CASH",
        "286355",
        "229799",
        "HKEX Monthly Market Highlights",
    ):
        assert retired_truth not in source


def test_typed_client_owns_the_runtime_http_contract() -> None:
    source = (CONSOLE_ROOT / "api-client.js").read_text(encoding="utf-8")

    for route in (
        "/api/readyz",
        "/api/runtime/active",
        "/api/ontology",
        "/api/analyze",
        "/control/workspaces/",
        "/draft",
        "/validate",
        "/publish",
        "/agent-control/runtime/prepare",
        "/agent-control/runtime/activate",
        "/agent-control/runtime/verify-active",
    ):
        assert route in source
    assert "STATUSES" in source
    assert "fallback" not in source.lower()


def test_demo_console_uses_same_origin_and_reverse_proxy_boundaries() -> None:
    runtime_config = (CONSOLE_ROOT / "runtime-config.demo.js").read_text(encoding="utf-8")
    nginx = (CONSOLE_ROOT / "nginx.conf").read_text(encoding="utf-8")

    assert runtime_config.count("global.location.origin") == 3
    assert "global.ATLAS_API_BASE || global.location.origin" in runtime_config
    assert "global.ATLAS_CONTROL_API_BASE || global.location.origin" in runtime_config
    assert "global.ATLAS_AGENT_CONTROL_API_BASE || global.location.origin" in runtime_config
    for route, upstream in (
        ("location /api/", "runtime:8790"),
        ("location /control/", "studio:8791"),
        ("location /agent-control/", "agent-control:8792"),
    ):
        assert route in nginx
        assert upstream in nginx

    assert "return 302 /ontology-agent/" in nginx
    assert "absolute_redirect off" in nginx
    assert "auth_request /_auth_verify" in nginx
    assert "proxy_pass http://auth:8793/auth/verify" in nginx
    assert "location ^~ /login/" in nginx
    assert "auth_basic" not in nginx
    assert nginx.count('proxy_set_header Authorization ""') == 4
    assert "location ^~ /ontology-agent/" in nginx
    assert "location ^~ /ontology-studio/" in nginx
    assert nginx.count("alias /usr/share/nginx/html/;\n") == 2


def test_public_demo_uses_outbound_tunnel_without_public_origin_port() -> None:
    compose = (CONSOLE_ROOT.parent / "deploy" / "adt-demo" / "docker-compose.yml").read_text(encoding="utf-8")

    assert '127.0.0.1:${ONTOLOGY_DEMO_LOCAL_PORT:-8080}:8080' in compose
    assert "cloudflare/cloudflared:2026.7.3" in compose
    assert '"--url", "http://console:8080"' in compose
    assert '"ontology_agent.demo_auth:app"' in compose
    assert "./secrets/auth/auth.env" in compose
    assert ".htpasswd" not in compose
    assert "0.0.0.0:80" not in compose


def test_public_product_paths_select_the_correct_product_surface() -> None:
    source = (CONSOLE_ROOT / "app.js").read_text(encoding="utf-8")
    html = (CONSOLE_ROOT / "index.html").read_text(encoding="utf-8")

    assert 'path.endsWith("/ontology-agent")' in source
    assert 'path.endsWith("/ontology-studio")' in source
    assert 'entryProductSurface === "agent" ? "chat" : "ontology"' in source
    assert 'return surface === "agent" ? "/ontology-agent/" : "/ontology-studio/"' in source
    assert 'window.location.assign(productPath(targetSurface))' in source
    assert 'id="product-studio-link"' in html
    assert 'href="/ontology-studio/"' in html
    assert 'id="product-agent-link"' in html
    assert 'href="/ontology-agent/"' in html
    assert 'link.setAttribute("aria-current", "page")' in source
    assert 'window.location.protocol === "file:"' in source


def test_login_page_uses_server_session_and_allowlisted_local_destinations() -> None:
    html = (CONSOLE_ROOT / "login.html").read_text(encoding="utf-8")
    source = (CONSOLE_ROOT / "login.js").read_text(encoding="utf-8")
    nginx = (CONSOLE_ROOT / "nginx.conf").read_text(encoding="utf-8")

    assert 'autocomplete="username"' in html
    assert 'autocomplete="current-password"' in html
    assert 'name="viewport"' in html
    assert 'fetch("/auth/login"' in source
    assert 'fetch("/auth/session"' in source
    assert 'credentials: "same-origin"' in source
    assert 'new Set(["/ontology-agent/", "/ontology-studio/"])' in source
    assert "parsed.origin !== window.location.origin" in source
    assert "auth_request /_auth_verify" in nginx
    assert "error_page 401 = @login_redirect" in nginx


def test_studio_ai_workbench_is_source_to_human_decision_not_chat_or_publish() -> None:
    client = (CONSOLE_ROOT / "api-client.js").read_text(encoding="utf-8")
    source = (CONSOLE_ROOT / "app.js").read_text(encoding="utf-8")

    for method in (
        "studioLLMStatus",
        "observationSets",
        "generateObservations",
        "reviewObservations",
    ):
        assert "async " + method + "(" in client
    assert '"/llm/observations"' in client
    assert '"/review"' in client
    assert "/llm/publish" not in client

    workbench = _function(
        source,
        "function studioObservationWorkbench()",
        "function ontologyLayout()",
    )
    assert "PROPOSED · not published ontology" in workbench
    assert "Source evidence" in workbench
    assert "Qwen proposal" in workbench
    assert "Human decision" in workbench
    assert "data-observation-action" in workbench
    assert "publishDraft(" not in workbench

    generate = _function(
        source,
        "async function generateStudioObservations()",
        "async function applyStudioObservationReview()",
    )
    review = _function(
        source,
        "async function applyStudioObservationReview()",
        "async function saveDraft()",
    )
    assert "studioApi.generateObservations(" in generate
    assert "studioApi.reviewObservations(" in review
    assert "studioApi.publishDraft(" not in generate + review
