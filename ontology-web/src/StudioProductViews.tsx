import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import type {
  ConstructionCandidate,
  PackageDraftOperation,
  StudioAuthoringProjection,
  StudioSourceKind,
  SourceIntakeBatchItemInput,
  SourceIntakeBatchReceipt,
  StudioSourceLibrary,
  StudioSourcePreview,
  StudioWorkbench,
} from "./api";
import { semanticAssetHref } from "./SemanticAssetCatalog";
import { studioPageHref } from "./StudioNavigation";
import { useUiLocale, type UiLocale } from "./i18n";

type OntologyPackage = StudioWorkbench["package"];

function confirmDiscard(dirty: boolean): boolean {
  return !dirty || window.confirm("放弃尚未保存的修改？");
}

function useDirtyNavigationGuard(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return undefined;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const protectLink = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (target && !window.confirm("当前页面有尚未保存的修改，确定离开？")) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", protectLink, true);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", protectLink, true);
    };
  }, [dirty]);
}

function useDialogFocus<T extends HTMLElement>(
  open: boolean,
  onClose: () => void,
  returnFocusRef?: { current: HTMLElement | null },
) {
  const dialogRef = useRef<T>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = returnFocusRef?.current
      ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusables = () => Array.from(dialog?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) ?? []).filter((item) => !item.hasAttribute("hidden"));
    window.requestAnimationFrame(() => (focusables()[0] ?? dialog)?.focus());
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const targets = focusables();
      if (!targets.length) {
        event.preventDefault();
        dialog?.focus();
        return;
      }
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      window.requestAnimationFrame(() => {
        if (previousFocus?.isConnected) previousFocus.focus();
        if (returnFocusRef) returnFocusRef.current = null;
      });
    };
  }, [open]);
  return dialogRef;
}

export type StudioVersionLineageProps = {
  sourcePack: {
    physicalFileCount: number;
    logicalSourceCount: number;
    installedSourceCount: number;
  };
  draft: {
    revision: number;
    targetVersion: string;
    validation: "NOT_RUN" | "STALE" | "PASS" | "FAIL";
  };
  reviewed: {
    version: string | null;
    status: string | null;
    metricCount: number;
  };
  active: {
    version: string;
    environmentId: string;
  } | null;
  solutionId: string;
};

export function StudioVersionLineage({
  sourcePack,
  draft,
  reviewed,
  active,
  solutionId,
}: StudioVersionLineageProps) {
  const sourceReady = sourcePack.logicalSourceCount > 0
    && sourcePack.installedSourceCount === sourcePack.logicalSourceCount;
  const reviewedLabel = reviewed.status === "INTERNAL_REVIEWED_WITH_PROVISIONAL_ASSUMPTIONS"
    ? "内部已审核（含待确认假设）"
    : reviewed.status
      ? "已有审核记录"
      : "尚无审核基线";
  const runtimeAligned = Boolean(active && reviewed.version && active.version === reviewed.version);
  const agentHref = `/ontology-agent/?solution=${encodeURIComponent(solutionId)}`;

  return <section className="studio-version-lineage" aria-label="Ontology 版本与权威链路">
    <header>
      <div><span>AUTHORITY LINEAGE</span><h2>从输入证据到 Agent 生效版本</h2></div>
      <p>四个阶段相互关联，但不会互相冒充：载入不等于建模，建模不等于审核，审核也不等于已经激活。</p>
    </header>
    <ol>
      <li className={sourceReady ? "is-ready" : "is-pending"}>
        <span>01</span><div><small>EXACT INPUT</small><strong>Source Pack</strong><p>{sourcePack.physicalFileCount} 份文件 · {sourcePack.logicalSourceCount} 个逻辑来源</p><em>{sourceReady ? "全部 exact source 已登记" : `已登记 ${sourcePack.installedSourceCount} / ${sourcePack.logicalSourceCount}`}</em></div>
      </li>
      <li className={draft.validation === "PASS" ? "is-ready" : "is-pending"}>
        <span>02</span><div><small>EDITABLE AUTHORITY</small><strong>Construction Draft</strong><p>v{draft.targetVersion} · Draft r{draft.revision}</p><em>{draft.validation === "PASS" ? "当前 Draft 验证通过" : `验证状态 ${draft.validation}`}</em></div>
      </li>
      <li className={reviewed.version ? "is-ready" : "is-pending"}>
        <span>03</span><div><small>HUMAN REVIEW</small><strong>Reviewed Baseline</strong><p>{reviewed.version ? `v${reviewed.version} · ${reviewed.metricCount} 个来源指标` : "尚未形成"}</p><em>{reviewedLabel}</em></div>
      </li>
      <li className={active ? "is-ready" : "is-pending"}>
        <span>04</span><div><small>RUNTIME AUTHORITY</small><strong>Agent Active</strong><p>{active ? `v${active.version} · ${active.environmentId}` : "尚未激活"}</p><em>{active ? runtimeAligned ? "与审核基线一致" : "与审核基线版本不同" : "等待认证与激活"}</em>{active ? <a href={agentHref}>进入 Agent 查询</a> : null}</div>
      </li>
    </ol>
    <footer><strong>边界：</strong>内部审核仅证明当前版本在已登记证据与显式假设下自洽、可追踪；<span>不等同于生产审批或运行激活</span>。</footer>
  </section>;
}

type GraphNodeKind = "entity" | "metric" | "rule";
type GraphNodeData = {
  label: string;
  technicalId: string;
  kind: GraphNodeKind;
  status: string;
  definition: string;
  layer: "canonical" | "candidate";
  candidateId?: string;
  supportClass?: ConstructionCandidate["support_class"];
};
type OntologyNode = Node<GraphNodeData, "ontologyNode">;
type OntologyEdge = Edge<{
  kind: "relationship" | "dependency" | "candidate-link" | "candidate-impact";
  technicalId: string;
  layer: "canonical" | "candidate";
  candidateId?: string;
}>;

export type OntologyGraphProjection = {
  nodes: OntologyNode[];
  edges: OntologyEdge[];
};

export function applyGraphSelection(
  projection: OntologyGraphProjection,
  selectedNodeId: string | null,
  selectedEdgeId: string | null,
): OntologyGraphProjection {
  const selectedEdge = selectedEdgeId
    ? projection.edges.find((edge) => edge.id === selectedEdgeId)
    : undefined;
  const focusedNodeIds = new Set<string>();
  const focusedEdgeIds = new Set<string>();

  if (selectedNodeId) {
    focusedNodeIds.add(selectedNodeId);
    projection.edges.forEach((edge) => {
      if (edge.source !== selectedNodeId && edge.target !== selectedNodeId) return;
      focusedEdgeIds.add(edge.id);
      focusedNodeIds.add(edge.source);
      focusedNodeIds.add(edge.target);
    });
  } else if (selectedEdge) {
    focusedEdgeIds.add(selectedEdge.id);
    focusedNodeIds.add(selectedEdge.source);
    focusedNodeIds.add(selectedEdge.target);
  }

  const hasFocus = focusedNodeIds.size > 0;
  return {
    nodes: projection.nodes.map((node) => ({
      ...node,
      selected: node.id === selectedNodeId,
      className: hasFocus
        ? node.id === selectedNodeId
          ? "is-graph-focus"
          : focusedNodeIds.has(node.id)
            ? "is-graph-neighbor"
            : "is-graph-dimmed"
        : undefined,
    })),
    edges: projection.edges.map((edge) => ({
      ...edge,
      className: hasFocus
        ? focusedEdgeIds.has(edge.id)
          ? "is-graph-highlighted"
          : "is-graph-dimmed"
        : undefined,
    })),
  };
}

type GraphLayoutMode = "force" | "layered";

export type OntologyGraphImpact = {
  nodeId: string;
  incoming: OntologyEdge[];
  outgoing: OntologyEdge[];
  affectedNodeIds: string[];
  canonicalDependencyCount: number;
};

export function graphImpactForNode(
  projection: OntologyGraphProjection,
  nodeId: string,
): OntologyGraphImpact {
  const incoming = projection.edges.filter((edge) => edge.target === nodeId);
  const outgoing = projection.edges.filter((edge) => edge.source === nodeId);
  const affectedNodeIds = [...new Set([
    ...incoming.map((edge) => edge.source),
    ...outgoing.map((edge) => edge.target),
  ])].sort();
  return {
    nodeId,
    incoming,
    outgoing,
    affectedNodeIds,
    canonicalDependencyCount: [...incoming, ...outgoing].filter(
      (edge) => edge.data?.layer === "canonical",
    ).length,
  };
}

function zhName(item: { name: { zh: string; en: string } }, locale: UiLocale = "zh"): string {
  return locale === "en" ? item.name.en || item.name.zh : item.name.zh || item.name.en;
}

function formulaMetricRefs(value: unknown, output = new Set<string>()): Set<string> {
  if (Array.isArray(value)) {
    value.forEach((item) => formulaMetricRefs(item, output));
    return output;
  }
  if (!value || typeof value !== "object") return output;
  const record = value as Record<string, unknown>;
  if (record.op === "metric_ref" && typeof record.ref === "string") output.add(record.ref);
  Object.values(record).forEach((item) => formulaMetricRefs(item, output));
  return output;
}

function candidateEndpoint(
  value: unknown,
  ontologyPackage: OntologyPackage,
): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const normalized = value.trim().toLowerCase();
  const exact = ontologyPackage.entities.find((entity) => entity.id === value);
  if (exact) return exact.id;
  const byLabel = ontologyPackage.entities.find((entity) => [
    entity.id,
    entity.name.en,
    entity.name.zh,
  ].some((candidate) => candidate.toLowerCase() === normalized));
  return byLabel?.id ?? null;
}

export function buildOntologyGraphProjection(
  ontologyPackage: OntologyPackage,
  candidates: ConstructionCandidate[] = [],
  locale: UiLocale = "zh",
): OntologyGraphProjection {
  const entityNodes: OntologyNode[] = ontologyPackage.entities.map((entity, index) => ({
    id: entity.id,
    type: "ontologyNode",
    position: { x: (index % 4) * 260, y: Math.floor(index / 4) * 180 },
    data: {
      label: zhName(entity, locale),
      technicalId: entity.id,
      kind: "entity",
      status: entity.status,
      definition: entity.definition,
      layer: "canonical",
    },
  }));
  const entityRows = Math.max(1, Math.ceil(entityNodes.length / 4));
  const metricStartY = entityRows * 180 + 80;
  const metricNodes: OntologyNode[] = ontologyPackage.metrics.map((metric, index) => ({
    id: metric.id,
    type: "ontologyNode",
    position: { x: (index % 4) * 260, y: metricStartY + Math.floor(index / 4) * 180 },
    data: {
      label: zhName(metric, locale),
      technicalId: metric.id,
      kind: "metric",
      status: metric.status,
      definition: metric.definition,
      layer: "canonical",
    },
  }));
  const metricRows = Math.max(1, Math.ceil(metricNodes.length / 4));
  const ruleStartY = metricStartY + metricRows * 180 + 80;
  const ruleNodes: OntologyNode[] = ontologyPackage.rules.map((rule, index) => ({
    id: rule.id,
    type: "ontologyNode",
    position: { x: (index % 4) * 260, y: ruleStartY + Math.floor(index / 4) * 180 },
    data: {
      label: zhName(rule, locale),
      technicalId: rule.id,
      kind: "rule",
      status: rule.status,
      definition: rule.definition,
      layer: "canonical",
    },
  }));
  const relationshipEdges: OntologyEdge[] = ontologyPackage.relationships.map((relationship) => ({
    id: relationship.id,
    source: relationship.from_entity,
    target: relationship.to_entity,
    label: relationship.predicate,
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed },
    data: { kind: "relationship", technicalId: relationship.id, layer: "canonical" },
  }));
  const metricIds = new Set(ontologyPackage.metrics.map((metric) => metric.id));
  const dependencyEdges: OntologyEdge[] = ontologyPackage.metrics.flatMap((metric) =>
    [...formulaMetricRefs(metric.formula)]
      .filter((dependency) => metricIds.has(dependency))
      .map((dependency) => ({
        id: `dependency:${metric.id}:${dependency}`,
        source: dependency,
        target: metric.id,
        label: "depends on",
        type: "smoothstep",
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed },
        data: { kind: "dependency" as const, technicalId: `dependency:${metric.id}:${dependency}`, layer: "canonical" as const },
      })),
  );

  const graphCandidates = candidates.filter((candidate) =>
    ["OBJECT", "LINK", "METRIC", "RULE"].includes(candidate.candidate_type),
  );
  const candidateNodes: OntologyNode[] = graphCandidates
    .filter((candidate) => candidate.candidate_type !== "LINK")
    .map((candidate, index) => ({
      id: `candidate-node:${candidate.candidate_id}`,
      type: "ontologyNode",
      position: { x: 1080 + (index % 2) * 250, y: Math.floor(index / 2) * 160 },
      data: {
        label: candidate.label,
        technicalId: candidate.candidate_id,
        kind: candidate.candidate_type === "METRIC" ? "metric" : candidate.candidate_type === "RULE" ? "rule" : "entity",
        status: "UNREVIEWED",
        definition: candidate.definition,
        layer: "candidate",
        candidateId: candidate.candidate_id,
        supportClass: candidate.support_class,
      },
    }));
  const candidateImpactEdges: OntologyEdge[] = graphCandidates
    .filter((candidate) => candidate.candidate_type !== "LINK" && candidate.canonical_target)
    .filter((candidate) => [...entityNodes, ...metricNodes, ...ruleNodes].some((node) => node.id === candidate.canonical_target))
    .map((candidate) => ({
      id: `candidate-impact:${candidate.candidate_id}`,
      source: `candidate-node:${candidate.candidate_id}`,
      target: candidate.canonical_target!,
      label: "proposes change",
      type: "smoothstep",
      animated: true,
      style: { strokeDasharray: "6 5" },
      markerEnd: { type: MarkerType.ArrowClosed },
      data: { kind: "candidate-impact", technicalId: candidate.candidate_id, layer: "candidate", candidateId: candidate.candidate_id },
    }));
  const candidateLinkEdges: OntologyEdge[] = graphCandidates
    .filter((candidate) => candidate.candidate_type === "LINK")
    .flatMap((candidate) => {
      const source = candidateEndpoint(candidate.proposal.subject, ontologyPackage);
      const target = candidateEndpoint(candidate.proposal.object, ontologyPackage);
      if (!source || !target) return [];
      return [{
        id: `candidate-link:${candidate.candidate_id}`,
        source,
        target,
        label: typeof candidate.proposal.predicate === "string" ? candidate.proposal.predicate : candidate.label,
        type: "smoothstep",
        animated: true,
        style: { stroke: "#d48c32", strokeDasharray: "6 5" },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#d48c32" },
        data: { kind: "candidate-link" as const, technicalId: candidate.candidate_id, layer: "candidate" as const, candidateId: candidate.candidate_id },
      }];
    });
  return {
    nodes: [...entityNodes, ...metricNodes, ...ruleNodes, ...candidateNodes],
    edges: [...relationshipEdges, ...dependencyEdges, ...candidateImpactEdges, ...candidateLinkEdges],
  };
}

function stableGraphSeed(value: string): number {
  let seed = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    seed ^= value.charCodeAt(index);
    seed = Math.imul(seed, 16777619);
  }
  return (seed >>> 0) / 4294967295;
}

/**
 * Deterministic force simulation: relationship structure shapes the graph,
 * while stable seeds keep a review workspace from jumping on every refresh.
 */
