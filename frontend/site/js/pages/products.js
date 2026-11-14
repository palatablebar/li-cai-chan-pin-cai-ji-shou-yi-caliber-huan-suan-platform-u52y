import { api } from '../api.js';
import { ENUMS, can, ingestTone, methodTone, riskTone } from '../config.js';
import { drawer, emptyState, errorBox, errorMessage, esc, field, fmtNum, fmtPct, table, toast } from '../ui.js';

const state = { q: '', type: '', risk_level: '', bucket: '', issuer: '', active: 'true', listed: '' };
const ingestState = { batchId: '', status: '' };

function quoteRows(quotes) {
  if (!quotes || !quotes.length) return '<p class="muted">该产品还没有报价记录。</p>';
  return `<div class="table-wrap"><table class="data" style="min-width:0">
    <thead><tr><th>报价日</th><th>净值</th><th>七日年化</th><th>万份收益</th><th>基准区间</th></tr></thead>
    <tbody>${quotes
      .map(
        (row) => `<tr><td class="mono">${esc(row.quote_date)}</td>
        <td class="num">${row.nav === null ? '—' : row.nav.toFixed(4)}</td>
        <td class="num">${row.seven_day_pct === null ? '—' : `${row.seven_day_pct.toFixed(2)}%`}</td>
        <td class="num">${row.wanfen_yield === null ? '—' : row.wanfen_yield.toFixed(4)}</td>
        <td class="num">${
          row.bench_low === null || row.bench_high === null
            ? '—'
            : `${row.bench_low.toFixed(2)}% ~ ${row.bench_high.toFixed(2)}%`
        }</td></tr>`,
      )
      .join('')}</tbody></table></div>`;
}

function openDetail(view, ctx, productId) {
  api
    .get(`/api/products/${productId}`)
    .then((data) => {
      const writable = can(ctx.user.role, 'product:write');
      const latestView = data.view;
      const sources = data.sources || [];
      const { root, close } = drawer({
        title: data.name,
        subtitle: `${data.code} · ${data.issuer} · ${data.type_label}`,
        body: `<dl class="kv">
          <dt>风险等级</dt><dd><span class="badge ${riskTone(data.risk_level)}">${esc(data.risk_label)}</span></dd>
          <dt>期限档</dt><dd>${data.term_days} 天 · ${esc(data.term_bucket_label)}</dd>
          <dt>起购金额</dt><dd>${fmtNum(data.min_amount_wan, 2)} 万元</dd>
          <dt>销售费率</dt><dd>${
            data.fee_hidden
              ? '<span class="muted">当前角色不展示费率明细</span>'
              : `${fmtNum(data.fee_rate, 2)}% / 年`
          }</dd>
          <dt>在售</dt><dd>${data.active ? '<span class="badge ok">在售</span>' : '<span class="badge">停售</span>'}</dd>
          <dt>正式对比榜</dt><dd>${
            data.listed
              ? '<span class="badge ok">已入榜</span>'
              : '<span class="badge copper">待确认</span> <span class="muted">补齐要素并确认后才进入对比榜</span>'
          }</dd>
          <dt>来源编码</dt><dd>${
            sources.length
              ? sources.map((item) => `<span class="mono">${esc(item.institution)} · ${esc(item.inst_code)}</span>`).join('<br>')
              : '<span class="muted">手工登记，无机构来源</span>'
          }</dd>
          <dt>最近口径</dt><dd>${
            latestView
              ? `<span class="badge ${methodTone(latestView.method)}">${esc(latestView.method_label)}</span> ${fmtPct(
                  latestView.comparable_pct,
                  4,
                )} · 同类${
                  latestView.peer_rank ? `第 ${latestView.peer_rank}/${latestView.group_size}` : '未排名'
                } · ${esc(latestView.status_label)}`
              : '还没有换算结果'
          }</dd>
          ${
            latestView && latestView.caveat
              ? `<dt>口径说明</dt><dd class="muted">${esc(latestView.caveat)}</dd>`
              : ''
          }
          <dt>备注</dt><dd>${esc(data.note || '—')}</dd>
        </dl>
        <h3 style="margin:14px 0 8px;font-size:1rem;color:var(--navy)">近 5 个交易日报价</h3>
        ${quoteRows(data.quotes)}
        <p class="note-line">报价原样展示；可比年化由后端按口径优先级换算，前端只做展示。</p>`,
        footer: writable
          ? `<button class="btn ghost" data-toggle>${data.active ? '标记为停售' : '恢复在售'}</button>`
          : '<span class="mono muted">客户经理角色：只读，不展示费率明细</span>',
      });
      root.querySelector('[data-toggle]')?.addEventListener('click', async () => {
        try {
          await api.patch(`/api/products/${data.id}`, { active: !data.active });
          toast('产品状态已更新');
          close();
          await productsPage.render(view, ctx);
        } catch (err) {
          toast(errorMessage(err), 'err');
        }
      });
    })
    .catch((err) => toast(errorMessage(err), 'err'));
}

