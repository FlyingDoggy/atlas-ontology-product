from __future__ import annotations

import argparse
import json
from pathlib import Path

from ontology_agent.intake import compile_tabular_xlsx


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile the exact External Review Team cash-trading XLSX packet"
    )
    project_root = Path(__file__).resolve().parents[1]
    workspace_root = project_root.parent
    scenario_root = project_root / "scenarios" / "cash_trading"
    parser.add_argument(
        "--input-root",
        type=Path,
        default=workspace_root / "private-inputs",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=scenario_root / "data",
    )
    args = parser.parse_args()
    result = compile_tabular_xlsx(
        spec_path=scenario_root / "intake" / "compile-spec.json",
        source_manifest_path=scenario_root / "intake" / "source-manifest.json",
        assumption_register_path=scenario_root
        / "governance"
        / "assumption-register.json",
        input_root=args.input_root.resolve(),
        output_dir=args.output_dir.resolve(),
    )
    print(
        json.dumps(
            {
                "quality_status": result.quality_status,
                "manifest_path": str(result.manifest_path),
                "manifest_checksum": result.manifest_checksum,
                "tables": [str(path) for path in result.table_paths],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
