import { api } from '../api.js';
import { ENUMS, can, riskTone, watchTone } from '../config.js';
import { drawer, emptyState, errorBox, errorMessage, esc, field, table, toast } from '../ui.js';

const state = { kind: '', status: '', due_within: '' };

function openWatch(ctx, watch, rerender) {
  const writable = can(ctx.user.role, 'watch:write');
  const { root, close } = drawer({
    title: watch.product_name || `产品 #${watch.product_id}`,
    subtitle: `${watch.kind_label} · 到期 ${watch.due_on}`,
    body: `<dl class="kv">
      <dt>剩余天数</dt><dd>${
        watch.overdue
          ? `<span class="badge danger">已逾期 ${Math.abs(watch.days_left)} 天</span>`
          : `<span class="badge ${watch.due_soon ? 'medium' : 'ok'}">${watch.days_left} 天</span>`
      }</dd>
      <dt>产品编码</dt><dd class="mono">${esc(watch.product_code)}</dd>
      <dt>发行机构</dt><dd>${esc(watch.issuer)}</dd>
      <dt>风险等级</dt><dd><span class="badge ${riskTone(watch.risk_level)}">${esc(watch.risk_level)}</span></dd>
      <dt>当前状态</dt><dd><span class="badge ${watchTone(watch.status)}">${esc(watch.status_label)}</span></dd>
      <dt>负责人</dt><dd>${esc(watch.owner)}</dd>
      <dt>备注</dt><dd>${esc(watch.note || '—')}</dd>
    </dl>`,
    footer: writable
      ? `<form id="watch-form" style="display:grid;gap:10px">
          ${field({
            label: '跟进状态',
            name: 'status',
            value: watch.status,
            options: Object.entries(ENUMS.watchStatus).map(([value, label]) => ({ value, label })),
          })}
          ${field({ label: '补充备注', name: 'note', value: watch.note || '' })}
          <button class="btn accent" type="submit">保存跟进</button>
        </form>`
      : '<span class="mono muted">客户经理角色：只读关注清单</span>',
  });
  root.querySelector('#watch-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      await api.patch(`/api/watchlist/${watch.id}`, {
        status: form.status.value,
        note: form.note.value.trim() || null,
      });
      toast('关注状态已更新');
      close();
      rerender();
    } catch (err) {
      toast(errorMessage(err), 'err');
    }
  });
}

function openCreate(ctx, products, rerender) {
  const today = new Date();
  const due = new Date(today.getTime() + 14 * 86400000).toISOString().slice(0, 10);
  const { root, close } = drawer({
    title: '新增关注',
    subtitle: '到期提醒或排名变动提醒，到期后出现在总览',
    body: `<form id="new-watch" style="display:grid;gap:12px">
      ${field({
        label: '产品',
        name: 'product_id',
        options: products.map((product) => ({ value: product.id, label: `${product.name}（${product.code}）` })),
      })}
      ${field({
        label: '关注类型',
        name: 'kind',
        value: 'expire',
        options: Object.entries(ENUMS.watchKind).map(([value, label]) => ({ value, label })),
      })}
      ${field({ label: '跟进日期', name: 'due_on', type: 'date', value: due })}
      ${field({ label: '备注', name: 'note', placeholder: '客户拟续投 / 需要复核口径' })}
      <div class="form-error" id="watch-error"></div>
      <button class="btn accent" type="submit">保存关注</button>
    </form>`,
  });
  root.querySelector('#new-watch').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      await api.post('/api/watchlist', {
        product_id: Number(form.product_id.value),
        kind: form.kind.value,
        due_on: form.due_on.value,
        note: form.note.value.trim() || null,
      });
      toast('关注已新增');
      close();
      rerender();
    } catch (err) {
      root.querySelector('#watch-error').textContent =
        err.code === 'CONFLICT' ? '这只产品已有同类型关注' : errorMessage(err);
    }
  });
}

export const watchlistPage = {
  async render(view, ctx) {
    let data;
    let products;
    try {
      [data, products] = await Promise.all([
        api.get('/api/watchlist', { kind: state.kind, status: state.status, due_within: state.due_within, limit: 100 }),
        api.get('/api/products', { limit: 200, active: true }),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => watchlistPage.render(view, ctx));
      return;
    }
    const rerender = () => watchlistPage.render(view, ctx);
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>关注与到期提醒</h2>
          <div class="toolbar">
            <span class="meta">${data.total} 条 · 7 天内到期 ${data.expiring_7d}</span>
            ${can(ctx.user.role, 'watch:write') ? '<button class="btn sm accent" id="new-watch-btn">新增关注</button>' : ''}
          </div>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="watch-filters">
            ${field({
              label: '类型',
              name: 'kind',
              value: state.kind,
              options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.watchKind).map(([value, label]) => ({ value, label }))],
            })}
            ${field({
              label: '状态',
              name: 'status',
              value: state.status,
              options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.watchStatus).map(([value, label]) => ({ value, label }))],
            })}
            ${field({
              label: '到期窗口',
              name: 'due_within',
              value: state.due_within,
              options: [
                { value: '', label: '全部' },
                { value: 7, label: '7 天内' },
                { value: 30, label: '30 天内' },
              ],
            })}
          </div>
        </div>
        ${table({
          rows: data.items,
          columns: [
            { key: 'due_on', label: '到期/跟进日', className: 'mono' },
            {
              key: 'days_left',
              label: '剩余',
              render: (row) =>
                row.overdue
                  ? `<span class="badge danger">逾期 ${Math.abs(row.days_left)} 天</span>`
                  : `<span class="badge ${row.due_soon ? 'medium' : 'ok'}">${row.days_left} 天</span>`,
            },
            {
              key: 'product_name',
              label: '产品',
              render: (row) =>
                `<b style="font-family:var(--font-display)">${esc(row.product_name)}</b><div class="mono muted">${esc(row.product_code)} · ${esc(row.issuer)}</div>`,
            },
            { key: 'kind_label', label: '类型' },
            {
              key: 'risk_level',
              label: '风险',
              render: (row) => `<span class="badge ${riskTone(row.risk_level)}">${esc(row.risk_level)}</span>`,
            },
            {
              key: 'status',
              label: '跟进',
              render: (row) => `<span class="badge ${watchTone(row.status)}">${esc(row.status_label)}</span>`,
            },
            { key: 'note', label: '备注', render: (row) => `<span class="muted">${esc(row.note || '—')}</span>` },
          ],
          empty: { title: '没有符合条件的关注', hint: '放宽到期窗口，或新增一条关注。' },
        })}
      </section>`;

    const filters = view.querySelector('#watch-filters');
    filters?.addEventListener('change', () => {
      state.kind = filters.querySelector('[name=kind]').value;
      state.status = filters.querySelector('[name=status]').value;
      state.due_within = filters.querySelector('[name=due_within]').value;
      rerender();
    });
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const watch = data.items.find((item) => String(item.id) === row.dataset.id);
        if (watch) openWatch(ctx, watch, rerender);
      });
    });
    view.querySelector('#new-watch-btn')?.addEventListener('click', () => openCreate(ctx, products.items, rerender));
  },
};

export default watchlistPage;