export function buildForceDirectedGraphProjection(
  projection: OntologyGraphProjection,
): OntologyGraphProjection {
  if (projection.nodes.length < 2) {
    return {
      nodes: projection.nodes.map((node) => ({ ...node, position: { ...node.position } })),
      edges: projection.edges.map((edge) => ({ ...edge, type: "default" })),
    };
  }

  const vertices = projection.nodes.map((node, index) => {
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    const progress = Math.sqrt((index + 0.75) / projection.nodes.length);
    const angle = index * goldenAngle + stableGraphSeed(node.id) * 0.42;
    const radius = (250 + Math.sqrt(projection.nodes.length) * 24) * progress;
    const kindAnchor = node.data.kind === "entity"
      ? { x: -210, y: -25 }
      : node.data.kind === "metric"
        ? { x: 190, y: -115 }
        : { x: 210, y: 190 };
    const candidateOffset = node.data.layer === "candidate" ? -150 : 0;
    return {
      node,
      x: Math.cos(angle) * radius + kindAnchor.x * 0.45,
      y: Math.sin(angle) * radius + kindAnchor.y * 0.45 + candidateOffset,
      vx: 0,
      vy: 0,
      kindAnchor,
    };
  });
  const vertexById = new Map(vertices.map((vertex, index) => [vertex.node.id, index]));
  const linkedEdges = projection.edges.flatMap((edge) => {
    const source = vertexById.get(edge.source);
    const target = vertexById.get(edge.target);
    return source === undefined || target === undefined ? [] : [{ edge, source, target }];
  });
  const degree = new Array(vertices.length).fill(0) as number[];
  linkedEdges.forEach(({ source, target }) => {
    degree[source] += 1;
    degree[target] += 1;
  });

  const iterations = vertices.length > 200 ? 45 : vertices.length > 100 ? 80 : 210;
  const repulsionStrength = 15_000;
  const collisionDistance = 218;
  for (let tick = 0; tick < iterations; tick += 1) {
    const temperature = 1 - tick / iterations;
    for (let left = 0; left < vertices.length; left += 1) {
      for (let right = left + 1; right < vertices.length; right += 1) {
        const a = vertices[left];
        const b = vertices[right];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        if (Math.abs(dx) + Math.abs(dy) < 0.001) {
          const nudge = stableGraphSeed(`${a.node.id}:${b.node.id}`) * Math.PI * 2;
          dx = Math.cos(nudge);
          dy = Math.sin(nudge);
        }
        const distanceSquared = Math.max(160, dx * dx + dy * dy);
        const distance = Math.sqrt(distanceSquared);
        const repel = (repulsionStrength / distanceSquared) * (0.55 + temperature * 0.45);
        const collision = distance < collisionDistance
          ? (collisionDistance - distance) * 0.034
          : 0;
        const force = repel + collision;
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }

    linkedEdges.forEach(({ edge, source, target }) => {
      const a = vertices[source];
      const b = vertices[target];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distance = Math.max(1, Math.sqrt(dx * dx + dy * dy));
      const idealDistance = edge.data?.kind === "candidate-impact" ? 285 : 235;
      const spring = (distance - idealDistance) * 0.014;
      const fx = (dx / distance) * spring;
      const fy = (dy / distance) * spring;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    });

    vertices.forEach((vertex, index) => {
      const hubGravity = Math.min(0.012, degree[index] * 0.0012);
      vertex.vx += -vertex.x * (0.0028 + hubGravity);
      vertex.vy += -vertex.y * (0.0028 + hubGravity);
      vertex.vx += (vertex.kindAnchor.x - vertex.x) * 0.0018;
      vertex.vy += (vertex.kindAnchor.y - vertex.y) * 0.0018;
      const speed = Math.max(1, Math.sqrt(vertex.vx * vertex.vx + vertex.vy * vertex.vy));
      const speedLimit = 14 * (0.35 + temperature * 0.65);
      if (speed > speedLimit) {
        vertex.vx = (vertex.vx / speed) * speedLimit;
        vertex.vy = (vertex.vy / speed) * speedLimit;
      }
      vertex.x += vertex.vx;
      vertex.y += vertex.vy;
      vertex.vx *= 0.78;
      vertex.vy *= 0.78;
    });
  }

  // React Flow nodes are cards rather than dots. Resolve remaining rectangle
  // collisions after the force simulation so labels stay readable at fitView.
  for (let pass = 0; pass < 140; pass += 1) {
    let collisionFound = false;
    for (let left = 0; left < vertices.length; left += 1) {
      for (let right = left + 1; right < vertices.length; right += 1) {
        const a = vertices[left];
        const b = vertices[right];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        if (Math.abs(dx) + Math.abs(dy) < 0.001) {
          dx = stableGraphSeed(`${a.node.id}:${b.node.id}`) < 0.5 ? -1 : 1;
          dy = 1;
        }
        const overlapX = 222 - Math.abs(dx);
        const overlapY = 104 - Math.abs(dy);
        if (overlapX <= 0 || overlapY <= 0) continue;
        collisionFound = true;
        if (overlapX < overlapY * 1.65) {
          const direction = dx < 0 ? -1 : 1;
          const shift = (overlapX + 3) / 2;
          a.x += direction * shift;
          b.x -= direction * shift;
        } else {
          const direction = dy < 0 ? -1 : 1;
          const shift = (overlapY + 3) / 2;
          a.y += direction * shift;
          b.y -= direction * shift;
        }
      }
    }
    if (!collisionFound) break;
  }

  const minX = Math.min(...vertices.map((vertex) => vertex.x));
  const minY = Math.min(...vertices.map((vertex) => vertex.y));
  return {
    nodes: vertices.map(({ node, x, y }) => ({
      ...node,
      position: { x: Math.round(x - minX + 90), y: Math.round(y - minY + 70) },
    })),
    edges: projection.edges.map((edge) => ({ ...edge, type: "default" })),
  };
}

export function RequirementsCatalogView({
  solutionId,
  ontologyPackage,
  authoring,
}: {
  solutionId: string;
  ontologyPackage: OntologyPackage;
  authoring?: StudioAuthoringProjection;
}) {
  const sourceRequirements = authoring?.requirements ?? [];
  const configuredRequirements = ontologyPackage.questions;
  const [layer, setLayer] = useState<"configured" | "source">("configured");
  const [selectedId, setSelectedId] = useState(configuredRequirements[0]?.id ?? sourceRequirements[0]?.requirement_key ?? "");
  const selectedSource = layer === "source"
    ? sourceRequirements.find((requirement) => requirement.requirement_key === selectedId) ?? sourceRequirements[0]
    : undefined;
  const selected = layer === "configured"
    ? configuredRequirements.find((question) => question.id === selectedId) ?? configuredRequirements[0]
    : undefined;
  const selectedCanonicalId = selected?.id ?? "";
  const selectedSourceId = selectedSource?.requirement_key ?? "";
  const sourcesHref = studioPageHref("inputs", solutionId, "sources");
  const selectLayer = (next: "configured" | "source") => {
    setLayer(next);
    setSelectedId(next === "configured" ? configuredRequirements[0]?.id ?? "" : sourceRequirements[0]?.requirement_key ?? "");
  };
  return (
    <section className="studio-object-page requirements-page" aria-labelledby="requirements-title">
      <header className="object-page-heading">
        <div><span>REQUIREMENTS CATALOG</span><h2 id="requirements-title">业务需求与分析流程</h2><p>在“业务配置”维护 Agent 应支持的问题、流程和期望答案；原始材料只作为不可改写的证据版本保留。</p></div>
        <div className="object-page-heading-side">
          <div className="object-page-counts"><strong>{configuredRequirements.length} 条业务配置</strong><span>{sourceRequirements.length} 条原始提取</span></div>
          <div className="object-page-actions">
            {layer === "configured" ? <>
              <Link className="is-secondary" to={semanticAssetHref(solutionId, "processes")}>新增业务过程</Link>
              <Link className="is-primary" to={semanticAssetHref(solutionId, "questions")}>新增分析需求</Link>
            </> : <Link className="is-primary" to={sourcesHref}>登记新的材料版本</Link>}
          </div>
        </div>
      </header>
      <nav className="authority-layer-switch" aria-label="需求信息层">
        <button type="button" className={layer === "configured" ? "is-active" : ""} onClick={() => selectLayer("configured")}>
          <strong>业务配置</strong><span>{configuredRequirements.length} 条 · 可编辑</span>
        </button>
        <button type="button" className={layer === "source" ? "is-active" : ""} onClick={() => selectLayer("source")}>
          <strong>原始需求提取</strong><span>{sourceRequirements.length} 条 · 只读证据</span>
        </button>
        <p>{layer === "configured" ? "这里的修改会形成 Ontology Draft 修订；不会覆盖原始需求文件。" : "这是从 exact source version 提取的证据快照。要纠正原文，请登记新的材料版本。"}</p>
      </nav>
      {layer === "configured" ? <div className="requirement-summary-grid">
        {ontologyPackage.processes.map((process) => <article key={process.id}><span>业务过程</span><h3>{zhName(process)}</h3><p>{process.definition}</p><footer><code>{process.id}</code><Link to={semanticAssetHref(solutionId, "processes", process.id)}>编辑过程</Link></footer></article>)}
        <article className="is-output"><span>期望输出</span><h3>可验证的分析答案</h3><p>每条分析需求分别定义回答粒度、必需输入、证据义务和不支持边界。</p><footer><code>questions[{configuredRequirements.length}]</code><Link to={semanticAssetHref(solutionId, "questions")}>新增输出要求</Link></footer></article>
      </div> : null}
      <div className="catalog-split-layout">
        <div className="catalog-table" role="list" aria-label={layer === "configured" ? "业务需求配置目录" : "原始需求提取目录"}>
          <div className="catalog-table-head"><span>分析需求</span><span>状态</span><span>标识</span></div>
          {layer === "source" ? sourceRequirements.map((requirement) => (
            <button key={requirement.requirement_key} type="button" role="listitem" className={selectedSourceId === requirement.requirement_key ? "is-selected" : ""} onClick={() => setSelectedId(requirement.requirement_key)}>
              <span><strong>{requirement.question}</strong><small>{requirement.minimum_output}</small></span>
              <em className="is-readonly">只读证据</em><code>{requirement.requirement_key}</code>
            </button>
          )) : configuredRequirements.map((question) => (
            <button key={question.id} type="button" role="listitem" className={selectedCanonicalId === question.id ? "is-selected" : ""} onClick={() => setSelectedId(question.id)}>
              <span><strong>{zhName(question)}</strong><small>{question.definition}</small></span>
              <em>{question.status === "confirmed" ? "已确认" : question.status === "needs_clarification" ? "待澄清" : "Draft"}</em><code>{question.id}</code>
            </button>
          ))}
        </div>
        <aside className="catalog-inspector requirement-inspector">
          {selectedSource ? <>
            <span>EXACT SOURCE REQUIREMENT</span><div className="inspector-mode-badge is-readonly">只读证据</div><h3>{selectedSource.question}</h3><p>{selectedSource.minimum_output}</p>
            <dl><div><dt>Requirement ID</dt><dd>{selectedSource.requirement_key}</dd></div><div><dt>呈现形式</dt><dd>{selectedSource.presentation}</dd></div><div><dt>证据锚点</dt><dd>{selectedSource.source_anchor ? `${selectedSource.source_anchor.source_id} · ${selectedSource.source_anchor.sheet_name ? `${selectedSource.source_anchor.sheet_name}!${selectedSource.source_anchor.cell_range}` : `line ${selectedSource.source_anchor.line_number}`}` : "尚无 exact anchor"}</dd></div></dl>
            <div className="inspector-actions"><Link className="is-primary" to={sourcesHref}>打开来源材料</Link><button type="button" disabled title="原始证据不可原地编辑">原始证据不可编辑</button></div>
          </> : selected ? <>
            <span>CONFIGURED REQUIREMENT</span><div className="inspector-mode-badge is-editable">Ontology Draft · 可编辑</div><h3>{zhName(selected)}</h3><p>{selected.definition}</p>
            <dl><div><dt>Requirement ID</dt><dd>{selected.id}</dd></div><div><dt>责任人</dt><dd>{selected.owner}</dd></div><div><dt>期望回答</dt><dd>{typeof selected.expected_answer === "string" && selected.expected_answer ? selected.expected_answer : "尚未填写"}</dd></div><div><dt>来源</dt><dd>{selected.sources.join(", ")}</dd></div></dl>
            <div className="inspector-actions"><Link className="is-primary" to={semanticAssetHref(solutionId, "questions", selected.id)}>编辑这条需求</Link><Link to={sourcesHref}>查看来源证据</Link></div>
          </> : <div className="data-empty-state"><h3>{layer === "configured" ? "尚无业务需求配置" : "尚无原始需求提取"}</h3><p>{layer === "configured" ? "新增一条分析需求，定义 Agent 应理解的问题和期望答案。" : "先在来源材料中登记需求文档版本。"}</p></div>}
        </aside>
      </div>
    </section>
  );
}

export function MetricCatalogView({ ontologyPackage, authoring }: { ontologyPackage: OntologyPackage; authoring?: StudioAuthoringProjection }) {
  const [query, setQuery] = useState("");
  const sourceCandidates = authoring?.metric_candidates ?? [];
  const [selectedId, setSelectedId] = useState(sourceCandidates[0]?.metric_key ?? ontologyPackage.metrics[0]?.id ?? "");
  const metrics = ontologyPackage.metrics.filter((metric) => `${metric.id} ${metric.name.zh} ${metric.name.en}`.toLowerCase().includes(query.toLowerCase()));
  const candidates = sourceCandidates.filter((metric) => `${metric.metric_key} ${metric.name}`.toLowerCase().includes(query.toLowerCase()));
  const selectedCandidate = sourceCandidates.find((metric) => metric.metric_key === selectedId);
  const selected = ontologyPackage.metrics.find((metric) => metric.id === selectedId);
  const metricCount = sourceCandidates.length || ontologyPackage.metrics.length;
  const runtimeMetricIds = new Set(
    ontologyPackage.analysis_patterns.flatMap((pattern) => {
      const required = pattern.required_metrics;
      return Array.isArray(required)
        ? required.filter((value): value is string => typeof value === "string")
        : [];
    }),
  );
  const ontologyCount = sourceCandidates.length
    ? sourceCandidates.filter((metric) => metric.ontology_status === "REVIEWED").length
    : ontologyPackage.metrics.filter((metric) => metric.status === "confirmed" || metric.status === "published").length;
  const runtimeCount = sourceCandidates.length
    ? sourceCandidates.filter((metric) => metric.runtime_status === "SUPPORTED").length
    : ontologyPackage.metrics.filter((metric) => runtimeMetricIds.has(metric.id)).length;
  const sourceStatusLabel = (metric: typeof sourceCandidates[number]) => (
    metric.runtime_status === "SUPPORTED"
      ? "Agent 可用"
      : metric.ontology_status === "REVIEWED"
        ? "本体已审核"
        : metric.ontology_status === "DRAFT"
          ? "本体草稿"
          : "待映射"
  );
  const ontologyDetail = (status: typeof sourceCandidates[number]["ontology_status"]) => (
    status === "REVIEWED" ? "已审核" : status === "DRAFT" ? "草稿" : "尚未映射"
  );
  const runtimeDetail = (status: typeof sourceCandidates[number]["runtime_status"]) => (
    status === "SUPPORTED" ? "已具备确定性分析工具与测试" : status === "NOT_YET_SUPPORTED" ? "本体已定义，Agent 工具尚未实现" : "不适用"
  );
  const governanceDetail = (status: typeof sourceCandidates[number]["governance_status"]) => (
    status === "REVIEWED_WITH_ASSUMPTIONS" ? "已审核（含待确认假设）" : status === "REVIEWED" ? "已审核" : "尚未审核"
  );
  return (
    <section className="studio-object-page" aria-labelledby="metrics-title">
      <header className="object-page-heading">
        <div><span>METRIC CONTRACTS</span><h2 id="metrics-title">指标与业务规则</h2><p>一个 Solution 的完整指标目录。选择指标查看口径、公式、粒度、单位和依赖。</p></div>
        <div className="object-page-counts"><strong>{metricCount} 个{sourceCandidates.length ? "来源" : "本体"}指标</strong><span>{ontologyCount} 个已进入 Ontology</span><span>{runtimeCount} 个 Agent 已支持</span></div>
      </header>
      <div className="catalog-toolbar"><label><span>搜索指标</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="名称或 ID" /></label><div>{sourceCandidates.length ? <><span>本体已审核 {ontologyCount}</span><span>Agent 待支持 {metricCount - runtimeCount}</span></> : <><span>基础指标 {ontologyPackage.metrics.filter((metric) => metric.metric_type === "base").length}</span><span>派生指标 {ontologyPackage.metrics.filter((metric) => metric.metric_type === "derived").length}</span></>}</div></div>
      <div className="catalog-split-layout">
        <div className="catalog-table" role="list" aria-label="指标目录">
          <div className="catalog-table-head"><span>指标</span><span>{sourceCandidates.length ? "当前能力" : "类型"}</span><span>单位</span></div>
          {sourceCandidates.length ? candidates.map((metric) => <button key={metric.metric_key} type="button" role="listitem" className={selectedId === metric.metric_key ? "is-selected" : ""} onClick={() => setSelectedId(metric.metric_key)}><span><strong>{metric.name}</strong><small>{metric.metric_key}{metric.canonical_metric_id ? ` · ${metric.canonical_metric_id}` : ""}</small></span><em className={`is-${metric.runtime_status.toLowerCase()}`}>{sourceStatusLabel(metric)}</em><code>{metric.unit}</code></button>) : metrics.map((metric) => <button key={metric.id} type="button" role="listitem" className={selectedId === metric.id ? "is-selected" : ""} onClick={() => setSelectedId(metric.id)}><span><strong>{zhName(metric)}</strong><small>{metric.id}</small></span><em>{metric.metric_type === "derived" ? "派生" : "基础"}</em><code>{metric.unit}</code></button>)}
        </div>
        <aside className="catalog-inspector">
          {selectedCandidate ? <><span>METRIC DETAIL</span><h3>{selectedCandidate.name}</h3><p>{selectedCandidate.definition}</p><dl><div><dt>来源状态</dt><dd>{selectedCandidate.support_class === "DIRECT_EXACT" ? "Exact 转写行已登记" : "Canonical draft"}</dd></div><div><dt>Ontology</dt><dd>{ontologyDetail(selectedCandidate.ontology_status)}{selectedCandidate.canonical_metric_id ? ` · ${selectedCandidate.canonical_metric_id}` : ""}</dd></div><div><dt>Agent Runtime</dt><dd>{runtimeDetail(selectedCandidate.runtime_status)}</dd></div><div><dt>治理状态</dt><dd>{governanceDetail(selectedCandidate.governance_status)}</dd></div><div><dt>粒度与维度</dt><dd>{selectedCandidate.grain_and_dimensions}</dd></div><div><dt>过滤与范围</dt><dd>{selectedCandidate.filters_and_scope}</dd></div><div><dt>空值 / 除零</dt><dd>{selectedCandidate.null_and_zero_policy}</dd></div><div><dt>Evidence</dt><dd>{selectedCandidate.source_anchor ? `${selectedCandidate.source_anchor.source_id} · ${selectedCandidate.source_anchor.sheet_name ? `${selectedCandidate.source_anchor.sheet_name}!${selectedCandidate.source_anchor.cell_range}` : `line ${selectedCandidate.source_anchor.line_number}`}` : "Canonical draft"}</dd></div></dl><details><summary>查看来源公式</summary><pre>{selectedCandidate.calculation_logic}</pre></details></> : selected ? <><span>METRIC DETAIL</span><h3>{zhName(selected)}</h3><p>{selected.definition}</p><dl><div><dt>聚合语义</dt><dd>{selected.aggregation_semantics}</dd></div><div><dt>结果粒度</dt><dd>{selected.result_grain.join(", ") || "总体"}</dd></div><div><dt>允许维度</dt><dd>{selected.allowed_dimensions.join(", ") || "无"}</dd></div><div><dt>空值 / 零分母</dt><dd>{selected.null_policy} / {selected.zero_denominator_policy}</dd></div></dl><details><summary>查看公式合同</summary><pre>{JSON.stringify(selected.formula, null, 2)}</pre></details></> : <p>选择一个指标查看详情。</p>}
        </aside>
      </div>
    </section>
  );
}

function OntologyNodeCard({ data, selected }: NodeProps<OntologyNode>) {
  return <div className={`ontology-graph-node is-${data.kind} is-${data.layer}${selected ? " is-selected" : ""}`}><Handle type="target" position={Position.Left} /><span>{data.layer === "candidate" ? `待复核${data.kind === "entity" ? "对象" : data.kind === "metric" ? "指标" : "规则"}` : data.kind === "entity" ? "对象" : data.kind === "metric" ? "指标" : "规则"}</span><strong>{data.label}</strong><small>{data.layer === "candidate" ? data.supportClass : data.technicalId}</small><Handle type="source" position={Position.Right} /></div>;
}

const ontologyNodeTypes = { ontologyNode: OntologyNodeCard };
const noConstructionCandidates: ConstructionCandidate[] = [];

export function OntologyGraphEditor({ ontologyPackage, candidates = noConstructionCandidates, reviewHref, createEntityHref, createRelationshipHref, editAssetHref, readOnly = false }: { ontologyPackage: OntologyPackage; candidates?: ConstructionCandidate[]; reviewHref?: string; createEntityHref?: string; createRelationshipHref?: string; editAssetHref?: (collection: "entities" | "relationships", objectId: string) => string; readOnly?: boolean }) {
  const { locale } = useUiLocale();
  const [layoutMode, setLayoutMode] = useState<GraphLayoutMode>("force");
  const [showCandidates, setShowCandidates] = useState(false);
  const layeredProjection = useMemo(() => buildOntologyGraphProjection(ontologyPackage, candidates, locale), [candidates, locale, ontologyPackage]);
  const forceInputProjection = useMemo(() => showCandidates ? layeredProjection : {
    nodes: layeredProjection.nodes.filter((node) => node.data.layer === "canonical"),
    edges: layeredProjection.edges.filter((edge) => edge.data?.layer === "canonical"),
  }, [layeredProjection, showCandidates]);
  const forceProjection = useMemo(() => buildForceDirectedGraphProjection(forceInputProjection), [forceInputProjection]);
  const projection = layoutMode === "force" ? forceProjection : layeredProjection;
  const [nodes, setNodes, onNodesChange] = useNodesState(projection.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(projection.edges);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<GraphNodeKind | "all">("all");
  const [focusNeighborhood, setFocusNeighborhood] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  useEffect(() => { setNodes(projection.nodes); setEdges(projection.edges); }, [projection, setEdges, setNodes]);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredNodeIds = new Set(nodes.filter((node) => (showCandidates || node.data.layer === "canonical") && (kind === "all" || node.data.kind === kind) && (!normalizedQuery || `${node.id} ${node.data.label}`.toLowerCase().includes(normalizedQuery))).map((node) => node.id));
  const neighborhoodNodeIds = selectedNodeId && focusNeighborhood
    ? new Set([selectedNodeId, ...graphImpactForNode(projection, selectedNodeId).affectedNodeIds])
    : null;
  const visibleNodeIds = new Set([...filteredNodeIds].filter((nodeId) => !neighborhoodNodeIds || neighborhoodNodeIds.has(nodeId)));
  const visibleProjection = applyGraphSelection({
    nodes: nodes.filter((node) => visibleNodeIds.has(node.id)),
    edges: edges.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)),
  }, selectedNodeId, selectedEdgeId);
  const visibleNodes = visibleProjection.nodes;
  const visibleEdges = visibleProjection.edges;
  const selectedNode = projection.nodes.find((node) => node.id === selectedNodeId);
  const selectedRelationship = selectedEdgeId ? ontologyPackage.relationships.find((relationship) => relationship.id === selectedEdgeId) : undefined;
  const selectedCandidateId = selectedNode?.data.candidateId
    ?? projection.edges.find((edge) => edge.id === selectedEdgeId)?.data?.candidateId;
  const selectedCandidate = candidates.find((candidate) => candidate.candidate_id === selectedCandidateId);
  const selectedImpact = selectedNodeId ? graphImpactForNode(projection, selectedNodeId) : null;
  const canonicalNodeCount = projection.nodes.filter((node) => node.data.layer === "canonical").length;
  const visibleCanonicalNodeCount = visibleNodes.filter((node) => node.data.layer === "canonical").length;
  const candidateCount = candidates.filter((candidate) => ["OBJECT", "LINK", "METRIC", "RULE"].includes(candidate.candidate_type)).length;

  return <section className="ontology-graph-workspace" aria-labelledby="graph-title">
    <header className="object-page-heading">
      <div><span>KNOWLEDGE GRAPH</span><h2 id="graph-title">知识图谱</h2><p>浏览对象、关系、指标和规则；选择节点或连线查看定义、来源与影响。</p></div>
      <div className="object-page-counts"><strong>{visibleCanonicalNodeCount} / {canonicalNodeCount} 个正式节点可见</strong><span>{candidateCount} 个待复核候选</span></div>
    </header>
    <div className="graph-toolbar">
      <label><span>搜索图谱</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="对象、指标或 ID" /></label>
      <label><span>节点类型</span><select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}><option value="all">全部</option><option value="entity">对象</option><option value="metric">指标</option><option value="rule">规则</option></select></label>
      <div className="graph-layout-switch" role="group" aria-label="图谱布局">
        <button type="button" className={layoutMode === "force" ? "is-active" : ""} aria-pressed={layoutMode === "force"} title="按关系强度组织节点" onClick={() => setLayoutMode("force")}>关联布局</button>
        <button type="button" className={layoutMode === "layered" ? "is-active" : ""} aria-pressed={layoutMode === "layered"} title="按对象、指标和规则分层排列" onClick={() => setLayoutMode("layered")}>分层布局</button>
      </div>
      <label className="graph-layer-toggle"><input type="checkbox" checked={showCandidates} onChange={(event) => setShowCandidates(event.target.checked)} />显示待复核候选</label>
      <label className="graph-layer-toggle"><input type="checkbox" checked={focusNeighborhood} disabled={!selectedNodeId} onChange={(event) => setFocusNeighborhood(event.target.checked)} />只看一跳影响</label>
      <div className="graph-toolbar-actions">{!readOnly && createEntityHref ? <a href={createEntityHref}>新建对象</a> : null}{!readOnly && createRelationshipHref ? <a className="is-primary" href={createRelationshipHref}>新建关系</a> : null}</div>
    </div>
    <div className="graph-editor-layout">
      <div className="graph-canvas" aria-label="Ontology graph canvas">
        <ReactFlow key={layoutMode} nodes={visibleNodes} edges={visibleEdges} nodeTypes={ontologyNodeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onNodeClick={(_, node) => { setSelectedNodeId(node.id); setSelectedEdgeId(null); }} onEdgeClick={(_, edge) => { setSelectedEdgeId(edge.id); setSelectedNodeId(null); }} onPaneClick={() => { setSelectedNodeId(null); setSelectedEdgeId(null); setFocusNeighborhood(false); }} fitView fitViewOptions={{ padding: 0.16 }} minZoom={0.25} maxZoom={2}>
          <Background gap={22} size={1} /><Controls /><MiniMap pannable zoomable nodeColor={(node) => node.data?.kind === "metric" ? "#d48c32" : node.data?.kind === "rule" ? "#7c6bb2" : "#0b776f"} />
        </ReactFlow>
      </div>
      <aside className="graph-inspector">
        {selectedCandidate ? <><span>CANDIDATE OVERLAY · NOT CANONICAL</span><h3>{selectedCandidate.label}</h3><p>{selectedCandidate.definition}</p><div className="evidence-lineage-mini"><b>{selectedCandidate.support_class}</b><span>Run → Candidate → 等待人工 Decision</span></div><dl><div><dt>候选类型</dt><dd>{selectedCandidate.candidate_type}</dd></div><div><dt>风险</dt><dd>{selectedCandidate.risk_class}</dd></div><div><dt>目标</dt><dd>{selectedCandidate.canonical_target ?? "尚未映射"}</dd></div><div><dt>证据锚点</dt><dd>{selectedCandidate.source_anchors.length}</dd></div></dl>{reviewHref ? <a className="graph-review-link" href={reviewHref}>{readOnly ? "查看复核记录 →" : "前往复核中心处理此候选 →"}</a> : null}</> : selectedRelationship ? <><span>RELATIONSHIP</span><h3>{zhName(selectedRelationship)}</h3><p>{selectedRelationship.definition}</p><dl><div><dt>Predicate</dt><dd>{selectedRelationship.predicate}</dd></div><div><dt>Direction</dt><dd>{selectedRelationship.from_entity} → {selectedRelationship.to_entity}</dd></div><div><dt>Cardinality</dt><dd>{selectedRelationship.cardinality}</dd></div></dl>{!readOnly && editAssetHref ? <a className="graph-review-link" href={editAssetHref("relationships", selectedRelationship.id)}>在资产工作台修改或弃用 →</a> : null}</> : selectedNode ? <><span>{selectedNode.data.kind.toUpperCase()}</span><h3>{selectedNode.data.label}</h3><p>{selectedNode.data.definition}</p><code>{selectedNode.id}</code>{selectedImpact ? <section className="graph-impact-summary"><strong>影响预检</strong><div><span>上游 {selectedImpact.incoming.length}</span><span>下游 {selectedImpact.outgoing.length}</span><span>相邻对象 {selectedImpact.affectedNodeIds.length}</span></div>{selectedImpact.affectedNodeIds.slice(0, 8).map((item) => <code key={item}>{item}</code>)}</section> : null}{!readOnly && selectedNode.data.kind === "entity" && editAssetHref ? <a className="graph-review-link" href={editAssetHref("entities", selectedNode.id)}>在资产工作台修改或弃用 →</a> : null}</> : <div className="graph-empty-inspector"><span>GRAPH INSPECTOR</span><h3>选择节点或关系</h3><p>查看定义、来源与影响；资产变更统一进入目录表单。</p></div>}
      </aside>
    </div>
  </section>;
}

