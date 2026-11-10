"""Refresh checksums after intentional edits to public synthetic demo sources.

Run after generate_fixtures.py. Rebuild the dependent cash controls and authoring
package in order, then update source manifests. Never edit published releases.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
from ontology_agent.io import sha256_value


ROOT = Path(__file__).resolve().parents[1] / "scenarios"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refresh_dataset() -> None:
    scenario = ROOT / "cash_trading"
    path = scenario / "data/manifest.json"
    manifest = json.loads(path.read_text())
    for key, relative in {
        "assumption_register_checksum": "governance/assumption-register.json",
        "compilation_spec_checksum": "intake/compile-spec.json",
        "source_manifest_checksum": "intake/source-manifest.json",
    }.items():
        manifest[key] = sha256_value(json.loads((scenario / relative).read_text()))
    for section in ("schema", "quality_report"):
        artifact = scenario / "data" / manifest[section]["path"]
        payload = json.loads(artifact.read_text())
        for key in ("assumption_register_checksum", "compilation_spec_checksum", "source_manifest_checksum"):
            payload[key] = manifest[key]
        save(artifact, payload)
        manifest[section]["sha256"] = digest(artifact)
        manifest[section]["size_bytes"] = artifact.stat().st_size
    save(path, manifest)


def refresh_registrations() -> None:
    for scenario in (ROOT / "adt", ROOT / "cash_trading"):
        path = scenario / "solution-registration.json"
        registration = json.loads(path.read_text())
        # Private source attachments are deliberately absent from public clones.
        # Keep their intake gaps explicit, but do not advertise missing bytes as
        # distributable solution resources.
        registration["resources"] = [item for item in registration["resources"]
            if not (item["locator"].startswith("intake/reference-source-pack/")
                    and not (scenario / item["locator"]).is_file())]
        for item in registration["components"] + registration["resources"]:
            source = scenario / item["locator"]
            if not source.is_file():
                raise FileNotFoundError(f"Missing registered public resource: {source}")
            item["sha256"] = digest(source)
            if "size_bytes" in item:
                item["size_bytes"] = source.stat().st_size
        save(path, registration)


if __name__ == "__main__":
    refresh_dataset()
    for name in ("generate_cash_trading_controls.py", "build_cash_trading_package.py"):
        subprocess.run([sys.executable, str(Path(__file__).with_name(name))],
                       check=True, stdout=subprocess.DEVNULL)
    refresh_registrations()
    print("Refreshed both public synthetic solution registrations")
