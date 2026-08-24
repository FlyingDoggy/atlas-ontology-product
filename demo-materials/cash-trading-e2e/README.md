# Cash Trading Demo Pack

本目录服务于 Atlas Ontology 产品的 Cash Trading 演示。业务输入来自 Deloitte HK；样例数据为构造数据，不代表 HKEX 生产数据。

本次演示明确分成两条路径：

1. **构建入口演示**：展示如何新建 Solution、批量选择材料、确认用途和启动 Ontology Builder；现场不真正上传，也不等待构建。
2. **结果与分析演示**：直接打开已经复核的 Cash Trading Ontology Package，浏览完整语义资产和知识图谱，再进入 Analytic Agent 查询样例数据。

## 目录

- `01_Deloitte_HK_Input/`：Deloitte HK 提供的四份材料副本，内容未修改。
- `02_Product_Supplement/`：Atlas 编写的可选参考 SQL；不是 Deloitte HK 或 HKEX 原始材料。
- `03_Review_Reference/`：针对八项指标、维度、对象、关系和字段映射整理的 Review Pack。它是内部复核基线，空白确认栏不代表 Deloitte HK/HKEX 已确认。
- `source-manifest.json`：文件身份、来源、用途、校验和与限制。
- `假设与补充记录.md`：标准化、推断、构造内容和待确认事项。
- `Cash_Trading_E2E_Demo_操作流程.md`：现场演示脚本。
- `Cash_Trading_Demo_问题与期望答案.md`：Agent 初始问题、期望数据与讲解口径。
- `Cash_Trading_Demo_使用手册.md`：产品、材料、截图和操作说明。
- `../../output/pdf/Atlas_Ontology_Cash_Trading_Demo_使用手册.pdf`：完成渲染验收的中文 PDF 手册。
- `LOCAL_ACCEPTANCE_REPORT.md`：本地合同、测试、Agent 和浏览器验收记录。

## 构建入口使用的材料

| 材料 | 入口中的用途 | 现场动作 |
| --- | --- | --- |
| `HKEX_Analytics_Scenario_Input_Template_with_ADT_Reference_v20260819.xlsx` | 需求与分析流程；指标逻辑 | 展示文件和说明，不提交 |
| `order_trade_activities_data_dictionary.xlsx` | 数据模型；字段字典与枚举 | 展示文件和说明，不提交 |
| `cash_trading_sample_data.xlsx` | 构造型样例数据 | 展示文件和说明，不提交 |
| `email screenshot.jpeg` | 来源与限制证据 | 可登记归档，不参与自动抽取 |
| `reference_controls.sql` | 现有 SQL（可选） | 说明为 Atlas 补充，不冒充客户输入 |

Review Pack 不作为首次 Build 输入。它用于说明预构建 Package 如何记录口径复核、内部假设和待 Deloitte HK 确认项。

## 演示完成标准

- “从材料构建”入口清楚展示所需材料、批量上传和后续步骤。
- 预构建 Cash Trading Package 可查看对象、属性、关系、指标、维度、规则、数据源、映射、Join、来源、假设和知识图谱。
- Package 中包含八项 Deloitte HK 指标，且每项均有可重现的样例计算结果和证据引用。
- Analytic Agent 使用 DeepAgent 运行时，读取同一 Active Package 和样例数据后回答问题。
- 用户可展开查看指标 ID、期间、维度、来源、口径决策和 Query hash。
- 页面和讲解始终说明：样例数据为构造数据，Review Pack 是内部基线，待确认项不是客户事实。

## 不在本次演示范围

- 现场真实执行从任意文档到发布版本的长时间自动构建。
- 通用 Builder 的生产级准确率证明。
- HKEX 数据接入、IAM、网络、环境审批和 Knowledge Center 集成。
- EC2 发布；本地版本需先由 Muyu 验收。