export function AgentExperienceView({ ontologyPackage }: { ontologyPackage: OntologyPackage }) {
  return <section className="studio-object-page"><header className="object-page-heading"><div><span>AGENT EXPERIENCE</span><h2>分析问题与回答义务</h2><p>Agent 的问题族、分析模式和证据展示与语义版本分开管理。</p></div><div className="object-page-counts"><strong>{ontologyPackage.questions.length} 个问题族</strong><span>{ontologyPackage.analysis_patterns.length} 个分析模式</span></div></header><div className="experience-grid">{ontologyPackage.questions.map((question) => <article key={question.id}><span>{question.status}</span><h3>{zhName(question)}</h3><p>{question.definition}</p><code>{question.id}</code></article>)}</div></section>;
}

type SourceUploadInput = {
  kind: StudioSourceKind;
  title: string;
  originalName: string;
  mediaType: string;
  body: Blob | string;
};

const sourceKindLabels: Record<StudioSourceKind, string> = {
  requirement_transcription: "需求文档（转写）",
  metric_transcription: "指标逻辑（转写）",
  data_model: "数据模型",
  data_dictionary: "Data Dictionary / Sample",
  sql: "现有 SQL",
  other: "其他材料",
};

type BatchFileDraft = {
  clientFileId: string;
  file: File;
  title: string;
  kinds: StudioSourceKind[];
};

function suggestedSourceKinds(file: File): StudioSourceKind[] {
  const name = file.name.toLocaleLowerCase();
  if (name.endsWith(".sql")) return ["sql"];
  if (/metric|indicator|kpi|指标|口径/.test(name)) return ["metric_transcription"];
  if (/requirement|需求|process|流程/.test(name)) return ["requirement_transcription"];
  if (/dictionary|字典|sample|样例/.test(name)) return ["data_dictionary"];
  if (/model|schema|模型/.test(name)) return ["data_model"];
  return ["other"];
}

function anticipatedCapability(file: File): { label: string; className: string } {
  const suffix = file.name.split(".").pop()?.toLocaleLowerCase() ?? "";
  if (suffix === "xlsx") return { label: "表格内容可提取", className: "is-ready" };
  if (["md", "txt", "csv", "json", "yaml", "yml", "sql"].includes(suffix)) {
    return { label: "文本内容可提取", className: "is-ready" };
  }
  return { label: "仅存档，不参与自动构建", className: "is-archive" };
}

