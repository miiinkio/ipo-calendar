"""Assemble the public site (index.html) from the dashboard page.

The dashboard page (page.html) is written against a small `dash` API.
This script wraps it in a standalone HTML document with:
  - theme tokens (light/dark) the page's CSS uses
  - a tiny `dash` shim that loads data/ipo.json and data/fees.json
Run: python3 build.py
"""
from pathlib import Path

ROOT = Path(__file__).parent
page = (ROOT / "page.html").read_text(encoding="utf-8")

HEAD = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>공모주 일정 캘린더</title>
<meta name="description" content="코스피·코스닥 공모주 청약일, 환불일, 상장일, 확정 공모가와 주관사를 한눈에 보는 캘린더. 매일 아침 자동 갱신.">
<meta property="og:title" content="공모주 일정 캘린더">
<meta property="og:description" content="청약·환불·상장 일정과 주관사, 확정 공모가, 청약 수수료를 한눈에.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect x='3' y='5' width='26' height='24' rx='4' fill='%232f6fdf'/%3E%3Crect x='3' y='5' width='26' height='7' rx='3' fill='%231b4fb0'/%3E%3Crect x='8' y='16' width='6' height='3' rx='1' fill='white'/%3E%3Crect x='8' y='22' width='12' height='3' rx='1' fill='white'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&family=Noto+Serif+KR:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {
  --font-anthropic-sans: 'Noto Sans KR', system-ui, -apple-system, 'Apple SD Gothic Neo', sans-serif;
  --font-anthropic-serif: 'Noto Serif KR', Georgia, serif;
  --color-bg: #f6f5f1; --color-panel: #ffffff; --color-fg: #1f1e1b; --color-fg-muted: #6b6860;
  --color-border-line: #e3e0d8; --color-ok: #1f7a4d; --color-warn: #a86a00; --color-bad: #c2352c;
  --c0: #2f6fdf; --c1: #d9822b; --c2: #2e9d6a; --c3: #8a5cd6; --c4: #e05d8c; --c5: #c98a1b; --c6: #2a9db5; --c7: #6d7a3a;
  --cds-font-size-caption: 12px; --cds-font-size-body: 14px; --cds-font-size-heading: 16px; --cds-font-size-title: 26px;
  --cds-font-weight-medium: 600;
  --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 12px; --cds-gap-lg: 20px; --cds-gap-xl: 32px;
  --cds-pad-xs: 4px; --cds-pad-sm: 8px; --cds-pad-md: 12px; --cds-pad-lg: 18px;
  --cds-radius: 10px; --cds-dur-slow: .3s;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #161614; --color-panel: #201f1c; --color-fg: #ecebe6; --color-fg-muted: #a3a097;
    --color-border-line: #34322d; --color-ok: #5cc794; --color-warn: #e0a64a; --color-bad: #ef6b61;
    --c0: #6c9cf0; --c1: #e9a25a; --c2: #5cc794; --c3: #b08cf0; --c4: #f08ab0; --c5: #e6b452; --c6: #5fc3d8; --c7: #a8b56a;
    color-scheme: dark;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; }
