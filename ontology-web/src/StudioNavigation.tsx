import { Link } from "react-router-dom";
import type { ReactNode } from "react";

export type StudioPageId =
  | "overview"
  | "inputs"
  | "construction"
  | "semantic"
  | "data"
  | "quality"
  | "solutions";

export type StudioSubpageId =
  | "summary"
  | "requirements"
  | "runs"
  | "model"
  | "metrics"
  | "graph"
  | "experience"
  | "sources"
  | "schemas"
  | "mappings"
  | "sql"
  | "samples"
  | "review"
  | "policies"
  | "validation"
  | "changes"
  | "versions"
  | "delivery";

export type StudioPageDefinition = {
  id: StudioPageId;
  label: string;
  description: string;
  defaultSubpage: StudioSubpageId;
  subpages: Array<{ id: StudioSubpageId; label: string; description: string }>;
};

export const studioPages: StudioPageDefinition[] = [
  {
    id: "overview",
    label: "概览",
    description: "状态、风险与下一步",
    defaultSubpage: "summary",
    subpages: [{ id: "summary", label: "工作区概览", description: "状态、资产与后续动作" }],
  },
  {
    id: "inputs",
    label: "输入与证据",
    description: "需求、材料与证据版本",
    defaultSubpage: "requirements",
    subpages: [
      { id: "requirements", label: "业务需求", description: "业务过程、分析问题和期望输出" },
      { id: "sources", label: "来源材料", description: "材料版本、证据锚点和处理状态" },
    ],
  },
  {
    id: "construction",
    label: "构建与复核",
    description: "生成候选、机器复核与人工处置",
    defaultSubpage: "runs",
    subpages: [
      { id: "runs", label: "构建任务", description: "选择材料、运行 Builder 并查看产出" },
      { id: "review", label: "复核队列", description: "证据、差异、机器发现与人工处置" },
    ],
  },
  {
    id: "semantic",
    label: "语义模型",
    description: "对象、关系、指标与规则",
    defaultSubpage: "model",
    subpages: [
      { id: "model", label: "业务模型", description: "对象、属性和关系目录" },
      { id: "metrics", label: "指标与规则", description: "指标口径、公式和业务规则" },
      { id: "graph", label: "知识图谱", description: "完整关系浏览、编辑和影响分析" },
      { id: "experience", label: "分析能力", description: "问题族、分析模式和回答义务" },
    ],
  },
  {
    id: "data",
    label: "数据",
    description: "来源、Schema、映射与关联",
    defaultSubpage: "schemas",
    subpages: [
      { id: "schemas", label: "数据源与 Schema", description: "物理表、字段和数据类型" },
      { id: "mappings", label: "映射与关联", description: "逻辑字段、物理字段和 Join" },
      { id: "sql", label: "SQL 合同", description: "语句来源、输入、输出和执行边界" },
      { id: "samples", label: "样例与枚举", description: "样例数据、枚举和控制用例" },
    ],
  },
  {
    id: "quality",
    label: "质量与发布",
    description: "策略、验证、版本与运行",
    defaultSubpage: "validation",
    subpages: [
      { id: "policies", label: "访问与披露策略", description: "角色、粒度和字段披露边界" },
      { id: "validation", label: "验证结果", description: "结构、语义和运行检查" },
      { id: "changes", label: "问题与变更", description: "缺口、反馈和修订历史" },
      { id: "versions", label: "版本与审批", description: "草稿、验证和发布记录" },
      { id: "delivery", label: "交付与运行", description: "绑定、认证、激活和回滚" },
    ],
  },
];

const globalPage: StudioPageDefinition = {
  id: "solutions",
  label: "解决方案目录",
  description: "新建、切换与管理 Ontology Solution",
  defaultSubpage: "summary",
  subpages: [],
};

const legacyPageAliases: Record<string, StudioPageId> = {
  authoring: "inputs",
  assistant: "construction",
  ontology: "semantic",
  validation: "quality",
  sources: "quality",
  release: "quality",
  about: "overview",
};