function BatchSourceIntakeDrawer({
  open,
  busy,
  error,
  onClose,
  onSubmit,
}: {
  open: boolean;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (items: SourceIntakeBatchItemInput[], idempotencyKey: string) => Promise<SourceIntakeBatchReceipt>;
}) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [drafts, setDrafts] = useState<BatchFileDraft[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<SourceIntakeBatchReceipt | null>(null);
  const [confirmClosing, setConfirmClosing] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState(() => `browser-${crypto.randomUUID()}`);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const drawerRef = useDialogFocus<HTMLElement>(open, requestClose, returnFocusRef);
  const dirty = drafts.length > 0 && receipt === null;

  useEffect(() => {
    if (!open) return;
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }, [open]);

  function reset() {
    setStep(1);
    setDrafts([]);
    setReceipt(null);
    setLocalError(null);
    setConfirmClosing(false);
    setIdempotencyKey(`browser-${crypto.randomUUID()}`);
  }

  function closeNow() {
    reset();
    onClose();
  }

  function requestClose() {
    if (dirty) {
      setConfirmClosing(true);
      return;
    }
    closeNow();
  }

  function selectFiles(files: FileList | null) {
    if (!files) return;
    const incoming = Array.from(files);
    const combined = [...drafts, ...incoming.map((file, index) => ({
      clientFileId: `file-${drafts.length + index + 1}-${crypto.randomUUID()}`,
      file,
      title: file.name.replace(/\.[^.]+$/, ""),
      kinds: suggestedSourceKinds(file),
    }))];
    if (combined.length > 20) {
      setLocalError("每批最多选择 20 个文件。");
      return;
    }
    if (combined.some((item) => item.file.size === 0 || item.file.size > 20 * 1024 * 1024)) {
      setLocalError("文件不能为空，且每个文件不能超过 20 MB。");
      return;
    }
    if (combined.reduce((sum, item) => sum + item.file.size, 0) > 100 * 1024 * 1024) {
      setLocalError("单批文件总量不能超过 100 MB。");
      return;
    }
    setDrafts(combined);
    setLocalError(null);
  }

  function toggleKind(clientFileId: string, kind: StudioSourceKind) {
    setDrafts((current) => current.map((item) => {
      if (item.clientFileId !== clientFileId) return item;
      const kinds = item.kinds.includes(kind)
        ? item.kinds.filter((value) => value !== kind)
        : [...item.kinds, kind];
      return { ...item, kinds };
    }));
  }

  async function registerBatch() {
    if (!drafts.length || drafts.some((item) => !item.title.trim() || !item.kinds.length)) {
      setLocalError("每个文件都需要标题和至少一个用途。");
      return;
    }
    setLocalError(null);
    const result = await onSubmit(drafts.map((item) => ({
      clientFileId: item.clientFileId,
      file: item.file,
      registrations: item.kinds.map((kind) => ({
        kind,
        title: item.kinds.length > 1
          ? `${item.title.trim()} · ${sourceKindLabels[kind]}`
          : item.title.trim(),
      })),
    })), idempotencyKey);
    setReceipt(result);
    setStep(3);
  }

  if (!open) return null;
  return <div className="configuration-drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) requestClose(); }}>
    <aside ref={drawerRef} tabIndex={-1} className="configuration-drawer source-register-drawer source-batch-drawer" role="dialog" aria-modal="true" aria-labelledby="source-batch-title">
      <header><div><span>SOURCE INTAKE</span><h2 id="source-batch-title">登记来源材料</h2><p>一次选择多份文件，确认用途后统一登记。文件内容不会在这里被改写。</p></div><button type="button" aria-label="关闭材料登记" onClick={requestClose}>×</button></header>
      <ol className="source-intake-steps" aria-label="材料登记步骤"><li className={step === 1 ? "is-active" : step > 1 ? "is-complete" : ""}><b>1</b><span>选择文件</span></li><li className={step === 2 ? "is-active" : step > 2 ? "is-complete" : ""}><b>2</b><span>确认用途</span></li><li className={step === 3 ? "is-active" : ""}><b>3</b><span>登记结果</span></li></ol>
      {step === 1 ? <section className="source-batch-step">
        <div className="source-format-guidance"><h3>支持范围</h3><ul><li><strong>可用于自动构建：</strong>Markdown、TXT、CSV、JSON、YAML、SQL、XLSX</li><li><strong>仅存档：</strong>PDF、DOCX、图片及其他格式；本轮不会声称已读取其内容</li><li><strong>容量：</strong>最多 20 个文件，20 MB/文件，100 MB/批次</li></ul></div>
        <label className="source-batch-dropzone"><input type="file" multiple onChange={(event) => { selectFiles(event.target.files); event.currentTarget.value = ""; }} /><strong>选择或拖入文件</strong><span>可以一次多选；下一步再统一确认用途</span></label>
        {drafts.length ? <div className="source-batch-file-list">{drafts.map((item) => { const capability = anticipatedCapability(item.file); return <article key={item.clientFileId}><div><strong>{item.file.name}</strong><span>{(item.file.size / 1024).toFixed(1)} KB</span></div><em className={capability.className}>{capability.label}</em><button type="button" onClick={() => setDrafts((current) => current.filter((value) => value.clientFileId !== item.clientFileId))}>移除</button></article>; })}</div> : null}
      </section> : null}
      {step === 2 ? <section className="source-batch-step"><div className="source-batch-purpose-head"><div><h3>确认每份文件的用途</h3><p>系统按文件名给出建议。只有不准确的项需要调整；同一文件可以承担多个用途。</p></div><span>{drafts.length} 个物理文件</span></div><div className="source-purpose-list">{drafts.map((item) => { const capability = anticipatedCapability(item.file); return <article key={item.clientFileId}><header><div><strong>{item.file.name}</strong><span className={capability.className}>{capability.label}</span></div><input aria-label={`${item.file.name} 标题`} value={item.title} onChange={(event) => setDrafts((current) => current.map((value) => value.clientFileId === item.clientFileId ? { ...value, title: event.target.value } : value))} /></header><fieldset><legend>用途</legend>{Object.entries(sourceKindLabels).map(([value, label]) => <label key={value} className={item.kinds.includes(value as StudioSourceKind) ? "is-selected" : ""}><input type="checkbox" checked={item.kinds.includes(value as StudioSourceKind)} onChange={() => toggleKind(item.clientFileId, value as StudioSourceKind)} />{label}</label>)}</fieldset></article>; })}</div></section> : null}
      {step === 3 && receipt ? <section className="source-batch-step source-batch-result"><header><div><h3>材料登记完成</h3><p>{receipt.physical_files.length} 个文件已登记，生成 {receipt.registrations.length} 个逻辑来源版本。</p></div><strong className={receipt.failures.length ? "has-failures" : "is-success"}>{receipt.failures.length ? `${receipt.failures.length} 个文件需要处理` : "全部成功"}</strong></header><div>{drafts.map((item) => { const physical = receipt.physical_files.find((value) => value.client_file_id === item.clientFileId); const failure = receipt.failures.find((value) => value.client_file_id === item.clientFileId); const count = receipt.registrations.filter((value) => value.client_file_id === item.clientFileId).length; return <article key={item.clientFileId}><div><strong>{item.file.name}</strong><span>{physical ? `${count} 个来源版本` : failure?.detail}</span></div><em className={physical?.capability === "ARCHIVED_ONLY" ? "is-archive" : failure ? "has-failures" : "is-ready"}>{physical?.capability === "TEXT_EXTRACTED" ? "文本已提取" : physical?.capability === "XLSX_TABULAR_EXTRACTED" ? "表格已提取" : physical ? "仅存档" : "登记失败"}</em></article>; })}</div></section> : null}
      {localError || error ? <p className="source-upload-error" role="alert">{localError ?? error}</p> : null}
      <footer className="source-batch-actions"><span>{step === 1 ? `已选择 ${drafts.length} 个文件` : step === 2 ? `${drafts.reduce((sum, item) => sum + item.kinds.length, 0)} 个逻辑用途` : `批次 ${receipt?.batch_id.slice(-8) ?? ""}`}</span>{step === 1 ? <><button type="button" onClick={requestClose}>取消</button><button type="button" className="is-primary" disabled={!drafts.length} onClick={() => setStep(2)}>下一步：确认用途</button></> : step === 2 ? <><button type="button" onClick={() => setStep(1)}>返回</button><button type="button" className="is-primary" disabled={busy || drafts.some((item) => !item.kinds.length || !item.title.trim())} onClick={() => void registerBatch()}>{busy ? "正在登记…" : "登记全部材料"}</button></> : <button type="button" className="is-primary" onClick={closeNow}>完成</button>}</footer>
      {confirmClosing ? <div className="eix-inline-confirm" role="alertdialog" aria-modal="true" aria-labelledby="discard-source-title"><div><h3 id="discard-source-title">放弃本次材料登记？</h3><p>已选择的文件和用途尚未登记，关闭后需要重新选择。</p><footer><button type="button" onClick={() => setConfirmClosing(false)}>继续编辑</button><button type="button" className="is-danger" onClick={closeNow}>放弃并关闭</button></footer></div></div> : null}
    </aside>
  </div>;
}

