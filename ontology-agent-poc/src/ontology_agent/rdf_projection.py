from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from pyshacl import validate as shacl_validate
from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

from .models import FormulaNode, OntologyPackage, ValidationCheck


BASE = "https://example.org/hkex/ontology/"
EX = Namespace(BASE)


def resource_uri(identifier: str) -> URIRef:
    return URIRef(BASE + quote(identifier, safe=".-_"))


def _add_common(graph: Graph, item: object, class_name: str) -> URIRef:
    uri = resource_uri(getattr(item, "id"))
    graph.add((uri, RDF.type, EX[class_name]))
    graph.add((uri, EX.id, Literal(getattr(item, "id"))))
    graph.add((uri, EX.version, Literal(getattr(item, "version"))))
    graph.add((uri, EX.status, Literal(str(getattr(item, "status").value))))
    graph.add((uri, RDFS.label, Literal(getattr(item, "name").en, lang="en")))
    graph.add((uri, RDFS.label, Literal(getattr(item, "name").zh, lang="zh")))
    graph.add((uri, EX.definition, Literal(getattr(item, "definition"))))
    graph.add((uri, EX.owner, resource_uri(getattr(item, "owner"))))
    for source in getattr(item, "sources"):
        graph.add((uri, EX.supportedBy, resource_uri(source)))
    for decision in getattr(item, "decisions"):
        graph.add((uri, EX.governedByDecision, resource_uri(decision)))
    return uri


def _metric_refs(node: FormulaNode) -> set[str]:
    refs = {node.ref} if node.op == "metric_ref" and node.ref else set()
    for child in node.args:
        refs.update(_metric_refs(child))
    return refs


def build_graph(package: OntologyPackage) -> Graph:
    graph = Graph()
    graph.bind("ex", EX)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)

    package_uri = resource_uri(package.package_id)
    graph.add((package_uri, RDF.type, EX.OntologyPackage))
    graph.add((package_uri, EX.version, Literal(package.version)))
    graph.add((package_uri, EX.status, Literal(package.status.value)))

    for source in package.sources:
        uri = resource_uri(source.id)
        graph.add((uri, RDF.type, EX.SourceReference))
        graph.add((uri, EX.id, Literal(source.id)))
        graph.add((uri, RDFS.label, Literal(source.title)))
        graph.add((uri, EX.locator, Literal(source.locator)))
        graph.add((uri, EX.trust, Literal(source.trust)))

    for decision in package.decisions:
        uri = resource_uri(decision.id)
        graph.add((uri, RDF.type, EX.Decision))
        graph.add((uri, EX.id, Literal(decision.id)))
        graph.add((uri, EX.decisionText, Literal(decision.decision)))
        for affected in decision.affects:
            graph.add((uri, EX.affects, resource_uri(affected)))

    collections = [
        ("Actor", package.actors),
        ("Process", package.processes),
        ("Entity", package.entities),
        ("Property", package.properties),
        ("Relationship", package.relationships),
        ("Dimension", package.dimensions),
        ("Rule", package.rules),
        ("Metric", package.metrics),
        ("DataSource", package.data_sources),
        ("PhysicalBinding", package.bindings),
        ("JoinContract", package.joins),
        ("SqlContract", package.sql_contracts),
        ("AnalysisPattern", package.analysis_patterns),
        ("Policy", package.policies),
        ("BusinessQuestion", package.questions),
    ]

    scenario_uri = _add_common(graph, package.scenario, "Scenario")
    graph.add((package_uri, EX.contains, scenario_uri))

    for class_name, items in collections:
        for item in items:
            uri = _add_common(graph, item, class_name)
            graph.add((package_uri, EX.contains, uri))

    for prop in package.properties:
        graph.add((resource_uri(prop.id), EX.propertyOf, resource_uri(prop.entity)))
        graph.add((resource_uri(prop.id), EX.dataType, Literal(prop.data_type)))

    for process in package.processes:
        process_uri = resource_uri(process.id)
        graph.add((process_uri, EX.trigger, Literal(process.trigger)))
        for step in process.steps:
            step_uri = resource_uri(f"{process.id}.{step.id}")
            graph.add((step_uri, RDF.type, EX.ProcessStep))
            graph.add((step_uri, RDFS.label, Literal(step.name)))
            graph.add((step_uri, EX.actor, resource_uri(step.actor)))
            graph.add((step_uri, EX.operation, Literal(step.operation)))
            graph.add((process_uri, EX.hasStep, step_uri))
            for reference in step.governed_refs:
                graph.add((step_uri, EX.uses, resource_uri(reference)))

    for relationship in package.relationships:
        uri = resource_uri(relationship.id)
        graph.add((uri, EX.fromEntity, resource_uri(relationship.from_entity)))
        graph.add((uri, EX.toEntity, resource_uri(relationship.to_entity)))
        graph.add((uri, EX.cardinality, Literal(relationship.cardinality)))

    for metric in package.metrics:
        uri = resource_uri(metric.id)
        graph.add((uri, EX.unit, Literal(metric.unit)))
        graph.add((uri, EX.formulaJson, Literal(json.dumps(metric.formula.model_dump(mode="json"), sort_keys=True))))
        for dependency in _metric_refs(metric.formula):
            graph.add((uri, EX.dependsOn, resource_uri(dependency)))
        for dimension in metric.allowed_dimensions:
            graph.add((uri, EX.allowedDimension, resource_uri(dimension)))

    for binding in package.bindings:
        uri = resource_uri(binding.id)
        graph.add((uri, EX.logicalTarget, resource_uri(binding.logical_target)))
        graph.add((uri, EX.source, resource_uri(binding.source)))
        graph.add((uri, EX.table, Literal(binding.table)))
        graph.add((uri, EX.column, Literal(binding.column)))

    for contract in package.sql_contracts:
        uri = resource_uri(contract.id)
        graph.add((uri, EX.statementSource, resource_uri(contract.statement_source)))
        graph.add((uri, EX.statementLocator, Literal(contract.statement_locator)))
        graph.add((uri, EX.executionMode, Literal(contract.execution_mode)))
        for implemented in contract.implements:
            graph.add((uri, EX.implements, resource_uri(implemented)))
        for relation in contract.inputs:
            graph.add((uri, EX.inputSource, resource_uri(relation.source)))
            graph.add((uri, EX.inputTable, Literal(relation.table)))

    for pattern in package.analysis_patterns:
        uri = resource_uri(pattern.id)
        for metric in pattern.required_metrics:
            graph.add((uri, EX.requiresMetric, resource_uri(metric)))
        for dimension in pattern.required_dimensions:
            graph.add((uri, EX.requiresDimension, resource_uri(dimension)))

    for question in package.questions:
        graph.add((resource_uri(question.id), EX.usesPattern, resource_uri(question.analysis_pattern)))

    return graph