const legacySubpageAliases: Record<string, StudioSubpageId> = {
  authoring: "requirements",
  assistant: "review",
  ontology: "model",
  validation: "validation",
  sources: "changes",
  about: "summary",
};

function studioPathSegments(pathname: string): string[] {
  return pathname
    .replace(/^\/ontology-studio\/?/, "")
    .split("/")
    .filter(Boolean)
    .map((segment) => decodeURIComponent(segment));
}

export function studioSolutionIdFromPath(pathname: string): string | null {
  const segments = studioPathSegments(pathname);
  if (segments[0] !== "solutions" || segments.length < 2) return null;
  const candidate = segments[1];
  return /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(candidate) ? candidate : null;
}

export function studioPageFromPath(pathname: string): StudioPageId {
  const segments = studioPathSegments(pathname);
  if (segments.length === 0) return "solutions";
  if (segments[0] === "solutions" && segments[2] === "builds") return "construction";
  const segment = segments[0] === "solutions" && segments.length >= 2
    ? segments[2]
    : segments[0];
  if (segments[0] === "solutions" && segments.length < 2) return "solutions";
  if (studioPages.some((page) => page.id === segment)) return segment as StudioPageId;
  return legacyPageAliases[segment] ?? "overview";
}

export function studioSubpageFromPath(
  pathname: string,
  pageId: StudioPageId,
): StudioSubpageId {
  if (pageId === "solutions") return "summary";
  const segments = studioPathSegments(pathname);
  if (segments[0] === "solutions" && segments[2] === "builds") return "review";
  const definition = studioPageDefinition(pageId);
  const explicitSolution = segments[0] === "solutions" && segments.length >= 2;
  const requested = segments[explicitSolution ? 3 : 1] as StudioSubpageId | undefined;
  if (requested && definition.subpages.some((item) => item.id === requested)) return requested;
  const requestedPage = segments[explicitSolution ? 2 : 0];
  if (requestedPage === "release" && (requested === "versions" || requested === "delivery")) {
    return requested;
  }
  const legacy = legacySubpageAliases[explicitSolution ? segments[2] : segments[0]];
  if (legacy && definition.subpages.some((item) => item.id === legacy)) return legacy;
  return definition.defaultSubpage;
}

export type StudioBuildRoute = {
  runId: string;
  decisionId: string | null;
};

export function studioBuildRouteFromPath(pathname: string): StudioBuildRoute | null {
  const segments = studioPathSegments(pathname);
  if (segments[0] !== "solutions" || segments[2] !== "builds" || segments[4] !== "review") return null;
  const runId = segments[3];
  if (!/^construction-run\.[0-9a-f]{32}$/.test(runId ?? "")) return null;
  const decisionId = segments[5] === "results" ? segments[6] ?? null : null;
  if (decisionId !== null && !/^construction-decision\.[0-9a-f]{32}$/.test(decisionId)) return null;
  return { runId, decisionId };
}

export function studioBuildReviewHref(solutionId: string, runId: string): string {
  return `/ontology-studio/solutions/${encodeURIComponent(solutionId)}/builds/${encodeURIComponent(runId)}/review/`;
}

export function studioBuildResultHref(solutionId: string, runId: string, decisionId: string): string {
  return `${studioBuildReviewHref(solutionId, runId)}results/${encodeURIComponent(decisionId)}/`;
}

export function studioPageHref(
  page: StudioPageId,
  solutionId: string,
  subpage?: StudioSubpageId,
): string {
  if (page === "solutions") return "/ontology-studio/solutions/";
  const definition = studioPageDefinition(page);
  const selectedSubpage = subpage ?? definition.defaultSubpage;
  const segment = page === "overview" && selectedSubpage === "summary"
    ? ""
    : `${selectedSubpage}/`;
  return `/ontology-studio/solutions/${encodeURIComponent(solutionId)}/${page}/${segment}`;
}

export function studioPageDefinition(pageId: StudioPageId): StudioPageDefinition {
  return pageId === "solutions"
    ? globalPage
    : studioPages.find((page) => page.id === pageId) ?? studioPages[0];
}

