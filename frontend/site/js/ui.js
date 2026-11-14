/** 无框架 UI 组件：表格 / 徽标 / 抽屉 / 空态 / 账页数字 / 目录条 / 条形榜 / toast。 */

export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

export function fmtTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return esc(iso);
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/** 百分数：null 一律显示「缺失」，不补 0、不猜。 */
export function fmtPct(value, digits = 2) {
  if (value === null || value === undefined) return '<span class="muted">缺失</span>';
  return `${Number(value).toFixed(digits)}%`;
}

export function fmtNum(value, digits = 2) {
  if (value === null || value === undefined) return '—';
  return Number(value).toFixed(digits);
}

export function badge(tone, text) {
  return `<span class="badge ${esc(tone)}">${esc(text)}</span>`;
}

export function ledger(items) {
  return `<div class="ledger">${items
    .map(
      (item) => `<div>
        <span class="k">${esc(item.label)}</span>
        <span class="v">${item.value}${item.unit ? `<small>${esc(item.unit)}</small>` : ''}</span>
        <span class="hint">${esc(item.hint || '')}</span>
      </div>`,
    )
    .join('')}</div>`;
}

export function emptyState({ title, hint, actionText, actionId }) {
  return `<div class="empty" data-testid="empty-state">
    <div class="mark">${esc(title)}</div>
    <p>${esc(hint || '')}</p>
    ${actionText ? `<button class="btn ghost" id="${esc(actionId || 'empty-action')}">${esc(actionText)}</button>` : ''}
  </div>`;
}

export function errorBox(message, retryId = 'retry-btn') {
  return `<div class="error-box"><span>${esc(message)}</span><button class="btn sm ghost" id="${esc(retryId)}">重试</button></div>`;
}

export function table({ columns, rows, rowId, empty }) {
  if (!rows || rows.length === 0) return emptyState(empty || { title: '暂无记录', hint: '调整筛选条件后重试。' });
  const head = columns.map((col) => `<th>${esc(col.label)}</th>`).join('');
  const body = rows
    .map(
      (row) => `<tr data-id="${esc(row.id)}" ${rowId ? `id="${esc(rowId(row))}"` : ''}>
        ${columns.map((col) => `<td class="${esc(col.className || '')}">${col.render ? col.render(row) : esc(row[col.key])}</td>`).join('')}
      </tr>`,
    )
    .join('');
  return `<div class="table-wrap"><table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function drawer({ title, subtitle, body, footer }) {
  const backdrop = document.createElement('div');
  backdrop.className = 'drawer-backdrop';
  backdrop.innerHTML = `<aside class="drawer" role="dialog" aria-modal="true" data-testid="drawer">
    <div class="drawer-head">
      <div>
        <h2>${esc(title)}</h2>
        <div class="mono muted">${esc(subtitle || '')}</div>
      </div>
      <button class="btn sm ghost" data-close>关闭</button>
    </div>
    <div class="drawer-body">${body}</div>
    ${footer ? `<div class="drawer-foot">${footer}</div>` : ''}
  </aside>`;
  const close = () => {
    backdrop.remove();
    document.removeEventListener('keydown', onKey);
  };
  const onKey = (event) => {
    if (event.key === 'Escape') close();
  };
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop || event.target.closest('[data-close]')) close();
  });
  document.addEventListener('keydown', onKey);
  document.body.appendChild(backdrop);
  return { root: backdrop, close };
}

export function kv(items) {
  return `<dl class="kv">${items
    .map(([key, value]) => `<dt>${esc(key)}</dt><dd>${value === undefined || value === null ? '—' : value}</dd>`)
    .join('')}</dl>`;
}

export function barList(items, tone = '') {
  const max = Math.max(1, ...items.map((item) => item.count));
  return `<div class="bars">${items
    .map(
      (item) => `<div class="bar-row" style="grid-template-columns:minmax(120px,1.6fr) 2fr 52px">
        <span class="name">${esc(item.label)}</span>
        <div class="bar-track"><div class="bar-fill ${esc(tone)}" style="width:${Math.round((item.count / max) * 100)}%"></div></div>
        <span class="bar-value">${esc(item.count)}</span>
      </div>`,
    )
    .join('')}</div>`;
}

/** 排名榜：序号 + 产品名 + 可比年化条 + 数值。 */
export function rankBars(rows) {
  const max = Math.max(0.01, ...rows.map((row) => Number(row.comparable_pct || 0)));
  return `<div class="bars">${rows
    .map(
      (row) => `<div class="bar-row" data-view-id="${esc(row.id)}">
        <span class="rank-no">${row.peer_rank ? String(row.peer_rank).padStart(2, '0') : '—'}</span>
        <span class="name">${esc(row.product_name || row.product_code)}</span>
        <div class="bar-track"><div class="bar-fill ${row.method === 'unknown' ? 'navy' : ''}" style="width:${
          row.comparable_pct === null || row.comparable_pct === undefined
            ? 0
            : Math.max(2, Math.round((Number(row.comparable_pct) / max) * 100))
        }%"></div></div>
        <span class="bar-value">${fmtPct(row.comparable_pct)}</span>
      </div>`,
    )
    .join('')}</div>`;
}

export function catalog(items) {
  return `<div class="catalog">${items
    .map(
      (item) => `<div class="catalog-item">
        <span class="catalog-no">${esc(item.no)}</span>
        <span class="title">${item.title}</span>
        <span class="sub">${esc(item.sub || '')}</span>
        <span>${item.tail || ''}</span>
      </div>`,
    )
    .join('')}</div>`;
}

export function field({ label, name, type = 'text', value = '', placeholder = '', options = null, attrs = '' }) {
  const control = options
    ? `<select name="${esc(name)}" id="${esc(name)}" ${attrs}>${options
        .map((opt) => `<option value="${esc(opt.value)}" ${String(opt.value) === String(value) ? 'selected' : ''}>${esc(opt.label)}</option>`)
        .join('')}</select>`
    : `<input name="${esc(name)}" id="${esc(name)}" type="${esc(type)}" value="${esc(value)}" placeholder="${esc(placeholder)}" ${attrs} />`;
  return `<div class="field"><label for="${esc(name)}">${esc(label)}</label>${control}</div>`;
}

export function toast(message, tone = '') {
  const stack = document.getElementById('toast-stack');
  const node = document.createElement('div');
  node.className = `toast ${tone}`;
  node.textContent = message;
  stack.appendChild(node);
  setTimeout(() => node.remove(), 3600);
}

export function errorMessage(err) {
  if (!err) return '未知错误';
  if (err.code === 'FORBIDDEN') return '当前角色没有这个操作的权限';
  return err.message || '请求失败';
}