SHAPES_TTL = f"""
@prefix ex: <{BASE}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:MetricShape a sh:NodeShape ;
  sh:targetClass ex:Metric ;
  sh:property [ sh:path ex:id ; sh:minCount 1 ; sh:maxCount 1 ] ;
  sh:property [ sh:path ex:version ; sh:minCount 1 ; sh:maxCount 1 ] ;
  sh:property [ sh:path ex:status ; sh:hasValue "confirmed" ] ;
  sh:property [ sh:path ex:definition ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:owner ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:supportedBy ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:unit ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:formulaJson ; sh:minCount 1 ] .

ex:BindingShape a sh:NodeShape ;
  sh:targetClass ex:PhysicalBinding ;
  sh:property [ sh:path ex:id ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:status ; sh:hasValue "confirmed" ] ;
  sh:property [ sh:path ex:logicalTarget ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:source ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:table ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:column ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:supportedBy ; sh:minCount 1 ] .

ex:AnalysisPatternShape a sh:NodeShape ;
  sh:targetClass ex:AnalysisPattern ;
  sh:property [ sh:path ex:id ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:status ; sh:hasValue "confirmed" ] ;
  sh:property [ sh:path ex:requiresMetric ; sh:minCount 1 ] .
"""


def validate_graph(package: OntologyPackage) -> tuple[ValidationCheck, Graph, Graph, str]:
    graph = build_graph(package)
    shapes = Graph().parse(data=SHAPES_TTL, format="turtle")
    conforms, report_graph, report_text = shacl_validate(
        graph,
        shacl_graph=shapes,
        inference="rdfs",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
    )
    check = ValidationCheck(
        check_id="SHACL_GRAPH_CONFORMS",
        category="shacl",
        status="PASS" if conforms else "FAIL",
        message="RDF projection conforms to SHACL shapes" if conforms else "RDF projection violates SHACL shapes",
        details={"report": report_text},
    )
    return check, graph, report_graph, report_text


def _stable_json(value: object) -> object:
    """Canonicalize JSON-LD arrays because RDF graph iteration order is undefined."""
    if isinstance(value, dict):
        return {key: _stable_json(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [_stable_json(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )
    return value


def write_graph_artifacts(package: OntologyPackage, output_dir: Path) -> dict[str, Path]:
    _, graph, report_graph, report_text = validate_graph(package)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "ttl": output_dir / "package.ttl",
        "jsonld": output_dir / "package.jsonld",
        "shapes": output_dir / "shapes.ttl",
        "shacl_report_ttl": output_dir / "shacl-report.ttl",
        "shacl_report_text": output_dir / "shacl-report.txt",
    }
    graph.serialize(destination=paths["ttl"], format="turtle")
    jsonld = json.loads(graph.serialize(format="json-ld"))
    paths["jsonld"].write_text(
        json.dumps(
            _stable_json(jsonld),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    paths["shapes"].write_text(SHAPES_TTL, encoding="utf-8")
    report_graph.serialize(destination=paths["shacl_report_ttl"], format="turtle")
    paths["shacl_report_text"].write_text(report_text, encoding="utf-8")
    return paths
