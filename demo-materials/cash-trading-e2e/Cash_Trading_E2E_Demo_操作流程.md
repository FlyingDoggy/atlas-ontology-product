# Cash Trading E2E Demo 操作流程

## 1. Demo 目标

在 Atlas Ontology Studio 中从空白 Solution 开始，上传 Deloitte HK 的 Cash Trading 材料与一份明确标识的产品补充 SQL，自动生成待复核 Ontology Candidate，经人工复核、确定性验证后发布 `0.1.0` 版本。

这次 Demo 证明的是一条通用产品链路，不是展示预置 Cash Trading 页面：

`原始材料 → 来源登记 → 自动构建 → 人工复核 → Draft → 验证 → 发布`

## 2. 演示前准备

从本目录选择以下五个文件：

1. `01_Deloitte_HK_Input/HKEX_Analytics_Scenario_Input_Template_with_ADT_Reference_v20260819.xlsx`
2. `01_Deloitte_HK_Input/order_trade_activities_data_dictionary.xlsx`
3. `01_Deloitte_HK_Input/cash_trading_sample_data.xlsx`
4. `01_Deloitte_HK_Input/email screenshot.jpeg`
5. `02_Product_Supplement/reference_controls.sql`

演示口径：前四份由 Deloitte HK 提供；第五份是 Atlas 产品团队补充的构造 SQL。样例数据不是 HKEX 生产数据。

## 3. 新建空白 Solution

1. 登录后进入“解决方案目录”。
2. 点击“新建解决方案”。
3. 选择“空白解决方案”。不要复制 ADT 或现有 Cash Trading Demo。
4. 填写：
   - 中文名称：`现金市场订单与成交活动监控`
   - 英文名称：`Cash Market Order and Trading Activity Monitoring`
   - Solution ID：使用系统建议值，或填写新的唯一 ID。
   - 描述：`基于日终订单与成交活动数据，为市场监察、市场和交易团队提供指标、趋势、异常与证据化分析。`
5. 创建后进入新 Solution 的“输入与证据”。

## 4. 批量登记来源材料

1. 打开“输入与证据 > 来源材料”。
2. 点击“登记来源材料”。
3. 一次选择上述五个文件。
4. 为每个文件确认逻辑角色：

| 文件 | 逻辑角色 | 说明 |
| --- | --- | --- |
| 需求与指标 Excel | 需求文档（转写）＋指标逻辑（转写） | 一个物理文件登记为两个逻辑来源 |
| 数据字典 Excel | 数据模型＋Data Dictionary / Sample | 包含模型概览与字段 Sheet |
| 样例数据 Excel | Data Dictionary / Sample | 用于结构、类型、枚举和粒度观察 |
| 邮件截图 | 其他材料 | 只归档，不作为自动构建权威 |
| 参考 SQL | 现有 SQL | 描述中写明“产品补充 / 构造材料” |

5. 检查接收回执：应为 `5 个物理文件 / 7 个逻辑来源`。
6. 在每个来源详情中可查看身份、校验和、版本、解析状态与预览。

## 5. 启动自动构建

1. 打开“构建与复核 > 构建运行”。
2. 选择刚登记的全部 7 个逻辑来源版本。
3. Ontology 输出语言选择“中文”。这控制生成名称和描述的语言，不改变稳定技术 ID。
4. 点击“开始构建”。
5. 页面离开后，使用全局“任务中心”查看跨 Solution 的任务状态；点击任务可返回当前 Solution 的构建详情。
6. 构建过程中重点说明：
   - Orchestrator 决定阶段、输入和允许调用的工具；
   - LLM 配合 Build Skill 提取对象、属性、关系、指标、规则、映射和缺口 Candidate；
   - 每个 Candidate 必须带来源锚点、风险和可编译状态；
   - Candidate 不会直接成为权威 Draft。

## 6. 人工复核 Candidate