export function SourceLibraryView({
  ontologyPackage,
  intake,
  library = null,
  busy = false,
  error = null,
  onUpload,
  onUploadBatch,
  onPreview,
  onInstallReferencePack,
  onImportInstalledSources,
  openIntakeOnLoad = false,
  readOnly = false,
}: {
  ontologyPackage: OntologyPackage;
  intake: Record<string, unknown>;
  library?: StudioSourceLibrary | null;
  busy?: boolean;
  error?: string | null;
  onUpload?: (input: SourceUploadInput) => Promise<void> | void;
  onUploadBatch?: (items: SourceIntakeBatchItemInput[], idempotencyKey: string) => Promise<SourceIntakeBatchReceipt>;
  onPreview?: (sourceVersionId: string) => Promise<StudioSourcePreview>;
  onInstallReferencePack?: () => Promise<void> | void;
  onImportInstalledSources?: () => Promise<void> | void;
  openIntakeOnLoad?: boolean;
  readOnly?: boolean;
}) {
  const assets = [
    ...(Array.isArray(intake.assets) ? intake.assets : []),
    ...(Array.isArray(intake.source_files) ? intake.source_files : []),
  ].filter((value): value is Record<string, unknown> => Boolean(value) && typeof value === "object");
  const [showForm, setShowForm] = useState(openIntakeOnLoad && !readOnly);
  const [kind, setKind] = useState<StudioSourceKind>("requirement_transcription");
  const [title, setTitle] = useState("需求与分析流程");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [preview, setPreview] = useState<StudioSourcePreview | null>(null);
  const [previewSourceVersionId, setPreviewSourceVersionId] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const registerReturnFocusRef = useRef<HTMLElement | null>(null);
  const previewReturnFocusRef = useRef<HTMLElement | null>(null);
  const current = library?.current ?? [];
  const currentSourceIds = new Set(current.map((item) => item.source_id));
  const referencePack = intake.reference_source_pack && typeof intake.reference_source_pack === "object"
    ? intake.reference_source_pack as Record<string, unknown>
    : null;
  const packRegistrations = referencePack && Array.isArray(referencePack.registrations)
    ? referencePack.registrations.filter((value): value is Record<string, unknown> => Boolean(value) && typeof value === "object")
    : [];
  const packSourceIds = packRegistrations.map((item) => String(item.source_id ?? "")).filter(Boolean);
  const packInstalled = packSourceIds.length > 0 && packSourceIds.every((sourceId) => currentSourceIds.has(sourceId));
  const packFileCount = referencePack && typeof referencePack.physical_file_count === "number"
    ? referencePack.physical_file_count
    : 0;
  const scenarioName = ontologyPackage.scenario.name.zh;
  const fallbackCount = assets.length || ontologyPackage.sources.length;
  const transcribed = kind === "requirement_transcription" || kind === "metric_transcription";
  const previewSource = library?.versions.find((item) => item.source_version_id === previewSourceVersionId)
    ?? current.find((item) => item.source_version_id === previewSourceVersionId)
    ?? null;
  const uploadDirty = showForm && (
    kind !== "requirement_transcription"
    || title !== "需求与分析流程"
    || Boolean(file)
    || Boolean(text.trim())
  );
  useDirtyNavigationGuard(uploadDirty);
  const registerDrawerRef = useDialogFocus<HTMLElement>(showForm && !onUploadBatch, closeSourceForm, registerReturnFocusRef);
  const previewDrawerRef = useDialogFocus<HTMLElement>(Boolean(previewSourceVersionId), closePreview, previewReturnFocusRef);

  function resetSourceForm() {
    setKind("requirement_transcription");
    setTitle("需求与分析流程");
    setFile(null);
    setText("");
    setLocalError(null);
  }

  function closeSourceForm() {
    if (!confirmDiscard(uploadDirty)) return;
    resetSourceForm();
    setShowForm(false);
  }

  function toggleSourceForm(trigger?: HTMLElement) {
    if (showForm) {
      closeSourceForm();
      return;
    }
    registerReturnFocusRef.current = trigger
      ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    setShowForm(true);
  }

  function changeSourceKind(next: StudioSourceKind) {
    if (!confirmDiscard(Boolean(file) || Boolean(text.trim()))) return;
    setKind(next);
    setTitle(sourceKindLabels[next]);
    setFile(null);
    setText("");
    setLocalError(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!onUpload) return;
    const body = file ?? text;
    if ((!file && !text.trim()) || !title.trim()) {
      setLocalError("请填写标题，并选择文件或粘贴转写内容。");
      return;
    }
    const originalName = file?.name ?? (kind === "metric_transcription" ? "metric-logic.md" : "requirements.md");
    const mediaType = file?.type || (transcribed ? "text/markdown" : "application/octet-stream");
    setLocalError(null);
    await onUpload({ kind, title: title.trim(), originalName, mediaType, body });
    resetSourceForm();
    setShowForm(false);
  }

  async function openPreview(sourceVersionId: string, trigger?: HTMLElement) {
    if (!onPreview) return;
    previewReturnFocusRef.current = trigger
      ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    setPreviewSourceVersionId(sourceVersionId);
    setPreview(null);
    setPreviewBusy(true);
    setPreviewError(null);
    try {
      setPreview(await onPreview(sourceVersionId));
    } catch (cause) {
      setPreviewError(cause instanceof Error ? cause.message : "材料预览失败。");
    } finally {
      setPreviewBusy(false);
    }
  }

  function closePreview() {
    setPreview(null);
    setPreviewError(null);
    setPreviewSourceVersionId(null);
  }

  return <section className="studio-object-page source-library-page">
    <header className="object-page-heading">
      <div><span>SOURCE LIBRARY</span><h2>来源材料与证据版本</h2><p>每次登记都会形成不可变的 exact version。当前版本用于构建，历史版本继续保留证据身份。</p></div>
      <div className="object-page-heading-side">
        <div className="object-page-counts"><strong>{current.length ? `${current.length} 个当前来源` : `${fallbackCount} 份安装材料`}</strong><span>{library?.versions.length ?? 0} 个可追溯版本</span></div>
        {!readOnly ? <div className="object-page-actions"><button type="button" className="is-primary" onClick={(event) => toggleSourceForm(event.currentTarget)}>{onUploadBatch ? "登记来源材料" : "登记材料版本"}</button></div> : null}
      </div>
    </header>
    <div className="page-authority-note"><strong>材料本身不可原地修改。</strong><span>要纠正或更新内容，请为同一逻辑来源登记新版本；系统会保留旧版本和校验摘要。</span></div>
    {!readOnly && !current.length && assets.length ? <section className="installed-source-versioning"><div><span>PREVIEW PREREQUISITE</span><h3>先把安装材料登记为可追溯版本</h3><p>当前 {assets.length} 份文件只存在于 Solution 安装包中。版本化会先校验包清单、文件大小和 SHA-256，再生成可预览、可引用的 exact source version；原文件不会被改写。</p></div><button type="button" className="is-primary" disabled={busy || !onImportInstalledSources} onClick={() => onImportInstalledSources?.()}>{busy ? "正在校验并登记…" : "版本化安装材料"}</button></section> : null}
    {referencePack ? <section className={`reference-source-pack${packInstalled ? " is-installed" : ""}`}><div><span>REFERENCE INPUT</span><h3>{scenarioName}参考材料包</h3><p>{readOnly ? "参考方案保留已登记材料及其精确身份。复制方案后可载入材料并重新构建。" : "将包内材料登记为可追溯的来源版本，供构建任务选择。"}</p></div><dl><div><dt>原始文件</dt><dd>{packFileCount} 份</dd></div><div><dt>逻辑来源</dt><dd>{packSourceIds.length} 个</dd></div><div><dt>状态</dt><dd>{packInstalled ? "已载入" : "尚未载入"}</dd></div></dl>{!readOnly ? <button type="button" disabled={busy || packInstalled || !onInstallReferencePack} onClick={() => onInstallReferencePack?.()}>{packInstalled ? "参考材料已载入" : "载入参考材料包"}</button> : null}</section> : null}
    {current.length ? <div className="source-library-table"><div className="source-library-head"><span>当前来源</span><span>类型</span><span>处理状态</span><span>版本</span></div>{current.map((source) => <button key={source.source_version_id} type="button" className="source-library-row" aria-label={`查看 ${source.title} 详情`} disabled={!onPreview || (previewBusy && previewSourceVersionId === source.source_version_id)} onClick={(event) => openPreview(source.source_version_id, event.currentTarget)}><span className="source-library-primary"><strong>{source.title}</strong><small>{source.original_name} · {(source.size_bytes / 1024).toFixed(1)} KB</small></span><span className="source-library-type">{sourceKindLabels[source.kind]}</span><em>{source.processing_mode === "TRANSCRIBED" ? "文本已解析" : source.processing_mode === "STRUCTURED_TRANSCRIPTION" ? "结构已解析" : "已登记，待解析"}</em><span className="source-library-version"><code title={source.content_checksum}>{source.content_checksum.slice(0, 12)}</code><b aria-hidden="true">→</b></span></button>)}</div> : <div className="source-library-table"><div className="source-library-head"><span>安装材料</span><span>类型</span><span>处理状态</span><span>版本身份</span></div>{assets.length ? assets.map((asset, index) => { const id = String(asset.asset_id ?? asset.file_id ?? `source-${index + 1}`); return <article key={id}><div><strong>{String(asset.title ?? asset.name ?? asset.locator ?? id)}</strong><small>{String(asset.locator ?? asset.original_name ?? id)}</small></div><span>{String(asset.kind ?? asset.media_type ?? "document")}</span><em>{String(asset.processing_mode ?? asset.status ?? "REGISTERED")}</em><code>{String(asset.checksum ?? asset.sha256 ?? "pending").slice(0, 12)}</code></article>; }) : ontologyPackage.sources.map((source) => <article key={source.id}><div><strong>{source.title}</strong><small>{source.locator}</small></div><span>{source.source_type}</span><em>REGISTERED</em><code>{source.id}</code></article>)}</div>}
    {library?.versions.length ? <section className="source-version-section"><header><div><span>VERSION HISTORY</span><h3>历史版本</h3></div><strong>{library.versions.length} 个版本</strong></header><div>{library.versions.map((source) => <article key={source.source_version_id}><div><strong>{source.title}</strong><small>{new Date(source.registered_at).toLocaleString("zh-CN")} · {source.original_name}</small></div><span>{sourceKindLabels[source.kind]}</span><code>{source.content_checksum.slice(0, 16)}</code><em>{source.is_current ? "当前" : "历史"}</em>{onPreview ? <button type="button" onClick={(event) => openPreview(source.source_version_id, event.currentTarget)}>查看</button> : null}</article>)}</div></section> : null}
    {!readOnly && onUploadBatch ? <BatchSourceIntakeDrawer open={showForm} busy={busy} error={error} onClose={() => setShowForm(false)} onSubmit={onUploadBatch} /> : null}
    {!readOnly && !onUploadBatch && showForm ? <div className="configuration-drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeSourceForm(); }}><aside ref={registerDrawerRef} tabIndex={-1} className="configuration-drawer source-register-drawer" role="dialog" aria-modal="true" aria-labelledby="source-register-title"><header><div><span>REGISTER EXACT SOURCE</span><h2 id="source-register-title">登记材料版本</h2><p>登记新材料，或为同一逻辑来源创建替代版本。旧版本不会被覆盖。</p></div><button type="button" aria-label="关闭材料登记" onClick={closeSourceForm}>×</button></header><form className="source-upload-panel" onSubmit={submit}><div className="source-upload-grid"><label>材料类型<select value={kind} onChange={(event) => changeSourceKind(event.target.value as StudioSourceKind)}>{Object.entries(sourceKindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>材料标题<input value={title} onChange={(event) => setTitle(event.target.value)} /></label><label className="source-file-field">选择文件<input type="file" accept={transcribed ? ".md,.txt,.xlsx,text/markdown,text/plain,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" : undefined} onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label></div>{transcribed ? <label className="source-text-field">或者直接粘贴转写内容<textarea value={text} disabled={Boolean(file)} onChange={(event) => setText(event.target.value)} placeholder="可粘贴 O-xx / M-xx Markdown 表格，或直接上传标准 Excel template。" /></label> : null}{localError || error ? <p className="source-upload-error" role="alert">{localError ?? error}</p> : null}<footer className="source-upload-actions"><span>{file ? `${file.name} · ${Math.ceil(file.size / 1024)} KB` : "尚未选择文件"}</span><button type="button" onClick={closeSourceForm}>取消</button><button type="submit" className="is-primary" disabled={busy || !title.trim() || (!file && !text.trim())}>{busy ? "登记中…" : "登记新版本"}</button></footer></form></aside></div> : null}
    {previewSourceVersionId ? <div className="configuration-drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closePreview(); }}><aside ref={previewDrawerRef} tabIndex={-1} className="configuration-drawer source-preview-drawer" role="dialog" aria-modal="true" aria-labelledby="source-preview-title"><header><div><span>EXACT SOURCE DETAIL</span><h2 id="source-preview-title">{previewSource?.title ?? "材料版本详情"}</h2><p>{previewSource ? `${previewSource.original_name} · ${sourceKindLabels[previewSource.kind]}` : "正在读取材料版本"}</p></div><button type="button" aria-label="关闭材料详情" onClick={closePreview}>×</button></header>{previewSource ? <dl className="source-version-metadata"><div><dt>版本身份</dt><dd>{previewSource.source_version_id}</dd></div><div><dt>登记时间</dt><dd>{new Date(previewSource.registered_at).toLocaleString("zh-CN")}</dd></div><div><dt>处理状态</dt><dd>{previewSource.processing_mode}</dd></div><div><dt>SHA-256</dt><dd>{previewSource.content_checksum}</dd></div></dl> : null}<section className="source-preview-content">{previewBusy ? <div className="drawer-loading"><strong>正在读取材料内容…</strong><span>校验 exact version 与预览结果</span></div> : null}{previewError ? <p className="source-upload-error" role="alert">{previewError}</p> : null}{preview?.limitation ? <p className="source-preview-limitation">{preview.limitation}</p> : null}{preview?.text_lines.length ? <div className="source-text-preview">{preview.text_lines.map((line) => <div key={line.line_number}><span>{line.line_number}</span><code>{line.text || " "}</code></div>)}</div> : null}{preview?.sheets.map((sheet) => <section key={sheet.sheet_name}><header><strong>{sheet.sheet_name}</strong><code>{sheet.used_range}{sheet.truncated ? " · preview truncated" : ""}</code></header><div className="source-sheet-preview"><div><b>Cell</b><b>Value</b><b>Raw formula</b></div>{sheet.cells.map((cell) => <article key={cell.cell}><code>{cell.cell}</code><span>{String(cell.display_value ?? "")}</span><code>{cell.raw_formula ?? "—"}</code></article>)}</div></section>)}</section></aside></div> : null}
  </section>;
}

type DataFieldDraft = {
  name: string;
  dataType: "string" | "integer" | "decimal" | "boolean" | "date" | "datetime";
  nullable: boolean;
  description: string;
  unit: string;
};

type DataTableDraft = {
  name: string;
  grain: string;
  primaryKeys: string;
  fields: DataFieldDraft[];
};

type DataSourceDraft = {
  id: string;
  version: string;
  nameZh: string;
  nameEn: string;
  definition: string;
  owner: string;
  evidenceSource: string;
  tables: DataTableDraft[];
};

const blankDataField = (): DataFieldDraft => ({
  name: "",
  dataType: "string",
  nullable: true,
  description: "",
  unit: "",
});

const blankDataTable = (): DataTableDraft => ({
  name: "",
  grain: "",
  primaryKeys: "",
  fields: [blankDataField()],
});

export function SchemaCatalogView({
  ontologyPackage,
  onApply,
  busy,
  error = null,
  readOnly = false,
}: {
  ontologyPackage: OntologyPackage;
  onApply: (operation: PackageDraftOperation) => Promise<void> | void;
  busy: boolean;
  error?: string | null;
  readOnly?: boolean;
}) {
  const [selectedSourceId, setSelectedSourceId] = useState(ontologyPackage.data_sources[0]?.id ?? "");
  const [selectedTableName, setSelectedTableName] = useState(ontologyPackage.data_sources[0]?.tables[0]?.name ?? "");
  const [editing, setEditing] = useState(false);
  const [confirmDeprecate, setConfirmDeprecate] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [draft, setDraft] = useState<DataSourceDraft>({
    id: "data_source.new",
    version: "1.0.0",
    nameZh: "",
    nameEn: "",
    definition: "",
    owner: ontologyPackage.scenario.owner,
    evidenceSource: "",
    tables: [blankDataTable()],
  });
  const [draftBaseline, setDraftBaseline] = useState("");
  const editorReturnFocusRef = useRef<HTMLElement | null>(null);
  const selectedSource = ontologyPackage.data_sources.find((source) => source.id === selectedSourceId) ?? ontologyPackage.data_sources[0];
  const selectedTable = selectedSource?.tables.find((table) => table.name === selectedTableName) ?? selectedSource?.tables[0];
  const fieldCount = ontologyPackage.data_sources.reduce((sum, source) => sum + source.tables.reduce((tableSum, table) => tableSum + table.fields.length, 0), 0);
  const draftDirty = editing && JSON.stringify(draft) !== draftBaseline;
  useDirtyNavigationGuard(draftDirty);
  const editorRef = useDialogFocus<HTMLElement>(editing, cancelEdit, editorReturnFocusRef);

  useEffect(() => {
    if (!selectedSource) return;
    if (!selectedSource.tables.some((table) => table.name === selectedTableName)) {
      setSelectedTableName(selectedSource.tables[0]?.name ?? "");
    }
  }, [selectedSource, selectedTableName]);

  function beginEdit(source?: OntologyPackage["data_sources"][number], trigger?: HTMLElement) {
    if (!confirmDiscard(draftDirty)) return;
    editorReturnFocusRef.current = trigger
      ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    const next: DataSourceDraft = {
      id: source?.id ?? "data_source.new",
      version: source?.version ?? "1.0.0",
      nameZh: source?.name.zh ?? "",
      nameEn: source?.name.en ?? "",
      definition: source?.definition ?? "",
      owner: source?.owner ?? ontologyPackage.scenario.owner,
      evidenceSource: source?.sources[0] ?? "",
      tables: source?.tables.map((table) => ({
        name: table.name,
        grain: table.grain,
        primaryKeys: table.primary_key.join(", "),
        fields: table.fields.map((field) => ({
          name: field.name,
          dataType: field.data_type,
          nullable: field.nullable,
          description: field.description,
          unit: field.unit ?? "",
        })),
      })) ?? [blankDataTable()],
    };
    setDraft(next);
    setDraftBaseline(JSON.stringify(next));
    setLocalError(null);
    setConfirmDeprecate(false);
    setEditing(true);
  }

  function cancelEdit() {
    if (confirmDiscard(draftDirty)) setEditing(false);
  }

  function updateTable(index: number, patch: Partial<DataTableDraft>) {
    setDraft((value) => ({
      ...value,
      tables: value.tables.map((table, tableIndex) => tableIndex === index ? { ...table, ...patch } : table),
    }));
  }

  function updateField(tableIndex: number, fieldIndex: number, patch: Partial<DataFieldDraft>) {
    setDraft((value) => ({
      ...value,
      tables: value.tables.map((table, currentTableIndex) => currentTableIndex === tableIndex
        ? { ...table, fields: table.fields.map((field, currentFieldIndex) => currentFieldIndex === fieldIndex ? { ...field, ...patch } : field) }
        : table),
    }));
  }

  function removeTable(index: number) {
    setDraft((value) => ({ ...value, tables: value.tables.filter((_, tableIndex) => tableIndex !== index) }));
  }

  function removeField(tableIndex: number, fieldIndex: number) {
    setDraft((value) => ({
      ...value,
      tables: value.tables.map((table, currentTableIndex) => currentTableIndex === tableIndex
        ? { ...table, fields: table.fields.filter((_, currentFieldIndex) => currentFieldIndex !== fieldIndex) }
        : table),
    }));
  }

  async function saveDataSource() {
    if (!draft.id.trim() || !draft.nameZh.trim() || !draft.nameEn.trim() || !draft.definition.trim()) {
      setLocalError("请完整填写数据源 ID、中英文名称与业务定义。");
      return;
    }
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(draft.id) || !/^\d+\.\d+\.\d+$/.test(draft.version)) {
      setLocalError("数据源 ID 或语义版本格式不正确。");
      return;
    }
    if (!draft.evidenceSource) {
      setLocalError("请选择一项来源证据，系统不会自动替你指定来源。");
      return;
    }
    if (!draft.tables.length) {
      setLocalError("数据源至少需要一个物理表合同。");
      return;
    }
    const tableNames = draft.tables.map((table) => table.name.trim());
    if (tableNames.some((name) => !name) || new Set(tableNames).size !== tableNames.length) {
      setLocalError("每个物理表都需要唯一且非空的表名。");
      return;
    }
    for (const table of draft.tables) {
      if (!table.grain.trim() || !table.fields.length) {
        setLocalError(`表 ${table.name || "（未命名）"} 需要声明粒度并至少包含一个字段。`);
        return;
      }
      const fieldNames = table.fields.map((field) => field.name.trim());
      if (fieldNames.some((name) => !name) || new Set(fieldNames).size !== fieldNames.length) {
        setLocalError(`表 ${table.name} 的字段名必须非空且唯一。`);
        return;
      }
      const primaryKeys = table.primaryKeys.split(",").map((item) => item.trim()).filter(Boolean);
      if (primaryKeys.some((key) => !fieldNames.includes(key))) {
        setLocalError(`表 ${table.name} 的主键只能引用已经定义的字段。`);
        return;
      }
    }
    const existing = ontologyPackage.data_sources.find((source) => source.id === draft.id);
    const tables = draft.tables.map((table) => ({
      name: table.name.trim(),
      grain: table.grain.trim(),
      primary_key: table.primaryKeys.split(",").map((item) => item.trim()).filter(Boolean),
      fields: table.fields.map((field) => ({
        name: field.name.trim(),
        data_type: field.dataType,
        nullable: field.nullable,
        description: field.description.trim(),
        unit: field.unit.trim() || null,
      })),
    }));
    setLocalError(null);
    try {
      await onApply({ action: "UPSERT", collection: "data_sources", object_id: draft.id, payload: {
        id: draft.id,
        version: draft.version,
        status: "proposed",
        name: { en: draft.nameEn.trim(), zh: draft.nameZh.trim() },
        definition: draft.definition.trim(),
        owner: draft.owner.trim() || ontologyPackage.scenario.owner,
        sources: [draft.evidenceSource],
        decisions: existing?.decisions ?? [],
        tags: [...new Set([...(existing?.tags ?? []), "studio-authored"])],
        protocol: "tabular/v1",
        tables,
      } });
      setSelectedSourceId(draft.id);
      setSelectedTableName(tables[0]?.name ?? "");
      setEditing(false);
    } catch { /* Keep the structured draft open; the parent renders the backend error. */ }
  }

  async function deprecateDataSource() {
    if (!selectedSource) return;
    try {
      await onApply({ action: "DEPRECATE", collection: "data_sources", object_id: selectedSource.id, payload: null });
      setConfirmDeprecate(false);
    } catch { /* Keep the impact confirmation visible. */ }
  }

  return <section className="studio-object-page data-catalog-page" aria-labelledby="schema-catalog-title">
    <header className="object-page-heading">
      <div><span>DATA CONTRACT CATALOG</span><h2 id="schema-catalog-title">数据源与 Schema</h2><p>按数据源、物理表和字段维护当前 Draft 的确定性数据合同；SQL 和样例是证据，不会替代这里的字段类型与粒度。</p></div>
      <div className="object-page-heading-side"><div className="object-page-counts"><strong>{ontologyPackage.data_sources.length} 个数据源</strong><span>{fieldCount} 个字段</span></div>{!readOnly ? <div className="object-page-actions">{selectedSource ? <button type="button" onClick={(event) => beginEdit(selectedSource, event.currentTarget)}>编辑当前数据源</button> : null}<button type="button" className="is-primary" onClick={(event) => beginEdit(undefined, event.currentTarget)}>新增数据源</button></div> : null}</div>
    </header>
    <div className="page-authority-note"><strong>浏览与编辑是两个明确状态。</strong><span>目录始终展示当前 Draft；编辑会打开结构化配置抽屉，保存后形成新的 Draft 修订。</span></div>
    {selectedSource ? <div className="schema-workspace">
      <aside className="schema-source-index"><header><span>DATA SOURCES</span><b>{ontologyPackage.data_sources.length}</b></header>{ontologyPackage.data_sources.map((source) => <button type="button" className={source.id === selectedSource.id ? "is-selected" : ""} key={source.id} onClick={() => setSelectedSourceId(source.id)}><strong>{zhName(source)}</strong><small>{source.tables.length} 张表 · {source.protocol}</small><code>{source.id}</code></button>)}</aside>
      <section className="schema-table-index"><header><div><span>PHYSICAL TABLES</span><h3>{zhName(selectedSource)}</h3></div>{!readOnly ? <button type="button" onClick={(event) => beginEdit(selectedSource, event.currentTarget)}>编辑合同</button> : null}</header>{selectedSource.tables.map((table) => <button type="button" className={table.name === selectedTable?.name ? "is-selected" : ""} key={table.name} onClick={() => setSelectedTableName(table.name)}><div><strong>{table.name}</strong><small>{table.grain}</small></div><span>{table.fields.length} 个字段</span></button>)}</section>
      <aside className="schema-field-inspector">{selectedTable ? <><span>SCHEMA DETAIL</span><h3>{selectedTable.name}</h3><dl><div><dt>粒度</dt><dd>{selectedTable.grain}</dd></div><div><dt>主键</dt><dd>{selectedTable.primary_key.join(", ") || "未声明"}</dd></div><div><dt>来源证据</dt><dd>{selectedSource.sources.join(", ")}</dd></div></dl><div className="schema-field-table"><div><span>字段</span><span>类型</span><span>约束</span></div>{selectedTable.fields.map((field) => <article key={field.name}><code>{field.name}</code><span>{field.data_type}{field.unit ? ` · ${field.unit}` : ""}</span><em>{field.nullable ? "可为空" : "必填"}</em><p>{field.description || "尚无字段说明"}</p></article>)}</div>{!readOnly ? <div className="inspector-actions"><button type="button" className="is-primary" onClick={(event) => beginEdit(selectedSource, event.currentTarget)}>编辑数据源合同</button><button type="button" className="is-danger" onClick={() => setConfirmDeprecate(true)}>弃用数据源</button></div> : null}{!readOnly && confirmDeprecate ? <div className="data-deprecate-confirm"><strong>先检查下游依赖</strong><p>字段映射、关系和指标查询仍引用该数据源时，后端会拒绝弃用。</p><div><button type="button" onClick={() => setConfirmDeprecate(false)}>返回</button><button type="button" className="is-danger" disabled={busy} onClick={() => void deprecateDataSource()}>检查并弃用</button></div></div> : null}{error ? <p className="operator-error" role="alert">{error}</p> : null}</> : <div className="data-empty-state"><h3>没有物理表</h3><p>当前数据源还没有物理表合同。</p>{!readOnly ? <button type="button" onClick={(event) => beginEdit(selectedSource, event.currentTarget)}>编辑数据源</button> : null}</div>}</aside>
    </div> : <div className="data-empty-state"><span>NO DATA SOURCE</span><h3>当前 Draft 尚无数据源合同</h3><p>{readOnly ? "该参考方案没有登记数据源合同。" : "新增数据源，并为它明确指定来源证据、表粒度与字段。"}</p>{!readOnly ? <button type="button" className="is-primary" onClick={(event) => beginEdit(undefined, event.currentTarget)}>新增第一个数据源</button> : null}</div>}
    {!readOnly && editing ? <div className="configuration-drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) cancelEdit(); }}><aside ref={editorRef} tabIndex={-1} className="configuration-drawer data-source-editor-drawer" role="dialog" aria-modal="true" aria-labelledby="data-source-editor-title"><header><div><span>DATA SOURCE EDITOR</span><h2 id="data-source-editor-title">{ontologyPackage.data_sources.some((source) => source.id === draft.id) ? "创建数据源修订" : "新增数据源"}</h2><p>按表和字段维护 typed contract；保存只进入 Proposed Draft，不会直接发布。</p></div><button type="button" aria-label="关闭数据源编辑器" onClick={cancelEdit}>×</button></header><form className="structured-data-editor" onSubmit={(event) => { event.preventDefault(); void saveDataSource(); }}>
      <section className="structured-editor-section"><header><div><span>01</span><h3>数据源基本信息</h3></div></header><div className="structured-editor-grid"><label>Data Source ID<input required disabled={ontologyPackage.data_sources.some((source) => source.id === draft.id)} value={draft.id} onChange={(event) => setDraft((value) => ({ ...value, id: event.target.value }))} /></label><label>语义版本<input required value={draft.version} onChange={(event) => setDraft((value) => ({ ...value, version: event.target.value }))} /></label><label>中文名称<input required value={draft.nameZh} onChange={(event) => setDraft((value) => ({ ...value, nameZh: event.target.value }))} /></label><label>英文名称<input required value={draft.nameEn} onChange={(event) => setDraft((value) => ({ ...value, nameEn: event.target.value }))} /></label><label>责任人<input required value={draft.owner} onChange={(event) => setDraft((value) => ({ ...value, owner: event.target.value }))} /></label><label>来源证据<select required value={draft.evidenceSource} onChange={(event) => setDraft((value) => ({ ...value, evidenceSource: event.target.value }))}><option value="">请选择，不自动填充</option>{ontologyPackage.sources.map((source) => <option key={source.id} value={source.id}>{source.title} · {source.id}</option>)}</select></label><label className="is-full">业务定义<textarea required rows={3} value={draft.definition} onChange={(event) => setDraft((value) => ({ ...value, definition: event.target.value }))} /></label></div></section>
      <section className="structured-editor-section table-contract-builder"><header><div><span>02</span><h3>物理表与字段合同</h3></div><button type="button" onClick={() => setDraft((value) => ({ ...value, tables: [...value.tables, blankDataTable()] }))}>新增物理表</button></header>{draft.tables.map((table, tableIndex) => <article className="table-contract-card" key={`table-${tableIndex}`}><header><div><strong>表 {tableIndex + 1}</strong><span>{table.name || "尚未命名"}</span></div><button type="button" className="is-danger-quiet" disabled={draft.tables.length === 1} onClick={() => removeTable(tableIndex)}>移除表</button></header><div className="structured-editor-grid"><label>物理表名<input required value={table.name} onChange={(event) => updateTable(tableIndex, { name: event.target.value })} /></label><label>记录粒度<input required value={table.grain} onChange={(event) => updateTable(tableIndex, { grain: event.target.value })} placeholder="例如：one trade activity event" /></label><label className="is-full">主键字段<input value={table.primaryKeys} onChange={(event) => updateTable(tableIndex, { primaryKeys: event.target.value })} placeholder="多个字段用英文逗号分隔" /></label></div><div className="field-contract-builder"><header><strong>字段</strong><button type="button" onClick={() => updateTable(tableIndex, { fields: [...table.fields, blankDataField()] })}>新增字段</button></header>{table.fields.map((field, fieldIndex) => <div className="field-contract-row" key={`field-${fieldIndex}`}><label>字段名<input required value={field.name} onChange={(event) => updateField(tableIndex, fieldIndex, { name: event.target.value })} /></label><label>数据类型<select value={field.dataType} onChange={(event) => updateField(tableIndex, fieldIndex, { dataType: event.target.value as DataFieldDraft["dataType"] })}><option value="string">string</option><option value="integer">integer</option><option value="decimal">decimal</option><option value="boolean">boolean</option><option value="date">date</option><option value="datetime">datetime</option></select></label><label>单位<input value={field.unit} onChange={(event) => updateField(tableIndex, fieldIndex, { unit: event.target.value })} placeholder="可选" /></label><label className="is-description">字段说明<input value={field.description} onChange={(event) => updateField(tableIndex, fieldIndex, { description: event.target.value })} /></label><label className="field-nullability"><input type="checkbox" checked={field.nullable} onChange={(event) => updateField(tableIndex, fieldIndex, { nullable: event.target.checked })} /><span>允许为空</span></label><button type="button" className="is-danger-quiet" aria-label={`移除 ${field.name || `字段 ${fieldIndex + 1}`}`} disabled={table.fields.length === 1} onClick={() => removeField(tableIndex, fieldIndex)}>移除</button></div>)}</div></article>)}</section>
      {localError || error ? <p className="operator-error structured-editor-error" role="alert">{localError ?? error}</p> : null}<footer className="configuration-drawer-actions"><span>{draftDirty ? "有尚未保存的修改" : "尚未修改"}</span><button type="button" onClick={cancelEdit}>取消</button><button type="submit" className="is-primary" disabled={busy || !draftDirty}>{busy ? "保存中…" : "保存数据源草稿"}</button></footer>
    </form></aside></div> : null}
  </section>;
}

type SqlInputDraft = { source: string; table: string; alias: string };
type SqlParameterDraft = {
  name: string;
  dataType: "string" | "integer" | "decimal" | "boolean" | "date" | "datetime";
  required: boolean;
  description: string;
};
type SqlContractDraft = {
  id: string;
  version: string;
  nameZh: string;
  nameEn: string;
  definition: string;
  owner: string;
  statementSource: string;
  statementLocator: string;
  dialect: "ansi" | "postgresql" | "duckdb" | "bigquery" | "snowflake" | "spark" | "other";
  executionMode: "reference_only" | "validated_query" | "runtime_tool";
  inputs: SqlInputDraft[];
  outputFields: string;
  implements: string;
  parameters: SqlParameterDraft[];
};

function blankSqlContract(ontologyPackage: OntologyPackage): SqlContractDraft {
  return {
    id: "sql.new",
    version: "1.0.0",
    nameZh: "",
    nameEn: "",
    definition: "",
    owner: ontologyPackage.actors[0]?.id ?? ontologyPackage.scenario.owner,
    statementSource: "",
    statementLocator: "",
    dialect: "ansi",
    executionMode: "reference_only",
    inputs: [],
    outputFields: "",
    implements: "",
    parameters: [],
  };
}

function sqlContractDraft(
  ontologyPackage: OntologyPackage,
  contract?: OntologyPackage["sql_contracts"][number],
): SqlContractDraft {
  if (!contract) return blankSqlContract(ontologyPackage);
  return {
    id: contract.id,
    version: contract.version,
    nameZh: contract.name.zh,
    nameEn: contract.name.en,
    definition: contract.definition,
    owner: contract.owner,
    statementSource: contract.statement_source,
    statementLocator: contract.statement_locator,
    dialect: contract.dialect,
    executionMode: contract.execution_mode,
    inputs: contract.inputs.map((input) => ({ source: input.source, table: input.table, alias: input.alias ?? "" })),
    outputFields: contract.output_fields.join("\n"),
    implements: contract.implements.join("\n"),
    parameters: contract.parameters.map((parameter) => ({
      name: parameter.name,
      dataType: parameter.data_type,
      required: parameter.required,
      description: parameter.description,
    })),
  };
}

export function SqlContractCatalogView({
  ontologyPackage,
  onApply,
  busy,
  error = null,
  readOnly = false,
}: {
  ontologyPackage: OntologyPackage;
  onApply: (operation: PackageDraftOperation) => Promise<void> | void;
  busy: boolean;
  error?: string | null;
  readOnly?: boolean;
}) {
  const [selectedId, setSelectedId] = useState(ontologyPackage.sql_contracts[0]?.id ?? "");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<SqlContractDraft>(() => blankSqlContract(ontologyPackage));
  const [baseline, setBaseline] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [confirmDeprecate, setConfirmDeprecate] = useState(false);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const selected = ontologyPackage.sql_contracts.find((contract) => contract.id === selectedId)
    ?? ontologyPackage.sql_contracts[0];
  const dirty = editing && JSON.stringify(draft) !== baseline;
  useDirtyNavigationGuard(dirty);
  const editorRef = useDialogFocus<HTMLElement>(editing, closeEditor, returnFocusRef);

  function openEditor(contract?: OntologyPackage["sql_contracts"][number], trigger?: HTMLElement) {
    if (!confirmDiscard(dirty)) return;
    returnFocusRef.current = trigger ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    const next = sqlContractDraft(ontologyPackage, contract);
    setDraft(next);
    setBaseline(JSON.stringify(next));
    setLocalError(null);
    setConfirmDeprecate(false);
    setEditing(true);
  }

  function closeEditor() {
    if (confirmDiscard(dirty)) setEditing(false);
  }

  function updateInput(index: number, patch: Partial<SqlInputDraft>) {
    setDraft((current) => ({
      ...current,
      inputs: current.inputs.map((input, currentIndex) => currentIndex === index ? { ...input, ...patch } : input),
    }));
  }

  function updateParameter(index: number, patch: Partial<SqlParameterDraft>) {
    setDraft((current) => ({
      ...current,
      parameters: current.parameters.map((parameter, currentIndex) => currentIndex === index ? { ...parameter, ...patch } : parameter),
    }));
  }

  async function saveContract() {
    const outputFields = draft.outputFields.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean);
    const implementsAssets = draft.implements.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean);
    if (!draft.id.trim() || !draft.nameZh.trim() || !draft.nameEn.trim() || !draft.definition.trim()) {
      setLocalError("请完整填写 SQL 合同 ID、中英文名称与业务定义。"); return;
    }
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(draft.id) || !/^\d+\.\d+\.\d+$/.test(draft.version)) {
      setLocalError("SQL 合同 ID 或语义版本格式不正确。"); return;
    }
    if (!draft.statementSource || !draft.statementLocator.trim()) {
      setLocalError("请选择 SQL 原文的 exact source，并填写可定位到具体语句的锚点。"); return;
    }
    const relationKeys = draft.inputs.map((input) => `${input.source}:${input.table}`);
    if (draft.inputs.some((input) => !input.source || !input.table) || new Set(relationKeys).size !== relationKeys.length) {
      setLocalError("每个输入关系必须指向唯一的数据源与物理表。"); return;
    }
    const parameterNames = draft.parameters.map((parameter) => parameter.name.trim());
    if (parameterNames.some((name) => !name) || new Set(parameterNames).size !== parameterNames.length) {
      setLocalError("SQL 参数名必须非空且唯一。"); return;
    }
    if (draft.executionMode !== "reference_only" && (!draft.inputs.length || !outputFields.length || !implementsAssets.length)) {
      setLocalError("可验证或可执行的 SQL 合同必须声明输入、输出字段和实现的治理资产。"); return;
    }
    const existing = ontologyPackage.sql_contracts.find((contract) => contract.id === draft.id);
    setLocalError(null);
    try {
      await onApply({ action: "UPSERT", collection: "sql_contracts", object_id: draft.id, payload: {
        id: draft.id.trim(), version: draft.version, status: "proposed",
        name: { zh: draft.nameZh.trim(), en: draft.nameEn.trim() }, definition: draft.definition.trim(),
        owner: draft.owner.trim() || ontologyPackage.scenario.owner,
        sources: [draft.statementSource], decisions: existing?.decisions ?? [],
        tags: [...new Set([...(existing?.tags ?? []), "studio-authored"])],
        dialect: draft.dialect, statement_source: draft.statementSource,
        statement_locator: draft.statementLocator.trim(),
        inputs: draft.inputs.map((input) => ({ source: input.source, table: input.table, alias: input.alias.trim() || null })),
        output_fields: outputFields, implements: implementsAssets,
        parameters: draft.parameters.map((parameter) => ({ name: parameter.name.trim(), data_type: parameter.dataType, required: parameter.required, description: parameter.description.trim() })),
        execution_mode: draft.executionMode, read_only: true,
      } });
      setSelectedId(draft.id);
      setEditing(false);
    } catch { /* Parent mutation preserves and displays the exact backend error. */ }
  }

  async function deprecateContract() {
    if (!selected) return;
    try {
      await onApply({ action: "DEPRECATE", collection: "sql_contracts", object_id: selected.id, payload: null });
      setConfirmDeprecate(false);
    } catch { /* Keep the confirmation open on a rejected operation. */ }
  }

  const implementedOptions = [
    ...ontologyPackage.metrics.map((asset) => ({ id: asset.id, label: asset.name.zh })),
    ...ontologyPackage.rules.map((asset) => ({ id: asset.id, label: asset.name.zh })),
    ...ontologyPackage.analysis_patterns.map((asset) => ({ id: asset.id, label: asset.name.zh })),
  ];
  return <section className="studio-object-page sql-contract-page" aria-labelledby="sql-contract-title">
    <header className="object-page-heading"><div><span>SQL CONTRACT CATALOG</span><h2 id="sql-contract-title">SQL 合同</h2><p>登记 SQL 原文的证据位置、输入输出与治理责任；Ontology 保存合同，不复制或改写 SQL 正文。</p></div><div className="object-page-heading-side"><div className="object-page-counts"><strong>{ontologyPackage.sql_contracts.length} 个 SQL 合同</strong><span>{ontologyPackage.sql_contracts.filter((item) => item.execution_mode !== "reference_only").length} 个可验证或运行</span></div>{!readOnly ? <div className="object-page-actions">{selected ? <button type="button" onClick={(event) => openEditor(selected, event.currentTarget)}>编辑当前合同</button> : null}<button type="button" className="is-primary" onClick={(event) => openEditor(undefined, event.currentTarget)}>新增 SQL 合同</button></div> : null}</div></header>
    <div className="page-authority-note"><strong>SQL 不是业务真相本身。</strong><span>合同必须明确它读取什么、产出什么、实现哪些指标或规则；运行前仍需确定性验证。</span></div>
    {selected ? <div className="sql-contract-layout"><section className="sql-contract-list"><header><span>合同</span><span>模式</span><span>状态</span></header>{ontologyPackage.sql_contracts.map((contract) => <button type="button" className={contract.id === selected.id ? "is-selected" : ""} key={contract.id} onClick={() => { setSelectedId(contract.id); setConfirmDeprecate(false); }}><span><strong>{contract.name.zh || contract.name.en}</strong><small>{contract.id}</small></span><code>{contract.execution_mode}</code><em>{contract.status}</em></button>)}</section><aside className="sql-contract-inspector"><span>SQL CONTRACT DETAIL</span><h3>{selected.name.zh || selected.name.en}</h3><p>{selected.definition}</p><dl><div><dt>语句证据</dt><dd>{selected.statement_source} · {selected.statement_locator}</dd></div><div><dt>方言 / 模式</dt><dd>{selected.dialect} · {selected.execution_mode}</dd></div><div><dt>输入</dt><dd>{selected.inputs.map((input) => `${input.source}.${input.table}`).join(" · ") || "无"}</dd></div><div><dt>实现资产</dt><dd>{selected.implements.join(" · ") || "仅作参考"}</dd></div><div><dt>输出字段</dt><dd>{selected.output_fields.join(" · ") || "未声明"}</dd></div></dl>{!readOnly ? <div className="inspector-actions"><button type="button" className="is-primary" onClick={(event) => openEditor(selected, event.currentTarget)}>创建修订</button><button type="button" className="is-danger" onClick={() => setConfirmDeprecate(true)}>弃用</button></div> : null}{!readOnly && confirmDeprecate ? <div className="data-deprecate-confirm"><strong>检查下游依赖后弃用</strong><p>仍被指标、规则或运行工具引用时，后端会拒绝操作。</p><div><button type="button" onClick={() => setConfirmDeprecate(false)}>返回</button><button type="button" className="is-danger" disabled={busy} onClick={() => void deprecateContract()}>检查并弃用</button></div></div> : null}{error ? <p className="operator-error" role="alert">{error}</p> : null}</aside></div> : <div className="data-empty-state"><span>NO SQL CONTRACT</span><h3>当前 Draft 尚无 SQL 合同</h3><p>{readOnly ? "该参考方案没有登记 SQL 合同。" : "如果材料中包含现有 SQL，请登记证据位置和它承担的计算责任。"}</p>{!readOnly ? <button type="button" className="is-primary" onClick={(event) => openEditor(undefined, event.currentTarget)}>新增第一个 SQL 合同</button> : null}</div>}
    {!readOnly && editing ? <div className="configuration-drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeEditor(); }}><aside ref={editorRef} tabIndex={-1} className="configuration-drawer sql-contract-editor-drawer" role="dialog" aria-modal="true" aria-labelledby="sql-contract-editor-title"><header><div><span>SQL CONTRACT EDITOR</span><h2 id="sql-contract-editor-title">{ontologyPackage.sql_contracts.some((item) => item.id === draft.id) ? "创建 SQL 合同修订" : "新增 SQL 合同"}</h2><p>维护证据锚点和执行合同，不在这里编辑 SQL 正文。</p></div><button type="button" aria-label="关闭 SQL 合同编辑器" onClick={closeEditor}>×</button></header><form className="structured-data-editor" onSubmit={(event) => { event.preventDefault(); void saveContract(); }}>
      <section className="structured-editor-section"><header><div><span>01</span><h3>身份与证据</h3></div></header><div className="structured-editor-grid"><label>SQL Contract ID<input required disabled={ontologyPackage.sql_contracts.some((item) => item.id === draft.id)} value={draft.id} onChange={(event) => setDraft((current) => ({ ...current, id: event.target.value }))} /></label><label>语义版本<input required value={draft.version} onChange={(event) => setDraft((current) => ({ ...current, version: event.target.value }))} /></label><label>中文名称<input required value={draft.nameZh} onChange={(event) => setDraft((current) => ({ ...current, nameZh: event.target.value }))} /></label><label>英文名称<input required value={draft.nameEn} onChange={(event) => setDraft((current) => ({ ...current, nameEn: event.target.value }))} /></label><label>责任人<input required value={draft.owner} onChange={(event) => setDraft((current) => ({ ...current, owner: event.target.value }))} /></label><label>SQL 原文来源<select required value={draft.statementSource} onChange={(event) => setDraft((current) => ({ ...current, statementSource: event.target.value }))}><option value="">请选择 exact source</option>{ontologyPackage.sources.map((source) => <option key={source.id} value={source.id}>{source.title} · {source.id}</option>)}</select></label><label className="is-full">业务定义<textarea required rows={3} value={draft.definition} onChange={(event) => setDraft((current) => ({ ...current, definition: event.target.value }))} /></label><label className="is-full">语句定位锚点<input required value={draft.statementLocator} onChange={(event) => setDraft((current) => ({ ...current, statementLocator: event.target.value }))} placeholder="例如 file.sql#L18-L64 或 statement:daily_turnover" /></label></div></section>
      <section className="structured-editor-section"><header><div><span>02</span><h3>执行责任</h3></div></header><div className="structured-editor-grid"><label>SQL 方言<select value={draft.dialect} onChange={(event) => setDraft((current) => ({ ...current, dialect: event.target.value as SqlContractDraft["dialect"] }))}>{["ansi", "postgresql", "duckdb", "bigquery", "snowflake", "spark", "other"].map((value) => <option key={value}>{value}</option>)}</select></label><label>执行模式<select value={draft.executionMode} onChange={(event) => setDraft((current) => ({ ...current, executionMode: event.target.value as SqlContractDraft["executionMode"] }))}><option value="reference_only">仅参考</option><option value="validated_query">已验证查询</option><option value="runtime_tool">运行工具</option></select></label><label className="is-full">输出字段（每行一个）<textarea rows={4} value={draft.outputFields} onChange={(event) => setDraft((current) => ({ ...current, outputFields: event.target.value }))} /></label><fieldset className="is-full contract-checkboxes"><legend>实现的治理资产</legend>{implementedOptions.length ? implementedOptions.map((asset) => { const selectedAssets = draft.implements.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean); return <label key={asset.id}><input type="checkbox" checked={selectedAssets.includes(asset.id)} onChange={() => setDraft((current) => ({ ...current, implements: (selectedAssets.includes(asset.id) ? selectedAssets.filter((id) => id !== asset.id) : [...selectedAssets, asset.id]).join("\n") }))} /><span>{asset.label}</span><code>{asset.id}</code></label>; }) : <p>先创建指标、规则或分析模式，再建立执行责任。</p>}</fieldset></div></section>
      <section className="structured-editor-section repeatable-contract-section"><header><div><span>03</span><h3>输入关系</h3></div><button type="button" onClick={() => setDraft((current) => ({ ...current, inputs: [...current.inputs, { source: ontologyPackage.data_sources[0]?.id ?? "", table: ontologyPackage.data_sources[0]?.tables[0]?.name ?? "", alias: "" }] }))}>新增输入</button></header>{draft.inputs.map((input, index) => { const source = ontologyPackage.data_sources.find((item) => item.id === input.source); return <div className="repeatable-contract-row" key={`sql-input-${index}`}><label>数据源<select required value={input.source} onChange={(event) => { const nextSource = ontologyPackage.data_sources.find((item) => item.id === event.target.value); updateInput(index, { source: event.target.value, table: nextSource?.tables[0]?.name ?? "" }); }}><option value="">请选择</option>{ontologyPackage.data_sources.map((item) => <option key={item.id} value={item.id}>{item.name.zh} · {item.id}</option>)}</select></label><label>物理表<select required value={input.table} onChange={(event) => updateInput(index, { table: event.target.value })}><option value="">请选择</option>{source?.tables.map((table) => <option key={table.name}>{table.name}</option>)}</select></label><label>别名<input value={input.alias} onChange={(event) => updateInput(index, { alias: event.target.value })} /></label><button type="button" className="is-danger-quiet" onClick={() => setDraft((current) => ({ ...current, inputs: current.inputs.filter((_, currentIndex) => currentIndex !== index) }))}>移除</button></div>; })}</section>
      <section className="structured-editor-section repeatable-contract-section"><header><div><span>04</span><h3>参数</h3></div><button type="button" onClick={() => setDraft((current) => ({ ...current, parameters: [...current.parameters, { name: "", dataType: "string", required: true, description: "" }] }))}>新增参数</button></header>{draft.parameters.map((parameter, index) => <div className="repeatable-contract-row is-parameter" key={`sql-param-${index}`}><label>参数名<input required value={parameter.name} onChange={(event) => updateParameter(index, { name: event.target.value })} /></label><label>类型<select value={parameter.dataType} onChange={(event) => updateParameter(index, { dataType: event.target.value as SqlParameterDraft["dataType"] })}>{["string", "integer", "decimal", "boolean", "date", "datetime"].map((value) => <option key={value}>{value}</option>)}</select></label><label>说明<input value={parameter.description} onChange={(event) => updateParameter(index, { description: event.target.value })} /></label><label className="field-nullability"><input type="checkbox" checked={parameter.required} onChange={(event) => updateParameter(index, { required: event.target.checked })} /><span>必填</span></label><button type="button" className="is-danger-quiet" onClick={() => setDraft((current) => ({ ...current, parameters: current.parameters.filter((_, currentIndex) => currentIndex !== index) }))}>移除</button></div>)}</section>
      {localError || error ? <p className="operator-error structured-editor-error" role="alert">{localError ?? error}</p> : null}<footer className="configuration-drawer-actions"><span>{dirty ? "有尚未保存的修改" : "尚未修改"}</span><button type="button" onClick={closeEditor}>取消</button><button type="submit" className="is-primary" disabled={busy || !dirty}>{busy ? "保存中…" : "保存 SQL 合同草稿"}</button></footer>
    </form></aside></div> : null}
  </section>;
}

