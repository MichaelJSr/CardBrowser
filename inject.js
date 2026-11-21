// CardBrowser's page side: run after every site page load. The site's hook (TTSCardMaker site/assets/app.js appHook):
// openCard puts an empty div.card-app (data-file-psd / data-file-png: repo paths) in #modal .image-wrap and fires
// "card-dialog" on document with detail {id, psd, png, slot}. This fills the slot with three buttons. DOM by textContent only.
// The app is read-only: guards.py START sets window.cardApp before the site's scripts, so the site shows no Sign in or Edit.
// ASCII only (\u escapes): on Linux pywebview gives WebKitGTK the length in characters, which it reads as bytes.
(() => {
  if (window.__cardBrowser) return;
  window.__cardBrowser = true;
  const C = %CONFIG%;                                  // {os, version, pre, releases}: never a path
  const SHOW = { mac: "Show in Finder", win: "Show in Explorer", linux: "Show in folder" }[C.os];
  const OPEN = C.os === "linux" ? "Open PSD" : "Open in Photoshop";
  const NOTE = "position:fixed;right:12px;bottom:12px;z-index:97;max-width:min(420px,calc(100vw - 24px));display:flex;" +
    "gap:10px;align-items:center;padding:8px 12px;border-radius:10px;border:1px solid var(--border-strong,#8884);" +
    "background:var(--surface,#fff);color:var(--ink,#000);box-shadow:0 4px 16px #0004;font:14px/1.4 system-ui,sans-serif";
  const button = (slot, label, tip, call, rels) => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = label; b.dataset.tip = tip;        // the site's own tooltips
    b.addEventListener("click", async () => {
      const api = window.pywebview && window.pywebview.api, say = slot.querySelector(".card-app-say");
      if (!api || typeof api[call] !== "function") {
        say.textContent = "CardBrowser can't reach this page: use Reload in the CardBrowser menu.";
        return;
      }
      say.textContent = "\u2026";
      try {
        let r;
        for (const rel of rels) if (!(r = await api[call](rel)).missing) break;   // Show: the PSD when the PNG isn't pulled
        say.textContent = String(r.msg);
      } catch { say.textContent = "That didn't work."; }
    });
    slot.append(b);
  };
  function fill(slot) {
    if (!slot || !slot.isConnected || slot.childElementCount) return;    // a refill never doubles the buttons
    const { filePsd: psd, filePng: png } = slot.dataset;
    if (psd) button(slot, OPEN, "Opens the card's PSD from your TTSCardMaker folder", "open_psd", [psd]);
    if (png || psd) button(slot, SHOW, "Shows the card's PNG in your folder (its PSD is beside it): drag it from there", "reveal", [png, psd].filter(Boolean));
    if (png) button(slot, "Copy PNG", "Copies the PNG from your folder, to paste anywhere", "copy_png", [png]);
    const say = document.createElement("span");
    say.className = "muted card-app-say"; say.setAttribute("role", "status"); say.style.alignSelf = "center";
    slot.append(say);
  }
  document.addEventListener("card-dialog", e => fill(e.detail && e.detail.slot));
  fill(document.querySelector("#modal:not([hidden]) .card-app"));       // a deep link opened it before this ran
  const modal = document.getElementById("modal");                       // a site version without the hook: say so
  const missing = () => {
    if (!modal || modal.hidden || modal.querySelector(".card-app, .card-app-missing") || !modal.querySelector(".image-wrap .card-actions")) return;
    const n = document.createElement("p");
    n.className = "muted card-app-missing";
    n.textContent = "CardBrowser: this version of the card site has no file buttons (its app hook is missing).";
    modal.querySelector(".image-wrap").append(n);
  };
  if (modal) {
    new MutationObserver(missing).observe(modal, { attributes: true, attributeFilter: ["hidden"], childList: true });
    missing();
  }
  document.addEventListener("keydown", e => {                          // WebView2 turns browser keys off
    if (e.key === "F5" || ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "r")) {
      e.preventDefault(); location.reload();
    }
  });
  function corner(cls, parts, ms) {
    document.querySelectorAll("." + cls).forEach(x => x.remove());
    const box = document.createElement("div");
    box.className = cls; box.setAttribute("role", "status"); box.style.cssText = NOTE;
    box.append(...parts);
    const x = document.createElement("button");
    x.type = "button"; x.textContent = "\u2715"; x.setAttribute("aria-label", "Close");
    x.style.cssText = "padding:0 6px;border:0;background:transparent;color:inherit;cursor:pointer";
    x.addEventListener("click", () => box.remove());
    box.append(x);
    document.body.append(box);
    if (ms) setTimeout(() => box.remove(), ms);
    return box;
  }
  window.__cardBrowserNote = text => { const s = document.createElement("span"); s.textContent = String(text); corner("card-app-note", [s], 8000); };
  const open = window.open;                          // the deck's Print proxies writes into a blank window: none here
  window.open = function (url, ...rest) {
    const w = open.call(window, url, ...rest);
    if (!w && (!url || url === "about:blank")) {
      window.__cardBrowserNote("To print proxies, choose Copy share link, then open that link in your browser and print there.");
    }
    return w;
  };
  const TAG = /^v(\d{1,3})\.(\d{1,3})\.(\d{1,3})(-[0-9A-Za-z.]{1,20})?$/;
  const key = t => { const m = TAG.exec(t); return m ? [+m[1], +m[2], +m[3], m[4] ? 0 : 1] : null; };   // x.y.z-pre < x.y.z
  const newer = (a, b) => { for (let i = 0; i < 4; i++) if (a[i] !== b[i]) return a[i] > b[i]; return false; };
  async function updateCheck() {                     // once per launch, in the page: Python never goes online
    try {
      const r = await fetch(C.releases, { headers: { Accept: "application/vnd.github+json" }, credentials: "omit" });
      if (!r.ok) return;
      const list = await r.json(), mine = key("v" + C.version);
      let best = null;
      for (const rel of Array.isArray(list) ? list : []) {
        if (!rel || rel.draft || (rel.prerelease && !C.pre) || typeof rel.tag_name !== "string") continue;
        const k = key(rel.tag_name);
        if (k && (!best || newer(k, best.k))) best = { tag: rel.tag_name, k };
      }
      if (!best || !mine || !newer(best.k, mine)) return;
      const s = document.createElement("span"), a = document.createElement("a");
      s.textContent = `CardBrowser ${best.tag} is out: `;
      a.textContent = "download it";
      a.href = "https://github.com/MichaelJSr/CardBrowser/releases/tag/" + encodeURIComponent(best.tag);
      a.target = "_blank"; a.rel = "noopener";                          // the system browser
      s.append(a);
      corner("card-app-update", [s], 0);
    } catch { /* offline or rate-limited: nothing to say */ }
  }
  if (C.releases) updateCheck();
})();
