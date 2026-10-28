/* ACL Console — 前端逻辑（无框架、无依赖）
   只读：仅 GET /api/*；每 2s 轮询当前视图（实时优先）。 */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function el(tag, attrs, kids) {
  const e = document.createElement(tag);
  if (attrs) for (const k in attrs) {
    if (k === 'html') e.innerHTML = attrs[k];
    else if (k === 'text') e.textContent = attrs[k];
    else if (k === 'class') e.className = attrs[k];
    else e.setAttribute(k, attrs[k]);
  }
  (kids || []).forEach(c => e.appendChild(c));
  return e;
}

const DIM_NAMES = ['arousal', 'valence', 'fatigue', 'tension', 'attention', 'memory', 'pred-err', 'boredom'];
const fmtNum = (v, d = 2) => (v == null || isNaN(v)) ? '—' : Number(v).toFixed(d);
const fmtInt = (v) => (v == null || isNaN(v)) ? '—' : String(Math.round(v));

function humanAge(ts) {
  if (!ts) return '—';
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return Math.round(s) + ' 秒前';
  if (s < 3600) return Math.round(s / 60) + ' 分钟前';
  if (s < 86400) return Math.round(s / 3600) + ' 小时前';
  return Math.round(s / 86400) + ' 天前';
}
function shortTime(t) {
  if (t == null) return '—';
  const d = Math.floor(t / 86400) + 1, h = (t % 86400) / 3600;
  return 'd' + d + ' ' + h.toFixed(1) + 'h';
}
/* 数字滚动：值变化时缓动过渡（首次直接设值，入场交给单元格动画） */
function tweenNum(sel, to, dec) {
  const el = typeof sel === 'string' ? $(sel) : sel;
  if (!el || to == null || isNaN(to)) return;
  const prev = el.__v;
  if (prev != null && Math.abs(prev - to) < 1e-9) return;
  const from = (prev == null) ? to : prev;
  el.__v = to;
  if (from === to || HALF.reduced) { el.textContent = to.toFixed(dec); return; }
  const t0 = performance.now(), dur = 950;
  const step = (t) => {
    const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = (from + (to - from) * e).toFixed(dec);
    if (p < 1) requestAnimationFrame(step); else el.textContent = to.toFixed(dec);
  };
  requestAnimationFrame(step);
}
/* 正方形统计单元格（线条由网格边框提供） */
function statTile(k, v) {
  return `<div class="cell sq"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`;
}

/* ============ 半调（Hero 正方形内 · 稀疏点径渐变 · 适中动态 · 纯黑点） ============ */
const HALF = { canvas: null, ctx: null, w: 0, h: 0, dpr: 1, pitch: 26, raf: 0, t0: 0, last: 0,
  px: 0, py: 0, tpx: 0, tpy: 0, reduced: false, ro: null,
  mx: 0, my: 0, hx: 0, hy: 0, hover: 0, hoverT: 0, hasHover: false };

function halftoneResize() {
  const c = HALF.canvas; if (!c) return;
  const w = c.clientWidth, h = c.clientHeight;
  if (w < 20 || h < 20) { HALF.w = 0; HALF.h = 0; return; }
  HALF.w = w; HALF.h = h;
  HALF.dpr = Math.min(2, window.devicePixelRatio || 1);
  c.width = Math.round(w * HALF.dpr);
  c.height = Math.round(h * HALF.dpr);
  HALF.ctx = c.getContext('2d');
  HALF.ctx.setTransform(HALF.dpr, 0, 0, HALF.dpr, 0, 0);
}