1. 构建完成后打开“复核队列”。
2. 逐项查看 Candidate 的：
   - 类型与拟议内容；
   - 来源文件和具体锚点；
   - 与当前 Draft 的差异；
   - 编译结果、机器发现和风险。
3. 使用四种处置：
   - “接受并应用”：证据直接支持、内容准确、可编译；
   - “修改后应用”：证据支持但名称、定义或绑定需要可解释修正；
   - “拒绝”：无证据、错误、重复或不满足合同；
   - “暂缓”：确实需要业务方补充或确认。
4. “本页填入保守建议”只帮助填入建议，不会保存、发布或激活。
5. 每处理一批点击“保存复核进度”。保存后再次导航不应出现“未保存”提示。
6. 所有 Candidate 处置完成后，点击“完成本轮复核并应用”。
7. 系统生成新的工作 Draft，并提供业务模型、指标与规则、映射与关联等结果入口。

演示时不得为了清零队列而机械接受。对缺少实体端点、来源锚点无效或依赖未闭合的 Candidate 应拒绝或暂缓。

## 7. 检查构建结果

至少抽查以下内容：

1. “语义模型 > 业务模型”：订单活动、成交活动、参与者、证券、交易日等对象及关系。
2. “语义模型 > 指标与规则”：八项 Cash Trading 指标、公式、粒度、维度、资格规则和缺口。
3. “数据 > 数据源与 Schema”：订单、成交和参考数据源及字段合同。
4. “数据 > 映射与关联”：物理字段到语义属性/指标输入的绑定。
5. “数据 > SQL 合同”：产品补充 SQL 的来源身份和可执行合同。
6. “输入与证据”：任一语义资产都能追溯到 exact source version 与证据锚点。

## 8. 验证与发布

1. 打开“质量与发布 > 验证结果”。
2. 验证当前 exact Draft。验证至少检查：
   - Schema 与语义合同；
   - 关系端点和依赖闭包；
   - 指标公式、输入绑定和资格规则；
   - 来源锚点、语言一致性和发布前阻断项。
3. 只有验证结果为 PASS 才能继续。
4. 打开“质量与发布 > 版本与审批”。
5. 发布首个语义版本 `0.1.0`，填写发布说明：
   `基于 Deloitte HK Cash Trading 输入构建；包含产品补充参考 SQL；样例数据为构造数据。`
6. 发布不会自动替换 Agent 的运行版本。若 Demo 还要进入 Agent，在“交付与运行”完成准备、认证、激活与验证，再点击“进入 Analytic Agent”。

## 9. Demo 验收标准

- 新建的是空白 Solution，而非预置 Demo 复制品。
- 五个物理文件成功登记为七个逻辑来源。
- 输出语言为中文，展示内容不再随机中英文混排。
- 自动构建任务可在任务中心追踪并返回 Solution。
- Candidate 经人工复核后才进入 Draft。
- 模型、指标、映射和 SQL 合同均有实际产出，不是空页面。
- 来源锚点可追溯，产品补充和构造数据有显式标签。
- 验证 PASS 后成功发布 `0.1.0`。
- 若进入 Agent，Agent 使用的是明确激活的已发布版本。

## 10. 当前参考结果与限制

旧本地链路曾形成以下形式结果：

- Solution：`ontology.custom.eb751f5edeaa`
- Run：`construction-run.48c7f6eee2c7436a906ffac9234b6f0d`
- Candidate：115
- 旧验证：PASS
- 旧发布版本：`0.1.0`

这组结果现在只用于回归和故障对照，**不能作为 E2E Demo 的合格结果**。严格复核已经证明：普通合同验证可以接受类型合法但业务计算错误的指标，旧 Builder 也没有让八个正式 Metric 全部形成语义闭合的可计算操作。

正式演示前必须以 Agentic Core v4 新建 Blank Solution，并通过：完整 Evidence recall、八指标 semantic signature、负向 mutation、人工复核、CAS Draft、Validation、Release、Activation 和真实 Agent 查询门禁。
