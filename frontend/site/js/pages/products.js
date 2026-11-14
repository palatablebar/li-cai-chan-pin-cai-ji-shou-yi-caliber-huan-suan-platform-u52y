import { api } from '../api.js';
import { ENUMS, can, methodTone, reviewTone, riskTone, runTone } from '../config.js';
import { drawer, emptyState, errorBox, errorMessage, esc, field, fmtPct, fmtNum, fmtTime, table, toast } from '../ui.js';

const state = { q: '', type: '', risk_level: '', bucket: '', issuer: '', active: 'true' };

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

export const productsPage = {
  async render(view, ctx) {
    let data;
    let issuers;
    try {
      [data, issuers] = await Promise.all([
        api.get('/api/products', {
          q: state.q,
          type: state.type,
          risk_level: state.risk_level,
          bucket: state.bucket,
          issuer: state.issuer,
          active: state.active,
          limit: 100,
        }),
        api.get('/api/products/issuers'),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => productsPage.render(view, ctx));
      return;
    }
    const startIndex = data.offset || 0;
    view.innerHTML = `
      <section class="panel">
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
              key: 'active',
              label: '状态',
              render: (row) => (row.active ? '<span class="badge ok">在售</span>' : '<span class="badge">停售</span>'),
            },
          ],
          empty: { title: '这个筛选条件下没有产品', hint: '放宽风险等级或期限档再试。' },
        })}
        <p class="note-line">客户经理（viewer）列表与详情都不返回费率明细，接口层已隐藏，不是前端遮挡。</p>
      </section>`;

    const filters = view.querySelector('#product-filters');
    const rerender = () => productsPage.render(view, ctx);
    filters?.addEventListener('change', () => {
      state.q = filters.querySelector('[name=q]').value.trim();
      state.type = filters.querySelector('[name=type]').value;
      state.risk_level = filters.querySelector('[name=risk_level]').value;
      state.bucket = filters.querySelector('[name=bucket]').value;
      state.issuer = filters.querySelector('[name=issuer]').value;
      state.active = filters.querySelector('[name=active]').value;
      rerender();
    });
    filters?.querySelector('[name=q]')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        state.q = event.target.value.trim();
        rerender();
      }
    });
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => openDetail(view, ctx, Number(row.dataset.id)));
    });
    view.querySelector('#new-product')?.addEventListener('click', () => openCreate(view, ctx, issuers.items));
  },
};

export default productsPage;
