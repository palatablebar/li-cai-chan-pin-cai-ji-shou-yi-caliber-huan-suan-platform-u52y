# 理财产品采集与收益口径换算台（`yieldbook`）

> 数据采集 / 产品要素归一 · 银行财富管理部产品组内部目录系统。
> 原生 HTML/CSS/JS（ES Modules）+ Python FastAPI + Celery worker + PostgreSQL + Redis，5 个容器一键起。

## 1. 场景

- **模拟客户**：江城银行财富管理部产品组 4 人，代销 68 只理财 / 基金产品，8 家合作机构。
- **现有工作流**：每天从机构官网与 APP 手工抄产品要素到 Excel，用计算器把「七日年化 / 万份收益 / 业绩基准 / 近 1 年年化」
  换算成同一个口径，再在微信群里发客户，排名靠肉眼比。
- **三个痛点**：
  1. 四种收益口径混用：现金类看万份收益、净值类看区间年化、有些只给业绩基准区间，客户拿到的数不可比；
  2. 起购金额、风险等级经常漏填，产品要素不完整就上架；
  3. 同类产品没有统一分组，无法回答「这只在同类里排第几」。
- **上下游**：机构官网/APP（采集）→ 本系统（产品入库 → 报价归一 → 同类排名 → 关注提醒）→ 客户经理与客户。
- **一天的工作剧本**：
  1. 08:50 口径专员打开「换算与导入」，确认 5 个交易日 340 条报价齐全；
  2. 09:00 管理员发起一次口径换算，68 只产品产出 68 条可比年化，其中 9 条口径缺失标 unknown；
  3. 09:10 打开「对比榜」，固定收益类 · 31-180 天分组第一名是「江城添利 120 天」3.05%；
  4. 09:20 复核「江城现金宝」：万份收益 0.62 → 可比 2.263%，口径 wanfen，确认复核；
  5. 09:30 查看「关注与到期」，7 天内到期 3 条，逐条标记跟进；
  6. 16:30 管理员导出对比榜 CSV（68 行）发给团队，审计日志留存导出记录。

## 2. 角色与权限

| 角色 | 账号 | 权限 | 典型动作 |
|---|---|---|---|
| 产品经理 `admin` | `admin@yieldbook.io` | 产品维护 + 报价导入 + 换算 + 复核 + 关注 + 导出 + 审计 | 登记产品、导入报价、导出对比榜、查审计 |
| 口径专员 `analyst` | `analyst@yieldbook.io` | 报价导入 + 换算 + 复核 + 关注（**不能导出、不能看审计**） | 跑换算、复核可比口径、维护到期提醒 |
| 客户经理 `viewer` | `viewer@yieldbook.io` | 只读榜单与产品要素，**费率字段在接口层被剔除** | 查看对比榜，向客户解释口径 |

密码统一：`Demo@2026`。无 token → **401**；低权越权 → **真实 403**（不是前端隐藏按钮）：

- `POST /api/products` 用 viewer → 403；`POST /api/yield-runs` 用 viewer → 403；
- `PATCH /api/yield-views/{id}/review` 用 viewer → 403；
- `GET /api/exports/views.csv` 用 analyst 或 viewer → 403；
- `GET /api/audit` 用 analyst 或 viewer → 403。
- `POST /api/products` 空 body → 422；`POST /api/quotes` 重复（产品 + 报价日）→ 409。

## 3. 功能模块

1. **产品库**（`/api/products`）：68 只产品的要素检索（类型 / 风险等级 / 期限档 / 机构 / 在售），详情含近 5 日报价与最近一次口径结果；管理员可登记、停售/复售。
2. **口径换算**（`/api/yield-runs`）：一键把全部产品报价换算成可比年化，记录产品数、方法分布、分组数与日志。
3. **对比榜**（`/api/yield-views`、`/api/yield-views/groups`）：按「类型 + 期限档」分组的前 N 名，含排名、年化波动、风险调整、置信度；口径缺失条目标 unknown 不参与排名。
4. **复核**（`PATCH /api/yield-views/{id}/review`）：口径专员确认/驳回，保留复核人与备注。
5. **关注与到期**（`/api/watchlist`）：到期提醒与排名提醒，带剩余天数与 7 天内到期统计。
6. **导入与导出**（`/api/quotes`、`/api/exports/views.csv`）：单条/批量写入报价，自然键冲突 409；CSV 导出带 UTF-8 BOM。
7. **审计**（`/api/audit`）：登录、产品维护、报价导入、换算、复核、导出全量留痕（HTTP 中间件 + 领域动作两层）。