function halftoneDraw(tsec) {
  const ctx = HALF.ctx;
  if (!ctx || !HALF.w) return;
  const w = HALF.w, h = HALF.h, pitch = HALF.pitch;
  const R = pitch * 0.44;                       // 最大点径 < 间距一半 → 绝不接触/重合
  const col = getComputedStyle(document.documentElement).getPropertyValue('--tx').trim() || '#000000';
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = col;                          // 纯黑点（不透明）→ 黑白分明
  ctx.globalAlpha = 1;
  HALF.px += (HALF.tpx - HALF.px) * 0.05;
  HALF.py += (HALF.tpy - HALF.py) * 0.05;
  const ox = HALF.px * 10, oy = HALF.py * 10;
  const cx = 0.5 + 0.18 * Math.sin(tsec * 0.34), cy = 0.5 + 0.18 * Math.cos(tsec * 0.29);
  // 悬停位置缓动（鼠标互动）
  HALF.hx += (HALF.mx - HALF.hx) * 0.2;
  HALF.hy += (HALF.my - HALF.hy) * 0.2;
  HALF.hover += (HALF.hoverT - HALF.hover) * 0.1;
  const ho = HALF.hover;
  const inflR = pitch * pitch * 4;
  for (let y = pitch * 0.5; y < h + pitch; y += pitch) {
    for (let x = pitch * 0.5; x < w + pitch; x += pitch) {
      const u = (x + ox) / w, v = (y + oy) / h;
      const band = Math.sin((u * 0.9 + v * 1.1) * Math.PI * 2 - tsec * 0.5);
      const g = Math.pow((band + 1) * 0.5, 2.4);
      const dx = u - cx, dy = v - cy;
      const clus = Math.exp(-(dx * dx + dy * dy) / 0.16);
      let a = Math.max(g, clus);
      // 边缘自然衰减：靠近四边时点径连续缩小到 0，避免突然隔开
      const edge = Math.min(u, 1 - u, v, 1 - v) / 0.30;
      const f = Math.min(1, Math.max(0, edge));
      a *= f * f * (3 - 2 * f);
      // 鼠标互动：光标附近的点“轻微变大”（半径上限仍为 R < 半间距，绝不重叠糊连）
      if (ho > 0.002) {
        const hdx = x - HALF.hx, hdy = y - HALF.hy;
        const infl = ho * Math.exp(-(hdx * hdx + hdy * hdy) / inflR);
        if (infl > 0.002) a += infl * 0.3;
      }
      if (a < 0.02) continue;                    // 稀疏
      const r = R * Math.pow(Math.min(1, a), 1.1);
      if (r < 0.5) continue;
      ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.fill();
    }
  }
}

function halftoneLoop(ts) {
  if (!HALF.t0) HALF.t0 = ts;
  if (!HALF.last || ts - HALF.last > 26) { HALF.last = ts; halftoneDraw((ts - HALF.t0) / 1000); }
  HALF.raf = requestAnimationFrame(halftoneLoop);
}
function halftoneStart() { if (HALF.reduced || HALF.raf) return; HALF.raf = requestAnimationFrame(halftoneLoop); }
function halftoneStop() { if (HALF.raf) { cancelAnimationFrame(HALF.raf); HALF.raf = 0; } }

function initHalftone() {
  HALF.canvas = $('#halftone');
  if (!HALF.canvas) return;
  HALF.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  halftoneResize();
  if (HALF.reduced) { halftoneDraw(2.0); return; }
  halftoneStart();
  // 鼠标悬停互动：光标附近的点变大并被推开
  const sq = HALF.canvas.parentElement || HALF.canvas;
  sq.addEventListener('pointermove', (e) => {
    const r = sq.getBoundingClientRect();
    HALF.mx = e.clientX - r.left; HALF.my = e.clientY - r.top;
    if (!HALF.hasHover) { HALF.hx = HALF.mx; HALF.hy = HALF.my; HALF.hasHover = true; }
    HALF.hoverT = 1;
  });
  sq.addEventListener('pointerleave', () => { HALF.hoverT = 0; });
  if (window.ResizeObserver) {
    HALF.ro = new ResizeObserver(() => halftoneResize());
    HALF.ro.observe(HALF.canvas.parentElement || HALF.canvas);
  }
  window.addEventListener('resize', halftoneResize);
  window.addEventListener('mousemove', (e) => {
    HALF.tpx = (e.clientX / window.innerWidth) * 2 - 1;
    HALF.tpy = (e.clientY / window.innerHeight) * 2 - 1;
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) halftoneStop(); else halftoneStart(); });
}

