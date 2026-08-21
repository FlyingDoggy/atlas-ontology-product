from __future__ import annotations

import pytest
from pydantic import ValidationError

from ontology_agent.io import sha256_value
from ontology_agent.models import OntologyPackage, SqlContract
from ontology_agent.studio.package_authoring import (
    PackageDraftOperation,
    PackageDraftOperationsV1,
    apply_package_operations,
)


COLLECTIONS = (
    "actors",
    "processes",
    "entities",
    "properties",
    "relationships",
    "dimensions",
    "rules",
    "metrics",
    "data_sources",
    "bindings",
    "joins",
    "analysis_patterns",
    "policies",
    "questions",
)


def test_exact_source_can_be_registered_without_fabricating_review_status(
    package: OntologyPackage,
) -> None:
    operation = PackageDraftOperation.model_validate(
        {
            "action": "UPSERT",
            "collection": "sources",
            "object_id": "source.registered_input",
            "payload": {
                "id": "source.registered_input",
                "source_type": "data_dictionary",
                "title": "Registered data dictionary",
                "locator": "source-library:source-version.123",
                "owner": "Ontology Team",
                "captured_on": "2026-08-22",
                "trust": "primary",
                "notes": "Exact source version; semantic claims still require review.",
            },
        }
    )

    candidate = apply_package_operations(package, (operation,))

    assert candidate.sources[-1].id == "source.registered_input"
    assert not hasattr(candidate.sources[-1], "status")


def test_exact_source_cannot_use_governed_asset_confirmation() -> None:
    with pytest.raises(ValidationError, match="do not use asset confirmation"):
        PackageDraftOperation.model_validate(
            {
                "action": "CONFIRM",
                "collection": "sources",
                "object_id": "source.input",
                "payload": {
                    "reviewer": "reviewer@example.com",
                    "reviewed_at": "2026-08-22T00:00:00Z",
                    "asset_checksum": "a" * 64,
                },
            }
        )


@pytest.mark.parametrize("collection", COLLECTIONS)
def test_every_governed_collection_accepts_its_own_closed_contract(
    package: OntologyPackage,
    collection: str,
) -> None:
    existing = getattr(package, collection)[0]
    operation = PackageDraftOperation.model_validate(
        {
            "action": "UPSERT",
            "collection": collection,
            "object_id": existing.id,
            "payload": existing.model_dump(mode="json"),
        }
    )

    candidate = apply_package_operations(package, (operation,))

    changed = next(item for item in getattr(candidate, collection) if item.id == existing.id)
    assert changed.status == "proposed"


def test_unreferenced_contract_supports_explicit_deprecation(
    package: OntologyPackage,
) -> None:
    existing = package.relationships[0]
    operation = PackageDraftOperation(
        action="DEPRECATE",
        collection="relationships",
        object_id=existing.id,
    )

    candidate = apply_package_operations(package, (operation,))

    assert all(item.id != existing.id for item in candidate.relationships)


def test_deprecation_is_blocked_while_active_references_remain(
    package: OntologyPackage,
) -> None:
    existing = package.entities[0]

    with pytest.raises(ValueError, match="active references remain"):
        apply_package_operations(
            package,
            (
                PackageDraftOperation(
                    action="DEPRECATE",
                    collection="entities",
                    object_id=existing.id,
                ),
            ),
        )


def test_confirmation_is_bound_to_the_exact_proposed_asset(
    package: OntologyPackage,
) -> None:
    existing = package.relationships[0]
    edited = existing.model_copy(
        update={"definition": "Reviewer-visible revised definition."}
    ).model_dump(mode="json")
    proposed = apply_package_operations(
        package,
        (
            PackageDraftOperation(
                action="UPSERT",
                collection="relationships",
                object_id=existing.id,
                payload=edited,
            ),
        ),
    )
    asset = proposed.relationships[0]
    receipt = {
        "reviewer": "reviewer@example.com",
        "reviewed_at": "2026-08-21T12:00:00Z",
        "asset_checksum": sha256_value(asset.model_dump(mode="json")),
    }

    confirmed = apply_package_operations(
        proposed,
        (
            PackageDraftOperation(
                action="CONFIRM",
                collection="relationships",
                object_id=asset.id,
                payload=receipt,
            ),
        ),
    )

    assert confirmed.relationships[0].status == "confirmed"


def test_confirmation_rejects_a_stale_asset_digest(
    package: OntologyPackage,
) -> None:
    existing = package.relationships[0]

    with pytest.raises(ValueError, match="exact asset"):
        apply_package_operations(
            existing_package := apply_package_operations(
                package,
                (
                    PackageDraftOperation(
                        action="UPSERT",
                        collection="relationships",
                        object_id=existing.id,
                        payload=existing.model_dump(mode="json"),
                    ),
                ),
            ),
            (
                PackageDraftOperation(
                    action="CONFIRM",
                    collection="relationships",
                    object_id=existing.id,
                    payload={
                        "reviewer": "reviewer@example.com",
                        "reviewed_at": "2026-08-21T12:00:00Z",
                        "asset_checksum": "0" * 64,
                    },
                ),
            ),
        )


def test_payload_cannot_smuggle_fields_outside_the_selected_closed_type(
    package: OntologyPackage,
) -> None:
    payload = package.relationships[0].model_dump(mode="json")
    payload["browser_authority"] = "PASS"

    with pytest.raises(ValidationError):
        PackageDraftOperation.model_validate(
            {
                "action": "UPSERT",
                "collection": "relationships",
                "object_id": payload["id"],
                "payload": payload,
            }
        )


def test_sql_contract_is_a_closed_governed_package_asset(
    package: OntologyPackage,
) -> None:
    source = package.data_sources[0]
    table = source.tables[0]
    statement_source = next(
        item.id for item in package.sources if item.source_type == "sql"
    )
    contract = SqlContract.model_validate(
        {
            "id": "sql.adt.reference",
            "status": "confirmed",
            "name": {"en": "ADT SQL", "zh": "ADT SQL"},
            "definition": "Governed reference to the exact ADT calculation SQL.",
            "owner": package.actors[0].id,
            "sources": [statement_source],
            "dialect": "duckdb",
            "statement_source": statement_source,
            "statement_locator": "statement:adt",
            "inputs": [{"source": source.id, "table": table.name, "alias": "base"}],
            "output_fields": ["adt"],
            "implements": [package.metrics[0].id],
            "execution_mode": "validated_query",
        }
    )
    operation = PackageDraftOperation(
        action="UPSERT",
        collection="sql_contracts",
        object_id=contract.id,
        payload=contract.model_dump(mode="json"),
    )

    candidate = apply_package_operations(package, (operation,))

    assert candidate.sql_contracts[0].id == contract.id
    assert candidate.sql_contracts[0].status == "proposed"


def test_one_batch_cannot_hide_two_writes_to_the_same_object(
    package: OntologyPackage,
) -> None:
    existing = package.relationships[0]
    operation = {
        "action": "UPSERT",
        "collection": "relationships",
        "object_id": existing.id,
        "payload": existing.model_dump(mode="json"),
    }

    with pytest.raises(ValidationError):
        PackageDraftOperationsV1(
            expected_revision=1,
            operations=(operation, operation),
        )
