#!/usr/bin/env python3
"""Run the local Real-Qwen construction acceptance gate.

This is intentionally not a CI test. It calls the configured provider and creates
an immutable test Solution/Release in the local product database. Credentials are
read at runtime and are never printed or persisted by this script.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import sync_playwright


TERMINAL_EXECUTION = {"SUCCEEDED", "FAILED", "CANCELLED", "STALE"}
REVIEW_READY = {"REVIEW_READY", "REVIEW_READY_WITH_WARNINGS"}
REQUIRED_COMPILE_TYPES = {
    "OBJECT",
    "PROPERTY",
    "LINK",
    "METRIC",
    "DATA_SOURCE",
    "MAPPING",
}

CASH_TRADING_FORMAL_METRIC_IDS = {
    "metric.active_client_trading_volume",
    "metric.cancel_to_trade_ratio",
    "metric.client_order_completion_rate",
    "metric.order_fill_rate",
    "metric.order_rejection_rate",
    "metric.order_to_trade_ratio",
    "metric.potential_self_trade_rate",
    "metric.trade_capture_latency_p95",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exercise Blank Solution -> Real Qwen -> HITL -> Validate -> Release."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:18083")
    parser.add_argument(
        "--access-file",
        type=Path,
        default=Path("AWS info/demo-access.txt"),
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional ontology-demo-source-manifest/v1 file for a non-Cash-Trading scenario.",
    )
    parser.add_argument(
        "--authoring-language",
        choices=("en", "zh"),
        help="Override the manifest's Ontology output language.",
    )
    parser.add_argument("--no-finalize", action="store_true")
    return parser.parse_args()


def load_demo_credentials(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    username = re.search(r"^Username:\s*(.+)$", text, re.MULTILINE)
    password = re.search(r"^Password:\s*(.+)$", text, re.MULTILINE)
    if not username or not password:
        raise RuntimeError("Demo access file does not contain Username/Password fields")
    return username.group(1).strip(), password.group(1).strip()


def expect(response: httpx.Response, status: int | tuple[int, ...]) -> dict[str, Any]:
    allowed = (status,) if isinstance(status, int) else status
    if response.status_code not in allowed:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:500]
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path} returned "
            f"{response.status_code}: {detail}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{response.request.url.path} did not return an object")
    return payload


def source_inventory(root: Path) -> list[dict[str, Any]]:
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return [
        {
            "path": root
            / "HKEX DTT Input/HKEX_Analytics_Scenario_Input_Template_with_ADT_Reference_v20260819.xlsx",
            "media_type": xlsx,
            "registrations": [
                {
                    "kind": "requirement_transcription",
                    "title": "Cash Trading business requirements and end-to-end analytics process",
                },
                {
                    "kind": "metric_transcription",
                    "title": "Cash Trading eight metric definitions",
                },
            ],
        },
        {
            "path": root / "HKEX DTT Input/order_trade_activities_data_dictionary.xlsx",
            "media_type": xlsx,
            "registrations": [
                {
                    "kind": "data_model",
                    "title": "Cash Trading order and trade logical data model",
                },
                {
                    "kind": "data_dictionary",
                    "title": "Cash Trading order and trade field dictionary",
                },
            ],
        },
        {
            "path": root / "HKEX DTT Input/cash_trading_sample_data.xlsx",
            "media_type": xlsx,
            "registrations": [
                {
                    "kind": "data_dictionary",
                    "title": "Cash Trading data dictionary and synthetic sample data",
                }
            ],
        },
        {
            "path": root / "HKEX DTT Input/email screenshot.jpeg",
            "media_type": "image/jpeg",
            "registrations": [
                {
                    "kind": "other",
                    "title": "Cash Trading source provenance and limitations",
                }
            ],
        },
        {
            "path": root
            / "ontology-agent-poc/scenarios/cash_trading/sql/reference_controls.sql",
            "media_type": "text/plain",
            "registrations": [
                {
                    "kind": "sql",
                    "title": "Synthetic Cash Trading reference control SQL",
                }
            ],
        },
    ]


def demo_definition(root: Path, manifest_path: Path | None) -> dict[str, Any]:
    if manifest_path is None:
        inventory = source_inventory(root)
        return {
            "solution": {
                "display_name": {
                    "en": f"Cash Trading Real Qwen Smoke {time.strftime('%Y%m%d-%H%M%S')}",
                    "zh": "现金交易真实模型验收",
                },
                "description": {
                    "en": "Build a reviewable Cash Trading ontology from the exact Deloitte HK input package.",
                    "zh": "基于 Deloitte HK 提供的现金交易材料，构建一套可复核的本体方案。",
                },
                "owner": "Ontology Product QA",
                "authoring_language": "zh",
            },
            "inventory": inventory,
            "acceptance": {
                "minimum_metric_or_gap_count": 8,
                "minimum_published_metric_count": 8,
                "expected_metric_ids": sorted(CASH_TRADING_FORMAL_METRIC_IDS),
                "required_compilable_types": sorted(REQUIRED_COMPILE_TYPES),
                "expected_physical_file_count": len(inventory),
                "expected_logical_source_count": sum(
                    len(item["registrations"]) for item in inventory
                ),
            },
        }
    resolved = manifest_path if manifest_path.is_absolute() else root / manifest_path
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if payload.get("contract") != "ontology-demo-source-manifest/v1":
        raise RuntimeError(f"Unsupported demo manifest contract: {payload.get('contract')}")
    inventory = []
    for item in payload.get("files", []):
        inventory.append(
            {
                "path": resolved.parent / item["path"],
                "media_type": item.get("media_type"),
                "registrations": item["registrations"],
            }
        )
    if not inventory:
        raise RuntimeError("Demo manifest does not declare any source files")
    solution = payload.get("solution")
    acceptance = payload.get("acceptance")
    if not isinstance(solution, dict) or not isinstance(acceptance, dict):
        raise RuntimeError("Demo manifest must declare solution and acceptance objects")
    return {"solution": solution, "inventory": inventory, "acceptance": acceptance}


def localized_solution_text(value: Any, language: str) -> str:
    if isinstance(value, dict):
        selected = value.get(language)
        if isinstance(selected, str) and selected.strip():
            return selected.strip()
        for fallback in ("en", "zh"):
            candidate = value.get(fallback)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        raise RuntimeError("Localized Solution text does not contain a usable value")
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise RuntimeError("Solution description must be non-empty text")


def register_sources(
    client: httpx.Client, workspace_id: str, inventory: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest_items: list[dict[str, Any]] = []
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for index, item in enumerate(inventory, start=1):
        path: Path = item["path"]
        if not path.is_file():
            raise RuntimeError(f"Required smoke input is missing: {path}")
        media_type = item.get("media_type") or mimetypes.guess_type(path.name)[0]
        media_type = media_type or "application/octet-stream"
        manifest_items.append(
            {
                "client_file_id": f"ontology-demo-{index}",
                "original_name": path.name,
                "declared_media_type": media_type,
                "registrations": item["registrations"],
            }
        )
        files.append(("files", (path.name, path.read_bytes(), media_type)))
    manifest = {
        "contract": "source-intake-batch/v1",
        "idempotency_key": f"real-qwen-demo-{time.time_ns()}",
        "items": manifest_items,
    }
    return expect(
        client.post(
            f"/control/workspaces/{workspace_id}/source-intake/batches",
            data={"manifest_json": json.dumps(manifest, ensure_ascii=False)},
            files=files,
        ),
        200,
    )


def poll_task(
    client: httpx.Client,
    job_id: str,
    *,
    poll_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_stage: tuple[str, int, str | None] | None = None
    while time.monotonic() < deadline:
        task = expect(client.get(f"/control/construction-tasks/{job_id}"), 200)
        stage = (
            str(task["execution_status"]),
            int(task["completed_stages"]),
            task.get("result_outcome"),
        )
        if stage != last_stage:
            print(
                "TASK",
                job_id[-8:],
                stage[0],
                f"{stage[1]}/{task['total_stages']}",
                task.get("progress_message"),
                stage[2] or "-",
                flush=True,
            )
            last_stage = stage
        if task["execution_status"] in TERMINAL_EXECUTION:
            return task
        time.sleep(poll_seconds)
    raise TimeoutError(f"Construction task {job_id} did not finish in time")


def run_payload(client: httpx.Client, workspace_id: str, run_id: str) -> dict[str, Any]:
    listing = expect(
        client.get(f"/control/workspaces/{workspace_id}/construction-runs"), 200
    )
    for record in listing["runs"]:
        if record["run"]["run_id"] == run_id:
            return record["run"]
    raise RuntimeError(f"Immutable run {run_id} was not found")


def oracle(
    run: dict[str, Any],
    task: dict[str, Any],
    *,
    required_compile_types: set[str] | None = None,
    minimum_metric_or_gap_count: int = 8,
    minimum_publishable_metric_count: int = 8,
    expected_metric_ids: set[str] | None = None,
) -> dict[str, Any]:
    required = required_compile_types or REQUIRED_COMPILE_TYPES
    blocked = {
        candidate_id
        for finding in run["machine_findings"]
        if finding["blocks_release"]
        for candidate_id in finding["candidate_ids"]
    }
    compilable = [
        item
        for item in run["candidates"]
        if item["compile_eligible"] and item["candidate_id"] not in blocked
    ]
    compilable_types = Counter(item["candidate_type"] for item in compilable)
    all_types = Counter(item["candidate_type"] for item in run["candidates"])
    metric_or_gap = all_types["METRIC"] + all_types["GAP"]
    unblocked_metric_ids = sorted(
        operation["object_id"]
        for item in compilable
        if item["candidate_type"] == "METRIC"
        for operation in [item.get("proposed_operation")]
        if isinstance(operation, dict)
    )
    missing_expected_metric_ids = sorted(
        (expected_metric_ids or set()) - set(unblocked_metric_ids)
    )
    missing_types = sorted(required - set(compilable_types))
    pass_gate = (
        task.get("result_outcome") in REVIEW_READY
        and not missing_types
        and metric_or_gap >= minimum_metric_or_gap_count
        and len(unblocked_metric_ids) >= minimum_publishable_metric_count
        and not missing_expected_metric_ids
    )
    return {
        "pass": pass_gate,
        "outcome": task.get("result_outcome"),
        "candidate_count": len(run["candidates"]),
        "compilable_count": len(compilable),
        "candidate_types": dict(sorted(all_types.items())),
        "compilable_types": dict(sorted(compilable_types.items())),
        "metric_or_gap_count": metric_or_gap,
        "unblocked_metric_ids": unblocked_metric_ids,
        "missing_expected_metric_ids": missing_expected_metric_ids,
        "missing_required_compile_types": missing_types,
        "run_checksum": run["run_checksum"],
        "source_set_digest": run["source_set_digest"],
        "language_policy_digest": run.get("language_policy_digest"),
        "stage_receipts": [
            {
                "stage": item["stage"],
                "status": item["status"],
                "implementation": item["implementation"],
                "input_digest": item["input_digest"],
                "output_digest": item["output_digest"],
                "item_count": item["item_count"],
            }
            for item in run["stage_receipts"]
        ],
    }


def finalize(
    client: httpx.Client,
    workspace_id: str,
    base_revision: int,
    run: dict[str, Any],
    *,
    minimum_published_metric_count: int,
    expected_metric_ids: set[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    blocked = {
        candidate_id
        for finding in run["machine_findings"]
        if finding["blocks_release"]
        for candidate_id in finding["candidate_ids"]
    }
    accepted_ids = {
        candidate["candidate_id"]
        for candidate in run["candidates"]
        if candidate["compile_eligible"] and candidate["candidate_id"] not in blocked
    }
    accepted_targets = {
        operation["object_id"]
        for candidate in run["candidates"]
        if candidate["candidate_id"] in accepted_ids
        for operation in [candidate.get("proposed_operation")]
        if isinstance(operation, dict)
    }
    # A human reviewer must not accept a contract that claims to implement
    # assets rejected in the same review batch.  Keep this local oracle narrow:
    # publication validation still owns every other package invariant.
    for candidate in run["candidates"]:
        operation = candidate.get("proposed_operation")
        if (
            candidate["candidate_id"] not in accepted_ids
            or not isinstance(operation, dict)
            or operation.get("collection") != "sql_contracts"
        ):
            continue
        payload = operation.get("payload")
        implements = payload.get("implements", []) if isinstance(payload, dict) else []
        if any(item not in accepted_targets for item in implements):
            accepted_ids.remove(candidate["candidate_id"])

    dispositions = []
    for candidate in run["candidates"]:
        accepted = candidate["candidate_id"] in accepted_ids
        dispositions.append(
            {
                "candidate_id": candidate["candidate_id"],
                "action": "ACCEPT" if accepted else "REJECT",
                "note": (
                    "Accepted by the local Real-Qwen acceptance oracle for human review."
                    if accepted
                    else "Rejected by the local acceptance oracle because it is non-compilable or blocked."
                ),
                "blocks_release": bool(candidate["candidate_id"] in blocked),
            }
        )
    review_draft = expect(
        client.put(
            f"/control/workspaces/{workspace_id}/construction-runs/{run['run_id']}/review-draft",
            json={
                "contract": "construction-review-draft-save/v1",
                "expected_review_revision": 0,
                "reviewer": "real-qwen-smoke-reviewer",
                "dispositions": dispositions,
            },
        ),
        200,
    )
    result = expect(
        client.post(
            f"/control/workspaces/{workspace_id}/construction-runs/{run['run_id']}/review",
            json={
                "contract": "construction-review-request/v1",
                "expected_revision": base_revision,
                "reviewer": "real-qwen-smoke-reviewer",
                "dispositions": dispositions,
                "review_batch_checksum": review_draft["batch_checksum"],
            },
        ),
        200,
    )
    workspace = result["workspace"]
    workbench = expect(
        client.get(f"/control/workspaces/{workspace_id}/workbench"), 200
    )
    package = workbench["package"]
    applied_metric_ids = {item["id"] for item in package["metrics"]}
    missing_expected_metrics = sorted(expected_metric_ids - applied_metric_ids)
    if (
        len(applied_metric_ids) < minimum_published_metric_count
        or missing_expected_metrics
    ):
        raise RuntimeError(
            "Human-reviewed Draft does not contain the required governed metrics: "
            f"count={len(applied_metric_ids)} "
            f"minimum={minimum_published_metric_count} "
            f"missing={','.join(missing_expected_metrics)}"
        )
    validated = expect(
        client.post(
            f"/control/workspaces/{workspace_id}/validate",
            json={"expected_revision": workspace["revision"]},
        ),
        200,
    )
    published = expect(
        client.post(
            f"/control/workspaces/{workspace_id}/publish",
            json={"expected_revision": validated["revision"]},
        ),
        200,
    )
    return result, published, {
        "metric_count": len(applied_metric_ids),
        "metric_ids": sorted(applied_metric_ids),
    }


def verify_product_routes(
    base_url: str,
    username: str,
    password: str,
    solution_id: str,
    run_id: str,
) -> None:
    with sync_playwright() as playwright:
        # The acceptance gate runs on demo operators' machines where Chrome is
        # already present. Using the installed stable channel avoids coupling a
        # production-route check to a separately downloaded Playwright browser.
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(f"{base_url}/login/", wait_until="networkidle")
        page.get_by_label("用户名").fill(username)
        page.locator("#password").fill(password)
        page.locator("#submit-button").click()
        page.wait_for_load_state("networkidle")
        page.goto(
            f"{base_url}/ontology-studio/solutions/{solution_id}/builds/{run_id}/review/",
            wait_until="networkidle",
        )
        if page.locator("body").get_by_text("读取失败").count():
            raise RuntimeError("Review result route rendered a load failure")
        if page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"):
            raise RuntimeError("Review result route has page-level horizontal overflow")
        browser.close()


def main() -> int:
    args = parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be positive")
    project_root = Path(__file__).resolve().parents[2]
    definition = demo_definition(project_root, args.manifest)
    solution_definition = definition["solution"]
    acceptance = definition["acceptance"]
    authoring_language = (
        args.authoring_language
        or str(solution_definition.get("authoring_language") or "en")
    )
    required_types = set(
        acceptance.get("required_compilable_types") or REQUIRED_COMPILE_TYPES
    )
    minimum_metric_or_gap_count = int(
        acceptance.get("minimum_metric_or_gap_count", 8)
    )
    minimum_published_metric_count = int(
        acceptance.get("minimum_published_metric_count", minimum_metric_or_gap_count)
    )
    expected_metric_ids = {
        str(item) for item in acceptance.get("expected_metric_ids", ())
    }
    username, password = load_demo_credentials(
        args.access_file if args.access_file.is_absolute() else project_root / args.access_file
    )
    base_url = args.base_url.rstrip("/")
    with httpx.Client(
        base_url=base_url,
        timeout=120.0,
        follow_redirects=False,
        headers={"Origin": base_url, "Accept": "application/json"},
    ) as client:
        login_response = client.post(
            "/auth/login",
            json={"username": username, "password": password},
        )
        expect(login_response, 200)
        # The deployable demo cookie is Secure. Chromium treats localhost as a
        # trustworthy origin, while an HTTP-only API test client correctly
        # refuses to resend it over plain HTTP. Reuse the exact signed value in
        # this local-only gate instead of weakening the product cookie policy.
        session_token = login_response.cookies.get("atlas_demo_session")
        if not session_token:
            raise RuntimeError("Authentication response did not issue a session")
        client.headers["Cookie"] = f"atlas_demo_session={session_token}"
        created = expect(
            client.post(
                "/control/solutions",
                json={
                    "contract": "studio-solution-create/v1",
                    "creation_mode": "BLANK",
                    "display_name": solution_definition["display_name"],
                    "description": localized_solution_text(
                        solution_definition["description"], authoring_language
                    ),
                    "owner": solution_definition["owner"],
                },
            ),
            201,
        )["solution"]
        solution_id = created["solution_id"]
        workspace_id = created["workspace_id"]
        initial = expect(client.get(f"/control/workspaces/{workspace_id}"), 200)
        receipt = register_sources(client, workspace_id, definition["inventory"])
        expected_physical = int(acceptance["expected_physical_file_count"])
        expected_logical = int(acceptance["expected_logical_source_count"])
        if (
            len(receipt["physical_files"]) != expected_physical
            or len(receipt["registrations"]) != expected_logical
        ):
            raise RuntimeError(
                "Demo input did not produce the expected physical/logical source counts: "
                f"expected={expected_physical}/{expected_logical} "
                f"actual={len(receipt['physical_files'])}/{len(receipt['registrations'])}"
            )
        if receipt["failures"]:
            raise RuntimeError(f"Demo source intake failed: {receipt['failures']}")
        source_ids = [item["source_version_id"] for item in receipt["registrations"]]
        print(
            "SOLUTION",
            solution_id,
            workspace_id,
            f"sources={expected_physical}/{expected_logical}",
            f"language={authoring_language}",
            flush=True,
        )
        results: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        semantic_baseline: dict[str, Any] | None = None
        for index in range(1, args.runs + 1):
            current = expect(client.get(f"/control/workspaces/{workspace_id}"), 200)
            job = expect(
                client.post(
                    f"/control/workspaces/{workspace_id}/construction-jobs",
                    json={
                        "expected_revision": current["revision"],
                        "source_version_ids": source_ids,
                        "authoring_language": authoring_language,
                    },
                ),
                200,
            )
            frozen = expect(client.get(f"/control/workspaces/{workspace_id}"), 200)
            if (
                frozen["revision"] != job["base_revision"]
                or frozen["draft_checksum"] != job["base_draft_checksum"]
            ):
                raise RuntimeError("Construction job did not freeze the exact Draft base")
            if semantic_baseline is None:
                semantic_baseline = frozen
            elif (
                frozen["revision"] != semantic_baseline["revision"]
                or frozen["draft_checksum"] != semantic_baseline["draft_checksum"]
            ):
                raise RuntimeError("Repeated model runs do not share one exact Draft base")
            print(f"RUN {index}/{args.runs} {job['job_id'][-8:]} queued", flush=True)
            task = poll_task(
                client,
                job["job_id"],
                poll_seconds=args.poll_seconds,
                timeout_seconds=args.timeout_seconds,
            )
            after = expect(client.get(f"/control/workspaces/{workspace_id}"), 200)
            if (
                after["revision"] != frozen["revision"]
                or after["draft_checksum"] != frozen["draft_checksum"]
            ):
                raise RuntimeError("A model run mutated Draft before HITL")
            run = run_payload(client, workspace_id, job["run_id"])
            assessed = oracle(
                run,
                task,
                required_compile_types=required_types,
                minimum_metric_or_gap_count=minimum_metric_or_gap_count,
                minimum_publishable_metric_count=minimum_published_metric_count,
                expected_metric_ids=expected_metric_ids,
            )
            results.append((task, run, assessed))
            print(
                "ORACLE",
                index,
                "PASS" if assessed["pass"] else "FAIL",
                assessed["outcome"],
                f"candidates={assessed['candidate_count']}",
                f"compilable={assessed['compilable_count']}",
                f"metric_or_gap={assessed['metric_or_gap_count']}",
                "missing=" + ",".join(assessed["missing_required_compile_types"]),
                "missing_metrics=" + ",".join(
                    assessed["missing_expected_metric_ids"]
                ),
                flush=True,
            )
        passing = [item for item in results if item[2]["pass"]]
        if len(passing) < (2 if args.runs >= 3 else 1):
            print(
                json.dumps(
                    {
                        "contract": "real-qwen-construction-gate/v1",
                        "status": "FAIL",
                        "solution_id": solution_id,
                        "workspace_id": workspace_id,
                        "runs": [item[2] for item in results],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 2
        publication: dict[str, Any] | None = None
        decision: dict[str, Any] | None = None
        governed_assets: dict[str, Any] | None = None
        selected_run = passing[0][1]
        if not args.no_finalize:
            review, publication, governed_assets = finalize(
                client,
                workspace_id,
                selected_run["base_revision"],
                selected_run,
                minimum_published_metric_count=minimum_published_metric_count,
                expected_metric_ids=expected_metric_ids,
            )
            decision = review["decision"]
            print(
                "RELEASE",
                publication["release"]["package_id"],
                publication["release"]["version"],
                publication["release"]["validation_status"],
                flush=True,
            )
    verify_product_routes(
        base_url, username, password, solution_id, selected_run["run_id"]
    )
    print(
        json.dumps(
            {
                "contract": "real-qwen-construction-gate/v1",
                "status": "PASS",
                "solution_id": solution_id,
                "workspace_id": workspace_id,
                "source_batch": {
                    "batch_id": receipt["batch_id"],
                    "physical_files": len(receipt["physical_files"]),
                    "logical_versions": len(receipt["registrations"]),
                    "source_set_digest": results[0][1]["source_set_digest"],
                },
                "runs": [item[2] for item in results],
                "decision_id": decision["decision_id"] if decision else None,
                "release": publication["release"] if publication else None,
                "governed_assets": governed_assets,
                "ui_route_verified": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - gate must emit one concise failure
        print(f"real_qwen_construction_gate: FAIL: {exc}", file=sys.stderr)
        raise