type BindingDraft = {
  id: string;
  logicalTarget: string;
  source: string;
  table: string;
  column: string;
  dataType: "string" | "integer" | "decimal" | "boolean" | "date" | "datetime";
  unit: string;
  transformation: string;
  evidenceSource: string;
};

type JoinDraft = {
  id: string;
  version: string;
  nameZh: string;
  nameEn: string;
  definition: string;
  evidenceSource: string;
  leftSource: string;
  leftTable: string;
  rightSource: string;
  rightTable: string;
  keys: string;
  expectedCardinality: "1:1" | "N:1";
  fanoutPolicy: "block" | "deduplicate_reviewed";
};

export function MappingWorkbenchView({
  ontologyPackage,
  onApply,
  busy,
  error = null,
  readOnly = false,
}: {
  ontologyPackage: OntologyPackage;
  onApply: (operation: PackageDraftOperation) => Promise<void> | void;
  busy: boolean;
  error?: string | null;
  readOnly?: boolean;
}) {
  const first = ontologyPackage.bindings[0];
  const [selectedId, setSelectedId] = useState(first?.id ?? "");
  const [editing, setEditingState] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [confirmBindingDeprecate, setConfirmBindingDeprecate] = useState(false);
  const [joinEditing, setJoinEditingState] = useState(false);
  const [selectedJoinId, setSelectedJoinId] = useState(ontologyPackage.joins[0]?.id ?? "");
  const [confirmJoinDeprecate, setConfirmJoinDeprecate] = useState(false);
  const [draft, setDraft] = useState<BindingDraft>(() => ({
    id: first?.id ?? "binding.new",
    logicalTarget: first?.logical_target ?? ontologyPackage.properties[0]?.id ?? "",
    source: first?.source ?? ontologyPackage.data_sources[0]?.id ?? "",
    table: first?.table ?? ontologyPackage.data_sources[0]?.tables[0]?.name ?? "",
    column: first?.column ?? ontologyPackage.data_sources[0]?.tables[0]?.fields[0]?.name ?? "",
    dataType: first?.data_type ?? "string",
    unit: first?.unit ?? "",
    transformation: first?.transformation ?? "identity",
    evidenceSource: first?.sources[0] ?? "",
  }));
  const [joinDraft, setJoinDraft] = useState<JoinDraft>(() => ({
    id: ontologyPackage.joins[0]?.id ?? "join.new",
    version: ontologyPackage.joins[0]?.version ?? "1.0.0",
    nameZh: ontologyPackage.joins[0]?.name.zh ?? "",
    nameEn: ontologyPackage.joins[0]?.name.en ?? "",
    definition: ontologyPackage.joins[0]?.definition ?? "",
    evidenceSource: ontologyPackage.joins[0]?.sources[0] ?? "",
    leftSource: ontologyPackage.joins[0]?.left_source ?? ontologyPackage.data_sources[0]?.id ?? "",
    leftTable: ontologyPackage.joins[0]?.left_table ?? ontologyPackage.data_sources[0]?.tables[0]?.name ?? "",
    rightSource: ontologyPackage.joins[0]?.right_source ?? ontologyPackage.data_sources[0]?.id ?? "",
    rightTable: ontologyPackage.joins[0]?.right_table ?? ontologyPackage.data_sources[0]?.tables[0]?.name ?? "",
    keys: ontologyPackage.joins[0]?.keys.map((key) => `${key.left_column} = ${key.right_column}`).join("\n") ?? "",
    expectedCardinality: ontologyPackage.joins[0]?.expected_cardinality ?? "N:1",
    fanoutPolicy: ontologyPackage.joins[0]?.fanout_policy ?? "block",
  }));
  const [bindingBaseline, setBindingBaseline] = useState(() => JSON.stringify(draft));
  const [joinBaseline, setJoinBaseline] = useState(() => JSON.stringify(joinDraft));
  const bindingDirty = editing && JSON.stringify(draft) !== bindingBaseline;
  const joinDirty = joinEditing && JSON.stringify(joinDraft) !== joinBaseline;
  const editorDirty = bindingDirty || joinDirty;
  useDirtyNavigationGuard(editorDirty);
  const setEditing = (value: boolean) => {
    if (!value && !confirmDiscard(bindingDirty)) return;
    setEditingState(value);
  };
  const setJoinEditing = (value: boolean) => {
    if (!value && !confirmDiscard(joinDirty)) return;
    setJoinEditingState(value);
  };
  const selected = ontologyPackage.bindings.find((binding) => binding.id === selectedId) ?? ontologyPackage.bindings[0];
  const selectedDataSource = ontologyPackage.data_sources.find((source) => source.id === draft.source);
  const availableTable = selectedDataSource?.tables.find((table) => table.name === draft.table) ?? selectedDataSource?.tables[0];
  const selectedJoin = ontologyPackage.joins.find((join) => join.id === selectedJoinId) ?? ontologyPackage.joins[0];
  const leftJoinSource = ontologyPackage.data_sources.find((source) => source.id === joinDraft.leftSource);
  const rightJoinSource = ontologyPackage.data_sources.find((source) => source.id === joinDraft.rightSource);

  function beginEdit(binding = selected) {
    if (!confirmDiscard(editorDirty)) return;
    const next = {
      id: binding?.id ?? "binding.new",
      logicalTarget: binding?.logical_target ?? ontologyPackage.properties[0]?.id ?? "",
      source: binding?.source ?? ontologyPackage.data_sources[0]?.id ?? "",
      table: binding?.table ?? ontologyPackage.data_sources[0]?.tables[0]?.name ?? "",
      column: binding?.column ?? ontologyPackage.data_sources[0]?.tables[0]?.fields[0]?.name ?? "",
      dataType: binding?.data_type ?? "string",
      unit: binding?.unit ?? "",
      transformation: binding?.transformation ?? "identity",
      evidenceSource: binding?.sources[0] ?? "",
    };
    setDraft(next);
    setBindingBaseline(JSON.stringify(next));
    setLocalError(null);
    setConfirmBindingDeprecate(false);
    setJoinEditingState(false);
    setEditingState(true);
  }

  function cancelEdit() {
    if (confirmDiscard(bindingDirty)) setEditingState(false);
  }

  async function saveBinding() {
    if (!draft.evidenceSource) { setLocalError("请选择字段映射的来源证据。"); return; }
    const existing = ontologyPackage.bindings.find((binding) => binding.id === draft.id);
    setLocalError(null);
    try { await onApply({ action: "UPSERT", collection: "bindings", object_id: draft.id, payload: {
      id: draft.id,
      version: existing?.version ?? "1.0.0",
      status: "proposed",
      name: existing?.name ?? { en: draft.id, zh: draft.id },
      definition: existing?.definition ?? `Maps ${draft.logicalTarget} to ${draft.table}.${draft.column}.`,
      owner: existing?.owner ?? ontologyPackage.scenario.owner,
      sources: [draft.evidenceSource],
      decisions: existing?.decisions ?? [],
      tags: [...new Set([...(existing?.tags ?? []), "studio-authored"])],
      logical_target: draft.logicalTarget,
      source: draft.source,
      table: draft.table,
      column: draft.column,
      data_type: draft.dataType,
      unit: draft.unit || null,
      transformation: draft.transformation,
    } });
      setEditingState(false);
    } catch { /* Preserve the editor and input on API failure. */ }
  }

  function beginJoinEdit(join?: OntologyPackage["joins"][number]) {
    if (!confirmDiscard(editorDirty)) return;
    const leftSource = join?.left_source ?? ontologyPackage.data_sources[0]?.id ?? "";
    const rightSource = join?.right_source ?? ontologyPackage.data_sources[0]?.id ?? "";
    const next = {
      id: join?.id ?? "join.new", version: join?.version ?? "1.0.0",
      nameZh: join?.name.zh ?? "", nameEn: join?.name.en ?? "", definition: join?.definition ?? "",
      evidenceSource: join?.sources[0] ?? "", leftSource,
      leftTable: join?.left_table ?? ontologyPackage.data_sources.find((source) => source.id === leftSource)?.tables[0]?.name ?? "",
      rightSource,
      rightTable: join?.right_table ?? ontologyPackage.data_sources.find((source) => source.id === rightSource)?.tables[0]?.name ?? "",
      keys: join?.keys.map((key) => `${key.left_column} = ${key.right_column}`).join("\n") ?? "",
      expectedCardinality: join?.expected_cardinality ?? "N:1", fanoutPolicy: join?.fanout_policy ?? "block",
    };
    setJoinDraft(next);
    setJoinBaseline(JSON.stringify(next));
    setLocalError(null);
    setConfirmJoinDeprecate(false);
    setEditingState(false);
    setJoinEditingState(true);
  }

  function cancelJoinEdit() {
    if (confirmDiscard(joinDirty)) setJoinEditingState(false);
  }

  function selectBinding(bindingId: string) {
    if (!confirmDiscard(bindingDirty)) return;
    setSelectedId(bindingId);
    setEditingState(false);
  }

  function selectJoin(joinId: string) {
    if (!confirmDiscard(joinDirty)) return;
    setSelectedJoinId(joinId);
    setJoinEditingState(false);
    setConfirmJoinDeprecate(false);
  }

  async function saveJoin() {
    if (!joinDraft.evidenceSource) { setLocalError("请选择 Join 合同的来源证据。"); return; }
    const keyLines = joinDraft.keys.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    const keys = keyLines.map((line) => {
      const [left, right, ...extra] = line.split("=").map((item) => item.trim());
      return extra.length || !left || !right ? null : { left_column: left, right_column: right };
    });
    if (!keys.length || keys.some((key) => key === null)) { setLocalError("Join Key 每行使用 left_column = right_column，且至少一行。"); return; }
    const existing = ontologyPackage.joins.find((join) => join.id === joinDraft.id);
    setLocalError(null);
    try {
      await onApply({ action: "UPSERT", collection: "joins", object_id: joinDraft.id, payload: {
        id: joinDraft.id, version: joinDraft.version, status: "proposed",
        name: { en: joinDraft.nameEn, zh: joinDraft.nameZh }, definition: joinDraft.definition,
        owner: existing?.owner ?? ontologyPackage.scenario.owner, sources: [joinDraft.evidenceSource],
        decisions: existing?.decisions ?? [], tags: [...new Set([...(existing?.tags ?? []), "studio-authored"])],
        left_source: joinDraft.leftSource, left_table: joinDraft.leftTable,
        right_source: joinDraft.rightSource, right_table: joinDraft.rightTable,
        keys, expected_cardinality: joinDraft.expectedCardinality, fanout_policy: joinDraft.fanoutPolicy,
      } });
      setJoinEditingState(false);
    } catch { /* Preserve input. */ }
  }

  async function deprecateBinding() {
    if (!selected) return;
    try {
      await onApply({ action: "DEPRECATE", collection: "bindings", object_id: selected.id, payload: null });
      setConfirmBindingDeprecate(false);
    } catch { /* Keep confirmation and backend error visible. */ }
  }

  async function deprecateJoin() {
    if (!selectedJoin) return;
    try {
      await onApply({ action: "DEPRECATE", collection: "joins", object_id: selectedJoin.id, payload: null });
      setConfirmJoinDeprecate(false);
    } catch { /* Keep confirmation and backend error visible. */ }
  }

  return <section className={`studio-object-page mapping-product-page${readOnly ? " is-readonly" : ""}`} aria-labelledby="mapping-title">
    <header className="object-page-heading"><div><span>LOGICAL TO PHYSICAL CONTRACT</span><h2 id="mapping-title">映射与关联</h2><p>每条映射都说明哪个逻辑字段由哪个 exact 数据源字段提供；Join 以独立合同管理，不从 SQL 猜测后直接生效。</p></div><div className="object-page-counts"><strong>{ontologyPackage.bindings.length} 条字段映射</strong><span>{ontologyPackage.joins.length} 个 Join 合同</span></div></header>
    <div className="mapping-workspace">
      <section className="mapping-index">
        <header><div><span>FIELD MAPPINGS</span><h3>逻辑字段 → 物理字段</h3></div>{!readOnly ? <button type="button" onClick={() => beginEdit(undefined)}>新增映射</button> : null}</header>
        {ontologyPackage.bindings.map((binding) => <button key={binding.id} type="button" className={binding.id === selected?.id ? "is-selected" : ""} onClick={() => selectBinding(binding.id)}><div><strong>{binding.logical_target}</strong><small>{binding.table}.{binding.column}</small></div><code>{binding.data_type}{binding.unit ? ` · ${binding.unit}` : ""}</code></button>)}
      </section>
      <aside className="mapping-inspector">{editing ? <form onSubmit={(event) => { event.preventDefault(); void saveBinding(); }}><span>MAPPING EDITOR</span><h3>{ontologyPackage.bindings.some((binding) => binding.id === draft.id) ? "创建映射修订" : "新增字段映射"}</h3><label>Mapping ID<input required disabled={ontologyPackage.bindings.some((binding) => binding.id === draft.id)} value={draft.id} onChange={(event) => setDraft((value) => ({ ...value, id: event.target.value }))} /></label><label>逻辑字段<select required value={draft.logicalTarget} onChange={(event) => setDraft((value) => ({ ...value, logicalTarget: event.target.value }))}>{ontologyPackage.properties.map((property) => <option key={property.id} value={property.id}>{property.name.zh} · {property.id}</option>)}</select></label><label>数据源<select required value={draft.source} onChange={(event) => { const nextSource = ontologyPackage.data_sources.find((source) => source.id === event.target.value); setDraft((value) => ({ ...value, source: event.target.value, table: nextSource?.tables[0]?.name ?? "", column: nextSource?.tables[0]?.fields[0]?.name ?? "" })); }}>{ontologyPackage.data_sources.map((source) => <option key={source.id} value={source.id}>{zhName(source)}</option>)}</select></label><label>物理表<select required value={draft.table} onChange={(event) => { const nextTable = selectedDataSource?.tables.find((table) => table.name === event.target.value); setDraft((value) => ({ ...value, table: event.target.value, column: nextTable?.fields[0]?.name ?? "" })); }}>{selectedDataSource?.tables.map((table) => <option key={table.name} value={table.name}>{table.name}</option>)}</select></label><label>物理字段<select required value={draft.column} onChange={(event) => { const field = availableTable?.fields.find((item) => item.name === event.target.value); setDraft((value) => ({ ...value, column: event.target.value, dataType: field?.data_type ?? value.dataType, unit: field?.unit ?? value.unit })); }}>{availableTable?.fields.map((field) => <option key={field.name} value={field.name}>{field.name}</option>)}</select></label><label>转换<input required value={draft.transformation} onChange={(event) => setDraft((value) => ({ ...value, transformation: event.target.value }))} /></label><label>来源证据<select required value={draft.evidenceSource} onChange={(event) => setDraft((value) => ({ ...value, evidenceSource: event.target.value }))}><option value="">请选择，不自动填充</option>{ontologyPackage.sources.map((source) => <option key={source.id} value={source.id}>{source.title} · {source.id}</option>)}</select></label>{localError || error ? <p className="operator-error" role="alert">{localError ?? error}</p> : null}<div className="inspector-actions"><button type="button" onClick={() => setEditing(false)}>取消</button><button type="submit" className="is-primary" disabled={busy}>{busy ? "保存中…" : "保存映射草稿"}</button></div></form> : selected ? <><span>MAPPING DETAIL</span><h3>{selected.name.zh}</h3><div className="mapping-path"><code>{selected.logical_target}</code><b>→</b><code>{selected.source}<br />{selected.table}.{selected.column}</code></div><dl><div><dt>数据类型</dt><dd>{selected.data_type}</dd></div><div><dt>单位</dt><dd>{selected.unit ?? "无"}</dd></div><div><dt>转换</dt><dd>{selected.transformation}</dd></div><div><dt>来源</dt><dd>{selected.sources.join(", ")}</dd></div></dl><div className="inspector-actions"><button type="button" onClick={() => beginEdit(selected)}>编辑映射</button><button type="button" className="is-danger" onClick={() => setConfirmBindingDeprecate(true)}>弃用映射</button></div>{confirmBindingDeprecate ? <div className="data-deprecate-confirm"><strong>确认影响</strong><p>依赖该映射的指标查询仍存在时，系统会阻止弃用。</p><div><button type="button" onClick={() => setConfirmBindingDeprecate(false)}>返回</button><button type="button" className="is-danger" disabled={busy} onClick={() => void deprecateBinding()}>检查并弃用</button></div></div> : null}{error ? <p className="operator-error" role="alert">{error}</p> : null}</> : <div className="data-empty-state"><h3>暂无字段映射</h3><button type="button" onClick={() => beginEdit(undefined)}>新增第一条映射</button></div>}</aside>
    </div>
    <section className="join-catalog"><header><div><span>JOIN CONTRACTS</span><h3>表关联与基数</h3></div><button type="button" onClick={() => beginJoinEdit(undefined)}>新增 Join</button></header><div>{ontologyPackage.joins.map((join) => <article className={selectedJoin?.id === join.id ? "is-selected" : ""} key={join.id} onClick={() => { setSelectedJoinId(join.id); setJoinEditing(false); setConfirmJoinDeprecate(false); }}><div><strong>{join.name.zh}</strong><code>{join.id}</code></div><p><code>{join.left_table}</code><b> → </b><code>{join.right_table}</code></p><small>{join.keys.map((key) => `${key.left_column} = ${key.right_column}`).join(" · ")}</small><footer><span>{join.expected_cardinality}</span><em>fan-out: {join.fanout_policy}</em><button type="button" onClick={(event) => { event.stopPropagation(); beginJoinEdit(join); }}>编辑</button></footer></article>)}</div>{joinEditing ? <form className="join-editor" onSubmit={(event) => { event.preventDefault(); void saveJoin(); }}><header><span>JOIN EDITOR</span><h3>{ontologyPackage.joins.some((join) => join.id === joinDraft.id) ? "创建 Join 修订" : "新增 Join 合同"}</h3></header><div><label>Join ID<input required disabled={ontologyPackage.joins.some((join) => join.id === joinDraft.id)} value={joinDraft.id} onChange={(event) => setJoinDraft((value) => ({ ...value, id: event.target.value }))} /></label><label>版本<input required value={joinDraft.version} onChange={(event) => setJoinDraft((value) => ({ ...value, version: event.target.value }))} /></label><label>中文名称<input required value={joinDraft.nameZh} onChange={(event) => setJoinDraft((value) => ({ ...value, nameZh: event.target.value }))} /></label><label>英文名称<input required value={joinDraft.nameEn} onChange={(event) => setJoinDraft((value) => ({ ...value, nameEn: event.target.value }))} /></label><label className="is-wide">定义<textarea required rows={3} value={joinDraft.definition} onChange={(event) => setJoinDraft((value) => ({ ...value, definition: event.target.value }))} /></label><label>左数据源<select required value={joinDraft.leftSource} onChange={(event) => { const source = ontologyPackage.data_sources.find((item) => item.id === event.target.value); setJoinDraft((value) => ({ ...value, leftSource: event.target.value, leftTable: source?.tables[0]?.name ?? "" })); }}>{ontologyPackage.data_sources.map((source) => <option key={source.id} value={source.id}>{zhName(source)}</option>)}</select></label><label>左表<select required value={joinDraft.leftTable} onChange={(event) => setJoinDraft((value) => ({ ...value, leftTable: event.target.value }))}>{leftJoinSource?.tables.map((table) => <option key={table.name} value={table.name}>{table.name}</option>)}</select></label><label>右数据源<select required value={joinDraft.rightSource} onChange={(event) => { const source = ontologyPackage.data_sources.find((item) => item.id === event.target.value); setJoinDraft((value) => ({ ...value, rightSource: event.target.value, rightTable: source?.tables[0]?.name ?? "" })); }}>{ontologyPackage.data_sources.map((source) => <option key={source.id} value={source.id}>{zhName(source)}</option>)}</select></label><label>右表<select required value={joinDraft.rightTable} onChange={(event) => setJoinDraft((value) => ({ ...value, rightTable: event.target.value }))}>{rightJoinSource?.tables.map((table) => <option key={table.name} value={table.name}>{table.name}</option>)}</select></label><label className="is-wide">Join Key（每行 left = right）<textarea required rows={5} value={joinDraft.keys} onChange={(event) => setJoinDraft((value) => ({ ...value, keys: event.target.value }))} /></label><label>预期基数<select value={joinDraft.expectedCardinality} onChange={(event) => setJoinDraft((value) => ({ ...value, expectedCardinality: event.target.value as JoinDraft["expectedCardinality"] }))}><option value="1:1">1:1</option><option value="N:1">N:1</option></select></label><label>Fan-out 策略<select value={joinDraft.fanoutPolicy} onChange={(event) => setJoinDraft((value) => ({ ...value, fanoutPolicy: event.target.value as JoinDraft["fanoutPolicy"] }))}><option value="block">block</option><option value="deduplicate_reviewed">deduplicate_reviewed</option></select></label><label className="is-wide">来源证据<select required value={joinDraft.evidenceSource} onChange={(event) => setJoinDraft((value) => ({ ...value, evidenceSource: event.target.value }))}><option value="">请选择，不自动填充</option>{ontologyPackage.sources.map((source) => <option key={source.id} value={source.id}>{source.title} · {source.id}</option>)}</select></label></div>{localError || error ? <p className="operator-error" role="alert">{localError ?? error}</p> : null}<footer><button type="button" onClick={() => setJoinEditing(false)}>取消</button><button type="submit" className="is-primary" disabled={busy}>{busy ? "保存中…" : "保存 Join 草稿"}</button></footer></form> : selectedJoin ? <aside className="join-inspector"><div><span>SELECTED JOIN</span><strong>{selectedJoin.name.zh}</strong><code>{selectedJoin.id}</code></div><button type="button" onClick={() => beginJoinEdit(selectedJoin)}>创建修订</button><button type="button" className="is-danger" onClick={() => setConfirmJoinDeprecate(true)}>弃用</button>{confirmJoinDeprecate ? <div className="data-deprecate-confirm"><strong>确认影响</strong><p>仍被查询或指标引用时，后端会拒绝弃用。</p><div><button type="button" onClick={() => setConfirmJoinDeprecate(false)}>返回</button><button type="button" className="is-danger" disabled={busy} onClick={() => void deprecateJoin()}>检查并弃用</button></div></div> : null}</aside> : null}</section>
  </section>;
}