function openCreate(view, ctx, issuers) {
  const { root, close } = drawer({
    title: '登记代销产品',
    subtitle: '要素一次录全，后续报价与口径换算都挂在这只产品上',
    body: `<form id="product-form" style="display:grid;gap:12px">
      ${field({ label: '产品编码（小写字母/数字）', name: 'code', placeholder: 'yb069' })}
      ${field({ label: '产品名称', name: 'name', placeholder: '江城稳健 90 天' })}
      ${field({
        label: '发行机构',
        name: 'issuer',
        options: issuers.map((name) => ({ value: name, label: name })),
      })}
      ${field({
        label: '产品类型',
        name: 'type',
        value: 'fixed',
        options: Object.entries(ENUMS.productType).map(([value, label]) => ({ value, label })),
      })}
      ${field({
        label: '风险等级',
        name: 'risk_level',
        value: 'R2',
        options: Object.entries(ENUMS.riskLevel).map(([value, label]) => ({ value, label })),
      })}
      ${field({ label: '起购金额（元）', name: 'min_amount', type: 'number', value: '10000' })}
      ${field({ label: '期限（天）', name: 'term_days', type: 'number', value: '90' })}
      ${field({ label: '销售费率（%/年）', name: 'fee_rate', type: 'number', value: '0.3' })}
      ${field({ label: '备注', name: 'note', placeholder: '机构官网采集，2026-11-13' })}
      <div class="form-error" id="product-error"></div>
      <button class="btn accent" type="submit">保存产品</button>
    </form>`,
  });
  root.querySelector('#product-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      await api.post('/api/products', {
        code: form.code.value.trim(),
        name: form.name.value.trim(),
        issuer: form.issuer.value,
        type: form.type.value,
        risk_level: form.risk_level.value,
        min_amount: Number(form.min_amount.value || 10000),
        term_days: Number(form.term_days.value || 0),
        fee_rate: Number(form.fee_rate.value || 0),
        note: form.note.value.trim() || null,
      });
      toast('产品已登记');
      close();
      await productsPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#product-error').textContent =
        err.code === 'CONFLICT' ? '产品编码已存在，请换一个' : errorMessage(err);
    }
  });
}

/* ---------------- 机构采集批次 ---------------- */

function fmtElem(fieldName, value) {
  if (value === null || value === undefined) return '—';
  if (fieldName === 'min_amount') return `${fmtNum(Number(value) / 10000, 2)} 万`;
  if (fieldName === 'fee_rate') return `${fmtNum(value, 2)}%`;
  if (fieldName === 'term_days') return `${value} 天`;
  return esc(value);
}

function recordIssue(record) {
  if (record.status === 'pending') {
    const parts = [];
    if (record.missing_labels && record.missing_labels.length) parts.push(`缺 ${record.missing_labels.join('、')}`);
    if (record.invalid_labels && record.invalid_labels.length) parts.push(`取值非法：${record.invalid_labels.join('、')}`);
    return `<span class="badge ${ingestTone('pending')}">${esc(parts.join('；') || '要素不全')}</span>`;
  }
  if (record.status === 'conflict') {
    const diffs = (record.conflict_fields || [])
      .map((item) => `${esc(item.field_label)} ${fmtElem(item.field, item.existing)} → ${fmtElem(item.field, item.incoming)}`)
      .join('、');
    return `<span class="badge ${ingestTone('conflict')}">待确认</span> <span class="muted">${diffs}</span>`;
  }
  if (record.status === 'confirmed') {
    return `<span class="muted">复核 ${esc(record.reviewer || '—')}</span>`;
  }
  return '<span class="muted">要素一致</span>';
}