## 4. 快速启动

```bash
cp .env.example .env
docker compose up -d --build
# 等 5/5 healthy，约 60-90 秒
open http://localhost:18202
```

首次启动 backend 自动建表并 seed 一次（`SEED_DEMO=true`）。seed 幂等，可重复执行：

```bash
docker compose exec -T backend python -m scripts.seed_demo
docker compose exec -T backend python -m pytest tests -q
```

## 5. 访问地址

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:18202 |
| 后端 API 文档 | http://localhost:19202/docs |
| 健康检查 | http://localhost:19202/api/health |
| 数据库映射 | localhost:17702 |

## 6. 技术栈

| 层 | 选型 |
|---|---|
| 前端 | 原生 HTML5 + CSS（oklch 令牌 / 网格与账页版式）+ ES Modules；无框架、无打包、无 CDN 脚本（仅 Google Fonts） |
| 后端 | Python 3.11、FastAPI 0.115、SQLAlchemy 2.0、PyJWT、passlib(bcrypt) |
| 异步 | Celery 5.4 + Redis（心跳、每日 07:30 重算） |
| 数据库 | PostgreSQL 16 |
| 部署 | Docker Compose，恰好 5 服务，全部带 healthcheck |

## 7. 目录

```text
backend/
  src/config         settings / app 装配 / database / celery
  src/constants      enums(共享枚举) / roles(权限) / limits / log_templates
  src/models         product / quote / watch / yield_run / yield_view / user / audit
  src/schemas        product / quote / yield / watch / auth / common
  src/services       yield_math(算法) / product / quote / yield / watch / export / overview / audit / auth
  src/controllers    产品 / 报价 / 换算 / 关注 / 导出 / 认证
  src/routes         products / quotes / yield / watchlist / exports / overview / audit / health / auth
  src/middlewares    auth(JWT) / rbac(403) / audit_logger / rate_limit / error_handler
  scripts            demo_config(种子数据) / seed_demo / worker_healthcheck.sh
  migrations/        001_core_tables.sql（DDL 参考，运行时不执行）
  tests/             test_yield_math.py(算法) / test_security.py
frontend/site/
  index.html  css/{tokens,app}.css
  js/{config,api,store,ui,app}.js  js/pages/{login,overview,products,compare,watchlist,runs,audit}.js
```

## 8. 核心算法与口径

两个算法都是纯函数（`backend/src/services/yield_math.py`），不带数据库依赖，前端只展示后端算出的数。

### 算法 A｜收益口径归一（优先级从上到下，缺失不猜）

| 优先级 | method | 输入 | 公式 | 置信度 |
|---|---|---|---|---|
| 1 | `direct` | `seven_day_pct` | 直接取七日年化 | high |
| 2 | `wanfen` | `wanfen_yield` | 万份收益 × 365 / 10000（百分数） | high |
| 3 | `nav` | 净值序列（≥2 点） | `(NAV_end / NAV_start) ^ (365 / 天数) - 1` | high（窗口 ≥30 天）/ medium |
| 4 | `bench` | `bench_low` + `bench_high` | 区间中值，标「非承诺」 | low |
| 5 | `unknown` | 四项全缺 | `comparable_pct = null`，**不估算** | none |

- 单边基准（只有下限或上限）视为不可用，继续降级；
- `year_pct`（近 1 年年化）是机构滚动披露值，口径不统一，**只展示、不参与换算**；
- 边界用例：`wanfen 0.62 → 2.263`、同日报价天数差为 0 → nav 返回 null 并降级、净值只有 1 个点不能算区间年化。

### 算法 B｜同类排名与风险调整

- PeerGroup = `类型 + 期限档`，期限档边界：`≤30` / `31-180` / `181-365` / `>365` 天；
- 年化波动 = 近 30 个交易日「净值日收益率」的样本标准差 × √252（返回百分数）；
- 风险调整 = `可比年化(%) / 年化波动(%)`；波动为 0 → 用同类样本中位数并打 `vol_zero_median` 标记；
- 样本 < 5 只 → 不排名（`peer_rank = null`，`sample_short`）；
- 排名并列时按产品编号升序，保证同一批数据两次运行结果一致。

