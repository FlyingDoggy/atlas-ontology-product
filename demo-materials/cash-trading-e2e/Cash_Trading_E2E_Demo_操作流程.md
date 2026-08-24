# Cash Trading Demo 操作流程

## 一、Demo 主线

整场演示控制在 12–15 分钟，按照下列顺序完成：

`构建入口 → 预构建 Package → 知识图谱 → Analytic Agent → 答案与证据`

不要在现场真正上传或等待自动构建。构建入口用于说明通用产品如何接收新案例；Cash Trading Package 用于展示已经形成并复核过的结果。

## 二、演示前检查

1. 本地服务已启动，浏览器使用桌面端 100% 缩放。
2. Solution Directory 中可以看到 Cash Trading Solution，且 Runtime 为 Active。
3. Analytic Agent 默认选中同一个 Cash Trading Solution。
4. `01_Deloitte_HK_Input/` 中四份文件可以在 Finder 中打开。
5. 从“问题与期望答案”中挑选 3–4 个问题；至少包括一个趋势问题和一个证据展开。

## 三、展示通用 Build 入口（约 2 分钟）

1. 进入 `Ontology Studio > 解决方案目录`。
2. 点击“新建解决方案”。
3. 保持默认选项“从材料构建”。
4. 指出入口清楚列出四类材料：需求与分析流程、指标逻辑、数据模型与字典、现有 SQL（可选）。
5. 解释现场准备的文件及用途：
   - 需求模板 Excel 同时承担需求与指标逻辑；
   - 数据字典 Excel 承担数据模型和字段字典；
   - 样例数据 Excel 用于类型、枚举、粒度和计算验证；
   - 邮件截图只用于归档来源与限制；
   - 参考 SQL 是 Atlas 可选补充，不是客户材料。
6. 说明创建后会进入批量材料登记，随后确认每个文件用途、选择 Ontology 输出语言并启动 Builder。
7. **到此停止，不点击创建、不上传、不触发真实构建。**关闭对话框，返回 Solution Directory。

建议讲解：

> 这个入口面向任何新业务案例。原始材料的语言不限制 Build；用户可以在启动时指定 Ontology 的统一输出语言。LLM 和构建工具形成待复核 Package，最终发布仍需人工确认。

## 四、打开预构建 Cash Trading Package（约 5 分钟）

1. 在 Solution Directory 打开 Cash Trading Solution。
2. 在“概览”确认五类资产及数量：业务模型；指标、维度与规则；数据语义；分析能力；证据与假设。
3. 进入“语义模型”：浏览对象和属性、关系、八项核心指标、维度和资格/口径规则。
4. 进入“知识图谱”，保持“全部”视图：
   - 展示对象、关系、指标、维度和数据资产的连接；
   - 点击节点查看定义、来源和关联资产；
   - 强调图是 Package 的另一种浏览方式，不是单独的事实权威。
5. 进入“数据”：查看数据源与 Schema、物理字段到语义属性的 Mapping、Join 和语义关联。
6. 进入“证据与假设”相关入口，指出 Deloitte HK 原始来源、Review Pack 内部复核基线、Atlas 标准化与构造内容，以及待确认项目。

建议讲解：

> Package 不是一张知识图。它同时包含业务对象、指标口径、可分析维度、数据映射、来源和假设。Agent 消费的是这个版本化 Package，而不是截图或一段 prompt。

## 五、进入 Analytic Agent（约 5 分钟）

1. 点击顶部“进入 Analytic Agent”。
2. 确认页面标题仍是 Cash Trading，Ontology 版本和 Runtime 状态可见。
3. 从左侧选择问题，点击“发送”。建议顺序：
   - `What was the order rejection rate from 2026-08-03 to 2026-08-07?`
   - `What were p50, p95 and p99 trade capture latency from 2026-08-03 to 2026-08-07?`
   - `Show the daily potential self-trade rate from 2026-08-03 to 2026-08-07.`
4. 对任一答案展开“查看计算口径与证据”，展示 Ontology Metric ID、分析期间和维度、来源与口径决策、Query hash。
5. 展开“本次运行信息”，说明 Package 版本、Active Snapshot、Execution 和模型运行信息属于同一次分析。

建议讲解：

> DeepAgent 负责理解问题、选择工具和组织解释；数值由 Ontology 定义的确定性查询工具计算。这样既保留 LLM 对开放问题的理解能力，又不会让模型凭空编造业务数字。

## 六、必须主动说明的限制

- 全部数据是构造型样例数据，不是 HKEX 生产数据。
- Review Pack 的 Review Conclusion / Comments 为空，因此属于内部基线，不是 Deloitte HK/HKEX 正式确认。
- Potential self-trade 是排查候选，不能被表述为违规或市场操纵结论。
- M-02 与 M-05 在当前样例中为 0，原因是 EXECUTE 事件无法可靠关联到 NEW 生命周期；这是输入数据关系缺口，不是系统把缺失解释成业务结论。
- 现场演示的是 Build 入口和预构建结果，不宣称当场跑完任意文档的自动构建。

## 七、现场异常时的降级

1. LLM 调用失败：Agent 使用同一 Ontology Semantic Engine 返回确定性结果，并显示 fallback；不要重载 Package。
2. 单个问题超时：切换到 M-01、M-03、M-06、M-07 或 M-08 的登记问题重试。
3. 图谱渲染卡顿：切换节点类型后再回到“全部”，或展示列表/关系详情；Package 内容不受影响。
4. 本地服务异常：不要临时改用旧 EC2 版本；记录问题并停止技术演示。