function StudioNavIcon({ page }: { page: StudioPageId }) {
  const paths: Record<StudioPageId, ReactNode> = {
    solutions: <><path d="M4 6.5h6l1.8 2H20v9.5H4z" /><path d="M4 9h16M7 3.5h7" /></>,
    overview: <><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="4" /><rect x="14" y="11" width="7" height="10" /><rect x="3" y="14" width="7" height="7" /></>,
    inputs: <><path d="M6 3h9l4 4v14H6z" /><path d="M15 3v5h5M9 12h6M9 16h6" /></>,
    construction: <><path d="M4 7h10M4 12h7M4 17h10" /><path d="m15 13 2 2 4-5" /><circle cx="18" cy="12" r="5" /></>,
    semantic: <><circle cx="12" cy="5" r="2.5" /><circle cx="5" cy="18" r="2.5" /><circle cx="19" cy="18" r="2.5" /><path d="M10.6 7.1 6.4 15.8M13.4 7.1l4.2 8.7M7.5 18h9" /></>,
    data: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>,
    quality: <><path d="m12 3 7 3v5c0 4.6-2.8 8.1-7 10-4.2-1.9-7-5.4-7-10V6z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[page]}</svg>;
}

export function StudioNavigation({
  activePage,
  solutionName,
  solutionVersion,
  activeRuntimeVersion,
  solutionId,
}: {
  activePage: StudioPageId;
  solutionName: string;
  solutionVersion: string;
  activeRuntimeVersion: string | null;
  solutionId: string;
}) {
  return (
    <aside className="studio-sidebar">
      <nav className="studio-product-navigation" aria-label="Ontology Studio">
        <Link className="studio-product-home" to="/ontology-studio/solutions/">
          <span className="studio-nav-icon"><StudioNavIcon page="solutions" /></span>
          <div><strong>解决方案目录</strong><small>切换、新建与管理</small></div>
        </Link>
        <Link className="studio-product-home" to="/ontology-studio/tasks/">
          <span className="studio-nav-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" /></svg></span>
          <div><strong>构建任务</strong><small>进度、结果与待处理</small></div>
        </Link>
      </nav>
      <div className="studio-sidebar-context">
        <span>当前解决方案</span>
        <strong>{solutionName}</strong>
        <dl>
          <div><dt>方案定义</dt><dd>v{solutionVersion}</dd></div>
          <div><dt>运行语义</dt><dd>{activeRuntimeVersion ? `v${activeRuntimeVersion}` : "未激活"}</dd></div>
        </dl>
      </div>
      <nav className="studio-workspace-navigation" aria-label="当前解决方案工作区">
        <h2>解决方案工作区</h2>
        {studioPages.map((page) => (
          <Link
            key={page.id}
            to={studioPageHref(page.id, solutionId)}
            className={activePage === page.id ? "is-active" : undefined}
            aria-current={activePage === page.id ? "page" : undefined}
          >
            <span className="studio-nav-icon"><StudioNavIcon page={page.id} /></span>
            <div><strong>{page.label}</strong><small>{page.description}</small></div>
          </Link>
        ))}
      </nav>
      <div className="studio-sidebar-footer">
        <a href={`/ontology-agent/?solution=${encodeURIComponent(solutionId)}`}>Ontology Agent <span aria-hidden="true">↗</span></a>
      </div>
    </aside>
  );
}

export function StudioSubnavigation({
  page,
  activeSubpage,
  solutionId,
}: {
  page: StudioPageId;
  activeSubpage: StudioSubpageId;
  solutionId: string;
}) {
  const definition = studioPageDefinition(page);
  if (definition.subpages.length <= 1) return null;
  return (
    <nav className="studio-subnavigation" aria-label={`${definition.label}子页面`}>
      {definition.subpages.map((subpage) => (
        <Link
          key={subpage.id}
          to={studioPageHref(page, solutionId, subpage.id)}
          className={activeSubpage === subpage.id ? "is-active" : undefined}
          aria-current={activeSubpage === subpage.id ? "page" : undefined}
        >
          <strong>{subpage.label}</strong>
          <small>{subpage.description}</small>
        </Link>
      ))}
    </nav>
  );
}
