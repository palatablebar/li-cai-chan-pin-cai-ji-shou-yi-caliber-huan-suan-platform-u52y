import { api } from '../api.js';
import { ENUMS, can, methodTone, reviewTone, riskTone, runTone } from '../config.js';
import { drawer, emptyState, errorBox, errorMessage, esc, field, fmtPct, fmtNum, kv, rankBars, toast } from '../ui.js';

const state = { runId: '', topN: 10 };

function openView(ctx, viewRow, rerender) {
  api
    .get(`/api/yield-views/${viewRow.id}`)
    .then((item) => {
      const canReview = can(ctx.user.role, 'yield:review');
      const { root, close } = drawer({
        title: item.product_name || item.product_code,
        subtitle: `${item.group_label} · ${item.run_no}`,
        body: `${kv([
          [
            '可比年化',
            `<b style="font-family:var(--font-display);font-size:1.2rem;color:var(--navy)">${fmtPct(item.comparable_pct, 4)}</b>`,
          ],
          ['换算口径', `<span class="badge ${methodTone(item.method)}">${esc(item.method_label)}</span>`],
          ['置信度', `${esc(item.confidence_label)}`],
          ['同类排名', item.peer_rank ? `第 ${item.peer_rank} / ${item.group_size}` : `未排名（样本 ${item.group_size} < 5）`],
          ['年化波动', item.vol_annual === null ? '<span class="muted">净值点不足</span>' : `${fmtNum(item.vol_annual, 4)}%`],
          ['风险调整', item.risk_adj === null ? '<span class="muted">不可计算</span>' : fmtNum(item.risk_adj, 3)],
          ['风险等级', `<span class="badge ${riskTone(item.risk_level)}">${esc(item.risk_label)}</span>`],
          ['期限', `${item.term_days} 天 · ${esc(item.term_bucket_label || '')}`],
          ['销售费率', item.fee_rate === null ? '<span class="muted">当前角色不展示</span>' : `${fmtNum(item.fee_rate, 2)}%`],
          ['复核状态', `<span class="badge ${reviewTone(item.status)}">${esc(item.status_label)}</span>`],
          ['复核人', esc(item.reviewer || '—')],
          ['复核备注', esc(item.review_note || '—')],
        ])}
        <h3 style="margin:14px 0 8px;font-size:1rem;color:var(--navy)">口径说明</h3>
        <pre class="code">${esc(item.caveat || '（无）')}</pre>
        <p class="note-line">可比年化由后端算法算出并落库；前端不重算、不改写。</p>`,
        footer: canReview
          ? `<form id="review-form" style="display:grid;gap:10px">
              ${field({
                label: '复核结论',
                name: 'status',
                value: item.status,
                options: Object.entries(ENUMS.review).map(([value, label]) => ({ value, label })),
              })}
              ${field({ label: '复核备注', name: 'note', value: item.review_note || '', placeholder: '写一句判定依据' })}
              <button class="btn accent" type="submit">提交复核</button>
            </form>`
          : '<span class="mono muted">客户经理角色：可查看榜单，不能复核口径</span>',
      });
      root.querySelector('#review-form')?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const form = event.target;
        try {
          await api.patch(`/api/yield-views/${item.id}/review`, {
            status: form.status.value,
            note: form.note.value.trim() || null,
          });
          toast('复核结论已保存');
          close();
          rerender();
        } catch (err) {
          toast(errorMessage(err), 'err');
        }
      });
    })
    .catch((err) => toast(errorMessage(err), 'err'));
}

export const comparePage = {
  async render(view, ctx) {
    let runs;
    let groups;
    try {
      runs = await api.get('/api/yield-runs', { limit: 20 });
      groups = await api.get('/api/yield-views/groups', {
        run_id: state.runId || undefined,
        top_n: state.topN,
      });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => comparePage.render(view, ctx));
      return;
    }
    const currentRun = runs.items.find((run) => String(run.id) === String(groups.run_id)) || runs.items[0];
    const rerender = () => comparePage.render(view, ctx);

    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>同类对比榜</h2>
          <div class="toolbar">
            <span class="meta">${groups.items.length} 个分组 · top ${state.topN}</span>
            ${can(ctx.user.role, 'export:read') ? '<button class="btn sm ghost" id="export-views">导出 CSV</button>' : ''}
          </div>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="compare-filters">
            ${field({
              label: '运行批次',
              name: 'run_id',
              value: groups.run_id || '',
              options: runs.items.map((run) => ({
                value: run.id,
                label: `${run.run_no} · ${run.status_label} · ${run.view_count} 条`,
              })),
            })}
            ${field({
              label: '每组展示',
              name: 'top_n',
              value: state.topN,
              options: [
                { value: 5, label: '前 5' },
                { value: 10, label: '前 10' },
              ],
            })}
          </div>
          <p class="note-line">
            分组 = 产品类型 + 期限档；样本 &lt;5 只不排名；风险调整 = 可比年化 ÷ 年化波动（近 30 日净值日收益标准差 × √252）。
            ${
              currentRun
                ? `当前批次 ${esc(currentRun.run_no)}：${
                    currentRun.metrics && currentRun.metrics.avg_comparable_pct
                      ? `平均可比 ${fmtPct(currentRun.metrics.avg_comparable_pct, 4)}`
                      : ''
                  } ${currentRun.metrics && currentRun.metrics.unknown ? `· 缺失 ${currentRun.metrics.unknown} 条` : ''}`
                : ''
            }
          </p>
        </div>
      </section>
      ${
        groups.items.length
          ? groups.items
              .map(
                (group) => `<section class="panel group-panel">
            <div class="panel-head">
              <h2>${esc(group.group_label)}</h2>
              <span class="meta">${group.ranked ? `样本 ${group.size} · 已排名` : `样本 ${group.size} · 不足 5 不排名`}</span>
            </div>
            <div class="panel-body">
              ${rankBars(group.top)}
              <p class="note-line">${
                group.ranked
                  ? '排名按可比年化降序，同值按产品编号升序。'
                  : '样本不足 5 只，仅展示数值不给出排名。'
              }</p>
            </div>
          </section>`,
              )
              .join('')
          : errorBox('还没有换算批次，先去「换算与导入」发起一次运行。')
      }`;

    const filters = view.querySelector('#compare-filters');
    filters?.addEventListener('change', () => {
      state.runId = filters.querySelector('[name=run_id]').value;
      state.topN = Number(filters.querySelector('[name=top_n]').value || 10);
      rerender();
    });
    view.querySelectorAll('.bar-row[data-view-id]').forEach((row) => {
      row.style.cursor = 'pointer';
      row.addEventListener('click', () => {
        let target = null;
        groups.items.forEach((group) => {
          group.top.forEach((item) => {
            if (String(item.id) === row.dataset.viewId) target = item;
          });
        });
        if (target) openView(ctx, target, rerender);
      });
    });
    view.querySelector('#export-views')?.addEventListener('click', async () => {
      try {
        await api.download(
          `/api/exports/views.csv${groups.run_id ? `?run_id=${groups.run_id}` : ''}`,
          'views.csv',
        );
        toast('已开始下载对比榜 CSV');
      } catch (err) {
        toast(errorMessage(err), 'err');
      }
    });
  },
};

export default comparePage;
