(() => {
  // Same-tab navigation preserves the main LIFF app's sessionStorage token.
  if (!/^\/(liff|admin|director)(\/|$)/i.test(location.pathname)) return;
  if (document.getElementById('jiaan1030-emergency-launcher')) return;
  function append() {
    if (!document.body || document.getElementById('jiaan1030-emergency-launcher')) return;
    const a = document.createElement('a');
    a.id = 'jiaan1030-emergency-launcher';
    a.href = '/api/jiaan1030/emergency-ui';
    a.textContent = '緊急通報／督導接手';
    a.setAttribute('aria-label', '開啟緊急通報及督導接手頁面');
    a.style.cssText = 'position:fixed;right:10px;bottom:90px;z-index:9999;background:#b42318;color:#fff;font-weight:700;border-radius:16px;padding:14px 16px;text-decoration:none;font-size:16px;box-shadow:0 4px 14px #0003;';
    document.body.appendChild(a);
    // Do not cover login/status on other routes or overlays after navigation.
    const obs = new MutationObserver(() => { a.style.display = /^\/(liff|admin|director)(\/|$)/i.test(location.pathname) ? '' : 'none'; });
    obs.observe(document.body, {childList:true,subtree:false});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', append, {once:true}); else append();
})();
