import { api } from '../api.js';
import { ENUMS, can, runTone } from '../config.js';
import { drawer, emptyState, errorBox, errorMessage, esc, field, fmtNum, fmtPct, fmtTime, kv, table, toast } from '../ui.js';

function runDuration(run) {
  if (!run.started_at || !run.finished_at) return '—';
  const ms = new Date(run.finished_at) - new Date(run.started_at);
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function openRun(run) {
  const { root } = drawer({
    title: `换算批次 ${run.run_no}`,
    subtitle: `${run.trigger_label} · ${run.operator_email}`,
    body: `${kv([
      ['状态', `<span class="badge ${runTone(run.status)}">${esc(run.status_label)}</span>`],
      ['产品数', `${run.product_count}`],
      ['结果数', `${run.view_count}`],
      ['开始', fmtTime(run.started_at)],
      ['结束', fmtTime(run.finished_at)],
      ['耗时', runDuration(run)],
      ['平均可比', fmtPct((run.metrics || {}).avg_comparable_pct, 4)],
    ])}
    <h3 style="margin:14px 0 8px;font-size:1rem;color:var(--navy)">运行指标</h3>
    <pre class="code">${esc(JSON.stringify(run.metrics || {}, null, 2))}</pre>
    <h3 style="margin:14px 0 8px;font-size:1rem;color:var(--navy)">运行日志</h3>
    <pre class="code">${esc(run.log_text || '（无日志）')}</pre>`,
    footer: `<button class="btn accent" data-views>查看这批对比结果</button>`,
  });
  root.querySelector('[data-views]')?.addEventListener('click', () => {
    location.hash = '#/compare';
  });
}

function openImport(ctx, products, rerender) {
  const today = new Date().toISOString().slice(0, 10);
  const { root, close } = drawer({
    title: '导入一条机构报价',
    subtitle: '自然键 = 产品 + 报价日；重复导入会返回 409，不覆盖已有报价',
    body: `<form id="quote-form" style="display:grid;gap:12px">
      ${field({
        label: '产品',
        name: 'product_id',
        options: products.map((product) => ({ value: product.id, label: `${product.name}（${product.code}）` })),
      })}
      ${field({ label: '报价日', name: 'quote_date', type: 'date', value: today })}
      ${field({ label: '单位净值', name: 'nav', type: 'number', placeholder: '1.0523，可留空' })}
      ${field({ label: '七日年化（%）', name: 'seven_day_pct', type: 'number', placeholder: '2.31，可留空' })}
      ${field({ label: '万份收益', name: 'wanfen_yield', type: 'number', placeholder: '0.62，可留空' })}
      ${field({ label: '业绩基准下限（%）', name: 'bench_low', type: 'number', placeholder: '2.2' })}
      ${field({ label: '业绩基准上限（%）', name: 'bench_high', type: 'number', placeholder: '3.4' })}
      <div class="form-error" id="quote-error"></div>
      <button class="btn accent" type="submit">写入报价</button>
    </form>`,
  });
  root.querySelector('#quote-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const numeric = (name) => {
      const raw = form[name].value.trim();
      return raw === '' ? null : Number(raw);
    };
    try {
      await api.post('/api/quotes', {
        product_id: Number(form.product_id.value),
        quote_date: form.quote_date.value,
        nav: numeric('nav'),
        seven_day_pct: numeric('seven_day_pct'),
        wanfen_yield: numeric('wanfen_yield'),
        bench_low: numeric('bench_low'),
        bench_high: numeric('bench_high'),
      });
      toast('报价已写入，可再发起一次换算');
      close();
      rerender();
    } catch (err) {
      root.querySelector('#quote-error').textContent =
        err.code === 'CONFLICT' ? '这只产品当天已有报价（409，不覆盖）' : errorMessage(err);
    }
  });
}