/* ---------------- 主题 ---------------- */
function initTheme() {
  const KEY = 'acl-theme-v2';                       // 换 key：忽略旧值，回到“纯白”默认
  const ATTR = 'data-acl-theme';                    // 用独立属性名，避免与预览宿主冲突
  const saved = localStorage.getItem(KEY);
  document.documentElement.setAttribute(ATTR, saved || 'light');   // 默认纯白
  $('#theme').addEventListener('click', () => {
    const cur = document.documentElement.getAttribute(ATTR);
    document.documentElement.setAttribute(ATTR, cur === 'dark' ? 'light' : 'dark');
    localStorage.setItem(KEY, document.documentElement.getAttribute(ATTR));
  });
}

/* ---------------- 侧边栏主机 ---------------- */
function renderHost(host) {
  if (!host) return;
  const th = host.thermal || {};
  $('#side-host').innerHTML =
    `<div class="r"><span>load</span><b>${fmtNum((host.load || [])[0], 2)}</b></div>` +
    `<div class="r"><span>温度</span><b>${th.status === 'throttled' ? '降频' : th.status === 'ok' ? '正常' : '—'}</b></div>` +
    `<div class="r"><span>磁盘</span><b>${host.disk_free_gb == null ? '—' : host.disk_free_gb + 'G'}</b></div>`;
}

