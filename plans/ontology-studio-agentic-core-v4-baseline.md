# Agentic Core v4 开发基线

冻结日期：2026-08-23  
父提交：`581fa868aa9cb6227c8be85fff58e140c743ab04`  
目的：在 Agentic Core 开发前保存当前 v1/E2E 改动、Cash exact inputs、已知失败事实与回退点。

## 1. Repository

- Remote：`FlyingDoggy/atlas-ontology-product`
- Visibility：`PRIVATE`
- 冻结分支：`feature/studio-build-e2e-v1`
- Agentic Core 开发必须从本基线提交切出独立分支。

## 2. Cash exact input checksums

| 文件 | SHA-256 |
|---|---|
| `HKEX_Analytics_Scenario_Input_Template_with_ADT_Reference_v20260819.xlsx` | `fc0452d06258c8bc6c5ffce1475604fe6dc9cb8706672a257e5582e1badc5fbf` |
| `order_trade_activities_data_dictionary.xlsx` | `2004452fe7030770756b1b6fca76605c20c280ea53b8c9fc0bb45fea10cca29a` |
| `cash_trading_sample_data.xlsx` | `d301e6b6bc5a2f80237917370d4e41b960d44692e37bca245300dcc814a4a018` |
| `email screenshot.jpeg` | `488ed1d5b718337236bca5b812bd6606d73888e5028d347671c2569bc798fb9c` |
| `reference_controls.sql` | `32457c30e9853c48ccea851322e7892e74e7a074ba2d45af80650741d6bcfdd5` |

前四份为 Deloitte HK 提供；SQL 为 Atlas product-owned synthetic supplement。不得改变 provenance 标签。

## 3. 回归状态

以下 targeted tests 在本基线冻结前通过：

```text
tests/test_studio_builder.py
tests/test_studio_construction.py
tests/test_studio_reviewer.py
tests/test_studio_source_projection.py
tests/test_skill_packages.py
36 passed
```

Frontend baseline：

```text
13 test files / 92 tests passed
TypeScript check and Vite production build passed
Known non-blocking warning: main JS chunk ~890 KB before gzip (~254 KB gzip)
```

## 4. Known-failing correctness baseline

- 旧链路能生成大量 Candidate 并走完形式上的 Review/Validation/Release；
- 严格门禁复核的最近失败 Run 为 `ontology.custom.2ec30bf44a55` / task suffix `98a7568a`；
- 141 个 Candidate、75 个旧定义下 compile eligible；
- 八个正式 Metric 的 `proposed_operation` 均为空，实际可发布正式 Metric 为 0；
- Builder 声称缺失的多个字段实际存在于 Deloitte 数据字典；
- `SUM(string)` 负向 mutation 仍可获得当前 semantic validation PASS。

因此：旧 PASS 只证明合同形状和流程回归，不证明 Cash 指标正确。Agentic Core v4 必须从该失败事实起步，不允许把旧 reference package 或 packaged fallback 当作新构建产出。
