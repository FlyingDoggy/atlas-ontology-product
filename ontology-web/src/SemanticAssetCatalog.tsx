import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import type {
  ConstructionCandidate,
  PackageDraftOperation,
  StudioAuthoringProjection,
  StudioWorkbench,
} from "./api";
import { studioPageHref } from "./StudioNavigation";

type OntologyPackage = StudioWorkbench["package"];
type Collection = PackageDraftOperation["collection"];
type SemanticCollection = Extract<Collection,
  | "actors"
  | "processes"
  | "entities"
  | "properties"
  | "relationships"
  | "dimensions"
  | "rules"
  | "metrics"
  | "analysis_patterns"
  | "policies"
  | "questions"
>;
type JsonObject = Record<string, unknown>;
type CatalogMode = "business" | "metrics" | "experience" | "policies";

const collectionConfig: Record<SemanticCollection, {
  label: string;
  singular: string;
  description: string;
  mode: CatalogMode;
  prefix: string;
}> = {
  entities: { label: "业务对象", singular: "对象", description: "业务中具有稳定身份、粒度和生命周期的事物", mode: "business", prefix: "entity" },
  properties: { label: "属性", singular: "属性", description: "对象上的受治理字段、类型、单位和枚举", mode: "business", prefix: "property" },
  relationships: { label: "关系", singular: "关系", description: "对象之间有方向、有基数的业务联系", mode: "business", prefix: "relationship" },
  actors: { label: "参与者", singular: "参与者", description: "对业务定义、流程或分析承担责任的角色", mode: "business", prefix: "actor" },
  processes: { label: "业务流程", singular: "流程", description: "触发、步骤、异常路径与责任人的端到端过程", mode: "business", prefix: "process" },
  dimensions: { label: "分析维度", singular: "维度", description: "指标可切分、聚合和比较的受控业务轴", mode: "business", prefix: "dimension" },
  metrics: { label: "指标", singular: "指标", description: "口径、公式、粒度、单位与物理查询责任", mode: "metrics", prefix: "metric" },
  rules: { label: "业务规则", singular: "规则", description: "资格、质量、日历、告警与失败行为", mode: "metrics", prefix: "rule" },
  analysis_patterns: { label: "分析模式", singular: "分析模式", description: "Agent 可执行的分析意图、依赖和输出义务", mode: "experience", prefix: "analysis" },
  questions: { label: "业务问题", singular: "问题", description: "用户问题族、必需输入和期望回答", mode: "experience", prefix: "question" },
  policies: { label: "访问与披露策略", singular: "策略", description: "角色、粒度、字段和最小群组的运行边界", mode: "policies", prefix: "policy" },
};

const modeCollections: Record<CatalogMode, SemanticCollection[]> = {
  business: ["entities", "properties", "relationships", "actors", "processes", "dimensions"],
  metrics: ["metrics", "rules"],
  experience: ["analysis_patterns", "questions"],
  policies: ["policies"],
};

