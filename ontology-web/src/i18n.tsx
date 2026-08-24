import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type UiLocale = "zh" | "en";

type LocalizedName = { zh?: string | null; en?: string | null };

type UiLocaleContextValue = {
  locale: UiLocale;
  setLocale: (locale: UiLocale) => void;
  t: (zh: string, en: string) => string;
  name: (value: LocalizedName) => string;
};

const defaultLocaleValue: UiLocaleContextValue = {
  locale: "zh",
  setLocale: () => undefined,
  t: (zh) => zh,
  name: (localized) => localized.zh || localized.en || "",
};

const UiLocaleContext = createContext<UiLocaleContextValue>(defaultLocaleValue);

const phraseTranslations: Array<[string, string]> = [
  ["正在核验来源版本与运行权威链路…", "Validating source versions and the runtime authority chain…"],
  ["正在核对运行记录、来源结算和候选合同。", "Checking run records, source resolution and candidate contracts."],
  ["系统正在校验候选、来源证据和已有复核进度。", "Validating candidates, source evidence and saved review progress."],
  ["在“业务配置”维护 Agent 应支持的问题、流程和期望答案；原始材料只作为不可改写的证据版本保留。", "Maintain the questions, processes and expected answers supported by the Agent in Business Configuration. Original materials remain immutable evidence versions."],
  ["每条分析需求分别定义回答粒度、必需输入、证据义务和不支持边界。", "Define the answer grain, required inputs, evidence obligations and unsupported boundaries for every analysis requirement."],
  ["这里的修改会形成 Ontology Draft 修订；不会覆盖原始需求文件。", "Changes here create an Ontology Draft revision and never overwrite the original requirement files."],
  ["参考方案保留已登记材料及其精确身份。复制方案后可载入材料并重新构建。", "The reference solution preserves registered materials and their exact identities. Copy the solution to load materials and rebuild."],
  ["每次登记都会形成不可变的 exact version。当前版本用于构建，历史版本继续保留证据身份。", "Every registration creates an immutable exact version. The current version is used for construction while historical versions preserve evidence identity."],
  ["要纠正或更新内容，请为同一逻辑来源登记新版本；系统会保留旧版本和校验摘要。", "To correct or update content, register a new version for the same logical source. Previous versions and checksums remain preserved."],
  ["材料本身不可原地修改。", "Source material cannot be modified in place."],
  ["参考方案保留已登记材料及其精确身份。复制方案后可载入材料并重新构建。", "The reference solution preserves registered materials and exact identities. Copy it to load materials and rebuild."],
  ["参考方案保留已登记材料及其精确身份。复制解决方案后可载入材料并重新构建。", "The reference solution preserves registered materials and exact identities. Copy it to load materials and rebuild."],
  ["复制参考方案后可登记材料并重新构建。", "Copy the reference solution to register materials and rebuild."],
  ["构建任务只读取本次选定的来源版本。", "The build task reads only the source versions selected for this run."],
  ["把选定来源结算为可追踪候选；构建结果不会直接修改 Draft，也不会自动发布。", "Resolve selected sources into traceable candidates. Build results never modify the Draft directly or publish automatically."],
  ["只控制名称、定义和业务说明。ID、SQL、字段名及原始证据保持不变。", "Controls names, definitions and business descriptions only. IDs, SQL, field names and original evidence remain unchanged."],
  ["当前 Solution 尚无可选来源版本。", "This solution has no selectable source versions."],
  ["当前解决方案尚无可选来源版本。", "This solution has no selectable source versions."],
  ["业务中具有稳定身份、粒度和生命周期的事物", "Business concepts with stable identity, grain and lifecycle"],
  ["从业务对象到流程与维度的统一资产目录", "A unified asset catalog spanning business objects, processes and dimensions"],
  ["触发、步骤、异常路径与责任人的端到端过程", "End-to-end processes with triggers, steps, exception paths and owners"],
  ["对象之间有方向、有基数的业务联系", "Directed, cardinality-aware business relationships between objects"],
  ["对象上的受治理字段、类型、单位和枚举", "Governed fields, types, units and enumerations on an object"],
  ["指标可切分、聚合和比较的受控业务轴", "Controlled business axes used to slice, aggregate and compare metrics"],
  ["对业务定义、流程或分析承担责任的角色", "Roles accountable for business definitions, processes or analysis"],
  ["权威指标、计算口径与规则目录", "Canonical metrics, calculation semantics and rule catalog"],
  ["资格、质量、日历、告警与失败行为", "Eligibility, quality, calendar, alerting and failure behavior"],
  ["口径、公式、粒度、单位与物理查询责任", "Definition, formula, grain, unit and physical query responsibility"],
  ["来源层与权威层已分开。", "The source and canonical layers are separated."],
  ["Agent 可以理解的问题与可以执行的分析", "Questions the Agent understands and analyses it can execute"],
  ["Agent 可执行的分析意图、依赖和输出义务", "Executable analytic intents, dependencies and output obligations"],
  ["用户问题族、必需输入和期望回答", "User question families, required inputs and expected answers"],
  ["按数据源、物理表和字段维护当前 Draft 的确定性数据合同；SQL 和样例是证据，不会替代这里的字段类型与粒度。", "Maintain deterministic data contracts for the current Draft by source, physical table and field. SQL and samples are evidence; they do not replace field types or grain."],
  ["目录始终展示当前 Draft；编辑会打开结构化配置抽屉，保存后形成新的 Draft 修订。", "The catalog always shows the current Draft. Editing opens a structured configuration drawer; saving creates a new Draft revision."],
  ["浏览与编辑是两个明确状态。", "Browse and edit are distinct states."],
  ["每条映射都说明哪个逻辑字段由哪个 exact 数据源字段提供；Join 以独立合同管理，不从 SQL 猜测后直接生效。", "Every mapping identifies the exact physical source field providing a logical field. Joins are governed as independent contracts and never activated directly from SQL inference."],
  ["逻辑字段 → 物理字段", "Logical field → physical field"],
  ["表关联与基数", "Table joins and cardinality"],
  ["SQL 不是业务真相本身。", "SQL is not the business truth by itself."],
  ["合同必须明确它读取什么、产出什么、实现哪些指标或规则；运行前仍需确定性验证。", "A contract must state what it reads, what it produces and which metrics or rules it implements. Deterministic validation is still required before execution."],
  ["登记 SQL 原文的证据位置、输入输出与治理责任；Ontology 保存合同，不复制或改写 SQL 正文。", "Register the evidence location, inputs, outputs and governance responsibility of the original SQL. The ontology stores the contract, not a copied or rewritten SQL body."],
  ["该参考方案没有登记 SQL 合同。", "This reference solution has no registered SQL contracts."],
  ["当前 Draft 尚无 SQL 合同", "The current Draft has no SQL contracts"],
  ["样例只用于理解和验证，枚举才是语义合同；两者都保留来源与适用范围，不能把一行样例当成完整业务规则。", "Samples support understanding and validation; enumerations are the semantic contract. Both preserve provenance and scope, and a sample row must never be treated as a complete business rule."],
  ["尚无独立样例或控制材料；这不会被伪装成“已验证”。", "No independent sample or control material is registered; the product does not present this as validated."],
  ["每行一个枚举值", "One enumeration value per row"],
  ["角色、粒度、字段和最小群组的运行边界", "Runtime boundaries for roles, grain, fields and minimum cohorts"],
  ["运行权限、数据粒度与结果披露边界", "Runtime permissions, data grain and result disclosure boundaries"],
  ["PASS/FAIL 只展示后端对 exact revision 与 checksum 的验证结论；浏览器不会自行补写验证状态。", "PASS/FAIL displays only backend validation for the exact revision and checksum. The browser never invents validation status."],
  ["先在上方编辑器保存并验证；未运行时不会显示推测性的 PASS。", "Save and validate in the editor above. No speculative PASS is shown before validation runs."],
  ["当前 revision 尚无可展示的后端检查明细。", "No backend check details are available for the current revision."],
  ["查看并维护当前工作区中的对象、关系、指标、数据映射与发布状态。", "Inspect and maintain objects, relationships, metrics, data mappings and publication status in the current workspace."],
  ["Agent 尚未提交 evidence-bound semantic change request。", "The Agent has not submitted an evidence-bound semantic change request."],
  ["Intake summary 未声明结构化 gap；这不等于生产材料已齐备。", "The intake summary declares no structured gap; this does not mean production materials are complete."],
  ["当前 Draft 通过精确验证后，才可以发布为不可变语义 Release。", "The current Draft can be published as an immutable semantic release only after exact validation passes."],
  ["Draft 修订、精确验证和不可变发布记录在这里汇合；运行准备与激活在“交付与运行”中操作。", "Draft revisions, exact validation and immutable publication records converge here. Runtime preparation and activation are managed in Delivery & Runtime."],
  ["“发布”“准备/认证”“激活”“验证/回滚”是独立动作。回滚同样使用 expected-current CAS，不能覆盖并发发生的新激活。", "Publish, prepare/certify, activate and verify/rollback are independent actions. Rollback also uses expected-current CAS and cannot overwrite a concurrent activation."],
  ["在正常 Agent API 路径重跑 reference suite，不把 prepare-time 认证冒充 active verification。", "Rerun the reference suite through the normal Agent API path; prepare-time certification is never presented as active verification."],
  ["将 release 绑定到 exact dataset、adapter、query engine 和 certification controls。", "Bind the release to the exact dataset, adapter, query engine and certification controls."],
  ["不可变 semantic release；发布不会改变 Agent active pointer。", "Immutable semantic release; publication does not change the Agent active pointer."],
  ["CAS 激活指针；失败时旧 active snapshot 继续服务。", "CAS activation pointer; the previous active snapshot continues serving if activation fails."],
  ["Draft materialization；只有 exact validation PASS 才能发布。", "Draft materialization; publication requires an exact validation PASS."],
  ["正在读取构建记录", "Loading build records"],
  ["正在读取候选集合", "Loading candidate set"],
  ["正在核验来源版本与运行权威链路…", "Validating source versions and the runtime authority chain…"],
  ["工作区来源", "Workspace sources"],
  ["当前使用来源投影", "Using source projection"],
  ["首次构建请选择", "Select for the first build"],
  ["Ontology 输出语言", "Ontology output language"],
  ["自动构建运行", "Automated build runs"],
  ["选择本次构建使用的材料版本", "Select material versions for this build"],
  ["简体中文", "Simplified Chinese"],
  ["业务需求与分析流程", "Business Requirements & Analysis Flow"],
  ["编辑这条需求", "Edit this requirement"],
  ["查看来源证据", "View source evidence"],
  ["新增业务过程", "Add business process"],
  ["新增分析需求", "Add analysis requirement"],
  ["新增输出要求", "Add output requirement"],
  ["业务配置", "Business Configuration"],
  ["原始需求提取", "Original Requirement Extraction"],
  ["原始提取", "Original extraction"],
  ["只读证据", "read-only evidence"],
  ["可编辑", "editable"],
  ["业务过程", "Business Process"],
  ["分析需求", "Analysis Requirement"],
  ["期望回答", "Expected Answer"],
  ["期望输出", "Expected Output"],
  ["答案证据", "Answer Evidence"],
  ["已确认", "Confirmed"],
  ["标识", "Identifier"],
  ["参与者证据时间线", "Participant evidence timeline"],
  ["受治理现金交易分析", "Governed cash trading analysis"],
  ["可验证的分析答案", "Verifiable analytic answers"],
  ["客户订单完成率", "Client order completion rate"],
  ["成交捕获延迟", "Trade capture latency"],
  ["撤单成交比", "Cancel-to-trade ratio"],
  ["昨日自成交分析", "Previous-day self-trade analysis"],
  ["活跃客户成交量", "Active client trading volume"],
  ["自成交日趋势", "Daily self-trade trend"],
  ["订单成交比", "Order-to-trade ratio"],
  ["订单成交率", "Order fill rate"],
  ["订单拒绝率", "Order rejection rate"],
  ["来源材料与证据版本", "Source Materials & Evidence Versions"],
  ["业务需求与端到端分析流程", "Business Requirements & End-to-End Analysis Flow"],
  ["Cash Trading 构造型样例数据", "Cash Trading synthetic sample data"],
  ["数据模型", "Data Model"],
  ["指标逻辑（转写）", "Metric logic (transcribed)"],
  ["八项 Cash Trading 指标逻辑", "Eight Cash Trading metric definitions"],
  ["材料来源与限制说明", "Material provenance and limitations"],
  ["订单与成交字段字典", "Order and trade field dictionary"],
  ["订单与成交逻辑数据模型", "Order and trade logical data model"],
  ["需求文档（转写）", "Requirements document (transcribed)"],
  ["参考材料包", "Reference material pack"],
  ["历史版本", "Version History"],
  ["原始文件", "Original file"],
  ["处理状态", "Processing status"],
  ["已登记，待解析", "Registered, pending parsing"],
  ["结构已解析", "Structure parsed"],
  ["已载入", "Loaded"],
  ["当前来源", "Current sources"],
  ["当前", "Current"],
  ["逻辑来源", "Logical source"],
  ["类型", "Type"],
  ["其他材料", "Other material"],
  ["业务对象", "Business Object"],
  ["业务规则", "Business Rule"],
  ["分析维度", "Analytic Dimension"],
  ["参与者", "Participant"],
  ["关系", "Relationship"],
  ["属性", "Property"],
  ["搜索当前类型", "Search current type"],
  ["来源证据", "Source evidence"],
  ["数据源", "Data source"],
  ["主键", "Primary key"],
  ["可为空", "Nullable"],
  ["字段", "Field"],
  ["张表", "tables"],
  ["必填", "Required"],
  ["现金交易分析视图", "Cash trading analytics view"],
  ["现金订单生命周期分析视图", "Cash order lifecycle analytics view"],
  ["粒度", "Grain"],
  ["约束", "Constraint"],
  ["编辑映射", "Edit mapping"],
  ["弃用映射", "Deprecate mapping"],
  ["个 Join 合同", "join contracts"],
  ["条字段映射", "field mappings"],
  ["成交关联买方参与者", "Trade joins buyer participant"],
  ["成交关联卖方参与者", "Trade joins seller participant"],
  ["成交关联日历", "Trade joins calendar"],
  ["成交关联证券", "Trade joins instrument"],
  ["订单关联交易日历", "Order joins trading calendar"],
  ["订单关联参与者", "Order joins participant"],
  ["订单关联订单类型", "Order joins order type"],
  ["订单关联证券", "Order joins instrument"],
  ["数据类型", "Data type"],
  ["转换", "Transformation"],
  ["单位", "Unit"],
  ["个 SQL 合同", "SQL contracts"],
  ["个可验证或运行", "validated or runnable"],
  ["个枚举字段", "enumerated fields"],
  ["份样例/控制材料", "sample/control materials"],
  ["受控值域", "Controlled value domain"],
  ["已登记材料", "Registered material"],
  ["是否交易日", "Is trading day"],
  ["订单状态", "Order status"],
  ["订单活动类型", "Order activity type"],
  ["参与者类型", "Participant type"],
  ["策略", "Policy"],
  ["打开完整合同编辑器", "Open full contract editor"],
  ["语义模型工作台", "Semantic Model Workspace"],
  ["精确验证结果", "Exact Validation Results"],
  ["来源证据与修订轨迹", "Source Evidence & Revision Trail"],
  ["不可变 Draft 修订", "Immutable Draft revisions"],
  ["个 Draft 修订", "Draft revisions"],
  ["前往交付与运行 →", "Go to Delivery & Runtime →"],
  ["尚未发布", "Not published"],
  ["发布、认证、激活和回滚", "Publish, certify, activate and rollback"],
  ["刷新运行状态", "Refresh runtime status"],
  ["刷新中…", "Refreshing…"],
  ["在 Agent 中打开 ↗", "Open in Agent ↗"],
  ["等待 active API 验证", "Awaiting active API verification"],
  ["当前无 active snapshot", "No active snapshot"],
  ["等待环境绑定与认证", "Awaiting environment binding and certification"],
  ["个canonical nodes visible", "canonical nodes visible"],
  ["个review candidates", "review candidates"],
  ["四个阶段相互关联，但不会互相冒充：载入不等于建模，建模不等于审核，审核也不等于已经激活。", "The four stages are connected but never interchangeable: loading is not modeling, modeling is not review, and review is not activation."],
  ["内部审核仅证明当前版本在已登记证据与显式假设下自洽、可追踪；", "Internal review only confirms that the current version is self-consistent and traceable against registered evidence and explicit assumptions;"],
  ["每一步都是独立页面，状态通过同一个工作区衔接。", "Each step has its own page and shares status through the same workspace."],
  ["从输入证据到 Agent 生效版本", "From input evidence to the Agent's active version"],
  ["从业务定义到可用运行版本", "From business definitions to a usable runtime version"],
  ["管理对象、关系、指标和分析能力", "Manage objects, relationships, metrics and analytic capabilities"],
  ["维护 Schema、映射、Join 和 SQL 合同", "Maintain schemas, mappings, joins and SQL contracts"],
  ["维护需求、材料和 exact version", "Maintain requirements, materials and exact versions"],
  ["生成候选、机器复核并人工处置", "Generate candidates, run machine review and record human decisions"],
  ["检查、审批、激活与回滚", "Validate, approve, activate and roll back"],
  ["验证当前 Draft 并处理阻断问题。", "Validate the current Draft and resolve blocking issues."],
  ["不等同于生产审批或运行激活", "does not constitute production approval or runtime activation"],
  ["内部已审核（含待确认假设）", "Internally reviewed (with assumptions pending confirmation)"],
  ["与审核基线一致", "Aligned with the review baseline"],
  ["全部 exact source 已登记", "All exact sources registered"],
  ["项已登记资产", "registered assets"],
  ["个逻辑来源", "logical sources"],
  ["份文件 ·", "files ·"],
  ["证据与假设", "Evidence & Assumptions"],
  ["指标与维度", "Metrics & Dimensions"],
  ["数据语义", "Data Semantics"],
  ["Package 内容", "Package Contents"],
  ["建模流程", "Modeling Flow"],
  ["建议下一步", "Recommended Next Step"],
  ["登记输入", "Register Inputs"],
  ["维护语义", "Maintain Semantics"],
  ["验证与发布", "Validate & Publish"],
  ["继续处理", "Continue"],
  ["进入 Agent 查询", "Open Agent"],
  ["边界：", "Boundary:"],
  ["决策/假设", "decisions/assumptions"],
  ["关联", "joins"],
  ["映射", "mappings"],
  ["模式", "patterns"],
  ["问题", "questions"],
  ["验证状态", "Validation status"],
  ["已登记", "Registered"],
  ["条SourcesMetric保留为证据，不会替换下方", "source metrics are retained as evidence and do not replace the canonical metrics below"],
  ["条来源指标保留为证据，不会替换下方", "source metrics are retained as evidence and do not replace the canonical metrics below"],
  ["条 Ontology Metric。", "ontology metrics."],
  ["Publish、认证、Activate与验证", "Publish, certify, activate and verify"],
  ["样例、枚举与控制材料", "Samples, enumerations and control materials"],
  ["property.trade.trading_activity_id绑定", "property.trade.trading_activity_id binding"],
  ["个可追溯Version", "traceable versions"],
  ["个可追溯版本", "traceable versions"],
  ["个Data source", "data sources"],
  ["个Field", "fields"],
  ["条 · read-only evidence", "items · read-only evidence"],
  ["条 · editable", "items · editable"],
  ["条Business Configuration", "business configuration items"],
  ["条Original extraction", "original extraction items"],
  ["Edit过程", "Edit process"],
  ["个Version", "versions"],
  ["业务流程", "Business Process"],
  ["业务问题", "Business Question"],
  ["分析模式", "Analysis Pattern"],
  ["版本身份", "Version identity"],
  ["安装材料", "installed materials"],
  ["尚未载入", "Not loaded"],
  ["查看", "View"],
  ["绑定", "Binding"],
  ["现金市场订单与成交活动监控", "Cash Market Order and Trading Activity Monitoring"],
  ["解决方案目录", "Solution Catalog"],
  ["切换、新建与管理", "Switch, create and manage"],
  ["Atlas Ontology Studio 首页", "Atlas Ontology Studio home"],
  ["Atlas Ontology Agent 首页", "Atlas Ontology Agent home"],
  ["配置目录", "catalog"],
  ["目录", "catalog"],
  ["子页面", "subpage"],
  ["需求信息层", "requirement information layer"],
  ["详情", "details"],
  ["图谱布局", "Graph layout"],
  ["按对象、指标和规则分层排列", "Arrange objects, metrics, and rules in layers"],
  ["按关系强度组织节点", "Arrange nodes by relationship strength"],
  ["按Object、Metric和Rule分层排列", "Arrange objects, metrics, and rules in layers"],
  ["按Relationship强度组织节点", "Arrange nodes by relationship strength"],
  ["任务中心", "Task Center"],
  ["跨方案进度与待处理", "Cross-solution progress and actions"],
  ["当前解决方案", "Current solution"],
  ["方案定义", "Solution definition"],
  ["运行语义", "Runtime semantics"],
  ["未激活", "Not active"],
  ["解决方案工作区", "Solution workspace"],
  ["状态、风险与下一步", "Status, risks and next steps"],
  ["需求、材料与证据版本", "Requirements, sources and evidence versions"],
  ["生成候选、机器复核与人工处置", "Generate candidates, machine review and human decisions"],
  ["对象、关系、指标与知识图谱", "Objects, relationships, metrics and knowledge graph"],
  ["来源、Schema、映射与关联", "Sources, schemas, mappings and joins"],
  ["策略、验证、版本与运行", "Policies, validation, versions and runtime"],
  ["工作区概览", "Workspace overview"],
  ["状态、资产与后续动作", "Status, assets and next actions"],
  ["输入与证据", "Inputs & Evidence"],
  ["业务需求", "Business Requirements"],
  ["业务过程、分析问题和期望输出", "Business process, analysis questions and expected outputs"],
  ["来源材料", "Source Materials"],
  ["材料版本、证据锚点和处理状态", "Material versions, evidence anchors and processing status"],
  ["构建与复核", "Build & Review"],
  ["构建运行", "Build Runs"],
  ["选择材料、运行 Builder 并查看产出", "Select materials, run the Builder and inspect outputs"],
  ["复核队列", "Review Queue"],
  ["证据、差异、机器发现与人工处置", "Evidence, differences, machine findings and human decisions"],
  ["语义模型", "Semantic Model"],
  ["业务模型", "Business Model"],
  ["对象、属性和关系目录", "Object, property and relationship catalog"],
  ["指标与规则", "Metrics & Rules"],
  ["指标口径、公式和业务规则", "Metric definitions, formulas and business rules"],
  ["知识图谱", "Knowledge Graph"],
  ["完整关系浏览、编辑和影响分析", "Relationship exploration, editing and impact analysis"],
  ["分析能力", "Analytic Capabilities"],
  ["问题族、分析模式和回答义务", "Question families, analysis patterns and answer obligations"],
  ["数据源与 Schema", "Data Sources & Schemas"],
  ["物理表、字段和数据类型", "Physical tables, fields and data types"],
  ["映射与关联", "Mappings & Joins"],
  ["逻辑字段、物理字段和 Join", "Logical fields, physical fields and joins"],
  ["SQL 合同", "SQL Contracts"],
  ["语句来源、输入、输出和执行边界", "Statement sources, inputs, outputs and execution boundaries"],
  ["样例与枚举", "Samples & Enumerations"],
  ["样例数据、枚举和控制用例", "Sample data, enumerations and control cases"],
  ["质量与发布", "Quality & Release"],
  ["访问与披露策略", "Access & Disclosure Policies"],
  ["角色、粒度和字段披露边界", "Role, grain and field disclosure boundaries"],
  ["验证结果", "Validation Results"],
  ["结构、语义和运行检查", "Structural, semantic and runtime checks"],
  ["问题与变更", "Issues & Changes"],
  ["缺口、反馈和修订历史", "Gaps, feedback and revision history"],
  ["版本与审批", "Versions & Approvals"],
  ["草稿、验证和发布记录", "Draft, validation and publication history"],
  ["交付与运行", "Delivery & Runtime"],
  ["绑定、认证、激活和回滚", "Binding, certification, activation and rollback"],
  ["概览", "Overview"],
  ["数据", "Data"],
  ["配置人员", "Operator"],
  ["只读访问", "Read-only"],
  ["正在确认权限", "Checking access"],
  ["进入 Ontology Studio", "Open Ontology Studio"],
  ["进入 Analytic Agent", "Open Analytic Agent"],
  ["切换解决方案", "Switch solution"],
  ["选择解决方案", "Select solution"],
  ["搜索解决方案", "Search solutions"],
  ["名称或 ID", "Name or ID"],
  ["查看全部解决方案", "View all solutions"],
  ["新建解决方案", "Create solution"],
  ["全部解决方案", "All Solutions"],
  ["创建、复制和管理 Ontology Solution。", "Create, copy, and manage Ontology Solutions."],
  ["解决方案筛选", "Filter solutions"],
  ["使用中", "Active"],
  ["已归档", "Archived"],
  ["搜索", "Search"],
  ["名称或 Solution ID", "Name or Solution ID"],
  ["名称、ID 或定义", "Name, ID, or definition"],
  ["全部状态", "All statuses"],
  ["解决方案", "Solution"],
  ["工作版本", "Working version"],
  ["运行状态", "Runtime status"],
  ["最近更新", "Last updated"],
  ["操作", "Actions"],
  ["参考方案副本", "Reference solution copy"],
  ["空白创建", "Created from blank"],
  ["导入创建", "Created by import"],
  ["参考方案", "Reference solution"],
  ["已激活", "Active"],
  ["Runtime 已绑定", "Runtime bound"],
  ["已安装", "Installed"],
  ["打开", "Open"],
  ["在 Agent 中打开", "Open in Agent"],
  ["编辑信息", "Edit details"],
  ["归档", "Archive"],
  ["恢复", "Restore"],
  ["永久移除", "Delete permanently"],
  ["管理", "Manage"],
  ["副本", "Copy"],
  ["没有匹配的解决方案", "No matching solutions"],
  ["调整搜索条件，或创建一个新的 Solution。", "Adjust the search criteria or create a new Solution."],
  ["版本内容保持不可变", "Version content is immutable"],
  ["编辑发生在 Draft；归档只隐藏日常工作入口。永久移除不会擦除依法需要保留的发布与审计工件。", "Edits occur in a Draft. Archiving only hides the day-to-day workspace entry. Permanent removal does not erase publication and audit artifacts subject to retention requirements."],
  ["新建", "Create"],
  ["方案", "Solution"],
  ["参考方案 · 只读", "Reference solution · Read-only"],
  ["浏览已确认的内容与运行结果；要重新构建或修改，请先复制为独立方案。", "Browse reviewed content and runtime results. Copy it to an independent solution before rebuilding or editing."],
  ["查看知识图谱", "View knowledge graph"],
  ["复制为可编辑方案", "Copy as editable solution"],
  ["模型和运行状态可查看；新建、修改、审核、发布与激活已锁定。", "Models and runtime status are viewable; create, edit, review, publish and activate actions are locked."],
  ["你可以查看解决方案，但新建、修改、删除和发布需要配置人员权限。", "You can view solutions; creating, editing, deleting and publishing require Operator access."],
  ["知识图谱", "Knowledge Graph"],
  ["浏览对象、关系、指标和规则；选择节点或连线查看定义、来源与影响。", "Explore objects, relationships, metrics and rules. Select a node or edge to inspect its definition, evidence and impact."],
  ["搜索图谱", "Search graph"],
  ["对象、指标或 ID", "Object, metric or ID"],
  ["节点类型", "Node type"],
  ["全部", "All"],
  ["对象", "Object"],
  ["指标", "Metric"],
  ["规则", "Rule"],
  ["关联布局", "Relationship layout"],
  ["分层布局", "Layered layout"],
  ["显示待复核候选", "Show review candidates"],
  ["只看一跳影响", "Show first-degree impact only"],
  ["新建对象", "Create object"],
  ["新建关系", "Create relationship"],
  ["选择节点或关系", "Select a node or relationship"],
  ["查看定义、来源与影响；资产变更统一进入目录表单。", "Inspect definitions, evidence and impact. Asset changes use the catalog form."],
  ["影响预检", "Impact preview"],
  ["上游", "Upstream"],
  ["下游", "Downstream"],
  ["相邻对象", "Adjacent objects"],
  ["正式节点可见", "canonical nodes visible"],
  ["待复核候选", "review candidates"],
  ["待复核对象", "Review candidate object"],
  ["待复核指标", "Review candidate metric"],
  ["待复核规则", "Review candidate rule"],
  ["指标与业务规则", "Metrics & Business Rules"],
  ["一个 Solution 的完整指标目录。选择指标查看口径、公式、粒度、单位和依赖。", "The complete metric catalog for this solution. Select a metric to inspect its definition, formula, grain, unit and dependencies."],
  ["搜索指标", "Search metrics"],
  ["治理状态", "Governance status"],
  ["来源", "Sources"],
  ["责任人", "Owner"],
  ["版本", "Version"],
  ["查看完整 typed contract", "View complete typed contract"],
  ["创建修订草稿", "Create revision draft"],
  ["继续编辑", "Continue editing"],
  ["选择一项资产", "Select an asset"],
  ["详情、依赖与治理动作会显示在这里。", "Details, dependencies and governance actions appear here."],
  ["没有匹配资产", "No matching assets"],
  ["调整搜索或状态筛选；也可以创建第一项。", "Adjust the search or status filter, or create the first asset."],
  ["当前 Draft", "Current Draft"],
  ["可追踪语义资产", "traceable semantic assets"],
  ["来源定义", "Source definitions"],
  ["原始材料转写层", "source transcription layer"],
  ["尚未进入权威模型", "not yet canonical"],
  ["Agent 已支持", "Agent supported"],
  ["已有执行能力", "runtime capabilities available"],
  ["资产", "Asset"],
  ["状态", "Status"],
  ["责任 / 来源", "Owner / Evidence"],
  ["项证据", "evidence items"],
  ["本次分析结果", "Analysis results"],
  ["查看计算口径与证据", "View calculation semantics and evidence"],
  ["分析期间", "Analysis period"],
  ["维度", "Dimensions"],
  ["整体", "Overall"],
  ["口径决策", "Semantic decisions"],
  ["正在加载分析语境…", "Loading analytic context…"],
  ["当前解决方案尚未激活，无法开始分析。", "The current solution is not active, so analysis cannot start."],
  ["已激活样例数据", "Active sample data"],
  ["当前分析语境", "Current analytic context"],
  ["数据期间", "Data period"],
  ["分析角色", "Analysis role"],
  ["示例问题", "Suggested Questions"],
  ["询问 Cash Trading 数据", "Ask about Cash Trading data"],
  ["可以直接输入问题，或从左侧选择一个示例。", "Enter a question directly or choose a suggested question on the left."],
  ["正在分析 Ontology 与样例数据…", "Analyzing the ontology and sample data…"],
  ["本次运行信息", "Run information"],
  ["输入分析问题", "Enter an analysis question"],
  ["分析中…", "Analyzing…"],
  ["发送", "Send"],
  ["你", "You"],
  ["正在核验 selected solution…", "Validating the selected solution…"],
  ["正在 materialize exact ontology package…", "Loading the exact ontology package…"],
  ["无法打开所选 solution", "Unable to open the selected solution"],
  ["Catalog 或 exact runtime 未通过验证。", "The catalog or exact runtime did not pass validation."],
  ["所选 solution 不在目录中", "The selected solution is not installed"],
  ["正在核验产品上下文…", "Validating product context…"],
  ["无法确认当前运行语境", "Unable to confirm the current runtime context"],
  ["重新检查", "Retry"],
  ["构建和治理业务语义", "Build and govern business semantics"],
  ["登记来源材料，构建并复核 Ontology Solution，再发布给 Analytic Agent 使用。", "Register source materials, build and review an Ontology Solution, then publish it for the Analytic Agent."],
  ["当前生效的分析语境", "Active analytic context"],
  ["基于当前已激活的 Runtime Snapshot 查询、分析并追踪证据。", "Query, analyze and trace evidence against the active runtime snapshot."],
  ["取消", "Cancel"],
  ["保存", "Save"],
  ["关闭", "Close"],
  ["删除", "Delete"],
  ["编辑", "Edit"],
  ["确认", "Confirm"],
  ["发布", "Publish"],
  ["激活", "Activate"],
  ["返回", "Back"],
];

