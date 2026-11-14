-- 核心表结构参考（PostgreSQL 语法，运行时不执行；建表由 SQLAlchemy create_all 完成）
-- 领域：理财产品采集与收益口径换算台（yieldbook）

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(160) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    display_name    VARCHAR(80)  NOT NULL,
    role            VARCHAR(20)  NOT NULL,
    org             VARCHAR(120),
    created_at      TIMESTAMP    NOT NULL
);

CREATE TABLE products (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(40)  NOT NULL UNIQUE,
    name            VARCHAR(120) NOT NULL,
    issuer          VARCHAR(80)  NOT NULL,
    type            VARCHAR(20)  NOT NULL,   -- cash / fixed / mixed / equity
    risk_level      VARCHAR(4)   NOT NULL,   -- R1..R5
    min_amount      DOUBLE PRECISION NOT NULL DEFAULT 10000,
    term_days       INTEGER      NOT NULL DEFAULT 0,
    fee_rate        DOUBLE PRECISION NOT NULL DEFAULT 0,
    active          BOOLEAN      NOT NULL DEFAULT TRUE,
    listed          BOOLEAN      NOT NULL DEFAULT TRUE,  -- FALSE = 采集待确认，不进正式对比榜
    note            TEXT,
    created_at      TIMESTAMP    NOT NULL,
    updated_at      TIMESTAMP    NOT NULL
);

-- 机构批量采集：同一（机构, batch_key）幂等，重试不新增
CREATE TABLE ingest_batches (
    id              SERIAL PRIMARY KEY,
    batch_no        VARCHAR(40)  NOT NULL UNIQUE,
    institution     VARCHAR(80)  NOT NULL,
    batch_key       VARCHAR(120) NOT NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'received',  -- received / processed
    row_count       INTEGER      NOT NULL DEFAULT 0,
    rejected        JSON,                    -- 缺机构编码、无法识别的行（行号 + 原因）
    operator_email  VARCHAR(160) NOT NULL,
    note            TEXT,
    created_at      TIMESTAMP    NOT NULL,
    updated_at      TIMESTAMP    NOT NULL,
    CONSTRAINT uq_ingest_batch_inst_key UNIQUE (institution, batch_key)
);

-- 来源记录：按（机构, 机构编码）识别；状态机 pending/merged/conflict/confirmed
CREATE TABLE source_records (
    id              SERIAL PRIMARY KEY,
    batch_id        INTEGER      NOT NULL REFERENCES ingest_batches(id) ON DELETE CASCADE,
    row_no          INTEGER      NOT NULL DEFAULT 0,
    institution     VARCHAR(80)  NOT NULL,
    inst_code       VARCHAR(40)  NOT NULL,   -- 机构自己的产品编码（机构间可重码）
    payload         JSON,                    -- 来源行原文，保留来源
    name            VARCHAR(120),
    product_type    VARCHAR(20),
    risk_level      VARCHAR(4),
    min_amount      DOUBLE PRECISION,
    term_days       INTEGER,
    fee_rate        DOUBLE PRECISION,
    missing_fields  JSON,                    -- 缺失要素逐字段列出，不再只显示「跳过一条」
    invalid_fields  JSON,                    -- 取值非法的要素（如风险等级 R9）
    conflict_fields JSON,                    -- 与目录不一致的要素 [{field, existing, incoming}]
    status          VARCHAR(16)  NOT NULL DEFAULT 'pending',
    product_id      INTEGER      REFERENCES products(id) ON DELETE SET NULL,
    reviewer        VARCHAR(160),
    review_note     TEXT,
    confirmed_at    TIMESTAMP,
    created_at      TIMESTAMP    NOT NULL,
    updated_at      TIMESTAMP    NOT NULL,
    CONSTRAINT uq_source_record_batch_code UNIQUE (batch_id, inst_code)
);

-- 机构编码映射：（机构, 机构编码）-> 正式产品；两家机构同码各自成行
CREATE TABLE product_sources (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER      NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    institution     VARCHAR(80)  NOT NULL,
    inst_code       VARCHAR(40)  NOT NULL,
    created_at      TIMESTAMP    NOT NULL,
    CONSTRAINT uq_product_source_inst_code UNIQUE (institution, inst_code)
);

CREATE TABLE quotes (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER      NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    quote_date      DATE         NOT NULL,
    nav             DOUBLE PRECISION,
    seven_day_pct   DOUBLE PRECISION,
    wanfen_yield    DOUBLE PRECISION,
    bench_low       DOUBLE PRECISION,
    bench_high      DOUBLE PRECISION,
    year_pct        DOUBLE PRECISION,
    source          VARCHAR(20)  NOT NULL DEFAULT 'seed',
    created_at      TIMESTAMP    NOT NULL,
    CONSTRAINT uq_quotes_product_date UNIQUE (product_id, quote_date)
);

CREATE TABLE watches (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER      NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    kind            VARCHAR(10)  NOT NULL,   -- expire / rank
    due_on          DATE         NOT NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'pending',
    note            TEXT,
    owner           VARCHAR(80),
    created_at      TIMESTAMP    NOT NULL,
    updated_at      TIMESTAMP    NOT NULL,
    CONSTRAINT uq_watches_product_kind UNIQUE (product_id, kind)
);

CREATE TABLE yield_runs (
    id              SERIAL PRIMARY KEY,
    run_no          VARCHAR(40)  NOT NULL UNIQUE,
    trigger         VARCHAR(20)  NOT NULL,
    status          VARCHAR(20)  NOT NULL,
    operator_email  VARCHAR(160) NOT NULL,
    product_count   INTEGER      NOT NULL DEFAULT 0,
    view_count      INTEGER      NOT NULL DEFAULT 0,
    metrics         JSON,
    log_text        TEXT,
    seed_key        VARCHAR(120) UNIQUE,
    started_at      TIMESTAMP    NOT NULL,
    finished_at     TIMESTAMP
);

CREATE TABLE yield_views (
    id              SERIAL PRIMARY KEY,
    run_id          INTEGER      NOT NULL REFERENCES yield_runs(id) ON DELETE CASCADE,
    product_id      INTEGER      NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    comparable_pct  DOUBLE PRECISION,
    method          VARCHAR(16)  NOT NULL,   -- direct / wanfen / nav / bench / unknown
    confidence      VARCHAR(10)  NOT NULL,
    peer_rank       INTEGER,
    risk_adj        DOUBLE PRECISION,
    group_key       VARCHAR(60)  NOT NULL,
    group_size      INTEGER      NOT NULL DEFAULT 0,
    vol_annual      DOUBLE PRECISION,
    status          VARCHAR(16)  NOT NULL DEFAULT 'pending',
    flags           JSON,
    note            TEXT,
    reviewer        VARCHAR(160),
    review_note     TEXT,
    created_at      TIMESTAMP    NOT NULL,
    updated_at      TIMESTAMP    NOT NULL,
    CONSTRAINT uq_views_run_product UNIQUE (run_id, product_id)
);

CREATE TABLE audit_logs (
    id              SERIAL PRIMARY KEY,
    actor_email     VARCHAR(160) NOT NULL,
    actor_role      VARCHAR(20)  NOT NULL,
    action          VARCHAR(64)  NOT NULL,
    entity          VARCHAR(40)  NOT NULL,
    entity_id       VARCHAR(64),
    detail          JSON,
    layer           VARCHAR(16)  NOT NULL DEFAULT 'domain',
    ip              VARCHAR(64),
    seed_key        VARCHAR(120) UNIQUE,
    created_at      TIMESTAMP    NOT NULL
);