function recordActions(record, ctx) {
  const canWrite = can(ctx.user.role, 'ingest:write');
  const canConfirm = can(ctx.user.role, 'ingest:confirm');
  if (record.status === 'pending' && canWrite) {
    return `<button class="btn sm ghost" data-act="complete" data-id="${record.id}">补齐要素</button>`;
  }
  if (record.status === 'merged' && canConfirm) {
    return `<button class="btn sm accent" data-act="confirm" data-id="${record.id}">确认入榜</button>`;
  }
  if (record.status === 'conflict' && canConfirm) {
    return `<button class="btn sm accent" data-act="resolve" data-id="${record.id}">处理冲突</button>`;
  }
  if (record.status === 'confirmed') {
    return '<span class="badge ok">已入榜</span>';
  }
  return '<span class="mono muted">只读</span>';
}

function openSubmitBatch(view, ctx) {
  const today = new Date().toISOString().slice(0, 10);
  const template = `[
  {"inst_code": "ZX100", "name": "中盈稳利 90 天", "product_type": "fixed", "risk_level": "R2", "min_amount": 10000, "term_days": 90, "fee_rate": 0.3},
  {"inst_code": "ZX101", "name": "中盈日日升", "product_type": "cash", "risk_level": "R1"}
]`;
  const { root, close } = drawer({
    title: '提交机构采集批次',
    subtitle: '按（机构, 机构编码）识别来源；同一机构同一批次号重试不新增、不丢失',
    body: `<form id="batch-form" style="display:grid;gap:12px">
      ${field({ label: '机构名称', name: 'institution', placeholder: '中盈基金' })}
      ${field({ label: '批次号（机构文件日期 / 编号）', name: 'batch_key', value: `${today}-01`, placeholder: '2026-11-14-01' })}
      ${field({ label: '备注', name: 'note', placeholder: '可选：文件名或采集说明' })}
      <div class="field">
        <label for="rows">机构记录（JSON 数组，每行一只产品；缺要素的行会进入「待补」并逐字段列出）</label>
        <textarea name="rows" id="rows" rows="9" style="font-family:var(--font-mono);font-size:0.82rem">${esc(template)}</textarea>
      </div>
      <div class="form-error" id="batch-error"></div>
      <button class="btn accent" type="submit">接收批次</button>
    </form>`,
  });
  root.querySelector('#batch-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const errorNode = root.querySelector('#batch-error');
    if (!form.institution.value.trim() || !form.batch_key.value.trim()) {
      errorNode.textContent = '机构名称与批次号必填；重试同一批请填同一个批次号';
      return;
    }
    let rows;
    try {
      rows = JSON.parse(form.rows.value);
      if (!Array.isArray(rows) || !rows.length) throw new Error('rows 必须是非空数组');
    } catch (err) {
      errorNode.textContent = `JSON 解析失败：${err.message}`;
      return;
    }
    try {
      const result = await api.post('/api/ingest/batches', {
        institution: form.institution.value.trim(),
        batch_key: form.batch_key.value.trim(),
        note: form.note.value.trim() || null,
        rows,
      });
      const counts = result.batch.counts || {};
      toast(
        `批次 ${result.batch.batch_no}：接收 ${result.batch.received} · 合入 ${counts.merged || 0} · 待补 ${counts.pending || 0} · 待确认 ${counts.conflict || 0}` +
          (result.reused ? '（重试批次，未新增）' : ''),
      );
      ingestState.batchId = result.batch.id;
      ingestState.status = '';
      close();
      await productsPage.render(view, ctx);
    } catch (err) {
      errorNode.textContent = errorMessage(err);
    }
  });
}