const sortedTranslations = [...phraseTranslations].sort((left, right) => right[0].length - left[0].length);
const exactTranslations = new Map(phraseTranslations);

export function translateUiText(value: string): string {
  const standaloneUnit = value.trim();
  const exact = exactTranslations.get(standaloneUnit);
  if (exact) {
    const leading = value.match(/^\s*/)?.[0] ?? "";
    const trailing = value.match(/\s*$/)?.[0] ?? "";
    return `${leading}${exact}${trailing}`;
  }
  if (standaloneUnit === "无") return value.replace(standaloneUnit, "None");
  if (standaloneUnit === "个" || standaloneUnit === "条" || standaloneUnit === "项") {
    return value.replace(standaloneUnit, "items");
  }
  if (standaloneUnit === "份") return value.replace(standaloneUnit, "files");
  let translated = value;
  // Two deterministic passes let long phrases remain authoritative while the
  // compatibility layer also resolves mixed legacy fragments produced by a
  // first replacement (for example, "Business Requirements与分析流程").
  for (let pass = 0; pass < 2; pass += 1) {
    for (const [zh, en] of sortedTranslations) translated = translated.replaceAll(zh, en);
  }
  translated = translated
    .replace(/(\d+)\s*个/g, "$1 ")
    .replace(/(\d+)\s*条/g, "$1 ")
    .replace(/(\d+)\s*项/g, "$1 ")
    .replace(/(\d+)\s*份/g, "$1 ");
  return translated;
}

