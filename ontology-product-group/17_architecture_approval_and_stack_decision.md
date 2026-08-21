# Ontology Analytics Product Family — Architecture Approval & Implementation Stack Decision

状态：`Approved / Implementation Authorized`

日期：2026-08-20

Decision Owner：Muyu

## 1. Decision

Decision Owner批准`16_common_product_and_ontology_package_architecture.md`的总体产品与架构方向，并授权进入开发。

以下成熟技术不再等待Final Generalization或Gate B证据，直接成为通用产品 implementation baseline：

- Frontend：TypeScript strict + React + Vite，采用vertical-slice/route-by-route迁移；
- Product state：PostgreSQL 17 + SQLAlchemy + Alembic + psycopg；
- Immutable artifact store：AWS S3-compatible exact-version object storage；local/test使用MinIO；
- Deployment：Kubernetes；当前自有EC2可使用k3s作为demo cluster，目标客户环境保持标准K8s manifests/Helm-compatible配置。

## 2. Boundaries retained

- PostgreSQL只承载产品状态、metadata、authority/read models、execution/evidence envelopes，不承载客户事实表；事实数据仍走Parquet + DuckDB或企业warehouse adapter。
- S3 digest/versioning证明artifact完整性与版本定位，不产生semantic、truth、activation或release authority。
- React是产品实现栈，不是portability proof；浏览器继续保持authority=0，所有事实与发布判断来自backend。
- Kubernetes是部署底座，不自动产生HA、SLA、生产IAM、HKEX target readiness或production-ready claim。
- 当前ADT constructed-synthetic demo必须持续通过；迁移不得建立第二套truth/calculator/release path。
- Listing仍是第二个materially-different synthetic falsifier；只有双场景证据允许提升common primitive。

## 3. Delivery consequence

- 原`21–36 active pd`只覆盖旧的D-1/D0/D1 core-only hypothesis，现因React/PostgreSQL/S3/K8s进入baseline而撤回；不得继续作为当前总估算。
- 实现按端到端vertical slices推进，不按React、数据库、对象存储、K8s四条水平工程分别建设。
- Docker Compose和filesystem/SQLite adapter仅作为当前已部署demo、迁移验证或isolated test compatibility，不是新产品的目标运行authority。
- 每条slice必须同时包含可演示用户路径、schema/API、persistence/artifact、deployment、tests、rollback和claim boundary。

## 4. Authority ceiling

本决定授权开发和内部部署验证，不等于common product已经实现，不产生`PORTABLE_PASS`、Stage 1 conformance、HKEX validation、production readiness或External GO。外部demo发布仍需要单独GO判断。