function openComplete(view, ctx, record) {
  const missing = (record.missing_labels || []).join('、');
  const invalid = (record.invalid_labels || []).join('、');
  const { root, close } = drawer({
    title: `补齐要素 · ${record.inst_code}`,
    subtitle: `${record.institution} · 第 ${record.row_no} 行`,
    body: `<form id="complete-form" style="display:grid;gap:12px">
      <p class="note-line" style="margin:0">
        ${missing ? `待补：缺 <b>${esc(missing)}</b>` : ''}${missing && invalid ? '；' : ''}${invalid ? `取值非法：<b>${esc(invalid)}</b>` : ''}
        ${!missing && !invalid ? '要素已齐全，可继续修订后重新评估。' : ''}
      </p>
      ${field({ label: '产品名称', name: 'name', value: record.name || '', placeholder: '机构文件里的产品全称' })}
      ${field({
        label: '产品类型',
        name: 'product_type',
        value: record.product_type || 'fixed',
        options: Object.entries(ENUMS.productType).map(([value, label]) => ({ value, label })),
      })}
      ${field({
        label: '风险等级',
        name: 'risk_level',
        value: record.risk_level || '',
        options: [
          { value: '', label: '（缺失，待补）' },
          ...Object.entries(ENUMS.riskLevel).map(([value, label]) => ({ value, label })),
        ],
      })}
      ${field({ label: '起购金额（元）', name: 'min_amount', type: 'number', value: record.min_amount ?? '', placeholder: '缺失，待补' })}
      ${field({ label: '期限（天）', name: 'term_days', type: 'number', value: record.term_days ?? '', placeholder: '0 = 期限未知' })}
      ${field({ label: '销售费率（%/年）', name: 'fee_rate', type: 'number', value: record.fee_rate ?? '', placeholder: '0' })}
      <div class="form-error" id="complete-error"></div>
      <button class="btn accent" type="submit">补齐并重新评估</button>
    </form>`,
  });
  root.querySelector('#complete-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const payload = {};
    if (form.name.value.trim()) payload.name = form.name.value.trim();
    if (form.product_type.value) payload.product_type = form.product_type.value;
    if (form.risk_level.value) payload.risk_level = form.risk_level.value;
    if (form.min_amount.value !== '') payload.min_amount = Number(form.min_amount.value);
    if (form.term_days.value !== '') payload.term_days = Number(form.term_days.value);
    if (form.fee_rate.value !== '') payload.fee_rate = Number(form.fee_rate.value);
    if (!Object.keys(payload).length) {
      root.querySelector('#complete-error').textContent = '至少补一项要素';
      return;
    }
    try {
      const updated = await api.patch(`/api/ingest/records/${record.id}`, payload);
      toast(`已重新评估：${updated.status_label}`);
      close();
      await productsPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#complete-error').textContent = errorMessage(err);
    }
  });
}

function openConfirmMerged(view, ctx, record) {
  const { root, close } = drawer({
    title: `确认入榜 · ${record.inst_code}`,
    subtitle: `${record.institution} · ${record.name || record.inst_code}`,
    body: `<form id="confirm-form" style="display:grid;gap:12px">
      <dl class="kv">
        <dt>机构编码</dt><dd class="mono">${esc(record.institution)} · ${esc(record.inst_code)}</dd>
        <dt>要素</dt><dd>${esc(record.name || '—')} · ${esc(record.product_type_label || '—')} · ${esc(
          record.risk_label || '—',
        )} · 起购 ${record.min_amount === null ? '—' : `${fmtNum(record.min_amount / 10000, 2)} 万`}</dd>
        <dt>关联产品</dt><dd>${
          record.product_code
            ? `${esc(record.product_name)}（${esc(record.product_code)}）${record.product_listed ? '' : ' · 当前未上榜'}`
            : '—'
        }</dd>
      </dl>
      <p class="note-line">要素与目录一致，确认后产品进入正式对比榜，参与下一次口径换算与同类排名。</p>
      ${field({ label: '复核备注', name: 'note', placeholder: '写一句确认依据，可选' })}
      <div class="form-error" id="confirm-error"></div>
      <button class="btn accent" type="submit">确认进入正式对比榜</button>
    </form>`,
  });
  root.querySelector('#confirm-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      await api.post(`/api/ingest/records/${record.id}/confirm`, { note: form.note.value.trim() || null });
      toast('已确认，产品进入正式对比榜');
      close();
      await productsPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#confirm-error').textContent = errorMessage(err);
    }
  });
}