function initialLocale(): UiLocale {
  if (typeof window === "undefined") return "zh";
  const queryLocale = new URLSearchParams(window.location.search).get("lang");
  if (queryLocale === "en" || queryLocale === "zh") return queryLocale;
  return window.localStorage.getItem("atlas-ui-locale") === "en" ? "en" : "zh";
}

export function UiLocaleProvider({ children }: { children: ReactNode }) {
  const [locale, updateLocale] = useState<UiLocale>(initialLocale);
  const setLocale = (next: UiLocale) => {
    updateLocale(next);
    window.localStorage.setItem("atlas-ui-locale", next);
    const url = new URL(window.location.href);
    url.searchParams.set("lang", next);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  };
  useEffect(() => { document.documentElement.lang = locale === "en" ? "en" : "zh-CN"; }, [locale]);
  const value = useMemo<UiLocaleContextValue>(() => ({
    locale,
    setLocale,
    t: (zh, en) => locale === "en" ? en : zh,
    name: (localized) => locale === "en"
      ? localized.en || localized.zh || ""
      : localized.zh || localized.en || "",
  }), [locale]);
  return <UiLocaleContext.Provider value={value}>{children}</UiLocaleContext.Provider>;
}

export function useUiLocale(): UiLocaleContextValue {
  return useContext(UiLocaleContext);
}