body { background: var(--color-bg); color: var(--color-fg); font-family: var(--font-anthropic-sans); -webkit-font-smoothing: antialiased; }
#dash-root { max-width: 1240px; margin: 0 auto; padding: 24px 16px 40px; }
@media (min-width: 900px) { #dash-root { padding: 36px 32px 56px; } }
.dash-skeleton { color: transparent !important; position: relative; }
.dash-skeleton::after { content: ""; position: absolute; left: 0; top: 50%; transform: translateY(-50%); width: min(10rem, 60%); height: .9em; border-radius: 6px; background: var(--color-border-line); animation: sk 1.2s ease-in-out infinite alternate; }
.ip-cal.dash-skeleton::after { top: 0; transform: none; width: 100%; height: 100%; }
@keyframes sk { from { opacity: .45; } to { opacity: 1; } }
.site-foot { max-width: 1240px; margin: 0 auto; padding: 0 16px 32px; color: var(--color-fg-muted); font-size: 12px; line-height: 1.6; }
@media (min-width: 900px) { .site-foot { padding: 0 32px 40px; } }
.ip-updated { color: var(--color-fg-muted); font-size: var(--cds-font-size-caption); margin-top: var(--cds-gap-xs); }
</style>
<script>
// Minimal stand-in for the dashboard runtime: loads the JSON files and re-runs subscribers.
window.dash = (() => {
  const files = { ipo: 'data/ipo.json', fees: 'data/fees.json' };
  const state = {};
  const subs = [];
  const fire = () => subs.forEach((f) => { try { f(); } catch (e) { console.error(e); } });
  Object.entries(files).forEach(([id, url]) => {
    state[id] = { status: 'loading', data: [] };
    fetch(url + '?v=' + Date.now(), { cache: 'no-store' })
      .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then((d) => { state[id] = { status: 'ok', data: Array.isArray(d) ? d : (d.rows || d.data || []) }; fire(); })
      .catch((e) => { state[id] = { status: 'error', data: [], message: String(e) }; fire(); });
  });
  let w = window.innerWidth;
  window.addEventListener('resize', () => { if (window.innerWidth !== w) { w = window.innerWidth; fire(); } });
  const calcs = {};
  const data = (id) => {
    if (calcs[id]) {
      const ins = calcs[id].inputs.map(data);
      if (ins.some((x) => x.status === 'error')) return { status: 'error', data: [] };
      if (ins.some((x) => x.status !== 'ok')) return { status: 'loading', data: [] };
      try { return { status: 'ok', data: calcs[id].fn(...ins.map((x) => x.data)) }; }
      catch (e) { console.error(e); return { status: 'error', data: [] }; }
    }
    return state[id] || { status: 'missing', data: [] };
  };
  return {
    data,
    onData: (fn) => { subs.push(fn); try { fn(); } catch (e) { console.error(e); } },
    colors: ['var(--c0)', 'var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)', 'var(--c6)', 'var(--c7)'],
    calc: (id, spec) => { calcs[id] = spec; },
    loader: () => {}, setLink: (h) => { try { history.replaceState(null, '', '#' + h); } catch (e) {} }, refresh: () => {},
    params: () => ({}), setParams: () => {}, resetParams: () => {},
  };
})();
</script>
<script>
// The page only needs these two d3 helpers, so they're inlined instead of loading d3.
window.d3 = {
  format: () => (n) => Number(n).toLocaleString('en-US'),
  ascending: (a, b) => (a == null ? NaN : b == null ? NaN : a < b ? -1 : a > b ? 1 : a >= b ? 0 : NaN),
};
</script>
</head>
<body>
<div id="dash-root">
"""

FOOT = """
</div>
<footer class="site-foot">
  공모주 일정은 DART 증권신고서 기반 공모주 일정 정리와 언론 보도를 교차 확인해 매일 아침 갱신합니다.
  청약 수수료는 비대면·일반 등급 기준이며 증권사 정책에 따라 달라질 수 있습니다.
  투자 권유가 아닌 정보 제공용이며, 청약 전 증권사 공고와 투자설명서를 꼭 확인하세요.
</footer>
<script>
// "마지막 업데이트" 표시
fetch('data/meta.json?v=' + Date.now(), { cache: 'no-store' })
  .then((r) => (r.ok ? r.json() : null))
  .then((m) => {
    if (!m || !m.updated_at) return;
    const d = new Date(m.updated_at);
    const t = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(d);
    const el = document.createElement('div'); el.className = 'ip-updated'; el.textContent = '마지막 업데이트 · ' + t;
    const head = document.querySelector('.ip-head'); if (head) head.appendChild(el);
  })
  .catch(() => {});
</script>
</body>
</html>
"""

(ROOT / "index.html").write_text(HEAD + page + FOOT, encoding="utf-8")
print("built index.html", len(HEAD + page + FOOT), "bytes")
