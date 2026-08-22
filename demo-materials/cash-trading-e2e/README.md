# Cash Trading E2E Demo Material Pack

本目录是 Atlas Ontology Studio 新建 Ontology Solution 的唯一标准 E2E 演示材料包。业务案例来自 Deloitte HK 提供的 Cash Trading 输入，不是 ADT，也不是另行虚构的业务场景。

## 目录结构

- `01_Deloitte_HK_Input/`：Deloitte HK 提供的四份原始材料副本。文件内容保持不变。
- `02_Product_Supplement/`：产品团队为补齐可执行 SQL 证据而提供的演示补充材料，不属于 Deloitte HK 或 HKEX 原始输入。
- `source-manifest.json`：文件身份、来源、逻辑角色、校验和与使用限制。
- `假设与补充记录.md`：所有标准化、推断、构造数据和产品补充的可审计记录。
- `Cash_Trading_E2E_Demo_操作流程.md`：从空白 Solution 到发布版本的演示步骤。

## 演示原则

1. 必须从“新建解决方案”开始，不得复制现有 Cash Trading Demo 的 Ontology 产出。
2. 五个物理文件一次性上传；一个文件可以登记为多个逻辑来源角色。
3. 构建语言选择“中文”，保证 Ontology 的展示名称、说明和生成内容语言一致。
4. LLM、Builder 和 Review Skill 只能生成待复核 Candidate；未经人工处置的内容不能进入 Draft。
5. 发布前必须通过确定性验证。LLM 置信度不能替代证据、编译和发布验证。
6. `reference_controls.sql` 必须始终显示为“产品补充 / 构造材料”，不得表述为 Deloitte HK 或 HKEX 现有 SQL。
7. 样例数据是构造型演示数据，不得表述为真实 HKEX 交易数据。

## 当前验证状态

- 本地复核日期：2026-08-23
- 输入身份：5 个物理文件，计划登记为 7 个逻辑来源
- 构建语言：中文
- 旧链路曾完成 Candidate → Draft → Validation → Release 的形式流程；旧参考 Solution 为 `ontology.custom.eb751f5edeaa`
- 新增严格门禁后，该旧结果**不能证明 Cash Ontology 构建正确**：八个正式 Metric 没有全部形成语义闭合、可计算的强类型操作；Candidate 数量和普通 Validation PASS 不能替代公式、字段、单位、粒度、过滤、映射、Join 与样例执行正确性
- 本材料包因此是 Agentic Core v4 的固定 E2E 输入和 known-failing 基线，不是“已通过”的产品证明

只有在 `ontology-studio-agentic-core-v4-final.md` 的 Slice B、C、D 门禁全部通过后，才能把新 Run 记录为可演示基线。正式演示仍必须从另一个 Blank Solution 重新执行完整链路。