const originalText = new WeakMap<Text, string>();
const translatedAttributes = ["aria-label", "placeholder", "title"] as const;

function localizeElement(root: ParentNode, locale: UiLocale) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let current = walker.nextNode();
  while (current) {
    const text = current as Text;
    const parent = text.parentElement;
    if (parent && !parent.closest("code, pre, textarea, script, style, [data-no-ui-translate]")) {
      const previousOriginal = originalText.get(text);
      const currentValue = text.nodeValue ?? "";
      const previousTranslation = previousOriginal ? translateUiText(previousOriginal) : null;
      const source = previousOriginal && (currentValue === previousOriginal || currentValue === previousTranslation)
        ? previousOriginal
        : currentValue;
      originalText.set(text, source);
      const next = locale === "en" ? translateUiText(source) : source;
      if (currentValue !== next) text.nodeValue = next;
    }
    current = walker.nextNode();
  }
  if (root instanceof Element) {
    [root, ...root.querySelectorAll("*")].forEach((element) => {
      translatedAttributes.forEach((attribute) => {
        const originalKey = `uiOriginal${attribute.replace(/(^|-)([a-z])/g, (_, __, letter: string) => letter.toUpperCase())}`;
        const currentValue = element.getAttribute(attribute);
        if (!currentValue) return;
        const stored = (element as HTMLElement).dataset[originalKey];
        const source = stored && (currentValue === stored || currentValue === translateUiText(stored)) ? stored : currentValue;
        (element as HTMLElement).dataset[originalKey] = source;
        element.setAttribute(attribute, locale === "en" ? translateUiText(source) : source);
      });
    });
  }
}

export function LegacyUiLocalizer() {
  const { locale } = useUiLocale();
  useEffect(() => {
    const root = document.getElementById("root");
    if (!root) return undefined;
    let scheduled = false;
    const apply = () => {
      scheduled = false;
      localizeElement(root, locale);
    };
    const schedule = () => {
      if (scheduled) return;
      scheduled = true;
      window.requestAnimationFrame(apply);
    };
    apply();
    const observer = new MutationObserver(schedule);
    observer.observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: [...translatedAttributes] });
    return () => observer.disconnect();
  }, [locale]);
  return null;
}

export function LanguageSwitch() {
  const { locale, setLocale } = useUiLocale();
  return <div className="language-switch" role="group" aria-label={locale === "en" ? "Interface language" : "界面语言"}>
    <button type="button" className={locale === "zh" ? "is-active" : undefined} aria-pressed={locale === "zh"} onClick={() => setLocale("zh")}>中文</button>
    <button type="button" className={locale === "en" ? "is-active" : undefined} aria-pressed={locale === "en"} onClick={() => setLocale("en")}>EN</button>
  </div>;
}
