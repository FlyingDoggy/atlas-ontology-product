import { useState } from "react";

import type { PackageDraftOperation, StudioWorkbench } from "./api";

type Collection = PackageDraftOperation["collection"];
type JsonObject = Record<string, unknown>;

const collections: Array<{ id: Collection; label: string }> = [
  { id: "sources", label: "Evidence sources" },
  { id: "decisions", label: "Decision records" },
  { id: "actors", label: "Actors" },
  { id: "processes", label: "Processes" },
  { id: "entities", label: "Entities / Objects" },
  { id: "properties", label: "Properties" },
  { id: "relationships", label: "Relationships / Links" },
  { id: "dimensions", label: "Dimensions" },
  { id: "metrics", label: "Metrics" },
  { id: "rules", label: "Rules" },
  { id: "data_sources", label: "Data sources" },
  { id: "bindings", label: "Physical bindings" },
  { id: "joins", label: "Join contracts" },
  { id: "sql_contracts", label: "SQL contracts" },
  { id: "analysis_patterns", label: "Analysis patterns" },
  { id: "policies", label: "Policies" },
  { id: "questions", label: "Business questions" },
];

function itemsFor(
  ontologyPackage: StudioWorkbench["package"],
  collection: Collection,
): JsonObject[] {
  const value = (ontologyPackage as unknown as Record<string, unknown>)[collection];
  return Array.isArray(value)
    ? value.filter((item): item is JsonObject => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function commonContract(
  collection: Collection,
  ontologyPackage: StudioWorkbench["package"],
): JsonObject {
  const singular = collection.endsWith("ies")
    ? `${collection.slice(0, -3)}y`
    : collection.endsWith("s")
      ? collection.slice(0, -1)
      : collection;
  return {
    id: `${singular}.new`,
    version: "1.0.0",
    status: "proposed",
    name: { en: `New ${singular}`, zh: `新${singular}` },
    definition: "Studio-authored contract pending semantic validation.",
    owner: ontologyPackage.scenario.owner,
    sources: [ontologyPackage.sources[0]?.id ?? "source.unconfirmed"],
    decisions: [],
    tags: ["studio-authored"],
  };
}

function templateFor(
  collection: Collection,
  ontologyPackage: StudioWorkbench["package"],
): JsonObject {
  const common = commonContract(collection, ontologyPackage);
  const entity = ontologyPackage.entities[0]?.id ?? "entity.pending";
  const property = ontologyPackage.properties[0]?.id ?? "property.pending";
  const dimension = ontologyPackage.dimensions[0]?.id ?? "dimension.pending";
  const metric = ontologyPackage.metrics[0]?.id ?? "metric.pending";
  const source = ontologyPackage.data_sources[0]?.id ?? "data_source.pending";
  const actor = ontologyPackage.actors[0]?.id ?? "actor.pending";
  const pattern = ontologyPackage.analysis_patterns[0]?.id ?? "analysis_pattern.pending";
  switch (collection) {
    // Scenario is a singleton package root. Builder/Reviewer operations may update it,
    // while the generic collection editor intentionally keeps it out of its list UI.
    case "scenario": return { ...ontologyPackage.scenario };
    case "sources": return {
      id: "source.new",
      source_type: "assumption_register",
      title: "New evidence source",
      locator: "source-library:pending",
      owner: ontologyPackage.scenario.owner,
      captured_on: new Date().toISOString().slice(0, 10),
      trust: "assumption",
      notes: "Register exact source identity before review.",
    };
    case "decisions": return {
      id: "decision.new",
      question: "What semantic choice must be governed?",
      options: [],
      decision: "Pending review",
      decided_by: actor,
      decided_on: new Date().toISOString().slice(0, 10),
      affects: [],
      residual_assumption: "",
    };
    case "actors": return { ...common, roles: [] };
    case "processes": return { ...common, process_type: "business", trigger: "manual", steps: [{ id: "step.1", name: "Review", actor, operation: "review", governed_refs: [], output_artifacts: [], on_failure: "stop" }], exception_paths: [] };
    case "entities": return { ...common, primary_key: property, grain: "one record", lifecycle: "proposed" };
    case "properties": return { ...common, entity, data_type: "string", required: false, unit: null, enum_values: [], null_meaning: "unknown" };
    case "relationships": return { ...common, from_entity: entity, to_entity: entity, predicate: "relatesTo", cardinality: "N:1" };
    case "dimensions": return { ...common, entity, key_property: property, label_property: property, hierarchy: [], member_resolution: "exact" };
    case "rules": return { ...common, rule_type: "quality", all: [], failure_behavior: "warn" };
    case "metrics": return { ...common, metric_type: "derived", base_entity: entity, result_grain: [], value_type: "decimal", unit: "count", aggregation_semantics: "derived_non_additive", formula: { op: "literal", value: 0, args: [] }, query: {}, allowed_dimensions: [dimension], null_policy: "fail_validation", zero_denominator_policy: "refuse" };
    case "data_sources": return { ...common, protocol: "tabular/v1", tables: [] };
    case "bindings": return { ...common, logical_target: property, source, table: "table_name", column: "column_name", data_type: "string", unit: null, transformation: "identity" };
    case "joins": return { ...common, left_source: source, left_table: "left_table", right_source: source, right_table: "right_table", keys: [{ left_column: "id", right_column: "id" }], expected_cardinality: "N:1", fanout_policy: "block" };
    case "sql_contracts": return { ...common, dialect: "ansi", statement_source: ontologyPackage.sources[0]?.id ?? "source.unconfirmed", statement_locator: "statement:pending", inputs: [], output_fields: [], implements: [], parameters: [], execution_mode: "reference_only", read_only: true };
    case "analysis_patterns": return { ...common, intent: "metric_fact", operation: "metric_fact", required_metrics: [metric], required_dimensions: [], exactly_two_periods: false, output_fields: ["value"], failure_conditions: [] };
    case "policies": return { ...common, allowed_roles: [], denied_roles: [], allowed_grains: ["aggregate"], denied_fields: [], minimum_group_size: 1 };
    case "questions": return { ...common, examples: [], analysis_pattern: pattern, required_inputs: [], expected_answer: "A grounded answer with evidence." };
  }
}

function stringify(value: JsonObject): string {
  return JSON.stringify(value, null, 2);
}

export function PackageContractEditor({
  ontologyPackage,
  busy,
  error,
  onSubmit,
  onClose,
}: {
  ontologyPackage: StudioWorkbench["package"];
  busy: boolean;
  error: string | null;
  onSubmit: (operation: PackageDraftOperation) => void;
  onClose: () => void;
}) {
  const initialCollection: Collection = "entities";
  const initialItems = itemsFor(ontologyPackage, initialCollection);
  const [collection, setCollection] = useState<Collection>(initialCollection);
  const [selectedId, setSelectedId] = useState(initialItems[0]?.id as string ?? "__new__");
  const [source, setSource] = useState(stringify(initialItems[0] ?? templateFor(initialCollection, ontologyPackage)));
  const [localError, setLocalError] = useState<string | null>(null);
  const items = itemsFor(ontologyPackage, collection);
  const selectedExists = items.some((item) => item.id === selectedId);

  function chooseCollection(next: Collection) {
    const nextItems = itemsFor(ontologyPackage, next);
    const nextSelected = typeof nextItems[0]?.id === "string" ? nextItems[0].id : "__new__";
    setCollection(next);
    setSelectedId(nextSelected);
    setSource(stringify(nextItems[0] ?? templateFor(next, ontologyPackage)));
    setLocalError(null);
  }

  function chooseObject(objectId: string) {
    setSelectedId(objectId);
    const item = items.find((candidate) => candidate.id === objectId);
    setSource(stringify(item ?? templateFor(collection, ontologyPackage)));
    setLocalError(null);
  }

  function newContract() {
    setSelectedId("__new__");
    setSource(stringify(templateFor(collection, ontologyPackage)));
    setLocalError(null);
  }

  function cloneContract() {
    let parsed: JsonObject;
    try {
      parsed = JSON.parse(source) as JsonObject;
    } catch {
      setLocalError("请先修复 JSON，再复制合同。");
      return;
    }
    const originalId = typeof parsed.id === "string" ? parsed.id : `${collection}.new`;
    parsed.id = `${originalId}.copy`;
    parsed.status = "proposed";
    setSelectedId("__new__");
    setSource(stringify(parsed));
    setLocalError(null);
  }

  function save() {
    let payload: JsonObject;
    try {
      const parsed: unknown = JSON.parse(source);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
      payload = parsed as JsonObject;
    } catch {
      setLocalError("Typed contract JSON 无法解析；没有向后端发送任何写入。");
      return;
    }
    if (typeof payload.id !== "string" || !payload.id) {
      setLocalError("Typed contract JSON 必须包含非空 id。");
      return;
    }
    setLocalError(null);
    onSubmit({ action: "UPSERT", collection, object_id: payload.id, payload });
  }

  return (
    <section className="package-contract-editor" aria-labelledby="package-contract-editor-heading">
      <header>
        <div><span>ADVANCED · CLOSED TYPE SYSTEM</span><h3 id="package-contract-editor-heading">完整 Ontology 合同编辑器</h3><p>JSON 是精确合同的编辑表示；后端仍按所选 collection 的闭合模型校验，不能绕过 schema。</p></div>
        <button type="button" onClick={onClose}>关闭</button>
      </header>
      <div className="contract-editor-controls">
        <label>Contract collection<select aria-label="Contract collection" value={collection} onChange={(event) => chooseCollection(event.target.value as Collection)}>{collections.map((item) => <option key={item.id} value={item.id}>{item.label} · {itemsFor(ontologyPackage, item.id).length}</option>)}</select></label>
        <label>Contract object<select aria-label="Contract object" value={selectedExists ? selectedId : "__new__"} onChange={(event) => chooseObject(event.target.value)}><option value="__new__">New typed contract</option>{items.map((item) => <option value={String(item.id)} key={String(item.id)}>{String(item.id)}</option>)}</select></label>
        <div><button type="button" onClick={newContract}>新建合同</button><button type="button" onClick={cloneContract}>复制为新合同</button></div>
      </div>
      <label className="contract-json-field">Typed contract JSON<textarea aria-label="Typed contract JSON" spellCheck={false} value={source} onChange={(event) => setSource(event.target.value)} rows={22} /></label>
      <footer>
        <div>
          <span>{collection}</span>
          <code>{selectedExists ? selectedId : "NEW"}</code>
          <p>引用完整性、ID 冲突、unit/cardinality/type 与 scenario compatibility 将由后端 validation 决定。</p>
        </div>
        <div>
          {selectedExists ? <button type="button" className="danger" disabled={busy} onClick={() => onSubmit({ action: "DEPRECATE", collection, object_id: selectedId, payload: null })}>标记 Deprecated</button> : null}
          <button type="button" className="primary" disabled={busy} onClick={save}>{busy ? "保存中…" : "保存 typed contract"}</button>
        </div>
      </footer>
      {localError || error ? <p className="operator-error" role="alert">{localError ?? error}</p> : null}
    </section>
  );
}