function openResolve(view, ctx, record) {
  const diffs = record.conflict_fields || [];
  const { root, close } = drawer({
    title: `处理冲突 · ${record.inst_code}`,
    subtitle: `${record.institution} 上报的要素与目录不一致，来源值已保留`,
    body: `<form id="resolve-form" style="display:grid;gap:12px">
      <div class="table-wrap"><table class="data" style="min-width:0">
        <thead><tr><th>要素</th><th>目录现有值</th><th>机构来源值</th></tr></thead>
        <tbody>${diffs
          .map(
            (item) => `<tr><td>${esc(item.field_label)}</td><td class="num">${fmtElem(item.field, item.existing)}</td><td class="num"><b>${fmtElem(
              item.field,
              item.incoming,
            )}</b></td></tr>`,
          )
          .join('')}</tbody>
      </table></div>
      <div class="field"><label>处理方式</label>
        <select name="resolution" id="resolution">
          <option value="keep_existing" selected>保留目录现有值（来源值留在记录里备查）</option>
          <option value="use_incoming">采用机构来源值，改写目录</option>
        </select>
      </div>
      ${field({ label: '复核备注', name: 'note', placeholder: '写一句判定依据' })}
      <div class="form-error" id="resolve-error"></div>
      <button class="btn accent" type="submit">确认处理结果</button>
    </form>`,
  });
  root.querySelector('#resolve-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      await api.post(`/api/ingest/records/${record.id}/confirm`, {
        resolution: form.resolution.value,
        note: form.note.value.trim() || null,
      });
      toast('冲突已处理，产品进入正式对比榜');
      close();
      await productsPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#resolve-error').textContent = errorMessage(err);
    }
  });
}

function ingestPanel(ctx, batches, batchDetail) {
  const canWrite = can(ctx.user.role, 'ingest:write');
  if (!batches.items.length) {
    return `<section class="panel" data-testid="ingest-panel">
      <div class="panel-head">
        <h2>机构采集批次</h2>
        <div class="toolbar">
          <span class="meta">还没有采集批次</span>
          ${canWrite ? '<button class="btn sm accent" id="new-batch">提交采集批次</button>' : ''}
        </div>
      </div>
      ${emptyState({
        title: '机构目录批量采集从这里开始',
        hint: '按（机构, 机构编码）接收来源记录：两家机构用同一个编码也不会互挂；缺起购金额、风险等级的行会逐条列出。',
        actionText: canWrite ? '提交第一批' : undefined,
        actionId: 'new-batch-empty',
      })}
    </section>`;
  }
  const batch = batchDetail;
  const counts = batch.counts || {};
  const records = (batch.records || []).filter((record) => !ingestState.status || record.status === ingestState.status);
  return `<section class="panel" data-testid="ingest-panel">
    <div class="panel-head">
      <h2>机构采集批次</h2>
      <div class="toolbar">
        <span class="meta">接收 ${batch.received} · 合入 ${counts.merged || 0} · 待补 ${counts.pending || 0} · 待确认 ${counts.conflict || 0} · 已确认 ${counts.confirmed || 0}</span>
        ${canWrite ? '<button class="btn sm accent" id="new-batch">提交采集批次</button>' : ''}
      </div>
    </div>
    <div class="panel-body">
      <div class="filter-bar" id="ingest-filters">
        ${field({
          label: '批次',
          name: 'batch_id',
          value: batch.id,
          options: batches.items.map((item) => ({
            value: item.id,
            label: `${item.batch_no} · ${item.institution} · 接收 ${item.received}`,
          })),
        })}
        ${field({
          label: '状态',
          name: 'status',
          value: ingestState.status,
          options: [
            { value: '', label: '全部（本批接收）' },
            ...Object.entries(ENUMS.ingestStatus).map(([value, label]) => ({ value, label })),
          ],
        })}
        <div class="spacer"></div>
        <span class="meta">${esc(batch.institution)} · ${esc(batch.operator_email)} · ${esc(batch.status_label)}</span>
      </div>
      ${
        (batch.rejected || []).length
          ? `<p class="note-line" style="color:var(--copper)">有 ${batch.rejected.length} 行未接收：${batch.rejected
              .map((item) => `第 ${item.row_no} 行（${esc(item.reason)}）`)
              .join('；')}</p>`
          : ''
      }
    </div>
    ${table({
      rows: records,
      columns: [
        { key: 'inst_code', label: '机构编码', className: 'mono', render: (row) => `${esc(row.inst_code)}<div class="mono muted">第 ${row.row_no} 行</div>` },
        { key: 'name', label: '产品名称', render: (row) => esc(row.name || '（缺名称）') },
        {
          key: 'status',
          label: '状态',
          render: (row) => `<span class="badge ${ingestTone(row.status)}">${esc(row.status_label)}</span>`,
        },
        { key: 'issue', label: '要素问题 / 待确认内容', render: (row) => recordIssue(row) },
        {
          key: 'product',
          label: '关联产品',
          render: (row) =>
            row.product_code
              ? `${esc(row.product_name)}<div class="mono muted">${esc(row.product_code)}${row.product_listed ? '' : ' · 未上榜'}</div>`
              : '<span class="muted">—</span>',
        },
        { key: 'act', label: '操作', render: (row) => recordActions(row, ctx) },
      ],
      empty: { title: '这个状态下没有记录', hint: '换个状态筛选，或查看全部本批接收。' },
    })}
    <p class="note-line">来源记录按（机构, 机构编码）识别；重试同一批不新增、不丢失、不改写已确认。待补补齐要素、待确认处理冲突后，确认才进正式对比榜。</p>
  </section>`;
}

