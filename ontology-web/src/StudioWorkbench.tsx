import { useMemo, useState } from "react";

import type {
  ActiveRuntimeVerification,
  AgentRuntimeStatus,
  PackageDraftOperation,
  PreparedRuntime,
  RuntimeSnapshotRef,
  StudioWorkbench,
} from "./api";
import { PackageContractEditor } from "./PackageContractEditor";

export type WorkbenchTab = "model" | "bindings" | "validate" | "evidence" | "release";
type ModelKind = "objects" | "metrics" | "rules" | "policies" | "catalog";

type ValidationCheckView = {
  check_id: string;
  category: string | null;
  status: string;
  message: string;
  details: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function validationChecks(value: unknown): ValidationCheckView[] {
  const checks: ValidationCheckView[] = [];
  const visit = (candidate: unknown) => {
    if (Array.isArray(candidate)) {
      candidate.forEach(visit);
      return;
    }
    if (!isRecord(candidate)) return;
    if (
      typeof candidate.check_id === "string"
      && typeof candidate.status === "string"
      && typeof candidate.message === "string"
    ) {
      checks.push({
        check_id: candidate.check_id,
        category: typeof candidate.category === "string" ? candidate.category : null,
        status: candidate.status,
        message: candidate.message,
        details: candidate.details,
      });
      return;
    }
    Object.values(candidate).forEach(visit);
  };
  visit(value);
  return [...new Map(checks.map((check) => [
    `${check.check_id}:${check.status}:${check.message}`,
    check,
  ])).values()];
}

function recordArray(record: Record<string, unknown>, key: string): Record<string, unknown>[] {
  const value = record[key];
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function textValue(record: Record<string, unknown>, key: string, fallback = "—"): string {
  const value = record[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}

const tabLabels: Array<{ id: WorkbenchTab; label: string; hint: string }> = [
  { id: "model", label: "业务语义", hint: "对象 · 关系 · 指标" },
  { id: "bindings", label: "数据绑定", hint: "Sources · Mappings · Joins" },
  { id: "validate", label: "验证", hint: "Checks · Preview" },
  { id: "evidence", label: "来源与历史", hint: "Intake · Anchors · Revisions" },
  { id: "release", label: "发布与运行", hint: "Publish · Activate" },
];

export type StudioRuntimeLifecycle = {
  status: AgentRuntimeStatus | null;
  prepared: PreparedRuntime | null;
  rollbackTarget: RuntimeSnapshotRef | null;
  verification: ActiveRuntimeVerification | null;
  busy: "refresh" | "prepare" | "activate" | "verify" | "rollback" | null;
  error: string | null;
  onRefresh: () => void;
  onPrepare: () => void;
  onActivate: () => void;
  onVerify: () => void;
  onRollback: () => void;
};

export type StudioAuthoringController = {
  busy: boolean;
  error: string | null;
  onApply: (operation: PackageDraftOperation) => void;
};

type LinkDraft = {
  id: string;
  version: string;
  status: "proposed" | "needs_clarification" | "confirmed";
  nameEn: string;
  nameZh: string;
  definition: string;
  owner: string;
  source: string;
  fromEntity: string;
  toEntity: string;
  predicate: string;
  cardinality: "1:1" | "1:N" | "N:1" | "N:N";
};

export function StudioWorkbenchView({
  workbench,
  lifecycle,
  authoring,
  activeTab,
  navigation = "rail",
  presentation = "standalone",
}: {
  workbench: StudioWorkbench;
  lifecycle?: StudioRuntimeLifecycle;
  authoring?: StudioAuthoringController;
  activeTab?: WorkbenchTab;
  navigation?: "rail" | "hidden";
  presentation?: "standalone" | "page";
}) {
  const [localTab, setLocalTab] = useState<WorkbenchTab>("model");
  const tab = activeTab ?? localTab;
  const [modelKind, setModelKind] = useState<ModelKind>("objects");
  const [linkDraft, setLinkDraft] = useState<LinkDraft | null>(null);
  const [contractEditorOpen, setContractEditorOpen] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState(
    workbench.package.entities[0]?.id ?? "",
  );
  const selectedEntity = useMemo(
    () => workbench.package.entities.find((item) => item.id === selectedEntityId)
      ?? workbench.package.entities[0],
    [selectedEntityId, workbench.package.entities],
  );
  const properties = selectedEntity
    ? workbench.package.properties.filter((item) => item.entity === selectedEntity.id)
    : [];
  const relationships = selectedEntity
    ? workbench.package.relationships.filter(
        (item) => item.from_entity === selectedEntity.id || item.to_entity === selectedEntity.id,
      )
    : [];
  const checks = useMemo(
    () => validationChecks(workbench.workspace.validation.report),
    [workbench.workspace.validation.report],
  );
  const intakeAssets = [
    ...recordArray(workbench.intake, "assets"),
    ...recordArray(workbench.intake, "source_files"),
  ];
  const intakeGaps = recordArray(workbench.intake, "gaps");
  const intakeAnchors = [
    ...recordArray(workbench.intake, "anchors"),
    ...workbench.workspace.source_anchors,
  ];
  const semanticChangeRequests = workbench.semantic_change_requests ?? [];
  const activeSnapshot = lifecycle?.status?.active ?? null;
  const preparedSnapshot = lifecycle?.prepared?.snapshot ?? null;

  function newLinkDraft(): LinkDraft {
    const entity = selectedEntity ?? workbench.package.entities[0];
    return {
      id: "",
      version: "1.0.0",
      status: "proposed",
      nameEn: "",
      nameZh: "",
      definition: "Studio-authored relationship pending semantic validation.",
      owner: entity?.owner ?? "actor.ontology_owner",
      source: workbench.package.sources[0]?.id ?? entity?.sources[0] ?? "source.unconfirmed",
      fromEntity: entity?.id ?? "",
      toEntity: workbench.package.entities[0]?.id ?? "",
      predicate: "",
      cardinality: "N:1",
    };
  }

  function editLinkDraft(relationship: StudioWorkbench["package"]["relationships"][number]) {
    setLinkDraft({
      id: relationship.id,
      version: relationship.version,
      status: relationship.status === "confirmed" || relationship.status === "needs_clarification" ? relationship.status : "proposed",
      nameEn: relationship.name.en,
      nameZh: relationship.name.zh,
      definition: relationship.definition,
      owner: relationship.owner,
      source: relationship.sources[0],
      fromEntity: relationship.from_entity,
      toEntity: relationship.to_entity,
      predicate: relationship.predicate,
      cardinality: relationship.cardinality,
    });
  }

  function updateLink<K extends keyof LinkDraft>(key: K, value: LinkDraft[K]) {
    setLinkDraft((current) => current ? { ...current, [key]: value } : current);
  }

  function submitLink() {
    if (!linkDraft || !authoring) return;
    authoring.onApply({
      action: "UPSERT",
      collection: "relationships",
      object_id: linkDraft.id,
      payload: {
        id: linkDraft.id,
        version: linkDraft.version,
        status: linkDraft.status,
        name: { en: linkDraft.nameEn, zh: linkDraft.nameZh },
        definition: linkDraft.definition,
        owner: linkDraft.owner,
        sources: [linkDraft.source],
        decisions: [],
        tags: ["studio-authored"],
        from_entity: linkDraft.fromEntity,
        to_entity: linkDraft.toEntity,
        predicate: linkDraft.predicate,
        cardinality: linkDraft.cardinality,
      },
    });
  }

  return (
    <section className={`semantic-workbench${presentation === "page" ? " is-page" : ""}`} aria-labelledby="semantic-workbench-heading">
      <header className="semantic-workbench-header">
        <div>
          <span>ONTOLOGY PACKAGE</span>
          <h2 id="semantic-workbench-heading">语义模型工作台</h2>
          <p>查看并维护当前工作区中的对象、关系、指标、数据映射与发布状态。</p>
          <div className="workbench-header-actions">
            <button type="button" disabled={!authoring} onClick={() => setContractEditorOpen(true)}>打开完整合同编辑器</button>
            <span>{(workbench.workspace.package_operations ?? []).length} draft operations</span>
          </div>
        </div>
        <dl>
          <div><dt>Package</dt><dd>{workbench.package.package_id}</dd></div>
          <div><dt>Candidate</dt><dd>{workbench.package.version}</dd></div>
          <div><dt>Revision</dt><dd>r{workbench.workspace.revision}</dd></div>
          <div><dt>Checksum</dt><dd>{workbench.package_checksum.slice(0, 12)}…</dd></div>
        </dl>
      </header>
      <div className="semantic-workbench-layout">
        {navigation === "rail" ? <nav className="workbench-rail" aria-label="Studio 工作区">
          {tabLabels.map((item, index) => (
            <button
              type="button"
              key={item.id}
              className={tab === item.id ? "is-active" : ""}
              aria-current={tab === item.id ? "page" : undefined}
              onClick={() => setLocalTab(item.id)}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{item.label}</strong>
              <small>{item.hint}</small>
            </button>
          ))}
        </nav> : null}
        <div className="workbench-stage">
          {contractEditorOpen ? (
            <PackageContractEditor
              ontologyPackage={workbench.package}
              busy={authoring?.busy ?? false}
              error={authoring?.error ?? null}
              onSubmit={(operation) => authoring?.onApply(operation)}
              onClose={() => setContractEditorOpen(false)}
            />
          ) : tab === "model" ? (
            <div className="model-workbench">
              <nav className="model-kind-tabs" aria-label="Ontology model categories">
                {([
                  ["objects", "对象与关系", workbench.package.entities.length],
                  ["metrics", "指标", workbench.package.metrics.length],
                  ["rules", "规则", workbench.package.rules.length],
                  ["policies", "策略", workbench.package.policies.length],
                  ["catalog", "其余语义", workbench.package.actors.length + workbench.package.processes.length + workbench.package.dimensions.length + workbench.package.analysis_patterns.length + workbench.package.questions.length],
                ] as Array<[ModelKind, string, number]>).map(([id, label, count]) => (
                  <button type="button" key={id} className={modelKind === id ? "is-active" : ""} onClick={() => setModelKind(id)}>
                    {label} {count}
                  </button>
                ))}
              </nav>
              {modelKind === "objects" ? (
                <div className="model-workspace">
                  <aside className="object-index">
                    <div className="workbench-section-heading"><span>OBJECT INDEX</span><b>{workbench.package.entities.length}</b></div>
                    {workbench.package.entities.map((entity) => (
                      <button type="button" className={entity.id === selectedEntity?.id ? "is-selected" : ""} key={entity.id} onClick={() => setSelectedEntityId(entity.id)}>
                        <strong>{entity.name.en}</strong><span>{entity.name.zh}</span><code>{entity.id}</code>
                      </button>
                    ))}
                  </aside>
                  <div className="object-detail">
                    <div className="workbench-section-heading"><div><span>ONTOLOGY MODEL</span><h3>业务对象与关系</h3></div><div className="heading-actions"><b>{workbench.package.relationships.length} 条关系</b><button type="button" disabled={!authoring} onClick={() => setLinkDraft(newLinkDraft())}>新增关系</button></div></div>
                    {selectedEntity ? (
                      <>
                        {linkDraft ? (
                          <form className="link-editor" onSubmit={(event) => { event.preventDefault(); submitLink(); }}>
                            <header><div><span>TYPED RELATIONSHIP CONTRACT</span><h4>关系合同编辑器</h4></div><button type="button" onClick={() => setLinkDraft(null)}>关闭</button></header>
                            <div className="link-editor-fields">
                              <label>Link ID<input aria-label="Link ID" required value={linkDraft.id} onChange={(event) => updateLink("id", event.target.value)} /></label>
                              <label>Version<input aria-label="Version" required pattern="[0-9]+\.[0-9]+\.[0-9]+" value={linkDraft.version} onChange={(event) => updateLink("version", event.target.value)} /></label>
                              <label>Governance status<select aria-label="Governance status" value={linkDraft.status} onChange={(event) => updateLink("status", event.target.value as LinkDraft["status"])}><option value="proposed">Proposed</option><option value="needs_clarification">Needs clarification</option><option value="confirmed">Confirmed by reviewer</option></select></label>
                              <label>English name<input aria-label="English name" required value={linkDraft.nameEn} onChange={(event) => updateLink("nameEn", event.target.value)} /></label>
                              <label>中文名称<input aria-label="中文名称" required value={linkDraft.nameZh} onChange={(event) => updateLink("nameZh", event.target.value)} /></label>
                              <label>From entity<select aria-label="From entity" value={linkDraft.fromEntity} onChange={(event) => updateLink("fromEntity", event.target.value)}>{workbench.package.entities.map((entity) => <option value={entity.id} key={entity.id}>{entity.name.en} · {entity.id}</option>)}</select></label>
                              <label>To entity<select aria-label="To entity" value={linkDraft.toEntity} onChange={(event) => updateLink("toEntity", event.target.value)}>{workbench.package.entities.map((entity) => <option value={entity.id} key={entity.id}>{entity.name.en} · {entity.id}</option>)}</select></label>
                              <label>Predicate<input aria-label="Predicate" required value={linkDraft.predicate} onChange={(event) => updateLink("predicate", event.target.value)} /></label>
                              <label>Cardinality<select aria-label="Cardinality" value={linkDraft.cardinality} onChange={(event) => updateLink("cardinality", event.target.value as LinkDraft["cardinality"])}><option>1:1</option><option>1:N</option><option>N:1</option><option>N:N</option></select></label>
                              <label>Owner<input aria-label="Owner" required value={linkDraft.owner} onChange={(event) => updateLink("owner", event.target.value)} /></label>
                              <label>Source reference<select aria-label="Source reference" value={linkDraft.source} onChange={(event) => updateLink("source", event.target.value)}>{workbench.package.sources.map((source) => <option value={source.id} key={source.id}>{source.title}</option>)}</select></label>
                              <label className="is-wide">Definition<textarea aria-label="Definition" required rows={3} value={linkDraft.definition} onChange={(event) => updateLink("definition", event.target.value)} /></label>
                            </div>
                            <footer><p>保存只生成 Draft 修订；仍需验证、发布、认证和运行激活。</p><button type="submit" disabled={!authoring || authoring.busy}>{authoring?.busy ? "保存中…" : "保存关系草稿"}</button></footer>
                            {authoring?.error ? <p className="operator-error" role="alert">{authoring.error}</p> : null}
                          </form>
                        ) : null}
                        <section className="object-contract">
                          <div><span>OBJECT</span><h4>{selectedEntity.name.zh}</h4><code>{selectedEntity.id}</code></div>
                          <p>{selectedEntity.definition}</p>
                          <dl>
                            <div><dt>Primary key</dt><dd>{selectedEntity.primary_key}</dd></div>
                            <div><dt>Grain</dt><dd>{selectedEntity.grain}</dd></div>
                            <div><dt>Lifecycle</dt><dd>{selectedEntity.lifecycle}</dd></div>
                            <div><dt>Owner</dt><dd>{selectedEntity.owner}</dd></div>
                          </dl>
                        </section>
                        <section className="property-ledger">
                          <h4>Properties</h4>
                          <div className="workbench-table-wrap">
                            <table><thead><tr><th>Property</th><th>Type</th><th>Required</th><th>Unit / Enum</th></tr></thead>
                              <tbody>{properties.map((property) => <tr key={property.id}><td><strong>{property.name.en}</strong><code>{property.id}</code></td><td>{property.data_type}</td><td>{property.required ? "YES" : "NO"}</td><td>{property.unit ?? (property.enum_values.join(" · ") || "—")}</td></tr>)}</tbody>
                            </table>
                          </div>
                        </section>
                        <section className="relationship-ledger">
                          <h4>对象关系</h4>
                          <div className="link-list">{relationships.map((relationship) => <article key={relationship.id}><code>{relationship.from_entity}</code><div><strong>{relationship.predicate}</strong><span>{relationship.cardinality}</span></div><code>{relationship.to_entity}</code>{authoring ? <button type="button" aria-label={`编辑关系 ${relationship.predicate}`} onClick={() => editLinkDraft(relationship)}>编辑</button> : null}</article>)}</div>
                        </section>
                      </>
                    ) : <p>当前 package 没有 Entity。</p>}
                  </div>
                </div>
              ) : modelKind === "metrics" ? (
                <section className="semantic-ledger">
                  <div className="workbench-section-heading"><div><span>METRIC CONTRACTS</span><h3>指标语义与公式</h3></div><b>{workbench.package.metrics.length} METRICS</b></div>
                  {workbench.package.metrics.map((metric) => <article key={metric.id}><header><div><strong>{metric.name.en}</strong><span>{metric.name.zh}</span><code>{metric.id}</code></div><b>{metric.metric_type}</b></header><p>{metric.definition}</p><dl><div><dt>Unit</dt><dd>{metric.unit}</dd></div><div><dt>Base entity</dt><dd>{metric.base_entity}</dd></div><div><dt>Semantics</dt><dd>{metric.aggregation_semantics}</dd></div><div><dt>Dimensions</dt><dd>{metric.allowed_dimensions.join(" · ") || "—"}</dd></div></dl><details><summary>Formula / query contract</summary><pre>{JSON.stringify({ formula: metric.formula, query: metric.query }, null, 2)}</pre></details></article>)}
                </section>
              ) : modelKind === "rules" ? (
                <section className="semantic-ledger">
                  <div className="workbench-section-heading"><div><span>RULE CONTRACTS</span><h3>业务规则与失败行为</h3></div><b>{workbench.package.rules.length} RULES</b></div>
                  {workbench.package.rules.map((rule) => <article key={rule.id}><header><div><strong>{rule.name.en}</strong><span>{rule.name.zh}</span><code>{rule.id}</code></div><b>{rule.rule_type}</b></header><p>{rule.definition}</p><dl><div><dt>Failure behavior</dt><dd>{rule.failure_behavior}</dd></div><div><dt>Owner</dt><dd>{rule.owner}</dd></div></dl><pre>{JSON.stringify(rule.all, null, 2)}</pre></article>)}
                </section>
              ) : modelKind === "policies" ? (
                <section className="semantic-ledger">
                  <div className="workbench-section-heading"><div><span>POLICY CONTRACTS</span><h3>权限与披露策略</h3></div><b>{workbench.package.policies.length} POLICIES</b></div>
                  {workbench.package.policies.map((policy) => <article key={policy.id}><header><div><strong>{policy.name.en}</strong><span>{policy.name.zh}</span><code>{policy.id}</code></div><b>k≥{policy.minimum_group_size}</b></header><p>{policy.definition}</p><dl><div><dt>Allowed roles</dt><dd>{policy.allowed_roles.join(" · ") || "—"}</dd></div><div><dt>Denied roles</dt><dd>{policy.denied_roles.join(" · ") || "—"}</dd></div><div><dt>Allowed grains</dt><dd>{policy.allowed_grains.join(" · ") || "—"}</dd></div><div><dt>Denied fields</dt><dd>{policy.denied_fields.join(" · ") || "—"}</dd></div></dl></article>)}
                </section>
              ) : (
                <section className="semantic-catalog">
                  <div className="workbench-section-heading"><div><span>SEMANTIC CATALOG</span><h3>角色、流程、维度与分析能力</h3></div><b>PACKAGE COMPLETE</b></div>
                  {([
                    ["Actors", workbench.package.actors], ["Processes", workbench.package.processes],
                    ["Dimensions", workbench.package.dimensions], ["Analysis patterns", workbench.package.analysis_patterns],
                    ["Questions", workbench.package.questions],
                  ] as Array<[string, Array<{ id: string; name: { en: string; zh: string }; definition: string }>]>).map(([label, items]) => <section key={label}><h4>{label} · {items.length}</h4>{items.map((item) => <article key={item.id}><strong>{item.name.en}</strong><span>{item.name.zh}</span><code>{item.id}</code><p>{item.definition}</p></article>)}</section>)}
                </section>
              )}
            </div>
          ) : tab === "bindings" ? (
            <div className="binding-workspace">
              <section className="binding-section">
                <div className="workbench-section-heading">
                  <div><span>PHYSICAL BINDINGS</span><h3>逻辑字段到物理数据</h3></div>
                  <b>{workbench.package.bindings.length} MAPPINGS</b>
                </div>
                <div className="workbench-table-wrap">
                  <table><thead><tr><th>Logical target</th><th>Physical field</th><th>Type / Unit</th><th>Transform</th><th>Owner</th></tr></thead>
                    <tbody>{workbench.package.bindings.map((binding) => <tr key={binding.id}><td><strong>{binding.logical_target}</strong><code>{binding.id}</code></td><td><code>{binding.table}.{binding.column}</code><small>{binding.source}</small></td><td>{binding.data_type}<small>{binding.unit ?? "—"}</small></td><td>{binding.transformation}</td><td>{binding.owner}</td></tr>)}</tbody>
                  </table>
                </div>
              </section>
              <section className="binding-section">
                <div className="workbench-section-heading">
                  <div><span>JOIN CONTRACTS</span><h3>关联、基数与 fan-out 策略</h3></div>
                  <b>{workbench.package.joins.length} JOINS</b>
                </div>
                <div className="join-contracts">{workbench.package.joins.map((join) => <article key={join.id}><header><div><strong>{join.name.en}</strong><code>{join.id}</code></div><span>{join.expected_cardinality}</span></header><div className="join-path"><code>{join.left_table}</code><b>→</b><div>{join.keys.map((key) => <small key={`${key.left_column}:${key.right_column}`}>{key.left_column} = {key.right_column}</small>)}</div><b>→</b><code>{join.right_table}</code></div><footer>Fan-out: {join.fanout_policy}</footer></article>)}</div>
              </section>
              <section className="binding-section">
                <div className="workbench-section-heading">
                  <div><span>SOURCE SCHEMA</span><h3>数据表与字段字典</h3></div>
                  <b>{workbench.package.data_sources.length} SOURCES</b>
                </div>
                <div className="source-schema-grid">{workbench.package.data_sources.map((source) => <article key={source.id}><header><strong>{source.name.zh}</strong><code>{source.id}</code></header>{source.tables.map((table) => <details key={table.name}><summary>{table.name} · {table.fields.length} fields</summary><p>{table.grain}</p><div className="schema-field-list">{table.fields.map((field) => <div key={field.name}><code>{field.name}</code><span>{field.data_type}{field.nullable ? " · nullable" : " · required"}</span></div>)}</div></details>)}</article>)}</div>
              </section>
            </div>
          ) : tab === "validate" ? (
            <div className="validation-workspace">
              <section className="validation-summary">
                <div className="workbench-section-heading">
                  <div><span>BACKEND VALIDATION</span><h3>精确验证结果</h3></div>
                  <b className={`validation-status is-${workbench.workspace.validation.status.toLowerCase()}`}>
                    {workbench.workspace.validation.status}
                  </b>
                </div>
                <dl>
                  <div><dt>Validated revision</dt><dd>{workbench.workspace.validation.revision === null ? "—" : `r${workbench.workspace.validation.revision}`}</dd></div>
                  <div><dt>Draft checksum</dt><dd>{workbench.workspace.validation.draft_checksum ? `${workbench.workspace.validation.draft_checksum.slice(0, 12)}…` : "—"}</dd></div>
                  <div><dt>Validated at</dt><dd>{workbench.workspace.validation.validated_at ?? "—"}</dd></div>
                  <div><dt>Exact candidate</dt><dd>{workbench.package_checksum.slice(0, 12)}…</dd></div>
                </dl>
                <p>
                  PASS/FAIL 只展示后端对 exact revision 与 checksum 的验证结论；浏览器不会自行补写验证状态。
                </p>
              </section>
              {checks.length > 0 ? (
                <section className="validation-ledger" aria-label="Validation checks">
                  {checks.map((check) => (
                    <article key={`${check.check_id}:${check.status}:${check.message}`}>
                      <header>
                        <span className={`check-state is-${check.status.toLowerCase()}`}>{check.status}</span>
                        <code>{check.check_id}</code>
                        {check.category ? <small>{check.category}</small> : null}
                      </header>
                      <p>{check.message}</p>
                      {check.details === undefined ? null : (
                        <details>
                          <summary>查看验证证据</summary>
                          <pre>{JSON.stringify(check.details, null, 2)}</pre>
                        </details>
                      )}
                    </article>
                  ))}
                </section>
              ) : (
                <div className="workbench-empty">
                  <span>{workbench.workspace.validation.status}</span>
                  <h3>当前 revision 尚无可展示的后端检查明细。</h3>
                  <p>先在上方编辑器保存并验证；未运行时不会显示推测性的 PASS。</p>
                </div>
              )}
            </div>
          ) : tab === "evidence" ? (
            <div className="evidence-workspace">
              <div className="workbench-section-heading">
                <div><span>LINEAGE & CHANGE</span><h3>来源证据与修订轨迹</h3></div>
                <b>{workbench.package.sources.length} PACKAGE SOURCES</b>
              </div>
              <section className="evidence-source-ledger">
                <h4>Package source register</h4>
                {workbench.package.sources.length > 0 ? workbench.package.sources.map((source) => (
                  <article key={source.id}>
                    <header><strong>{source.title}</strong><span>{source.trust}</span></header>
                    <code>{source.id}</code>
                    <p>{source.source_type} · {source.locator}</p>
                    <footer>{source.owner} · {source.captured_on}</footer>
                  </article>
                )) : <p className="evidence-none">当前 candidate package 未登记 SourceReference。</p>}
              </section>
              <div className="evidence-columns">
                <section>
                  <h4>Intake assets</h4>
                  <div className="compact-ledger">
                    {intakeAssets.map((asset, index) => (
                      <article key={`${textValue(asset, "asset_id", textValue(asset, "source_id", "asset"))}:${index}`}>
                        <strong>{textValue(asset, "asset_id", textValue(asset, "source_id", `asset-${index + 1}`))}</strong>
                        <span>{textValue(asset, "kind", textValue(asset, "media_type", "registered source"))}</span>
                        <code>{textValue(asset, "locator", textValue(asset, "sha256"))}</code>
                        <small>{textValue(asset, "processing_mode", textValue(asset, "size_bytes", "registered"))}</small>
                      </article>
                    ))}
                    {intakeAssets.length === 0 ? <p className="evidence-none">没有单独登记的 intake asset。</p> : null}
                  </div>
                </section>
                <section>
                  <h4>Source anchors</h4>
                  <div className="compact-ledger">
                    {intakeAnchors.map((anchor, index) => (
                      <article key={`${textValue(anchor, "field", "anchor")}:${index}`}>
                        <strong>{textValue(anchor, "field", `anchor-${index + 1}`)}</strong>
                        <span>{textValue(anchor, "asset_id", textValue(anchor, "source_id", "source"))}</span>
                        <code>{textValue(anchor, "locator")}</code>
                      </article>
                    ))}
                    {intakeAnchors.length === 0 ? <p className="evidence-none">当前 adapter 未提供字段级 source anchor。</p> : null}
                  </div>
                </section>
              </div>
              <section className="gap-register">
                <h4>Missing / unconfirmed register</h4>
                {intakeGaps.map((gap, index) => (
                  <article key={textValue(gap, "gap_id", `gap-${index + 1}`)}>
                    <span className={`gap-state is-${textValue(gap, "status", "OPEN").toLowerCase()}`}>{textValue(gap, "status", "OPEN")}</span>
                    <div><strong>{textValue(gap, "gap_id", `gap-${index + 1}`)}</strong><p>{textValue(gap, "description")}</p></div>
                  </article>
                ))}
                {intakeGaps.length === 0 ? <p className="evidence-none">Intake summary 未声明结构化 gap；这不等于生产材料已齐备。</p> : null}
              </section>
              <section className="scr-inbox">
                <div className="workbench-section-heading"><div><span>AGENT FEEDBACK</span><h3>Semantic Change Request inbox</h3></div><b>{semanticChangeRequests.length} PROPOSED</b></div>
                {semanticChangeRequests.map((request, index) => (
                  <article key={textValue(request, "request_id", `scr-${index + 1}`)}>
                    <header><span>{textValue(request, "status", "PROPOSED_UNTRIAGED")}</span><b>{textValue(request, "request_type", "OTHER")}</b><code>{textValue(request, "request_id")}</code></header>
                    <h4>{textValue(request, "title")}</h4>
                    <p>{textValue(request, "observation")}</p>
                    <blockquote>{textValue(request, "proposed_change")}</blockquote>
                    <footer><code>{textValue(request, "execution_id")}</code><span>{Array.isArray(request.claim_refs) ? request.claim_refs.join(" · ") : "no claim refs"}</span></footer>
                  </article>
                ))}
                {semanticChangeRequests.length === 0 ? <p className="evidence-none">Agent 尚未提交 evidence-bound semantic change request。</p> : null}
              </section>
              <section className="revision-ledger">
                <h4>Immutable draft revisions</h4>
                {workbench.revisions.map((revision, index) => (
                  <article key={`${textValue(revision, "revision", String(index + 1))}:${textValue(revision, "record_checksum")}`}>
                    <b>r{textValue(revision, "revision", String(index + 1))}</b>
                    <div><strong>{textValue(revision, "target_version")}</strong><span>{textValue(revision, "recorded_at")}</span></div>
                    <div><code>{textValue(revision, "draft_checksum").slice(0, 12)}…</code><small>{Array.isArray(revision.modified_fields) && revision.modified_fields.length ? "changed" : "snapshot"}</small></div>
                  </article>
                ))}
                {workbench.revisions.length === 0 ? <p className="evidence-none">当前存储未返回 revision ledger。</p> : null}
              </section>
            </div>
          ) : tab === "release" ? (
            <div className="release-workspace">
              <div className="workbench-section-heading">
                <div><span>CONTROLLED DELIVERY</span><h3>发布、认证、激活与验证</h3></div>
                <button type="button" className="quiet-action" disabled={!lifecycle || lifecycle.busy !== null} onClick={lifecycle?.onRefresh}>
                  {lifecycle?.busy === "refresh" ? "刷新中…" : "刷新运行状态"}
                </button>
              </div>
              <ol className="release-pipeline">
                <li className={workbench.workspace.validation.status === "PASS" ? "is-complete" : ""}>
                  <span>01</span><div><b>CANDIDATE</b><strong>r{workbench.workspace.revision} · {workbench.package.version}</strong><code>{workbench.package_checksum}</code><p>Draft materialization；只有 exact validation PASS 才能发布。</p></div>
                </li>
                <li className={workbench.workspace.last_published ? "is-complete" : ""}>
                  <span>02</span><div><b>PUBLISHED</b><strong>{workbench.workspace.last_published?.version ?? "尚未发布"}</strong><code>{workbench.workspace.last_published?.checksum ?? "—"}</code><p>不可变 semantic release；发布不会改变 Agent active pointer。</p></div>
                </li>
                <li className={preparedSnapshot ? "is-complete" : ""}>
                  <span>03</span><div><b>{preparedSnapshot ? "PREPARED" : "NOT PREPARED"}</b><strong>{lifecycle?.prepared?.readiness.certification_profile ?? "等待环境绑定与认证"}</strong><code>{preparedSnapshot?.checksum ?? "—"}</code><p>{lifecycle?.prepared ? `${lifecycle.prepared.readiness.checks.length} 个 readiness checks · ${lifecycle.prepared.readiness.status}` : "将 release 绑定到 exact dataset、adapter、query engine 和 certification controls。"}</p></div>
                </li>
                <li className={activeSnapshot ? "is-complete is-active" : ""}>
                  <span>04</span><div><b>{activeSnapshot ? "ACTIVE" : "NOT ACTIVE"}</b><strong>{activeSnapshot ? `${activeSnapshot.release.version} · ${activeSnapshot.environment_id}` : "当前无 active snapshot"}</strong><code>{activeSnapshot?.checksum ?? "—"}</code><p>CAS 激活指针；失败时旧 active snapshot 继续服务。</p></div>
                </li>
                <li className={lifecycle?.verification?.status === "PASS" ? "is-complete" : ""}>
                  <span>05</span><div><b>{lifecycle?.verification ? `VERIFIED ${lifecycle.verification.status}` : "NOT VERIFIED"}</b><strong>{lifecycle?.verification?.suite_id ?? "等待 active API 验证"}</strong><code>{lifecycle?.verification ? `${lifecycle.verification.case_count}/${lifecycle.verification.cases.length} cases` : "—"}</code><p>在正常 Agent API 路径重跑 reference suite，不把 prepare-time 认证冒充 active verification。</p></div>
                </li>
              </ol>
              <div className="operator-actions">
                <button type="button" disabled={!lifecycle || !workbench.workspace.last_published || lifecycle.busy !== null} onClick={lifecycle?.onPrepare}>
                  {lifecycle?.busy === "prepare" ? "准备中…" : "准备并认证"}
                </button>
                <button type="button" disabled={!lifecycle || !preparedSnapshot || lifecycle.busy !== null || preparedSnapshot.checksum === activeSnapshot?.checksum} onClick={lifecycle?.onActivate}>
                  {lifecycle?.busy === "activate" ? "激活中…" : "激活准备版本"}
                </button>
                <button type="button" disabled={!lifecycle || !activeSnapshot || lifecycle.busy !== null} onClick={lifecycle?.onVerify}>
                  {lifecycle?.busy === "verify" ? "验证中…" : "验证当前 Active"}
                </button>
                {lifecycle?.rollbackTarget ? (
                  <button type="button" className="danger-action" disabled={!activeSnapshot || lifecycle.busy !== null} onClick={lifecycle.onRollback}>
                    {lifecycle.busy === "rollback" ? "回滚中…" : `回滚到上一版本 ${lifecycle.rollbackTarget.release.version}`}
                  </button>
                ) : null}
                <a href={`/ontology-agent/?solution=${encodeURIComponent(workbench.package.package_id)}`}>在 Agent 中打开 ↗</a>
              </div>
              {lifecycle?.error ? <p className="operator-error" role="alert">{lifecycle.error}</p> : null}
              {lifecycle?.verification ? (
                <section className="verification-cases">
                  <h4>Active verification cases</h4>
                  {lifecycle.verification.cases.map((item) => <article key={item.case_id}><span className={`check-state is-${item.status.toLowerCase()}`}>{item.status}</span><code>{item.case_id}</code><small>{item.execution_id ?? "no execution"}</small><p>{item.defects.join(" · ") || "No defects"}</p></article>)}
                </section>
              ) : null}
              <p className="release-boundary">
                “发布”“准备/认证”“激活”“验证/回滚”是独立动作。回滚同样使用 expected-current CAS，不能覆盖并发发生的新激活。
              </p>
            </div>
          ) : <div className="workbench-empty"><span>UNKNOWN</span><h3>未知工作区。</h3></div>}
        </div>
      </div>
    </section>
  );
}
