import { api } from '../api.js';
import { ENUMS, can, methodTone, riskTone, runTone } from '../config.js';
import { barList, catalog, emptyState, errorBox, errorMessage, esc, fmtPct, fmtTime, kv } from '../ui.js';

export const overviewPage = {
  async render(view, ctx) {
    view.innerHTML = '<div class="empty"><div class="mark">正在翻账页…</div></div>';
    try {
      const data = await api.get('/api/overview');
      const latest = data.latest_run;
      const riskTop = data.risk_top || {};
      const riskRows = ['R1', 'R2', 'R3', 'R4', 'R5']
        .filter((level) => riskTop[level])
        .map((level) => ({
          level,
          ...riskTop[level],
        }));

      const topEntries = [];
      (data.groups || []).forEach((group) => {
        (group.top || []).slice(0, 2).forEach((row) => {
          topEntries.push({
            no: row.peer_rank ? `第 ${String(row.peer_rank).padStart(2, '0')}` : '未排名',
            title: esc(row.product_name),
            sub: `${group.group_label} · ${ENUMS.method[row.method] || row.method}`,
            tail: `<span class="badge ${methodTone(row.method)}">${fmtPct(row.comparable_pct)}</span>`,
          });
        });
      });

      view.innerHTML = `
        <section class="ledger-block">
          <div class="ledger">
            <div>
              <span class="k">在售产品 / PRODUCTS</span>
              <span class="v">${data.active_total}<small>/ ${data.products_total} 只</small></span>
              <span class="hint">${data.issuer_total} 家合作机构 · ${data.quotes_total} 条报价</span>
            </div>
            <div>
              <span class="k">7 天内到期 / EXPIRING</span>
              <span class="v">${data.expiring_total}<small>条</small></span>
              <span class="hint">关注清单共 ${data.watches_total} 条，待跟进 ${data.watch_pending}</span>
            </div>
            <div>
              <span class="k">口径缺失 / UNKNOWN</span>
              <span class="v">${data.unknown_total}<small>/ ${latest ? latest.view_count : 0} 条</small></span>
              <span class="hint">四项口径全缺，标 unknown 不估算</span>
            </div>
            <div>
              <span class="k">待复核 / REVIEW</span>
              <span class="v">${data.pending_review}<small>条</small></span>
              <span class="hint">已确认 ${data.confirmed_review} · 已驳回 ${data.dismissed_review}</span>
            </div>
          </div>
        </section>

        <div class="grid-2">
          <section class="panel">
            <div class="panel-head"><h2>产品类型分布</h2><span class="meta">type / count</span></div>
            <div class="panel-body">
              ${
                data.type_mix.length
                  ? barList(data.type_mix.map((item) => ({ ...item, count: item.count })), 'navy')
                  : emptyState({ title: '产品库还是空的', hint: '管理员可在产品库登记第一只产品。' })
              }
              <p class="note-line">同类排名的一级分组维度：产品类型 + 期限档。</p>
            </div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>最近一次口径换算</h2><span class="meta">latest run</span></div>
            <div class="panel-body">
              ${
                latest
                  ? `${kv([
                      ['运行编号', `<span class="mono">${esc(latest.run_no)}</span>`],
                      ['状态', `<span class="badge ${runTone(latest.status)}">${esc(latest.status_label)}</span>`],
                      ['结果条数', `${latest.view_count} 条（缺失 ${data.unknown_total}）`],
                      ['开始时间', fmtTime(latest.started_at)],
                      ['平均可比', fmtPct(data.avg_comparable_pct, 4)],
                      [
                        '榜首',
                        latest.top_group
                          ? `${esc(latest.top_group.group_label)} · ${esc(latest.top_group.top_product_name)} ${fmtPct(latest.top_group.top_comparable_pct)}`
                          : '—',
                      ],
                    ])}
                    <p class="note-line">换算规则：七日年化直取 → 万份收益 ×365/10000 → 净值区间年化 → 基准中值；全缺 → unknown。</p>`
                  : emptyState({ title: '还没有换算记录', hint: '到「换算与导入」发起一次口径换算。' })
              }
            </div>
          </section>
        </div>

        <div class="grid-2">
          <section class="panel">
            <div class="panel-head"><h2>同类榜首（每组前 2）</h2><span class="meta">peer groups</span></div>
            <div class="panel-body">
              ${
                topEntries.length
                  ? catalog(topEntries)
                  : emptyState({ title: '还没有可排名的分组', hint: '样本 ≥5 只才会排名。' })
              }
            </div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>各风险等级第一</h2><span class="meta">R1-R5 top1</span></div>
            <div class="panel-body">
              ${
                riskRows.length
                  ? catalog(
                      riskRows.map((row) => ({
                        no: row.level,
                        title: `<b>${esc(row.product_name || '—')}</b>`,
                        sub: `同类排名 ${row.peer_rank ? `第 ${row.peer_rank}` : '未排名'} · ${esc(row.group_key || '')}`,
                        tail: `<span class="badge ${riskTone(row.level)}">${fmtPct(row.comparable_pct, 4)}</span>`,
                      })),
                    )
                  : emptyState({ title: '还没有换算结果', hint: '先跑一次口径换算。' })
              }
              <p class="note-line">验收口径：R2 组第一名 3.05%（固定收益类 · 31-180 天，peer_rank=1）。</p>
            </div>
          </section>
        </div>

        <section class="panel">
          <div class="panel-head">
            <h2>7 天内到期提醒</h2>
            <span class="meta">watchlist · expire</span>
          </div>
          <div class="panel-body">
            ${
              data.expiring && data.expiring.length
                ? catalog(
                    data.expiring.map((item) => ({
                      no: `${item.days_left}天`,
                      title: `<b>${esc(item.product_name || '—')}</b>`,
                      sub: `${esc(ENUMS.watchKind.expire)} · ${esc(item.due_on)}`,
                      tail: `<span class="badge ${item.days_left <= 3 ? 'danger' : 'medium'}">${esc(item.risk_level || '')}</span>`,
                    })),
                  )
                : emptyState({ title: '7 天内没有到期产品', hint: '关注清单里的到期提醒会显示在这里。' })
            }
          </div>
        </section>`;
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => overviewPage.render(view, ctx));
    }
  },
};

export default overviewPage;