export const productsPage = {
  async render(view, ctx) {
    let data;
    let issuers;
    let batches;
    try {
      [data, issuers, batches] = await Promise.all([
        api.get('/api/products', {
          q: state.q,
          type: state.type,
          risk_level: state.risk_level,
          bucket: state.bucket,
          issuer: state.issuer,
          active: state.active,
          listed: state.listed,
          limit: 100,
        }),
        api.get('/api/products/issuers'),
        api.get('/api/ingest/batches', { limit: 10 }),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => productsPage.render(view, ctx));
      return;
    }
    let batchDetail = null;
    if (batches.items.length) {
      const selected =
        batches.items.find((item) => String(item.id) === String(ingestState.batchId)) || batches.items[0];
      ingestState.batchId = selected.id;
      try {
        batchDetail = await api.get(`/api/ingest/batches/${selected.id}`);
      } catch (err) {
        view.innerHTML = errorBox(errorMessage(err));
        view.querySelector('#retry-btn')?.addEventListener('click', () => productsPage.render(view, ctx));
        return;
      }
    }
    const startIndex = data.offset || 0;
    view.innerHTML = `
      ${ingestPanel(ctx, batches, batchDetail)}
      <section class="panel" data-testid="product-panel">
        <div class="panel-head">
          <h2>产品库</h2>
          <div class="toolbar">
            <span class="meta">${data.total} 只 · 目录 No.${String(startIndex + 1).padStart(3, '0')} 起</span>
            ${can(ctx.user.role, 'product:write') ? '<button class="btn sm accent" id="new-product">登记产品</button>' : ''}
          </div>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="product-filters">
            ${field({ label: '搜索', name: 'q', value: state.q, placeholder: '名称 / 编码 / 机构' })}
            ${field({
              label: '类型',
              name: 'type',
              value: state.type,
              options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.productType).map(([value, label]) => ({ value, label }))],
            })}
            ${field({
              label: '风险等级',
              name: 'risk_level',
              value: state.risk_level,
              options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.riskLevel).map(([value, label]) => ({ value, label }))],
            })}
            ${field({
              label: '期限档',
              name: 'bucket',
              value: state.bucket,
              options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.termBucket).map(([value, label]) => ({ value, label }))],
            })}
            ${field({
              label: '发行机构',
              name: 'issuer',
              value: state.issuer,
              options: [{ value: '', label: '全部' }, ...issuers.items.map((name) => ({ value: name, label: name }))],
            })}
            ${field({
              label: '状态',
              name: 'active',
              value: state.active,
              options: [
                { value: 'true', label: '在售' },
                { value: 'false', label: '停售' },
                { value: '', label: '全部' },
              ],
            })}
            ${field({
              label: '对比榜',
              name: 'listed',
              value: state.listed,
              options: [
                { value: '', label: '全部' },
                { value: 'true', label: '已入榜' },
                { value: 'false', label: '待确认' },
              ],
            })}
            <div class="spacer"></div>
          </div>
        </div>
        ${table({
          rows: data.items,
          columns: [
            {
              key: 'code',
              label: 'No. / 编码',
              className: 'idx',
              render: (row) => `${String(startIndex + data.items.indexOf(row) + 1).padStart(3, '0')} · ${esc(row.code)}`,
            },
            {
              key: 'name',
              label: '产品名称',
              render: (row) =>
                `<b style="font-family:var(--font-display);font-size:1rem">${esc(row.name)}</b><div class="mono muted">${esc(row.issuer)}</div>`,
            },
            { key: 'type_label', label: '类型' },
            {
              key: 'risk_level',
              label: '风险',
              render: (row) => `<span class="badge ${riskTone(row.risk_level)}">${esc(row.risk_level)}</span>`,
            },
            { key: 'term_days', label: '期限', className: 'num', render: (row) => `${row.term_days} 天` },
            { key: 'min_amount_wan', label: '起购', className: 'num', render: (row) => `${fmtNum(row.min_amount_wan, 2)} 万` },
            {
              key: 'fee_rate',
              label: '费率',
              className: 'num',
              render: (row) => (row.fee_hidden ? '<span class="muted">隐藏</span>' : `${fmtNum(row.fee_rate, 2)}%`),
            },
            {
              key: 'listed',
              label: '对比榜',
              render: (row) => (row.listed ? '<span class="badge ok">已入榜</span>' : '<span class="badge copper">待确认</span>'),
            },
            {
              key: 'active',
              label: '状态',
              render: (row) => (row.active ? '<span class="badge ok">在售</span>' : '<span class="badge">停售</span>'),
            },
          ],
          empty: { title: '这个筛选条件下没有产品', hint: '放宽风险等级或期限档再试。' },
        })}
        <p class="note-line">客户经理（viewer）列表与详情都不返回费率明细，接口层已隐藏，不是前端遮挡。</p>
      </section>`;

    const rerender = () => productsPage.render(view, ctx);
    const filters = view.querySelector('#product-filters');
    filters?.addEventListener('change', () => {
      state.q = filters.querySelector('[name=q]').value.trim();
      state.type = filters.querySelector('[name=type]').value;
      state.risk_level = filters.querySelector('[name=risk_level]').value;
      state.bucket = filters.querySelector('[name=bucket]').value;
      state.issuer = filters.querySelector('[name=issuer]').value;
      state.active = filters.querySelector('[name=active]').value;
      state.listed = filters.querySelector('[name=listed]').value;
      rerender();
    });
    filters?.querySelector('[name=q]')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        state.q = event.target.value.trim();
        rerender();
      }
    });
    const ingestFilters = view.querySelector('#ingest-filters');
    ingestFilters?.addEventListener('change', () => {
      ingestState.batchId = ingestFilters.querySelector('[name=batch_id]').value;
      ingestState.status = ingestFilters.querySelector('[name=status]').value;
      rerender();
    });
    view.querySelector('#new-batch')?.addEventListener('click', () => openSubmitBatch(view, ctx));
    view.querySelector('#new-batch-empty')?.addEventListener('click', () => openSubmitBatch(view, ctx));
    const ingestPanelNode = view.querySelector('[data-testid=ingest-panel]');
    ingestPanelNode?.querySelectorAll('[data-act]').forEach((button) => {
      button.addEventListener('click', () => {
        const record = (batchDetail?.records || []).find((item) => String(item.id) === button.dataset.id);
        if (!record) return;
        if (button.dataset.act === 'complete') openComplete(view, ctx, record);
        if (button.dataset.act === 'confirm') openConfirmMerged(view, ctx, record);
        if (button.dataset.act === 'resolve') openResolve(view, ctx, record);
      });
    });
    const productTable = view.querySelector('[data-testid=product-panel]');
    productTable?.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => openDetail(view, ctx, Number(row.dataset.id)));
    });
    view.querySelector('#new-product')?.addEventListener('click', () => openCreate(view, ctx, issuers.items));
  },
};

export default productsPage;
