// Keeps open pages current without a manual refresh.
// Polls /api/state; when the inbox changes it updates the unread count and favicon,
// and on the inbox page swaps in the fresh list. Notification pages never reload.
(function () {
  const POLL_MS = 10000;
  const body = document.body;
  const isInbox = body.dataset.page === "inbox";
  const icon = document.getElementById("favicon");
  const headerCount = document.getElementById("header-count");
  let version = body.dataset.version;
  let busy = false;

  function setUnread(n) {
    if (headerCount) {
      headerCount.textContent = n;
      headerCount.hidden = n === 0;
    }
    if (icon) icon.href = n ? icon.dataset.unread : icon.dataset.read;
  }

  async function refreshInbox() {
    // GET / has no side effects, so re-fetching it is safe (unlike /n/<id>, which marks read).
    const res = await fetch(location.href, { cache: "no-store" });
    if (!res.ok) return;
    const doc = new DOMParser().parseFromString(await res.text(), "text/html");
    const fresh = doc.querySelector("main");
    const current = document.querySelector("main");
    if (!fresh || !current) return;
    const y = window.scrollY;
    current.replaceWith(fresh);
    document.title = doc.title;
    window.scrollTo(0, y);
  }

  async function poll() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const res = await fetch("/api/state", { cache: "no-store" });
      if (!res.ok) return;
      const state = await res.json();
      if (state.version === version) return;
      version = state.version;
      setUnread(state.unread);
      if (isInbox) await refreshInbox();
    } catch (_) {
      // Server restarting or asleep; try again on the next tick.
    } finally {
      busy = false;
    }
  }

  setInterval(poll, POLL_MS);
  // Catch up immediately when you switch back to the tab, or come Back to this page.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) poll();
  });
  window.addEventListener("pageshow", (e) => {
    if (e.persisted) poll();
  });
})();
