from __future__ import annotations

from urllib.parse import unquote

from .models import OntologyPackage
from .rdf_projection import BASE, EX, build_graph, resource_uri


def _identifier(uri: object) -> str:
    value = str(uri)
    if not value.startswith(BASE):
        raise ValueError(f"Unexpected ontology resource URI: {value}")
    return unquote(value.removeprefix(BASE))


def metric_dependencies_sparql(
    package: OntologyPackage,
    metric_id: str,
) -> tuple[str, ...]:
    """Governance query over the RDF projection; never used for business aggregation."""
    if metric_id not in {metric.id for metric in package.metrics}:
        raise ValueError(f"Unknown metric: {metric_id}")
    graph = build_graph(package)
    rows = graph.query(
        """
        SELECT ?dependency
        WHERE { ?metric ex:dependsOn ?dependency . }
        ORDER BY ?dependency
        """,
        initNs={"ex": EX},
        initBindings={"metric": resource_uri(metric_id)},
    )
    return tuple(_identifier(row.dependency) for row in rows)
