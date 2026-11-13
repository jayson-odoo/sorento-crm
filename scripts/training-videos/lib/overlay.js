// Injected into every page of a recording: a visible cursor, a click ripple and a caption
// bar. Headless Chromium draws no cursor, so without this the viewer cannot follow the
// hand. Everything here is pointer-events: none, so it never intercepts a real click.
(() => {
  if (window.__tvOverlay) return;
  window.__tvOverlay = true;
  const css = `
  #tv-cursor{position:fixed;left:0;top:0;width:22px;height:22px;z-index:2147483647;pointer-events:none;
    transform:translate(-3px,-2px);transition:none}
  #tv-cursor svg{filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))}
  .tv-ripple{position:fixed;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;
    border:3px solid #f59e0b;background:rgba(245,158,11,.25);z-index:2147483646;pointer-events:none;
    animation:tvr .7s ease-out forwards}
  @keyframes tvr{from{transform:scale(.3);opacity:1}to{transform:scale(1.6);opacity:0}}
  #tv-caption{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);max-width:1080px;
    padding:9px 18px;border-radius:10px;background:rgba(17,24,39,.86);color:#fff;
    font:500 19px/1.35 system-ui,-apple-system,"Segoe UI",sans-serif;text-align:center;
    z-index:2147483645;pointer-events:none;opacity:0;transition:opacity .25s}
  #tv-caption.on{opacity:1}
  .tv-focus{outline:3px solid #f59e0b !important;outline-offset:3px !important;border-radius:6px}
  nextjs-portal{display:none !important}
  #tv-title{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
    background:#0f172a;color:#fff;z-index:2147483644;font-family:system-ui,sans-serif;pointer-events:none}
  #tv-title h1{font-size:44px;font-weight:700;margin:0 0 14px}
  #tv-title p{font-size:22px;opacity:.8;margin:0}`;
  const boot = () => {
    if (!document.body || document.getElementById('tv-cursor')) return;
    const st = document.createElement('style');
    st.textContent = css;
    document.head.appendChild(st);
    const c = document.createElement('div');
    c.id = 'tv-cursor';
    c.innerHTML =
      '<svg width="22" height="22" viewBox="0 0 24 24"><path d="M3 2l7 19 2.6-7.4L20 11z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    const p = window.__tvPos || { x: 640, y: 360 };
    c.style.left = p.x + 'px';
    c.style.top = p.y + 'px';
    document.body.appendChild(c);
    const cap = document.createElement('div');
    cap.id = 'tv-caption';
    document.body.appendChild(cap);
    if (window.__tvCaption) window.__tvSetCaption(window.__tvCaption);
  };
  window.__tvSetCaption = (t) => {
    window.__tvCaption = t;
    const el = document.getElementById('tv-caption');
    if (!el) return;
    el.textContent = t || '';
    el.classList.toggle('on', !!t);
  };
  document.addEventListener(
    'mousemove',
    (e) => {
      window.__tvPos = { x: e.clientX, y: e.clientY };
      const c = document.getElementById('tv-cursor');
      if (c) {
        c.style.left = e.clientX + 'px';
        c.style.top = e.clientY + 'px';
      } else boot();
    },
    true,
  );
  document.addEventListener(
    'mousedown',
    (e) => {
      const r = document.createElement('div');
      r.className = 'tv-ripple';
      r.style.left = e.clientX + 'px';
      r.style.top = e.clientY + 'px';
      document.body.appendChild(r);
      setTimeout(() => r.remove(), 800);
    },
    true,
  );
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
  new MutationObserver(boot).observe(document.documentElement, { childList: true, subtree: false });
})();