function recordsFor(ontologyPackage: OntologyPackage, collection: SemanticCollection): JsonObject[] {
  const value = (ontologyPackage as unknown as Record<string, unknown>)[collection];
  return Array.isArray(value)
    ? value.filter((item): item is JsonObject => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function localizedName(item: JsonObject): { en: string; zh: string } {
  const name = item.name;
  if (!name || typeof name !== "object" || Array.isArray(name)) return { en: "", zh: "" };
  const record = name as JsonObject;
  return { en: stringValue(record.en), zh: stringValue(record.zh) };
}

function commonTemplate(
  collection: SemanticCollection,
  ontologyPackage: OntologyPackage,
): JsonObject {
  const config = collectionConfig[collection];
  return {
    id: `${config.prefix}.new`,
    version: "1.0.0",
    status: "proposed",
    name: { en: "", zh: "" },
    definition: "",
    owner: collection === "actors"
      ? `${config.prefix}.new`
      : ontologyPackage.actors[0]?.id ?? ontologyPackage.scenario.owner,
    sources: [],
    decisions: [],
    tags: ["studio-authored"],
  };
}

function templateFor(collection: SemanticCollection, ontologyPackage: OntologyPackage): JsonObject {
  const common = commonTemplate(collection, ontologyPackage);
  const entity = ontologyPackage.entities[0]?.id ?? "";
  const property = ontologyPackage.properties[0]?.id ?? "";
  const actor = ontologyPackage.actors[0]?.id ?? ontologyPackage.scenario.owner;
  const metric = ontologyPackage.metrics[0]?.id ?? "";
  const dimension = ontologyPackage.dimensions[0]?.id ?? "";
  const pattern = ontologyPackage.analysis_patterns[0]?.id ?? "";
  switch (collection) {
    case "entities": return { ...common, primary_key: property, grain: "", lifecycle: "" };
    case "properties": return { ...common, entity, data_type: "string", required: false, unit: null, enum_values: [], null_meaning: "not_allowed" };
    case "relationships": return { ...common, from_entity: entity, to_entity: entity, predicate: "", cardinality: "N:1" };
    case "actors": return { ...common, roles: [] };
    case "processes": return { ...common, process_type: "business", trigger: "", steps: [{ id: "step.1", name: "", actor, operation: "", governed_refs: [], output_artifacts: [], on_failure: "review" }], exception_paths: [] };
    case "dimensions": return { ...common, entity, key_property: property, label_property: property, hierarchy: [], member_resolution: "exact" };
    case "rules": return { ...common, rule_type: "quality", all: [], failure_behavior: "warn" };
    case "metrics": return { ...common, metric_type: "derived", base_entity: entity, result_grain: [], value_type: "decimal", unit: "", aggregation_semantics: "derived_non_additive", formula: { op: "literal", value: 0, args: [] }, query: {}, allowed_dimensions: dimension ? [dimension] : [], null_policy: "fail_validation", zero_denominator_policy: "refuse" };
    case "analysis_patterns": return { ...common, intent: "metric_fact", operation: "", required_metrics: metric ? [metric] : [], required_dimensions: [], exactly_two_periods: false, output_fields: [], failure_conditions: [] };
    case "questions": return { ...common, examples: [], analysis_pattern: pattern, required_inputs: [], expected_answer: "" };
    case "policies": return { ...common, allowed_roles: [], denied_roles: [], allowed_grains: [], denied_fields: [], minimum_group_size: 1 };
  }
}

function pageFor(collection: SemanticCollection): "model" | "metrics" | "experience" {
  const mode = collectionConfig[collection].mode;
  return mode === "metrics" ? "metrics" : mode === "experience" ? "experience" : "model";
}

export function semanticAssetHref(
  solutionId: string,
  collection: SemanticCollection,
  objectId: string = "new",
): string {
  const base = collection === "policies"
    ? studioPageHref("quality", solutionId, "policies")
    : studioPageHref("semantic", solutionId, pageFor(collection));
  const params = new URLSearchParams({ assetType: collection, assetId: objectId });
  return `${base}?${params.toString()}`;
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as JsonObject)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

function lines(value: unknown): string {
  return stringList(value).join("\n");
}

function parseLines(value: string): string[] {
  return [...new Set(value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean))];
}

function CommonFields({
  payload,
  ontologyPackage,
  existing,
  update,
}: {
  payload: JsonObject;
  ontologyPackage: OntologyPackage;
  existing: boolean;
  update: (key: string, value: unknown) => void;
}) {
  const name = localizedName(payload);
  const selectedSources = stringList(payload.sources);
  return <>
    <section className="asset-editor-section">
      <header><span>01</span><div><h3>基本信息</h3><p>技术身份创建后不可修改；中文名、英文名和定义用于业务沟通与检索。</p></div></header>
      <div className="asset-form-grid">
        <label>技术 ID<input required disabled={existing} pattern="[A-Za-z0-9][A-Za-z0-9._\-]*" value={stringValue(payload.id)} onChange={(event) => update("id", event.target.value)} /><small>{existing ? "ID 已锁定；重命名请复制、迁移依赖后弃用旧资产。" : "使用稳定命名空间，例如 metric.turnover_value。"}</small></label>
        <label>版本<input required pattern="[0-9]+\.[0-9]+\.[0-9]+" value={stringValue(payload.version, "1.0.0")} onChange={(event) => update("version", event.target.value)} /></label>
        <label>中文名称<input required value={name.zh} onChange={(event) => update("name", { ...name, zh: event.target.value })} /></label>
        <label>英文名称<input required value={name.en} onChange={(event) => update("name", { ...name, en: event.target.value })} /></label>
        <label className="is-wide">业务定义<textarea required rows={4} value={stringValue(payload.definition)} onChange={(event) => update("definition", event.target.value)} placeholder="说明它是什么、适用边界以及不代表什么。" /></label>
        <label>责任人<input required list="asset-owner-options" value={stringValue(payload.owner)} onChange={(event) => update("owner", event.target.value)} /><small>选择已登记参与者；新建首个参与者时可填写该参与者自身 ID。</small></label>
        <fieldset className="asset-source-selector"><legend>来源证据（至少一项）</legend>{ontologyPackage.sources.map((source) => <label key={source.id}><input type="checkbox" checked={selectedSources.includes(source.id)} onChange={() => update("sources", selectedSources.includes(source.id) ? selectedSources.filter((id) => id !== source.id) : [...selectedSources, source.id])} /><span><strong>{source.title}</strong><small>{source.id} · {source.trust}</small></span></label>)}</fieldset>
      </div>
      <datalist id="asset-owner-options">{ontologyPackage.actors.map((actor) => <option key={actor.id} value={actor.id}>{actor.name.zh}</option>)}<option value={ontologyPackage.scenario.owner} /></datalist>
    </section>
  </>;
}

function objectValue(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject
    : {};
}

function objectList(value: unknown): JsonObject[] {
  return Array.isArray(value)
    ? value.filter((item): item is JsonObject => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function ProcessStepsEditor({
  value,
  ontologyPackage,
  onChange,
}: {
  value: unknown;
  ontologyPackage: OntologyPackage;
  onChange: (value: JsonObject[]) => void;
}) {
  const steps = objectList(value);
  const actorFallback = ontologyPackage.actors[0]?.id ?? "";
  const updateStep = (index: number, patch: JsonObject) => onChange(
    steps.map((step, current) => current === index ? { ...step, ...patch } : step),
  );
  return <fieldset className="structured-array-editor is-wide"><legend>流程步骤</legend>
    {steps.map((step, index) => <article key={`${stringValue(step.id)}-${index}`}>
      <header><strong>步骤 {index + 1}</strong><button type="button" disabled={steps.length === 1} onClick={() => onChange(steps.filter((_, current) => current !== index))}>移除</button></header>
      <div>
        <label>步骤 ID<input required value={stringValue(step.id)} onChange={(event) => updateStep(index, { id: event.target.value })} /></label>
        <label>名称<input required value={stringValue(step.name)} onChange={(event) => updateStep(index, { name: event.target.value })} /></label>
        <label>执行者<select required value={stringValue(step.actor)} onChange={(event) => updateStep(index, { actor: event.target.value })}><option value="">请选择</option>{ontologyPackage.actors.map((actor) => <option key={actor.id} value={actor.id}>{actor.name.zh} · {actor.id}</option>)}</select></label>
        <label>操作<input required value={stringValue(step.operation)} onChange={(event) => updateStep(index, { operation: event.target.value })} /></label>
        <label>失败处理<select value={stringValue(step.on_failure, "review")} onChange={(event) => updateStep(index, { on_failure: event.target.value })}>{["stop", "clarify", "review", "refuse"].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label className="is-wide">治理资产引用（每行一个 ID）<textarea rows={3} value={lines(step.governed_refs)} onChange={(event) => updateStep(index, { governed_refs: parseLines(event.target.value) })} /></label>
        <label className="is-wide">输出物（每行一个）<textarea rows={3} value={lines(step.output_artifacts)} onChange={(event) => updateStep(index, { output_artifacts: parseLines(event.target.value) })} /></label>
      </div>
    </article>)}
    <button type="button" onClick={() => onChange([...steps, { id: `step.${steps.length + 1}`, name: "", actor: actorFallback, operation: "", governed_refs: [], output_artifacts: [], on_failure: "review" }])}>＋ 新增步骤</button>
  </fieldset>;
}

function RuleConditionsEditor({
  value,
  ontologyPackage,
  onChange,
}: {
  value: unknown;
  ontologyPackage: OntologyPackage;
  onChange: (value: JsonObject[]) => void;
}) {
  const conditions = objectList(value);
  const updateCondition = (index: number, patch: JsonObject) => onChange(
    conditions.map((condition, current) => current === index ? { ...condition, ...patch } : condition),
  );
  return <fieldset className="structured-array-editor is-wide"><legend>条件（全部满足）</legend>
    {conditions.map((condition, index) => {
      const operator = stringValue(condition.op, "eq");
      const raw = condition.value;
      const renderedValue = Array.isArray(raw) ? raw.join(", ") : String(raw ?? "");
      return <article key={`${stringValue(condition.property)}-${index}`}><header><strong>条件 {index + 1}</strong><button type="button" onClick={() => onChange(conditions.filter((_, current) => current !== index))}>移除</button></header><div>
        <label>属性<select required value={stringValue(condition.property)} onChange={(event) => updateCondition(index, { property: event.target.value })}><option value="">请选择</option>{ontologyPackage.properties.map((property) => <option key={property.id} value={property.id}>{property.name.zh} · {property.id}</option>)}</select></label>
        <label>操作符<select value={operator} onChange={(event) => updateCondition(index, { op: event.target.value, value: ["is_true", "is_false"].includes(event.target.value) ? null : condition.value ?? "" })}>{["eq", "neq", "in", "not_in", "is_true", "is_false"].map((item) => <option key={item}>{item}</option>)}</select></label>
        {!['is_true', 'is_false'].includes(operator) ? <label>值<input required value={renderedValue} onChange={(event) => updateCondition(index, { value: ["in", "not_in"].includes(operator) ? parseLines(event.target.value) : event.target.value })} placeholder={["in", "not_in"].includes(operator) ? "多个值用逗号分隔" : "比较值"} /></label> : null}
      </div></article>;
    })}
    <button type="button" onClick={() => onChange([...conditions, { property: ontologyPackage.properties[0]?.id ?? "", op: "eq", value: "" }])}>＋ 新增条件</button>
  </fieldset>;
}

const formulaOps = ["field_ref", "metric_ref", "literal", "sum", "count_distinct", "add", "subtract", "multiply", "divide"] as const;

function newFormulaNode(
  op: typeof formulaOps[number],
  ontologyPackage: OntologyPackage,
): JsonObject {
  if (op === "field_ref") return { op, ref: ontologyPackage.properties[0]?.id ?? "", args: [] };
  if (op === "metric_ref") return { op, ref: ontologyPackage.metrics[0]?.id ?? "", args: [] };
  if (op === "literal") return { op, value: 0, args: [] };
  if (["sum", "count_distinct"].includes(op)) return { op, args: [newFormulaNode("field_ref", ontologyPackage)] };
  return { op, args: [newFormulaNode("literal", ontologyPackage), newFormulaNode("literal", ontologyPackage)] };
}

function FormulaNodeEditor({
  value,
  ontologyPackage,
  onChange,
  depth = 0,
}: {
  value: unknown;
  ontologyPackage: OntologyPackage;
  onChange: (value: JsonObject) => void;
  depth?: number;
}) {
  const node = objectValue(value);
  const op = formulaOps.includes(stringValue(node.op) as typeof formulaOps[number])
    ? stringValue(node.op) as typeof formulaOps[number]
    : "literal";
  const args = objectList(node.args);
  const updateArg = (index: number, next: JsonObject) => onChange({ ...node, op, args: args.map((item, current) => current === index ? next : item) });
  return <fieldset className="formula-node-editor"><legend>{depth === 0 ? "公式" : `参数 ${depth}`}</legend>
    <label>运算<select value={op} onChange={(event) => onChange(newFormulaNode(event.target.value as typeof formulaOps[number], ontologyPackage))}>{formulaOps.map((item) => <option key={item}>{item}</option>)}</select></label>
    {op === "field_ref" ? <label>字段<select required value={stringValue(node.ref)} onChange={(event) => onChange({ op, ref: event.target.value, args: [] })}><option value="">请选择</option>{ontologyPackage.properties.map((property) => <option key={property.id} value={property.id}>{property.name.zh} · {property.id}</option>)}</select></label> : null}
    {op === "metric_ref" ? <label>指标<select required value={stringValue(node.ref)} onChange={(event) => onChange({ op, ref: event.target.value, args: [] })}><option value="">请选择</option>{ontologyPackage.metrics.map((metric) => <option key={metric.id} value={metric.id}>{metric.name.zh} · {metric.id}</option>)}</select></label> : null}
    {op === "literal" ? <label>数值<input required type="number" step="any" value={String(node.value ?? 0)} onChange={(event) => onChange({ op, value: Number(event.target.value), args: [] })} /></label> : null}
    {args.map((child, index) => <FormulaNodeEditor key={index} value={child} ontologyPackage={ontologyPackage} onChange={(next) => updateArg(index, next)} depth={depth + 1} />)}
  </fieldset>;
}

function QueryContractEditor({
  value,
  ontologyPackage,
  onChange,
}: {
  value: unknown;
  ontologyPackage: OntologyPackage;
  onChange: (value: JsonObject) => void;
}) {
  const query = objectValue(value);
  const updateQuery = (key: string, next: unknown) => onChange({ ...query, [key]: next });
  const propertyOptions = ontologyPackage.properties.map((property) => <option key={property.id} value={property.id}>{property.name.zh} · {property.id}</option>);
  const selectedJoins = stringList(query.required_joins);
  const selectedRules = stringList(query.filters);
  return <fieldset className="query-contract-editor is-wide"><legend>确定性查询合同</legend><div>
    <label>基础数据源<select required value={stringValue(query.base_source)} onChange={(event) => updateQuery("base_source", event.target.value)}><option value="">请选择</option>{ontologyPackage.data_sources.map((source) => <option key={source.id} value={source.id}>{source.name.zh} · {source.id}</option>)}</select></label>
    <label>度量字段<select required value={stringValue(query.measure_property)} onChange={(event) => updateQuery("measure_property", event.target.value)}><option value="">请选择</option>{propertyOptions}</select></label>
    <label>期间字段<select required value={stringValue(query.period_property)} onChange={(event) => updateQuery("period_property", event.target.value)}><option value="">请选择</option>{propertyOptions}</select></label>
    <label>日期字段<select required value={stringValue(query.date_property)} onChange={(event) => updateQuery("date_property", event.target.value)}><option value="">请选择</option>{propertyOptions}</select></label>
    <label>总体字段<select required value={stringValue(query.population_property)} onChange={(event) => updateQuery("population_property", event.target.value)}><option value="">请选择</option>{propertyOptions}</select></label>
  </div><fieldset><legend>需要的 Join</legend>{ontologyPackage.joins.length ? ontologyPackage.joins.map((join) => <label key={join.id}><input type="checkbox" checked={selectedJoins.includes(join.id)} onChange={() => updateQuery("required_joins", selectedJoins.includes(join.id) ? selectedJoins.filter((id) => id !== join.id) : [...selectedJoins, join.id])} />{join.name.zh} · {join.id}</label>) : <p>当前没有 Join 合同</p>}</fieldset><fieldset><legend>过滤规则</legend>{ontologyPackage.rules.length ? ontologyPackage.rules.map((rule) => <label key={rule.id}><input type="checkbox" checked={selectedRules.includes(rule.id)} onChange={() => updateQuery("filters", selectedRules.includes(rule.id) ? selectedRules.filter((id) => id !== rule.id) : [...selectedRules, rule.id])} />{rule.name.zh} · {rule.id}</label>) : <p>当前没有规则</p>}</fieldset>
  </fieldset>;
}

function TypeFields({
  collection,
  payload,
  ontologyPackage,
  update,
}: {
  collection: SemanticCollection;
  payload: JsonObject;
  ontologyPackage: OntologyPackage;
  update: (key: string, value: unknown) => void;
}) {
  const entityOptions = ontologyPackage.entities.map((entity) => <option key={entity.id} value={entity.id}>{entity.name.zh} · {entity.id}</option>);
  const propertyOptions = ontologyPackage.properties.map((property) => <option key={property.id} value={property.id}>{property.name.zh} · {property.id}</option>);
  const dimensionOptions = ontologyPackage.dimensions.map((dimension) => <option key={dimension.id} value={dimension.id}>{dimension.name.zh} · {dimension.id}</option>);
  const metricOptions = ontologyPackage.metrics.map((metric) => <option key={metric.id} value={metric.id}>{metric.name.zh} · {metric.id}</option>);
  return <section className="asset-editor-section">
    <header><span>02</span><div><h3>{collectionConfig[collection].singular}语义</h3><p>{collectionConfig[collection].description}。</p></div></header>
    <div className="asset-form-grid">
      {collection === "entities" ? <><label>主键属性<input required value={stringValue(payload.primary_key)} onChange={(event) => update("primary_key", event.target.value)} list="asset-property-options" /></label><label>业务粒度<input required value={stringValue(payload.grain)} onChange={(event) => update("grain", event.target.value)} placeholder="例如：每笔成交事件" /></label><label className="is-wide">生命周期<input required value={stringValue(payload.lifecycle)} onChange={(event) => update("lifecycle", event.target.value)} placeholder="说明创建、修正、终止与保留方式" /></label></> : null}
      {collection === "properties" ? <><label>所属对象<select required value={stringValue(payload.entity)} onChange={(event) => update("entity", event.target.value)}>{entityOptions}</select></label><label>数据类型<select value={stringValue(payload.data_type, "string")} onChange={(event) => update("data_type", event.target.value)}>{["string", "integer", "decimal", "boolean", "date", "datetime", "enum"].map((item) => <option key={item}>{item}</option>)}</select></label><label className="asset-checkbox"><input type="checkbox" checked={Boolean(payload.required)} onChange={(event) => update("required", event.target.checked)} />必填字段</label><label>单位<input value={stringValue(payload.unit)} onChange={(event) => update("unit", event.target.value || null)} placeholder="无单位可留空" /></label><label>空值含义<input required value={stringValue(payload.null_meaning, "not_allowed")} onChange={(event) => update("null_meaning", event.target.value)} /></label><label className="is-wide">枚举值（每行一个）<textarea rows={5} value={lines(payload.enum_values)} onChange={(event) => update("enum_values", parseLines(event.target.value))} /></label></> : null}
      {collection === "relationships" ? <><label>起点对象<select required value={stringValue(payload.from_entity)} onChange={(event) => update("from_entity", event.target.value)}>{entityOptions}</select></label><label>终点对象<select required value={stringValue(payload.to_entity)} onChange={(event) => update("to_entity", event.target.value)}>{entityOptions}</select></label><label>谓词<input required value={stringValue(payload.predicate)} onChange={(event) => update("predicate", event.target.value)} placeholder="例如 belongsTo" /></label><label>基数<select value={stringValue(payload.cardinality, "N:1")} onChange={(event) => update("cardinality", event.target.value)}>{["1:1", "1:N", "N:1", "N:N"].map((item) => <option key={item}>{item}</option>)}</select></label></> : null}
      {collection === "actors" ? <label className="is-wide">业务角色（每行一个）<textarea required rows={6} value={lines(payload.roles)} onChange={(event) => update("roles", parseLines(event.target.value))} /></label> : null}
      {collection === "processes" ? <><label>流程类型<select value={stringValue(payload.process_type, "business")} onChange={(event) => update("process_type", event.target.value)}>{["business", "analysis", "governance"].map((item) => <option key={item}>{item}</option>)}</select></label><label>触发条件<input required value={stringValue(payload.trigger)} onChange={(event) => update("trigger", event.target.value)} /></label><ProcessStepsEditor value={payload.steps} ontologyPackage={ontologyPackage} onChange={(value) => update("steps", value)} /><label className="is-wide">异常路径（每行一个）<textarea rows={5} value={lines(payload.exception_paths)} onChange={(event) => update("exception_paths", parseLines(event.target.value))} /></label></> : null}
      {collection === "dimensions" ? <><label>所属对象<select required value={stringValue(payload.entity)} onChange={(event) => update("entity", event.target.value)}>{entityOptions}</select></label><label>键属性<select required value={stringValue(payload.key_property)} onChange={(event) => update("key_property", event.target.value)}>{propertyOptions}</select></label><label>标签属性<select required value={stringValue(payload.label_property)} onChange={(event) => update("label_property", event.target.value)}>{propertyOptions}</select></label><label>成员解析<select value={stringValue(payload.member_resolution, "exact")} onChange={(event) => update("member_resolution", event.target.value)}>{["exact", "controlled_alias", "none"].map((item) => <option key={item}>{item}</option>)}</select></label><label className="is-wide">层级名称（每行一级）<textarea rows={5} value={lines(payload.hierarchy)} onChange={(event) => update("hierarchy", parseLines(event.target.value))} /></label></> : null}
      {collection === "rules" ? <><label>规则类型<select value={stringValue(payload.rule_type, "quality")} onChange={(event) => update("rule_type", event.target.value)}>{["eligibility", "quality", "calendar", "policy", "alert"].map((item) => <option key={item}>{item}</option>)}</select></label><label>失败行为<select value={stringValue(payload.failure_behavior, "warn")} onChange={(event) => update("failure_behavior", event.target.value)}>{["exclude", "block", "warn"].map((item) => <option key={item}>{item}</option>)}</select></label><RuleConditionsEditor value={payload.all} ontologyPackage={ontologyPackage} onChange={(value) => update("all", value)} /></> : null}
      {collection === "metrics" ? <><label>指标类型<select value={stringValue(payload.metric_type, "derived")} onChange={(event) => { const next = event.target.value; update("metric_type", next); update("query", next === "derived" ? {} : { base_source: ontologyPackage.data_sources[0]?.id ?? null, measure_property: ontologyPackage.properties[0]?.id ?? null, period_property: ontologyPackage.properties[0]?.id ?? null, date_property: ontologyPackage.properties[0]?.id ?? null, population_property: ontologyPackage.properties[0]?.id ?? null, required_joins: [], filters: [] }); }}>{["base", "derived"].map((item) => <option key={item}>{item}</option>)}</select></label><label>基础对象<select required value={stringValue(payload.base_entity)} onChange={(event) => update("base_entity", event.target.value)}>{entityOptions}</select></label><label>值类型<select value={stringValue(payload.value_type, "decimal")} onChange={(event) => update("value_type", event.target.value)}>{["integer", "decimal", "percentage"].map((item) => <option key={item}>{item}</option>)}</select></label><label>单位<input required value={stringValue(payload.unit)} onChange={(event) => update("unit", event.target.value)} /></label><label>聚合语义<select value={stringValue(payload.aggregation_semantics, "derived_non_additive")} onChange={(event) => update("aggregation_semantics", event.target.value)}>{["additive", "semi_additive", "non_additive", "derived_non_additive"].map((item) => <option key={item}>{item}</option>)}</select></label><label>空值策略<select value={stringValue(payload.null_policy, "fail_validation")} onChange={(event) => update("null_policy", event.target.value)}>{["exclude", "zero", "fail_validation"].map((item) => <option key={item}>{item}</option>)}</select></label><label>零分母策略<select value={stringValue(payload.zero_denominator_policy, "refuse")} onChange={(event) => update("zero_denominator_policy", event.target.value)}>{["zero", "null", "refuse"].map((item) => <option key={item}>{item}</option>)}</select></label><label className="is-wide">结果粒度（每行一个维度 ID）<textarea rows={4} value={lines(payload.result_grain)} onChange={(event) => update("result_grain", parseLines(event.target.value))} /></label><label className="is-wide">允许维度（每行一个维度 ID）<textarea rows={4} value={lines(payload.allowed_dimensions)} onChange={(event) => update("allowed_dimensions", parseLines(event.target.value))} /></label><div className="is-wide"><FormulaNodeEditor value={payload.formula} ontologyPackage={ontologyPackage} onChange={(value) => update("formula", value)} /></div>{stringValue(payload.metric_type, "derived") === "base" ? <QueryContractEditor value={payload.query} ontologyPackage={ontologyPackage} onChange={(value) => update("query", value)} /> : <div className="derived-query-note is-wide"><strong>派生指标不绑定物理查询。</strong><span>公式只能引用已治理指标；物理查询责任保留在基础指标。</span></div>}</> : null}
      {collection === "analysis_patterns" ? <><label>分析意图<select value={stringValue(payload.intent, "metric_fact")} onChange={(event) => update("intent", event.target.value)}>{["metric_fact", "period_compare", "segment_contribution", "sequential_decomposition", "evidence_audit", "turnover_driver", "anomaly_triage", "time_series", "latency_profile", "timeline_evidence"].map((item) => <option key={item}>{item}</option>)}</select></label><label>执行操作<input required value={stringValue(payload.operation)} onChange={(event) => update("operation", event.target.value)} /></label><label className="asset-checkbox"><input type="checkbox" checked={Boolean(payload.exactly_two_periods)} onChange={(event) => update("exactly_two_periods", event.target.checked)} />要求恰好两个期间</label><label className="is-wide">依赖指标（每行一个 ID）<textarea required rows={5} value={lines(payload.required_metrics)} onChange={(event) => update("required_metrics", parseLines(event.target.value))} /></label><label className="is-wide">依赖维度（每行一个 ID）<textarea rows={4} value={lines(payload.required_dimensions)} onChange={(event) => update("required_dimensions", parseLines(event.target.value))} /></label><label className="is-wide">输出字段（每行一个）<textarea required rows={5} value={lines(payload.output_fields)} onChange={(event) => update("output_fields", parseLines(event.target.value))} /></label><label className="is-wide">失败条件（每行一个）<textarea rows={5} value={lines(payload.failure_conditions)} onChange={(event) => update("failure_conditions", parseLines(event.target.value))} /></label></> : null}
      {collection === "questions" ? <><label>分析模式<select required value={stringValue(payload.analysis_pattern)} onChange={(event) => update("analysis_pattern", event.target.value)}>{ontologyPackage.analysis_patterns.map((patternItem) => <option key={patternItem.id} value={patternItem.id}>{patternItem.name.zh} · {patternItem.id}</option>)}</select></label><label className="is-wide">问题示例（每行一条）<textarea required rows={6} value={lines(payload.examples)} onChange={(event) => update("examples", parseLines(event.target.value))} /></label><label className="is-wide">必需输入（每行一个）<textarea rows={4} value={lines(payload.required_inputs)} onChange={(event) => update("required_inputs", parseLines(event.target.value))} /></label><label className="is-wide">期望回答<textarea required rows={5} value={stringValue(payload.expected_answer)} onChange={(event) => update("expected_answer", event.target.value)} /></label></> : null}
      {collection === "policies" ? <><label className="is-wide">允许角色（每行一个）<textarea rows={4} value={lines(payload.allowed_roles)} onChange={(event) => update("allowed_roles", parseLines(event.target.value))} /></label><label className="is-wide">拒绝角色（每行一个）<textarea rows={4} value={lines(payload.denied_roles)} onChange={(event) => update("denied_roles", parseLines(event.target.value))} /></label><label className="is-wide">允许粒度（每行一个）<textarea required rows={4} value={lines(payload.allowed_grains)} onChange={(event) => update("allowed_grains", parseLines(event.target.value))} /></label><label className="is-wide">拒绝字段（每行一个）<textarea rows={4} value={lines(payload.denied_fields)} onChange={(event) => update("denied_fields", parseLines(event.target.value))} /></label><label>最小群组<input required type="number" min={1} value={String(payload.minimum_group_size ?? 1)} onChange={(event) => update("minimum_group_size", Number(event.target.value))} /></label></> : null}
      <datalist id="asset-property-options">{propertyOptions}</datalist>
      <datalist id="asset-dimension-options">{dimensionOptions}</datalist>
      <datalist id="asset-metric-options">{metricOptions}</datalist>
    </div>
  </section>;
}

function AssetEditorShell({
  collection,
  item,
  ontologyPackage,
  busy,
  error,
  onClose,
  onApply,
  onApplyAndValidate,
}: {
  collection: SemanticCollection;
  item: JsonObject | null;
  ontologyPackage: OntologyPackage;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onApply: (operation: PackageDraftOperation) => Promise<void> | void;
  onApplyAndValidate?: (operation: PackageDraftOperation) => Promise<void> | void;
}) {
  const existing = item !== null;
  const initial = useMemo(() => item ? structuredClone(item) : templateFor(collection, ontologyPackage), [collection, item, ontologyPackage]);
  const [payload, setPayload] = useState<JsonObject>(initial);
  const [localError, setLocalError] = useState<string | null>(null);
  const dirty = stableJson(payload) !== stableJson(initial);
  useEffect(() => { setPayload(initial); setLocalError(null); }, [initial]);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);
  const update = (key: string, value: unknown) => setPayload((current) => ({ ...current, [key]: value }));
  const close = () => { if (!dirty || window.confirm("放弃尚未保存的修改？")) onClose(); };
  const save = async (validate: boolean) => {
    if (!stringList(payload.sources).length) { setLocalError("至少选择一项来源证据。"); return; }
    setLocalError(null);
    const normalized = { ...payload, status: "proposed", tags: [...new Set([...stringList(payload.tags), "studio-authored"])] };
    const operation: PackageDraftOperation = { action: "UPSERT", collection, object_id: stringValue(payload.id), payload: normalized };
    try {
      if (validate && onApplyAndValidate) await onApplyAndValidate(operation);
      else await onApply(operation);
      onClose();
    } catch {
      // Parent mutation owns the exact backend error. Keep the editor and input open.
    }
  };
  return <div className="asset-editor-backdrop" role="presentation">
    <section className="asset-editor-shell" role="dialog" aria-modal="true" aria-labelledby="asset-editor-title">
      <header className="asset-editor-heading"><div><span>{existing ? "CREATE REVISION" : "NEW SEMANTIC ASSET"}</span><h2 id="asset-editor-title">{existing ? `修改${collectionConfig[collection].singular}` : `新增${collectionConfig[collection].singular}`}</h2><p>{existing ? "保存会创建 Proposed 修订；原确认状态不会被继承。" : collectionConfig[collection].description}</p></div><button type="button" onClick={close} aria-label="关闭资产编辑器">×</button></header>
      <div className="asset-state-strip"><span className="is-active">Draft</span><i>→</i><span>人工确认</span><i>→</i><span>验证</span><i>→</i><span>发布</span><i>→</i><span>Agent Active</span></div>
      <form onSubmit={(event) => { event.preventDefault(); const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null; void save(submitter?.dataset.validate === "true"); }}>
        <CommonFields payload={payload} ontologyPackage={ontologyPackage} existing={existing} update={update} />
        <TypeFields collection={collection} payload={payload} ontologyPackage={ontologyPackage} update={update} />
        <footer className="asset-editor-actions"><div><strong>{dirty ? "有未保存修改" : "尚未修改"}</strong><span>保存失败时内容会保留在当前编辑器中。</span>{localError || error ? <p role="alert">{localError ?? error}</p> : null}</div><div><button type="button" onClick={close}>取消</button><button type="submit" disabled={busy || !dirty}>{busy ? "保存中…" : "保存草稿"}</button>{onApplyAndValidate ? <button type="submit" data-validate="true" className="is-primary" disabled={busy || !dirty}>{busy ? "处理中…" : "保存并验证"}</button> : null}</div></footer>
      </form>
    </section>
  </div>;
}

function AssetCreateMenu({ solutionId }: { solutionId: string }) {
  const groups: Array<[string, SemanticCollection[]]> = [
    ["业务结构", ["entities", "properties", "relationships", "actors", "processes", "dimensions"]],
    ["计算语义", ["metrics", "rules"]],
    ["分析能力", ["analysis_patterns", "questions"]],
    ["运行治理", ["policies"]],
  ];
  return <details className="asset-create-menu"><summary>＋ 新建语义资产</summary><div>{groups.map(([label, collections]) => <section key={label}><h3>{label}</h3>{collections.map((collection) => <Link key={collection} to={semanticAssetHref(solutionId, collection)}><strong>{collectionConfig[collection].singular}</strong><small>{collectionConfig[collection].description}</small></Link>)}</section>)}</div></details>;
}

export function SemanticAssetCatalog({
  mode,
  solutionId,
  ontologyPackage,
  authoring,
  candidates = [],
  busy,
  error,
  onApply,
  onApplyAndValidate,
  onConfirm,
  onDeprecate,
  assetChecksums = {},
  reviewer,
  readOnly = false,
}: {
  mode: CatalogMode;
  solutionId: string;
  ontologyPackage: OntologyPackage;
  authoring?: StudioAuthoringProjection;
  candidates?: ConstructionCandidate[];
  busy: boolean;
  error: string | null;
  onApply: (operation: PackageDraftOperation) => Promise<void> | void;
  onApplyAndValidate?: (operation: PackageDraftOperation) => Promise<void> | void;
  onConfirm?: (operation: PackageDraftOperation) => Promise<void> | void;
  onDeprecate?: (operation: PackageDraftOperation) => Promise<void> | void;
  assetChecksums?: Record<string, string>;
  reviewer: string;
  readOnly?: boolean;
}) {
  const allowedCollections = modeCollections[mode];
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedCollection = searchParams.get("assetType") as SemanticCollection | null;
  const selectedCollection = requestedCollection && allowedCollections.includes(requestedCollection)
    ? requestedCollection
    : allowedCollections[0];
  const requestedId = searchParams.get("assetId");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [selectedId, setSelectedId] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [deprecating, setDeprecating] = useState<string | null>(null);
  const [deprecationAcknowledged, setDeprecationAcknowledged] = useState(false);
  const items = recordsFor(ontologyPackage, selectedCollection);
  const visible = items.filter((item) => {
    const name = localizedName(item);
    const matchesQuery = `${stringValue(item.id)} ${name.zh} ${name.en} ${stringValue(item.definition)}`.toLowerCase().includes(query.toLowerCase());
    return matchesQuery && (status === "all" || item.status === status);
  });
  const selected = items.find((item) => item.id === selectedId) ?? visible[0] ?? items[0];
  const editingItem = requestedId && requestedId !== "new"
    ? items.find((item) => item.id === requestedId) ?? null
    : null;
  const editorOpen = !readOnly && (requestedId === "new" || Boolean(editingItem));
  const sourceCount = mode === "metrics" ? authoring?.metric_candidates.length ?? 0 : 0;
  const pendingCount = candidates.filter((candidate) => candidate.review_status === "UNREVIEWED").length;
  const runtimeMetricIds = new Set(ontologyPackage.analysis_patterns.flatMap((pattern) => pattern.required_metrics));
  const supportedCount = mode === "metrics"
    ? ontologyPackage.metrics.filter((metric) => runtimeMetricIds.has(metric.id)).length
    : mode === "experience" ? ontologyPackage.analysis_patterns.length : 0;
  const closeEditor = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("assetType"); next.delete("assetId");
    setSearchParams(next, { replace: true });
  };
  const editHref = (item: JsonObject) => semanticAssetHref(solutionId, selectedCollection, stringValue(item.id));
  const confirmAsset = async (item: JsonObject) => {
    if (!onConfirm) return;
    const checksum = assetChecksums[`${selectedCollection}:${stringValue(item.id)}`];
    if (!checksum) return;
    setConfirming(stringValue(item.id));
    try {
      await onConfirm({
        action: "CONFIRM",
        collection: selectedCollection,
        object_id: stringValue(item.id),
        payload: {
          reviewer,
          reviewed_at: new Date().toISOString(),
          asset_checksum: checksum,
        },
      });
    } catch {
      // Parent mutation exposes the exact backend error without losing selection.
    } finally { setConfirming(null); }
  };
  const deprecateAsset = async (item: JsonObject) => {
    if (!onDeprecate) return;
    try {
      await onDeprecate({ action: "DEPRECATE", collection: selectedCollection, object_id: stringValue(item.id), payload: null });
      setDeprecating(null);
    } catch { /* Keep impact confirmation open with parent error. */ }
  };
  const title = mode === "business" ? "业务模型" : mode === "metrics" ? "指标与规则" : mode === "experience" ? "分析能力" : "访问与披露策略";
  const description = mode === "business" ? "从业务对象到流程与维度的统一资产目录" : mode === "metrics" ? "权威指标、计算口径与规则目录" : mode === "experience" ? "Agent 可以理解的问题与可以执行的分析" : "运行权限、数据粒度与结果披露边界";
  return <section className="semantic-asset-catalog" aria-labelledby="semantic-assets-title">
    <header className="asset-catalog-heading"><div><span>SEMANTIC ASSET CATALOG</span><h2 id="semantic-assets-title">{title}</h2><p>{description}</p></div>{!readOnly ? <AssetCreateMenu solutionId={solutionId} /> : null}</header>
    <div className="asset-authority-summary"><div><span>当前 Draft</span><strong>{allowedCollections.reduce((total, collection) => total + recordsFor(ontologyPackage, collection).length, 0)}</strong><small>可追踪语义资产</small></div><div><span>来源定义</span><strong>{sourceCount}</strong><small>原始材料转写层</small></div><div><span>待复核候选</span><strong>{pendingCount}</strong><small>尚未进入权威模型</small></div><div><span>Agent 已支持</span><strong>{supportedCount}</strong><small>已有执行能力</small></div></div>
    {sourceCount ? <div className="asset-layer-notice"><strong>来源层与权威层已分开。</strong><span>{sourceCount} 条来源指标保留为证据，不会替换下方 {ontologyPackage.metrics.length} 条 Ontology 指标。</span></div> : null}
    <nav className="asset-category-nav" aria-label={`${title}资产类型`}>{allowedCollections.map((collection) => <button type="button" className={selectedCollection === collection ? "is-active" : ""} key={collection} onClick={() => { const next = new URLSearchParams(searchParams); next.set("assetType", collection); next.delete("assetId"); setSearchParams(next); setSelectedId(""); }}><strong>{collectionConfig[collection].label}</strong><span>{recordsFor(ontologyPackage, collection).length}</span><small>{collectionConfig[collection].description}</small></button>)}</nav>
    <div className="asset-catalog-toolbar"><label><span>搜索当前类型</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="名称、ID 或定义" /></label><label><span>治理状态</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">全部状态</option><option value="proposed">Proposed</option><option value="needs_clarification">Needs clarification</option><option value="confirmed">Confirmed</option></select></label>{!readOnly ? <Link className="context-create-action" to={semanticAssetHref(solutionId, selectedCollection)}>＋ 新增{collectionConfig[selectedCollection].singular}</Link> : null}</div>
    <div className="asset-catalog-layout">
      <div className="asset-list" role="list" aria-label={`${collectionConfig[selectedCollection].label}目录`}><header><span>资产</span><span>状态</span><span>责任 / 来源</span></header>{visible.map((item) => { const name = localizedName(item); return <button type="button" role="listitem" className={selected?.id === item.id ? "is-selected" : ""} key={stringValue(item.id)} onClick={() => { setSelectedId(stringValue(item.id)); setDeprecating(null); setDeprecationAcknowledged(false); }}><span><strong>{name.zh || name.en}</strong><small>{name.en}</small><code>{stringValue(item.id)}</code></span><em className={`is-${stringValue(item.status)}`}>{stringValue(item.status)}</em><span><strong>{stringValue(item.owner)}</strong><small>{stringList(item.sources).length} 项证据</small></span></button>; })}{visible.length === 0 ? <div className="asset-empty"><h3>没有匹配资产</h3><p>调整搜索或状态筛选；也可以创建第一项。</p></div> : null}</div>
      <aside className="asset-inspector">
        {selected ? <>
          <span>{collectionConfig[selectedCollection].singular.toUpperCase()} DETAIL</span>
          <h3>{localizedName(selected).zh || localizedName(selected).en}</h3>
          <p>{stringValue(selected.definition)}</p>
          <code>{stringValue(selected.id)}</code>
          <dl>
            <div><dt>治理状态</dt><dd>{stringValue(selected.status)}</dd></div>
            <div><dt>版本</dt><dd>{stringValue(selected.version)}</dd></div>
            <div><dt>责任人</dt><dd>{stringValue(selected.owner)}</dd></div>
            <div><dt>来源</dt><dd>{stringList(selected.sources).join(" · ")}</dd></div>
          </dl>
          <details><summary>查看完整 typed contract</summary><pre>{JSON.stringify(selected, null, 2)}</pre></details>
          {!readOnly ? <div className="asset-inspector-actions">
            <Link to={editHref(selected)}>{selected.status === "confirmed" ? "创建修订草稿" : "继续编辑"}</Link>
            {["proposed", "needs_clarification"].includes(stringValue(selected.status)) && onConfirm ? <button type="button" disabled={busy || !assetChecksums[`${selectedCollection}:${stringValue(selected.id)}`]} onClick={() => void confirmAsset(selected)}>{confirming === selected.id ? "确认中…" : assetChecksums[`${selectedCollection}:${stringValue(selected.id)}`] ? "确认当前摘要" : "等待权威摘要"}</button> : null}
            {onDeprecate ? <button type="button" className="is-danger" onClick={() => { setDeprecating(stringValue(selected.id)); setDeprecationAcknowledged(false); }}>弃用</button> : null}
          </div> : null}
          {!readOnly && deprecating === selected.id ? <div className="asset-deprecate-confirm">
            <strong>先确认影响，再弃用</strong>
            <p>系统会检查对象、指标、规则、映射和流程中的所有活动引用；仍有依赖时操作会被后端阻止，当前输入不会丢失。</p>
            <label><input type="checkbox" checked={deprecationAcknowledged} onChange={(event) => setDeprecationAcknowledged(event.target.checked)} />我已确认这是当前选中的 <code>{stringValue(selected.id)}</code></label>
            <div><button type="button" onClick={() => { setDeprecating(null); setDeprecationAcknowledged(false); }}>返回</button><button type="button" className="is-danger" disabled={busy || !deprecationAcknowledged} onClick={() => void deprecateAsset(selected)}>检查依赖并弃用</button></div>
          </div> : null}
          {error ? <p className="asset-operation-error" role="alert">{error}</p> : null}
        </> : <div className="asset-empty"><h3>选择一项资产</h3><p>详情、依赖与治理动作会显示在这里。</p></div>}
      </aside>
    </div>
    {editorOpen ? <AssetEditorShell collection={selectedCollection} item={editingItem} ontologyPackage={ontologyPackage} busy={busy} error={error} onClose={closeEditor} onApply={onApply} onApplyAndValidate={onApplyAndValidate} /> : null}
  </section>;
}
