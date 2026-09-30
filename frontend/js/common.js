// Shared by every page.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// JSON request helper. Throws Error(message) on failure; a lost session goes back to sign-in.
async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    location.href = "/login";
    throw new Error("Please sign in.");
  }
  let data = null;
  try { data = await res.json(); } catch (_) { /* empty or non-JSON body */ }
  if (!res.ok) throw new Error(data?.error || `Something went wrong (${res.status}).`);
  return data;
}

// Top bar on signed-in pages.
async function initTopbar() {
  const { user } = await api("/api/auth/me");
  if (!user) return (location.href = "/login");
  $("who").textContent = user.name || user.email;
  if ($("adminLink")) $("adminLink").hidden = !user.can_manage;
  $("signout").onclick = async () => { await api("/api/auth/logout", { method: "POST" }); location.href = "/login"; };
  return user;
}

// Numbers for the stats tiles.
const fmtBytes = (n) => n < 1024 ** 2 ? `${Math.round(n / 1024)} KB`
  : n < 1024 ** 3 ? `${(n / 1024 ** 2).toFixed(1)} MB` : `${(n / 1024 ** 3).toFixed(2)} GB`;
const fmtMinutes = (seconds) => seconds < 60 ? `${Math.round(seconds)} s` : `${(seconds / 60).toFixed(seconds < 600 ? 1 : 0)} min`;
const statTiles = (tiles) => tiles.map(([label, value, note]) => `
  <div class="stat"><span class="stat-value">${esc(value)}</span><span class="stat-label">${esc(label)}</span>
    ${note ? `<span class="stat-note">${esc(note)}</span>` : ""}</div>`).join("");