export const runsPage = {
  async render(view, ctx) {
    let runs;
    let products;
    let quotes;
    try {
      [runs, products, quotes] = await Promise.all([
        api.get('/api/yield-runs', { limit: 20 }),
        api.get('/api/products', { limit: 200 }),
        api.get('/api/quotes', { limit: 8 }),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => runsPage.render(view, ctx));
      return;
    }
    const rerender = () => runsPage.render(view, ctx);
    const canRun = can(ctx.user.role, 'yield:run');
    const canImport = can(ctx.user.role, 'quote:import');
    const canExport = can(ctx.user.role, 'export:read');

    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>口径换算批次</h2>
          <div class="toolbar">
            <span class="meta">${runs.total} 次</span>
            ${canRun ? '<button class="btn sm accent" id="new-run">发起换算</button>' : ''}
            ${
              canExport
                ? `<button class="btn sm ghost" data-export="views">对比榜 CSV</button>
                   <button class="btn sm ghost" data-export="quotes">报价流水 CSV</button>
                   <button class="btn sm ghost" data-export="runs">批次 CSV</button>`
                : ''
            }
          </div>
        </div>
        ${table({
          rows: runs.items,
          columns: [
            { key: 'run_no', label: '运行编号', className: 'mono' },
            {
              key: 'status',
              label: '状态',
              render: (row) => `<span class="badge ${runTone(row.status)}">${esc(row.status_label)}</span>`,
            },
            { key: 'trigger_label', label: '触发' },
            { key: 'product_count', label: '产品', className: 'num' },
            { key: 'view_count', label: '结果', className: 'num' },
            {
              key: 'avg_comparable',
              label: '平均可比',
              className: 'num',
              render: (row) => fmtPct((row.metrics || {}).avg_comparable_pct, 4),
            },
            {
              key: 'unknown',
              label: '缺失',
              className: 'num',
              render: (row) => `${(row.metrics || {}).unknown ?? 0} 条`,
            },
            { key: 'started_at', label: '开始时间', render: (row) => fmtTime(row.started_at) },
            { key: 'duration', label: '耗时', className: 'num', render: (row) => runDuration(row) },
          ],
          empty: { title: '还没有换算批次', hint: '口径专员可以发起第一次换算。' },
        })}
      </section>

      <div class="grid-2">
        <section class="panel">
          <div class="panel-head">
            <h2>报价导入</h2>
            <span class="meta">quotes · manual</span>
          </div>
          <div class="panel-body">
            ${
              canImport
                ? `<p class="note-line" style="margin-top:0">采集到的机构报价在这里补录；重复（产品 + 报价日）返回 409，避免覆盖原始数据。</p>
                   <button class="btn accent" id="import-quote">补录一条报价</button>`
                : '<p class="muted">客户经理角色只能查看报价，不能导入。</p>'
            }
            <h3 style="margin:16px 0 8px;font-size:1rem;color:var(--navy)">最近导入</h3>
            ${table({
              rows: quotes.items,
              columns: [
                { key: 'quote_date', label: '报价日', className: 'mono' },
                { key: 'product_name', label: '产品' },
                { key: 'nav', label: '净值', className: 'num', render: (row) => (row.nav === null ? '—' : fmtNum(row.nav, 4)) },
                {
                  key: 'seven_day_pct',
                  label: '七日年化',
                  className: 'num',
                  render: (row) => (row.seven_day_pct === null ? '—' : `${fmtNum(row.seven_day_pct, 2)}%`),
                },
                {
                  key: 'wanfen_yield',
                  label: '万份收益',
                  className: 'num',
                  render: (row) => (row.wanfen_yield === null ? '—' : fmtNum(row.wanfen_yield, 4)),
                },
                { key: 'source_label', label: '来源' },
              ],
              empty: { title: '还没有报价', hint: '补录或等待每日采集任务。' },
            })}
          </div>
        </section>
        <section class="panel">
          <div class="panel-head">
            <h2>口径与导出说明</h2>
            <span class="meta">notes</span>
          </div>
          <div class="panel-body">
            <pre class="code">算法 A｜收益口径归一（优先级从上到下，缺失不猜）
  1. direct  七日年化直接取
  2. wanfen  万份收益 × 365 / 10000
  3. nav     (NAV_end/NAV_start)^(365/天数) - 1
  4. bench   业绩基准区间中值（非承诺）
  5. unknown 四项全缺，标 unknown 不估算

算法 B｜同类排名与风险调整
  PeerGroup = 产品类型 + 期限档（≤30/31-180/181-365/>365）
  年化波动 = 近 30 日净值日收益标准差 × √252
  风险调整 = 可比年化 / 年化波动；波动为 0 → 同类中位数并标记
  样本 < 5 只不排名

导入：自然键（产品, 报价日），重复导入 409；导出 CSV 仅管理员。</pre>
            <p class="note-line">
              worker 每日 07:30 按最新报价重算一次（Celery beat），心跳写入 Redis 供健康检查。
            </p>
          </div>
        </section>
      </div>`;

    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      const run = runs.items.find((item) => String(item.id) === row.dataset.id);
      if (run) row.addEventListener('click', () => openRun(run));
    });
    view.querySelector('#new-run')?.addEventListener('click', async () => {
      try {
        const run = await api.post('/api/yield-runs', { trigger: 'manual' });
        toast(`换算完成：${run.run_no}，${run.view_count} 条结果`);
        rerender();
      } catch (err) {
        toast(errorMessage(err), 'err');
      }
    });
    view.querySelector('#import-quote')?.addEventListener('click', () => openImport(ctx, products.items, rerender));
    view.querySelectorAll('[data-export]').forEach((button) => {
      button.addEventListener('click', async () => {
        const kind = button.dataset.export;
        try {
          await api.download(`/api/exports/${kind}.csv`, `${kind}.csv`);
          toast('已开始下载');
        } catch (err) {
          toast(errorMessage(err), 'err');
        }
      });
    });
  },
};

export default runsPage;
