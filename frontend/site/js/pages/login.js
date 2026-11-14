import { api } from '../api.js';
import { session } from '../store.js';
import { BRAND } from '../config.js';
import { errorMessage, esc, toast } from '../ui.js';

export const loginPage = {
  async render(root, ctx) {
    root.className = 'login-host';
    root.innerHTML = `
      <div class="login">
        <section class="login-cover">
          <div class="cover-eyebrow">${esc(BRAND.catalogueNo)} · ${esc(BRAND.edition)}</div>
          <h1 class="cover-title">${esc(BRAND.title)}<em>yieldbook · 收益口径目录</em></h1>
          <p class="cover-lead">${esc(BRAND.loginLead)}</p>
          <div class="cover-index">
            ${BRAND.loginPoints
              .map(
                ([no, title, text]) =>
                  `<div class="cover-entry"><b>NO.${esc(no)}</b><i>${esc(title)}</i><span>${esc(text)}</span></div>`,
              )
              .join('')}
          </div>
          <div class="cover-foot">
            <span>${esc(BRAND.org)}</span>
            <span>${esc(BRAND.coverFoot[1])}</span>
          </div>
        </section>
        <section class="login-form-wrap">
          <form class="login-card" id="login-form" novalidate>
            <div class="card-head">
              <b>${esc(BRAND.org)}</b>
              <span>目录系统登录</span>
            </div>
            <div class="field">
              <label for="email">邮箱</label>
              <input id="email" name="email" type="email" autocomplete="username" value="admin@${esc(BRAND.short)}.io" required />
            </div>
            <div class="field">
              <label for="password">密码</label>
              <input id="password" name="password" type="password" autocomplete="current-password" value="Demo@2026" required />
            </div>
            <div class="form-error" id="login-error" role="alert"></div>
            <button class="btn accent" id="login-submit" type="submit">进入产品目录</button>
            <div class="login-hint">
              演示账号（密码 <code>Demo@2026</code>）：<br />
              <code>admin@${esc(BRAND.short)}.io</code> 产品经理 · <code>analyst@${esc(BRAND.short)}.io</code> 口径专员 ·
              <code>viewer@${esc(BRAND.short)}.io</code> 客户经理（费率隐藏）
            </div>
          </form>
        </section>
      </div>`;

    const form = root.querySelector('#login-form');
    const errorNode = root.querySelector('#login-error');
    const submit = root.querySelector('#login-submit');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      errorNode.textContent = '';
      submit.disabled = true;
      submit.textContent = '正在核对账号…';
      try {
        const result = await api.post('/api/auth/login', {
          email: form.email.value.trim(),
          password: form.password.value,
        });
        session.set(result.access_token, result.user);
        toast(`欢迎回来，${result.user.display_name}`);
        location.hash = '#/overview';
        await ctx.reload();
      } catch (err) {
        errorNode.textContent = err.code === 'AUTH_INVALID' ? '账号或密码不正确' : errorMessage(err);
      } finally {
        submit.disabled = false;
        submit.textContent = '进入产品目录';
      }
    });
  },
};

export default loginPage;