/* ---------------- Hero：优先运行中带目标的；否则最近有结果的 ---------------- */
let HERO_ID = null;
function pickLead(exps) {
  return exps.find(e => e.status === 'running' && e.target) ||
         exps.filter(e => e.has_results && e.target).sort((a, b) => (b.updated || 0) - (a.updated || 0))[0] ||
         exps.find(e => e.status === 'running') ||
         exps.find(e => e.has_results) || exps[0];
}
function renderHero(data) {
  const lead = pickLead(data.experiments || []);
  if (!lead) return;
  const arm = (lead.arms || []).find(a => a.running) || (lead.arms || [])[0] || {};
  const pcts = (lead.arms || []).map(a => a.pct).filter(p => p != null);
  const avg = pcts.length ? pcts.reduce((x, y) => x + y, 0) / pcts.length : 0;

  $('#hero-eyebrow').textContent = lead.status === 'running' ? '运行中 · 主实验' : '最近实验 · 已完成';
  $('#bignum').textContent = arm.day == null ? '—' : String(arm.day);
  $('#hero-unit').textContent = lead.target ? '/ ' + lead.target + ' 日' : '';
  $('#hero-name').textContent = lead.id + (lead.prereg_title ? ' · ' + lead.prereg_title.slice(0, 38) : '');
  $('#hero-meta').textContent = (lead.arms || []).map(a => a.arm + ' ' + (a.day == null ? '—' : a.day)).join('　·　');
  $('#hero-bar-fill').style.width = Math.round(avg * 100) + '%';

  if (HERO_ID !== lead.id) {
    const node = $('#bignum');
    if (node) { node.classList.remove('num-in'); void node.offsetWidth; node.classList.add('num-in'); }
  }
  if (HERO_ID !== lead.id && arm.day != null && !HALF.reduced) {
    const node = $('#bignum'), tgt = arm.day, t0 = performance.now();
    const step = (t) => {
      const p = Math.min(1, (t - t0) / 850), e = 1 - Math.pow(1 - p, 3);
      node.textContent = String(Math.round(tgt * e));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  HERO_ID = lead.id;
}

/* ---------------- 概览 ---------------- */
function expItem(e, withVerdicts) {
  const item = el('div', { class: 'item' });
  item.innerHTML =
    `<div class="item-head">` +
    `<span class="dot ${e.status === 'running' ? 'run' : e.status === 'done' ? 'done' : 'idle'}"></span>` +
    `<span class="item-name">${esc(e.id)}</span>` +
    `<span class="item-id">${esc(e.log || '')}</span>` +
    (e.prereg_title ? `<span class="item-sub">${esc(e.prereg_title)}</span>` : '') +
    `</div>`;
  const arms = el('div', { class: 'arms' });
  (e.arms || []).forEach(a => {
    const pct = a.pct == null ? 0 : Math.round(a.pct * 100);
    const tgt = e.target ? ' / ' + e.target : '';
    arms.innerHTML +=
      `<div class="arm"><div class="nm"><span class="dot ${a.running ? 'run' : 'done'}"></span>${esc(a.arm)}</div>` +
      `<div class="bar"><i style="width:${pct}%"></i></div>` +
      `<div class="num">day ${a.day == null ? '—' : a.day}${tgt}</div></div>`;
  });
  item.appendChild(arms);
  if (withVerdicts && e.verdicts) {
    const v = el('div', { class: 'verd' });
    Object.entries(e.verdicts).forEach(([k, o]) => {
      const parts = k.split('_');
      v.innerHTML +=
        `<div class="v"><div class="k">${esc(parts[0] + ' ' + parts.slice(1).join(' '))}</div>` +
        `<div class="val">${esc(o.detail || '')}</div>` +
        `<div class="st${o.pass ? '' : ' f'}">${o.pass ? 'PASS' : 'FAIL'}</div></div>`;
    });
    item.appendChild(v);
  }
  return item;
}

function renderOverview(data) {
  const exps = data.experiments || [];
  const running = exps.filter(e => e.status === 'running');
  const withRes = exps.filter(e => e.has_results).slice(0, 4);
  $('#ov-live-note').textContent = running.length ? running.length + ' 个进行中' : '无';

  const h = data.host || {};
  tweenNum('#t-run', running.length, 0);
  tweenNum('#t-exp', exps.length, 0);
  tweenNum('#t-disk', h.disk_free_gb, 1);
  tweenNum('#t-load', (h.load || [])[0], 2);

  const b1 = $('#ov-running'); b1.innerHTML = '';
  if (!running.length) b1.appendChild(el('div', { class: 'empty', text: '没有运行中的实验' }));
  running.forEach(e => b1.appendChild(expItem(e, false)));

  const b2 = $('#ov-results'); b2.innerHTML = '';
  if (!withRes.length) b2.appendChild(el('div', { class: 'empty', text: '暂无结果文件' }));
  withRes.forEach(e => b2.appendChild(expItem(e, true)));

  renderHero(data);
}

/* ---------------- 实验表 ---------------- */
const EXPANDED = new Set();
const expRelevant = (e) => e.status === 'running' || e.has_results || e.has_prereg || e.target;

function renderExperiments(data) {
  const exps = data.experiments || [];
  tweenNum('#e-total', exps.length, 0);
  tweenNum('#e-run', exps.filter(e => e.status === 'running').length, 0);
  tweenNum('#e-done', exps.filter(e => e.status === 'done').length, 0);
  tweenNum('#e-res', exps.filter(e => e.has_results).length, 0);

  const q = ($('#exp-filter').value || '').trim().toLowerCase();
  const showArch = $('#exp-archived').checked;
  const rows = exps.filter(e => {
    if (!showArch && !expRelevant(e)) return false;
    if (q && !e.id.toLowerCase().includes(q)) return false;
    return true;
  });
  const wrap = $('#exp-table'); wrap.innerHTML = '';
  if (!rows.length) { wrap.appendChild(el('div', { class: 'empty', text: '没有匹配的实验（勾选「含归档」可看全部）' })); return; }

  const table = el('table');
  table.innerHTML = `<thead><tr><th>实验</th><th>状态</th><th>臂 / 进度</th>
    <th class="mono">目标</th><th>判据</th><th class="mono">更新</th></tr></thead>`;
  const tb = el('tbody');
  rows.forEach(e => {
    const tr = el('tr', { class: 'rowlink' });
    const badge = e.status === 'running' ? '运行中' : e.status === 'done' ? '完成' : '空闲';
    tr.innerHTML =
      `<td><b>${esc(e.id)}</b></td>` +
      `<td><span class="dot ${e.status === 'running' ? 'run' : e.status === 'done' ? 'done' : 'idle'}"></span> <span class="note">${badge}</span></td>` +
      `<td>${(e.arms || []).map(a => `<span class="chip ${a.running ? 'run' : ''}">${esc(a.arm)} · ${a.day == null ? '—' : a.day}</span>`).join('')}</td>` +
      `<td class="num">${e.target == null ? '—' : e.target}</td>` +
      `<td>${verdictBadge(e)}</td>` +
      `<td class="mono">${humanAge(e.updated)}</td>`;
    tb.appendChild(tr);
    if (e.verdicts) {
      const det = el('tr', { class: 'verd-detail' });
      det.hidden = !EXPANDED.has(e.id);
      det.appendChild(el('td', { colspan: '6' }, [expItem(e, true)]));
      tb.appendChild(det);
      tr.addEventListener('click', () => {
        if (EXPANDED.has(e.id)) EXPANDED.delete(e.id); else EXPANDED.add(e.id);
        det.hidden = !det.hidden;
      });
    }
  });
  table.appendChild(tb);
  wrap.appendChild(table);
}
function verdictBadge(e) {
  if (!e.verdicts) return e.has_results ? '<span class="note">结果已出</span>' : '<span class="note">—</span>';
  const vals = Object.values(e.verdicts), p = vals.filter(v => v.pass).length;
  return `<span class="mono">${p}/${vals.length}</span> <span class="note">PASS</span>`;
}

/* ---------------- 实时 ---------------- */
async function loadLive(stateDir) {
  const d = await (await fetch('/api/live?state=' + encodeURIComponent(stateDir))).json();
  const host = $('#live-kpis');
  if (d.error) { host.innerHTML = `<div class="empty">${esc(d.error)}</div>`; $('#live-dims').innerHTML = ''; $('#live-meta').innerHTML = ''; return; }
  const last = d.last || {}, en = d.energy || {}, stage = d.stage || {}, sm = d.self_model || {};
  host.innerHTML = [
    statTile('day', esc(fmtInt(last.day))),
    statTile('阶段', esc(stage.stage || '—')),
    statTile('睡眠', last.asleep ? '睡眠中' : '清醒'),
    statTile('能量', fmtInt(en.fraction == null ? null : en.fraction * 100) + '<small>%</small>'),
    statTile('self_ratio', esc(fmtNum(last.self_ratio, 3))),
    statTile('预测惊奇', esc(fmtNum(last.s7, 2))),
    statTile('模式', esc(last.mode || '—')),
  ].join('');

  const series = d.series || [];
  $('#live-range').textContent = series.length ? ('最近 ' + series.length + ' 点 · 最新 ' + shortTime(series[series.length - 1].t)) : '无数据';
  const dims = $('#live-dims'); dims.innerHTML = '';
  for (let i = 0; i < 8; i++) {
    const vals = series.map(p => p.s[i]).filter(v => v != null);
    const cur = vals.length ? vals[vals.length - 1] : null;
    dims.innerHTML += `<div class="dim"><div class="t"><span class="s">s${i + 1}</span>` +
      `<span class="n">${DIM_NAMES[i]}</span><span class="val">${fmtNum(cur, 3)}</span></div>${sparkSVG(vals)}</div>`;
  }
  $('#live-meta').innerHTML = [
    ['sleep_pressure', esc(fmtNum(last.sleep_pressure, 3))],
    ['能量 level', en.level == null ? '—' : esc(fmtNum(en.level, 1))],
    ['stage.json', stage.stage ? '已读' : '无'],
    ['自我模型', esc(sm.text || (sm.n_versions ? 'v' + sm.n_versions : '—'))],
  ].map(([k, v]) => `<div class="i"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`).join('');
}

function sparkSVG(vals) {
  const W = 100, H = 38, pad = 2;
  if (!vals || vals.length < 2) return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"></svg>`;
  const mn = Math.min(...vals), mx = Math.max(...vals), rng = (mx - mn) || 1;
  const d = 'M' + vals.map((v, i) => {
    const x = pad + (W - 2 * pad) * i / (vals.length - 1);
    const y = pad + (H - 2 * pad) * (1 - (v - mn) / rng);
    return x.toFixed(2) + ' ' + y.toFixed(2);
  }).join(' L');
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><path d="${d}"/></svg>`;
}

/* ---------------- 流 ---------------- */
async function loadStreams(stateDir) {
  const d = await (await fetch('/api/streams?state=' + encodeURIComponent(stateDir) + '&n=60')).json();
  const inner = (d.inner_speech || []).slice().reverse();
  const voc = (d.vocalizations || []).slice().reverse();
  $('#stream-inner').innerHTML = inner.length ? inner.map(x =>
    `<div class="srow"><span class="t">${esc(shortTime(x.t))}</span>` +
    `<span class="x">${esc(x.text)}${x.composed ? '<span class="pill">composed</span>' : ''}</span>` +
    `<span class="a">act ${fmtNum(x.activation, 2)}</span></div>`).join('') : '<div class="empty">无数据</div>';
  $('#stream-voc').innerHTML = voc.length ? voc.map(x => {
    const tag = x.selected_by ? (x.was_winner === false ? '<span class="pill sel">selected</span>' : '<span class="pill">winner</span>') : '';
    return `<div class="srow"><span class="t">${esc(shortTime(x.t))}</span>` +
      `<span class="x">${esc(x.text)}${tag}</span>` +
      `<span class="a">s1 ${fmtNum(x.s1, 2)}</span></div>`;
  }).join('') : '<div class="empty">无数据</div>';
}

/* ---------------- 日志 ---------------- */
async function loadLogs() {
  if (!$('#log-file').options.length) {
    const d = await (await fetch('/api/logs')).json();
    $('#log-file').innerHTML = (d.files || []).map(f => `<option>${esc(f)}</option>`).join('');
  }
  const f = $('#log-file').value; if (!f) return;
  const d = await (await fetch('/api/logs?file=' + encodeURIComponent(f) + '&n=200')).json();
  $('#log-body').textContent = (d.lines || []).join('\n') || '（空）';
}

/* ---------------- 导航 / 轮询 ---------------- */
let VIEW = 'overview', OVERVIEW = null;

function fillSelects(ordered, prefers) {
  const len = String(ordered.length);
  for (const id of ['#live-state', '#stream-state']) {
    const sel = $(id);
    if (!sel || sel.dataset.count === len) continue;
    const prefer = prefers[id] || ordered[0];
    const keep = sel.value;
    sel.innerHTML = ordered.map(s => `<option${s === prefer ? ' selected' : ''}>${esc(s)}</option>`).join('');
    if (keep && ordered.includes(keep)) sel.value = keep;
    sel.dataset.count = len;
  }
}

async function tickOverview() {
  OVERVIEW = await (await fetch('/api/overview')).json();
  renderHost(OVERVIEW.host);
  renderOverview(OVERVIEW);
  renderExperiments(OVERVIEW);
  const states = OVERVIEW.live_states || [];
  const runningDirs = [];
  OVERVIEW.experiments.forEach(e => (e.arms || []).forEach(a => { if (a.running) runningDirs.push(a.dir); }));
  // 主实验的臂目录优先（数据更完整：轨迹+念头流）
  const lead = pickLead(OVERVIEW.experiments || []);
  const heroArms = lead ? (lead.arms || []).map(a => a.dir) : [];
  const ordered = runningDirs
    .concat(heroArms)
    .concat(states.filter(s => !runningDirs.includes(s) && !heroArms.includes(s)));
  fillSelects(ordered, {
    '#live-state': runningDirs[0] || heroArms[0] || 'state',
    '#stream-state': heroArms[0] || runningDirs[0] || 'state',
  });
  $('#footer-status').textContent = '已更新 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false }) + ' · 2s 自动刷新';
}

async function refreshView() {
  if (VIEW === 'live') return loadLive($('#live-state').value);
  if (VIEW === 'streams') return loadStreams($('#stream-state').value);
  if (VIEW === 'logs') return loadLogs();
}
function switchView(v) {
  VIEW = v;
  $$('#nav button').forEach(b => b.classList.toggle('on', b.dataset.view === v));
  $$('.view').forEach(s => { s.hidden = (s.id !== 'view-' + v); });
  refreshView();
}

function init() {
  initTheme();
  initHalftone();
  const on = (sel, ev, fn) => { const n = $(sel); if (n) n.addEventListener(ev, fn); };
  on('#nav', 'click', e => { const b = e.target.closest('button'); if (b) switchView(b.dataset.view); });
  on('#exp-filter', 'input', () => OVERVIEW && renderExperiments(OVERVIEW));
  on('#exp-archived', 'change', () => OVERVIEW && renderExperiments(OVERVIEW));
  on('#live-state', 'change', () => loadLive($('#live-state').value));
  on('#stream-state', 'change', () => loadStreams($('#stream-state').value));
  on('#log-file', 'change', loadLogs);
  on('#log-refresh', 'click', loadLogs);

  tickOverview().then(refreshView);
  setInterval(tickOverview, 2000);
  setInterval(refreshView, 2000);
}

document.addEventListener('DOMContentLoaded', init);