export function SampleAndEnumView({
  ontologyPackage,
  intake,
  onApply,
  busy,
  error = null,
  readOnly = false,
}: {
  ontologyPackage: OntologyPackage;
  intake: Record<string, unknown>;
  onApply: (operation: PackageDraftOperation) => Promise<void> | void;
  busy: boolean;
  error?: string | null;
  readOnly?: boolean;
}) {
  const enumProperties = ontologyPackage.properties.filter((property) => property.data_type === "enum" || property.enum_values.length > 0);
  const [selectedId, setSelectedIdState] = useState(enumProperties[0]?.id ?? "");
  const [editorValue, setEditorValue] = useState(enumProperties[0]?.enum_values.join("\n") ?? "");
  const selected = enumProperties.find((property) => property.id === selectedId) ?? enumProperties[0];
  const enumDirty = !readOnly && Boolean(selected) && editorValue !== selected.enum_values.join("\n");
  useDirtyNavigationGuard(enumDirty);
  const setSelectedId = (value: string) => {
    if (!confirmDiscard(enumDirty)) return;
    setSelectedIdState(value);
  };
  const assets = (Array.isArray(intake.assets) ? intake.assets : []).filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && ["sample_data", "data_dictionary", "derived_control"].includes(String((item as Record<string, unknown>).kind)));

  useEffect(() => { setEditorValue(selected?.enum_values.join("\n") ?? ""); }, [selected?.id, selected?.enum_values]);
  async function saveEnum() {
    if (!selected) return;
    const values = [...new Set(editorValue.split(/\r?\n|,/).map((value) => value.trim()).filter(Boolean))];
    try {
      await onApply({ action: "UPSERT", collection: "properties", object_id: selected.id, payload: { ...selected, status: "proposed", enum_values: values, tags: [...new Set([...selected.tags, "studio-authored"])] } });
    } catch { /* Keep edited enum text visible; parent renders the API error. */ }
  }

  return <section className="studio-object-page" aria-labelledby="sample-enum-title"><header className="object-page-heading"><div><span>SAMPLE & ENUM REGISTRY</span><h2 id="sample-enum-title">样例、枚举与控制材料</h2><p>样例只用于理解和验证，枚举才是语义合同；两者都保留来源与适用范围，不能把一行样例当成完整业务规则。</p></div><div className="object-page-counts"><strong>{enumProperties.length} 个枚举字段</strong><span>{assets.length} 份样例/控制材料</span></div></header><div className="sample-enum-grid"><section><header><span>ENUM DICTIONARY</span><h3>受控值域</h3></header>{enumProperties.map((property) => <button type="button" className={property.id === selected?.id ? "is-selected" : ""} key={property.id} onClick={() => setSelectedId(property.id)}><div><strong>{property.name.zh}</strong><small>{property.entity}</small></div><span>{property.enum_values.length} values</span></button>)}</section><aside>{selected ? <><span>{readOnly ? "ENUM DETAIL" : "ENUM EDITOR"}</span><h3>{selected.name.zh}</h3><p>{selected.definition}</p><label>每行一个枚举值<textarea rows={10} readOnly={readOnly} value={editorValue} onChange={(event) => setEditorValue(event.target.value)} /></label><div className="enum-chip-list">{selected.enum_values.map((value) => <code key={value}>{value}</code>)}</div>{error ? <p className="operator-error" role="alert">{error}</p> : null}{!readOnly ? <button type="button" className="is-primary" disabled={busy || editorValue === selected.enum_values.join("\n")} onClick={() => void saveEnum()}>{busy ? "保存中…" : "保存枚举草稿"}</button> : null}</> : <div className="data-empty-state"><h3>没有枚举字段</h3><p>将属性 data_type 设为 enum 后，可在这里维护受控值域。</p></div>}</aside></div><section className="sample-asset-list"><header><span>EXACT SAMPLE / CONTROL SOURCES</span><h3>已登记材料</h3></header>{assets.length ? assets.map((asset, index) => <article key={String(asset.asset_id ?? index)}><strong>{String(asset.title ?? asset.asset_id ?? "样例材料")}</strong><span>{String(asset.kind)}</span><code>{String(asset.checksum ?? "pending").slice(0, 16)}</code></article>) : <div className="data-empty-state"><p>尚无独立样例或控制材料；这不会被伪装成“已验证”。</p></div>}</section></section>;
}