**实测锚点（seed 保证，可由 `GET /api/yield-views` 复现）**

- 「江城稳健 90 天」七日年化 2.31% → 可比 **2.31%**，method `direct`；
- 「江城现金宝」万份收益 0.62 → 可比 **2.263%**，method `wanfen`；
- 「江城添利 120 天」可比 **3.05%**，固定收益类 · 31-180 天分组 `peer_rank = 1`（R2 组第一）；
- 68 条结果中 **9 条 unknown**；7 天内到期关注 **3 条**；对比榜 CSV **68 行**数据（不含表头）。

## 9. 共享枚举出现位置

| 枚举 | 后端 | 前端 |
|---|---|---|
| 角色 `admin/analyst/viewer` | `backend/src/constants/{roles,enums}.py` | `frontend/site/js/config.js`(`ROLE_LABELS`/`PERMISSIONS`) |
| 产品类型 `cash/fixed/mixed/equity` | `backend/src/constants/enums.py`(`ProductType`) | `js/config.js`(`ENUMS.productType`) |
| 风险等级 `R1..R5` | `backend/src/constants/enums.py`(`RiskLevel`) | `js/config.js`(`ENUMS.riskLevel`) |
| 期限档 `le30/d31_180/d181_365/gt365` | `backend/src/constants/enums.py`(`TermBucket`) | `js/config.js`(`ENUMS.termBucket`) |
| 换算口径 `direct/wanfen/nav/bench/unknown` | `backend/src/constants/enums.py`(`YieldMethod`) | `js/config.js`(`ENUMS.method`) |
| 置信度 `high/medium/low/none` | `backend/src/constants/enums.py`(`Confidence`) | `js/config.js`(`ENUMS.confidence`) |
| 复核状态 `pending/confirmed/dismissed` | `backend/src/constants/enums.py`(`ReviewStatus`) | `js/config.js`(`ENUMS.review`) |
| 运行状态 `running/success/partial/failed` | `backend/src/constants/enums.py`(`RunStatus`) | `js/config.js`(`ENUMS.runStatus`) |
| 关注类型/状态 `expire|rank`、`pending/notified/done` | `backend/src/constants/enums.py`(`WatchKind`/`WatchStatus`) | `js/config.js`(`ENUMS.watchKind`/`watchStatus`) |

## 10. 种子数据与幂等

- `backend/scripts/demo_config.py`：68 只产品（手工命名，覆盖 4 类 / R1-R5 / 4 个期限档）、
  5 个交易日 × 68 条 = 340 条报价（锚定 2026-11-09 ~ 2026-11-13）、12 条关注；
- 自然键：`users.email`、`products.code`、`quotes(product_id, quote_date)`、`watches(product_id, kind)`、
  `yield_runs.seed_key`、`yield_views(run_id, product_id)`、`audit_logs.seed_key`；
- 重复执行只补缺失行，**不覆盖人工复核状态**（`yield_views.status/reviewer/review_note` 保留）；
- 结束打印一行固定契约（键名与顺序按 batch-plan）：
  `SEED_SUMMARY brand=yieldbook users=3 sources=68 runs=1 findings=68 pending=68`
  其中 `sources` = 产品主档数、`findings` = 换算结果数（契约键名固定，含义映射见本节）。

## 11. 环境变量

见 `.env.example`：`COMPOSE_PROJECT_NAME`、`FRONTEND_PORT=18202`、`BACKEND_PORT=19202`、`DB_PORT=17702`、
`DB_*`、`JWT_SECRET`、`REDIS_URL`、`SEED_DEMO`、`RATE_LIMIT_PER_MINUTE`、`RATE_LIMIT_WRITE_PER_MINUTE`、
`APP_TIMEZONE_OFFSET_MINUTES`。

## 12. Docker 说明

- 5 个服务：`frontend`(Nginx 静态站) / `backend`(uvicorn) / `worker`(Celery) / `db`(PostgreSQL 16) / `redis`，全部带 healthcheck；
- 命名卷：`db_data`、`redis_data`；`worker` 依赖 backend healthy，靠 Redis 心跳 + Celery ping 判定自身健康；
- Nginx：`location /api/ { proxy_pass http://backend:8000/; }`（剥掉 `/api` 前缀）+ SPA 回落；
- 收尾：`docker compose down -v --remove-orphans`。

## License

内部演示项目，仅用于评测与教学。
