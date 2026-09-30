// Admin: site overview, users and roles, and (admins only) the Google OAuth client.

const SERVICES = [
  {
    key: "google", title: "Google sign-in and YouTube", idLabel: "Client ID", platform: "YouTube",
    idPlaceholder: "1234567890-abc123.apps.googleusercontent.com", secretPlaceholder: "GOCSPX-…",
    envVars: ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
    intro: `One Google OAuth client powers <strong>Continue with Google</strong> on the sign-in page and
      <strong>Connect YouTube</strong> in Settings.`,
    steps: (uris) => `
      <li>In <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener">Google Cloud
        Console → Credentials ↗</a>, choose <strong>Create credentials → OAuth client ID → Web application</strong>.
        (First time: set up the <strong>OAuth consent screen</strong> as <strong>External</strong>.)</li>
      <li>Under <strong>Authorised redirect URIs</strong>, add both of these:${uris}</li>
      <li>For YouTube sharing, also enable <strong>YouTube Data API v3</strong> in the API Library and add the
        <code>youtube.upload</code> and <code>youtube.readonly</code> scopes to the consent screen. While the app
        is in <em>Testing</em>, add each person who will connect under <strong>Test users</strong>.</li>
      <li>Paste the client ID and secret above.</li>`,
  },
];

const state = {};  // key -> latest status from the server
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function card(s) {
  return `
  <section class="card" id="svc-${s.key}">
    <div class="provider-head">
      <h2>${s.title}</h2>
      <span class="badge" data-f="badge"></span>
    </div>
    <p class="meta">${s.intro} Changes apply straight away, with no restart.</p>

    <div data-f="current" hidden>
      <label>${s.idLabel}</label>
      <p class="mono" data-f="id"></p>
      <label>Secret</label>
      <p class="mono" data-f="secret"></p>
      <p class="meta" data-f="updated"></p>
    </div>

    <p class="meta" data-f="env" hidden>These come from the <code>${s.envVars[0]}</code> and
      <code>${s.envVars[1]}</code> environment variables on the server, which take priority.
      To manage them here instead, remove those variables and restart the app.</p>

    <form data-f="form" hidden>
      <label for="${s.key}-id">${s.idLabel}</label>
      <input type="text" id="${s.key}-id" data-f="idInput" autocomplete="off" spellcheck="false" placeholder="${s.idPlaceholder}">
      <label for="${s.key}-secret">Secret</label>
      <input type="password" id="${s.key}-secret" data-f="secretInput" autocomplete="off" spellcheck="false" placeholder="${s.secretPlaceholder}">
      <div class="actions">
        <button type="submit" class="primary small" data-f="save">Check and save</button>
        <button type="button" class="ghost small" data-f="cancel" hidden>Cancel</button>
      </div>
    </form>

    <div class="actions" data-f="buttons" hidden>
      <button type="button" class="ghost small" data-f="replace">Replace</button>
      <button type="button" class="danger small" data-f="remove">Remove</button>
    </div>
    <p class="status" data-f="msg" hidden></p>

    <details class="setup">
      <summary>How to get these</summary>
      <ol class="steps" data-f="steps"></ol>
    </details>
  </section>`;
}

function wire(s) {
  const root = $(`svc-${s.key}`);
  const f = (name) => root.querySelector(`[data-f="${name}"]`);
  const msg = (text, isErr = false) => {
    f("msg").hidden = !text; f("msg").textContent = text || ""; f("msg").classList.toggle("err", isErr);
  };

  const render = (g) => {
    state[s.key] = g;
    const fromEnv = g.source === "env", saved = g.source === "admin";
    f("badge").textContent = fromEnv ? "Set by the server" : saved ? "On" : "Not set up";
    f("badge").classList.toggle("on", Boolean(g.source));
    f("current").hidden = !g.source;
    f("id").textContent = g.client_id;
    f("secret").textContent = g.secret_hint;
    f("updated").textContent = saved && g.updated_at
      ? `Saved ${new Date(g.updated_at).toLocaleString()}${g.updated_by ? ` by ${g.updated_by}` : ""}.` : "";
    f("env").hidden = !fromEnv;
    f("buttons").hidden = !saved;
    f("form").hidden = Boolean(g.source);
    f("cancel").hidden = true;
    root.querySelector("details").open = !g.source;  // show the steps until it's set up

    const uris = g.redirect_uris.map((u) => `
      <div class="copyrow"><code>${esc(u)}</code>
        <button type="button" class="ghost small" data-copy="${esc(u)}">Copy</button></div>`).join("");
    f("steps").innerHTML = s.steps(uris);
    root.querySelectorAll("[data-copy]").forEach((b) => (b.onclick = async () => {
      try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = "Copied"; }
      catch (_) { b.textContent = "Select and copy"; }
      setTimeout(() => (b.textContent = "Copy"), 1500);
    }));
  };

  f("replace").onclick = () => {
    f("form").hidden = false; f("cancel").hidden = false; f("buttons").hidden = true;
    f("idInput").value = state[s.key].client_id;
    f("secretInput").value = "";
    f("secretInput").placeholder = "Paste the secret again";
    f("idInput").focus();
    msg("");
  };
  f("cancel").onclick = () => { render(state[s.key]); msg(""); };

  f("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const g = state[s.key], clientId = f("idInput").value.trim();
    if (g.client_id && clientId !== g.client_id && g.connections > 0 &&
        !confirm(`This is a different app. ${plural(g.connections, `${s.platform} connection`)} made with the ` +
                 "old one will stop working and be removed, so those users must connect again. Continue?")) return;
    f("save").disabled = true;
    msg("Checking…");
    try {
      const r = await api(`/api/admin/${s.key}`, { method: "PUT",
        body: { client_id: clientId, client_secret: f("secretInput").value } });
      render(r);
      msg("Saved and checked. It's on now." +
          (r.removed_connections ? ` Removed ${plural(r.removed_connections, `old ${s.platform} connection`)}.` : ""));
    } catch (err) { msg(err.message, true); }
    f("save").disabled = false;
  });

  f("remove").onclick = async () => {
    const g = state[s.key], warnings = [];
    if (g.google_only_users) warnings.push(`${plural(g.google_only_users, "account")} can only sign in with Google and will be locked out until it's set up again.`);
    if (g.connections) warnings.push(`${plural(g.connections, `${s.platform} connection`)} will be removed.`);
    if (!confirm([`Remove the ${s.title} settings? That turns it off.`, ...warnings].join("\n\n"))) return;
    try {
      render(await api(`/api/admin/${s.key}`, { method: "DELETE" }));
      msg("Removed. It's off now.");
    } catch (err) { msg(err.message, true); }
  };

  return render;
}

// ---------- overview ----------
let users = [];
let me = null;  // the signed-in admin or manager
const ROLE_NAMES = { user: "User", manager: "Manager", admin: "Admin" };
const ROLE_HELP = {
  user: "Makes videos. No access to this page.",
  manager: "Sees this page and can add, edit and remove users. Can't change managers, admins or site settings.",
  admin: "Full access, including roles and the Google settings.",
};
const isAdmin = () => me.role === "admin";
const canManage = (u) => isAdmin() || u.role === "user";
const fmtDay = (iso) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

function bars(el, days, noun) {
  const max = Math.max(1, ...days.map((d) => d.count)), total = days.reduce((n, d) => n + d.count, 0);
  const short = (iso) => new Date(iso + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" });
  el.closest("figure").querySelector(".chart-total").textContent = `${total} ${noun}${total === 1 ? "" : "s"}`;
  el.closest("figure").querySelector(".chart-axis").innerHTML = `<span>${short(days[0].day)}</span><span>Today</span>`;
  el.innerHTML = days.map((d) => {
    const label = `${short(d.day)}: ${d.count}`;
    return `<span class="bar-col" title="${esc(label)}"><span class="bar-fill${d.count ? "" : " zero"}" style="height:${(100 * d.count) / max}%"></span></span>`;
  }).join("");
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", `${total} in the last ${days.length} days, most in one day ${max}`);
}

function renderUsers() {
  const q = $("userFilter").value.trim().toLowerCase();
  const shown = users.filter((u) => !q || u.email.toLowerCase().includes(q) || (u.name || "").toLowerCase().includes(q));
  $("noUsers").hidden = shown.length > 0;
  $("userRows").innerHTML = shown.map((u) => `
    <tr>
      <td><div class="who-cell">${esc(u.email)}${u.email === me.email ? ` <span class="meta">(you)</span>` : ""}</div>
        <div class="meta">${[u.name && esc(u.name), [u.has_password && "Email", u.google && "Google"].filter(Boolean).join(" + ")].filter(Boolean).join(" · ")}</div></td>
      <td data-label="Role"><span class="badge ${u.role === "user" ? "" : "on"}">${ROLE_NAMES[u.role] || esc(u.role)}</span></td>
      <td data-label="Plan">${esc(planName(u.plan))}</td>
      <td data-label="Signed up">${fmtDay(u.created_at)}</td>
      <td class="num" data-label="Videos">${u.videos}${u.videos ? `<div class="meta">${fmtMinutes(u.seconds)}</div>` : ""}</td>
      <td class="num" data-label="Posted">${u.posts || "–"}</td>
      <td data-label="Last video">${u.last_video ? fmtDay(u.last_video) : "–"}</td>
      <td data-label="AI keys">${u.ai_keys.length ? esc(u.ai_keys.map((k) => ({ anthropic: "Claude", openai: "ChatGPT", gemini: "Gemini" }[k] || k)).join(", ")) : "–"}</td>
      <td data-label="YouTube">${u.youtube ? "Connected" : "–"}</td>
      <td class="num" data-label="Disk">${u.disk_bytes ? fmtBytes(u.disk_bytes) : "–"}</td>
      <td class="row-actions">${canManage(u) ? `
        <button type="button" class="ghost small" data-edit="${u.id}">Edit</button>
        ${u.email === me.email ? "" : `<button type="button" class="danger small" data-remove="${u.id}">Delete</button>`}` : ""}</td>
    </tr>`).join("");
  document.querySelectorAll("[data-edit]").forEach((b) => (b.onclick = () => openUser(users.find((u) => u.id === Number(b.dataset.edit)))));
  document.querySelectorAll("[data-remove]").forEach((b) => (b.onclick = () => removeUser(users.find((u) => u.id === Number(b.dataset.remove)))));
}

async function loadStats() {
  const s = await api("/api/admin/stats"), t = s.totals;
  $("totals").innerHTML = statTiles([
    ["Users", t.users, t.new_7d ? `+${t.new_7d} this week, +${t.new_30d} in 30 days` : `+${t.new_30d} in 30 days`],
    ["Active this week", t.active_7d, "made a video in the last 7 days"],
    ["Email / Google sign-in", `${t.password_users} / ${t.google_users}`, "some accounts use both"],
    ["With an AI key", t.with_ai_key, t.users ? `${Math.round((100 * t.with_ai_key) / t.users)}% of users` : ""],
    ["Videos", t.videos, `${t.videos_7d} this week · ${fmtMinutes(t.seconds)} in total`],
    ["Posted to YouTube", t.posts_done, `${t.youtube_connections} channels connected${t.posts_failed ? ` · ${t.posts_failed} failed` : ""}`],
    ["On a paid plan", (t.plans.creator || 0) + (t.plans.pro || 0),
      `${t.plans.creator || 0} ${planName("creator")} · ${t.plans.pro || 0} ${planName("pro")}${t.pending_requests ? ` · ${t.pending_requests} waiting` : ""}`],
    ["Disk used", fmtBytes(t.disk_bytes), "videos and thumbnails"],
  ]);
  bars($("signupChart"), s.signups_by_day, "sign-up");
  bars($("videoChart"), s.videos_by_day, "video");
  users = s.users;
  renderUsers();
}

// ---------- plans ----------
let planInfo = {};  // key -> {name, monthly, videos, watermark}
const PLAN_ORDER = ["free", "creator", "pro"];
const inOrder = (all) => PLAN_ORDER.filter((k) => all[k]).map((k) => [k, all[k]]);
const planName = (key) => planInfo[key]?.name || key;

async function loadRequests() {
  const list = await api("/api/admin/plan-requests");
  $("requestsCard").hidden = list.length === 0;
  $("requestCount").textContent = `${list.length} waiting`;
  $("requestList").innerHTML = list.map((r) => `
    <div class="plan-row">
      <div><strong>${esc(r.email)}</strong>
        <div class="meta">${esc(planName(r.current_plan))} → ${esc(planName(r.plan))}, billed ${r.period} · asked ${fmtDay(r.created_at)}</div></div>
      <div class="plan-price">${planInfo[r.plan] ? `$${r.period === "yearly" ? planInfo[r.plan].yearly : planInfo[r.plan].monthly}` : ""}</div>
      <div class="plan-action">
        <button type="button" class="primary small" data-approve="${r.id}">Approve</button>
        <button type="button" class="ghost small" data-dismiss="${r.id}">Dismiss</button>
      </div>
    </div>`).join("");
  document.querySelectorAll("[data-approve], [data-dismiss]").forEach((b) => (b.onclick = async () => {
    const approve = "approve" in b.dataset;
    try {
      await api(`/api/admin/plan-requests/${approve ? b.dataset.approve : b.dataset.dismiss}/${approve ? "approve" : "dismiss"}`, { method: "POST" });
    } catch (err) { alert(err.message); }
    loadRequests(); loadStats();
  }));
}

const plansCard = () => `
  <section class="card" id="plansCard">
    <h2>Plans and prices</h2>
    <p class="meta">Shown on the home page and in Settings. Yearly price is 10 months, so 2 months free.
      Staff (managers and admins) have no limit.</p>
    <div class="table-wrap"><table class="users plans-edit">
      <thead><tr><th>Plan</th><th>Name</th><th class="num">$ per month</th><th class="num">Videos per month</th><th>Watermark</th></tr></thead>
      <tbody id="planRows"></tbody>
    </table></div>
    <div class="actions"><button type="button" class="primary small" id="savePlans">Save prices</button></div>
    <p class="status" id="plansMsg" hidden></p>
  </section>`;

function renderPlanRows(all) {
  $("planRows").innerHTML = inOrder(all).map(([k, p]) => `
    <tr data-plan="${k}">
      <td>${k}</td>
      <td><input type="text" data-f="name" value="${esc(p.name)}" maxlength="30"></td>
      <td class="num"><input type="number" data-f="monthly" value="${p.monthly}" min="0" step="0.01" ${k === "free" ? "disabled" : ""}></td>
      <td class="num"><input type="number" data-f="videos" value="${p.videos}" min="1" step="1"></td>
      <td><input type="checkbox" data-f="watermark" ${p.watermark ? "checked" : ""} aria-label="Watermark on ${esc(p.name)}"></td>
    </tr>`).join("");
}

async function initPlans() {
  renderPlanRows((await api("/api/admin/plans")).plans);
  $("savePlans").onclick = async () => {
    const body = {};
    document.querySelectorAll("#planRows tr").forEach((tr) => {
      const v = (f) => tr.querySelector(`[data-f="${f}"]`);
      body[tr.dataset.plan] = { name: v("name").value, monthly: v("monthly").value, videos: v("videos").value, watermark: v("watermark").checked };
    });
    const msg = (t, e = false) => { $("plansMsg").hidden = false; $("plansMsg").textContent = t; $("plansMsg").classList.toggle("err", e); };
    try {
      const r = await api("/api/admin/plans", { method: "PUT", body });
      renderPlanRows(r.plans);
      planInfo = r.plans;
      msg("Saved. The home page and Settings show the new prices now.");
      renderUsers();
    } catch (err) { msg(err.message, true); }
  };
}

// ---------- payment settings (admins) ----------
const CHECKOUT_LABELS = { creator_monthly: "Creator, monthly", creator_yearly: "Creator, yearly",
                          pro_monthly: "Pro, monthly", pro_yearly: "Pro, yearly" };

const paymentsCard = () => `
  <section class="card" id="paymentsCard">
    <div class="provider-head">
      <h2>Payments</h2>
      <span class="badge" id="payBadge"></span>
    </div>
    <p class="meta">Fill these in once the app is online. Saving them doesn't switch on card payments yet: that
      part gets built after launch. Until then, people request a plan in Settings and you approve it under
      Upgrade requests.</p>
    <form id="payForm">
      <div class="row">
        <div><label for="payProvider">Payment service</label><select id="payProvider"></select></div>
        <div><label for="payMode">Mode</label>
          <select id="payMode"><option value="test">Test (no real money)</option><option value="live">Live</option></select></div>
      </div>
      <label for="payStore">Store or vendor ID</label>
      <input type="text" id="payStore" autocomplete="off" spellcheck="false" placeholder="From your payment service's dashboard">
      <label for="payKey">API key <span class="meta" id="payKeyHint"></span></label>
      <input type="password" id="payKey" autocomplete="off" spellcheck="false" placeholder="Leave blank to keep the saved one">
      <label for="payWebhook">Webhook signing secret <span class="meta" id="payWebhookHint"></span></label>
      <input type="password" id="payWebhook" autocomplete="off" spellcheck="false" placeholder="Leave blank to keep the saved one">
      <label>Webhook address to give the payment service</label>
      <div class="copyrow"><code id="payWebhookUrl"></code>
        <button type="button" class="ghost small" id="payCopy">Copy</button></div>
      <p class="meta" id="payPublicNote"></p>
      <label class="first-group">Checkout links</label>
      <div class="checkout-grid" id="payCheckouts"></div>
      <p class="err" id="payError" hidden></p>
      <div class="actions">
        <button type="submit" class="primary small" id="paySave">Save payment settings</button>
        <button type="button" class="danger small" id="payClear">Clear all</button>
      </div>
      <p class="status" id="payMsg" hidden></p>
    </form>
  </section>`;

function renderPayments(c) {
  $("payProvider").innerHTML = Object.entries(c.providers).map(([k, label]) => `<option value="${k}">${esc(label)}</option>`).join("");
  $("payProvider").value = c.provider;
  $("payMode").value = c.mode;
  $("payStore").value = c.store_id;
  $("payKey").value = $("payWebhook").value = "";
  $("payKeyHint").textContent = c.api_key_hint ? `(saved ${c.api_key_hint})` : "(not saved)";
  $("payWebhookHint").textContent = c.webhook_secret_hint ? `(saved ${c.webhook_secret_hint})` : "(not saved)";
  $("payWebhookUrl").textContent = c.webhook_url;
  $("payPublicNote").textContent = c.public_site ? ""
    : "This is a local address, which payment services can't reach. Open this page on your public https:// site to get the real one.";
  $("payCheckouts").innerHTML = Object.entries(CHECKOUT_LABELS).map(([k, label]) => `
    <div><label for="co-${k}">${label}</label>
      <input type="url" id="co-${k}" data-checkout="${k}" value="${esc(c.checkout[k] || "")}" placeholder="https://…" spellcheck="false"></div>`).join("");
  const filled = c.provider && (c.api_key_hint || Object.values(c.checkout).some(Boolean));
  $("payBadge").textContent = filled ? `${c.providers[c.provider]} · ${c.mode === "live" ? "live" : "test"} · saved` : "Not set up";
  $("payBadge").classList.toggle("on", Boolean(filled));
}

async function initPayments() {
  renderPayments(await api("/api/admin/payments"));
  const msg = (t, e = false) => {
    $("payError").hidden = !e; $("payError").textContent = e ? t : "";
    $("payMsg").hidden = e || !t; $("payMsg").textContent = e ? "" : t;
  };
  $("payProvider").onchange = () => {
    $("payWebhookUrl").textContent = $("payWebhookUrl").textContent.replace(/[^/]+$/, $("payProvider").value || "provider");
  };
  $("payCopy").onclick = async () => {
    try { await navigator.clipboard.writeText($("payWebhookUrl").textContent); $("payCopy").textContent = "Copied"; }
    catch (_) { $("payCopy").textContent = "Select and copy"; }
    setTimeout(() => ($("payCopy").textContent = "Copy"), 1500);
  };
  $("payForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = { provider: $("payProvider").value, mode: $("payMode").value, store_id: $("payStore").value,
                   api_key: $("payKey").value, webhook_secret: $("payWebhook").value, checkout: {} };
    document.querySelectorAll("[data-checkout]").forEach((i) => (body.checkout[i.dataset.checkout] = i.value));
    if (body.mode === "live" && !confirm("Save in live mode? Use it only with your real, live keys.")) return;
    $("paySave").disabled = true;
    try { renderPayments(await api("/api/admin/payments", { method: "PUT", body })); msg("Saved."); }
    catch (err) { msg(err.message, true); }
    $("paySave").disabled = false;
  });
  $("payClear").onclick = async () => {
    if (!confirm("Clear all payment settings, including the saved keys?")) return;
    renderPayments(await api("/api/admin/payments", { method: "DELETE" }));
    msg("Cleared.");
  };
}

// ---------- auto-clean (admins) ----------
const cleanCard = () => `
  <section class="card" id="cleanup">
    <div class="provider-head">
      <h2>Auto-clean posted videos</h2>
      <span class="badge" id="cleanBadge"></span>
    </div>
    <p class="meta">Removes a video's file from this computer once it's on YouTube, to save space. The entry,
      its thumbnail and its YouTube link stay in My videos. Checks every 15 minutes while the app is running.</p>
    <label for="cleanDelay">Remove the file</label>
    <div class="keyrow">
      <select id="cleanDelay"></select>
      <button type="button" class="ghost small" id="cleanRun">Run now</button>
    </div>
    <p class="meta" id="cleanLast"></p>
    <p class="status" id="cleanMsg" hidden></p>
  </section>`;

function renderClean(c) {
  $("cleanDelay").innerHTML = [["", "Never (off)"], ...Object.entries(c.options)]
    .map(([v, label]) => `<option value="${v}">${esc(label)}</option>`).join("");
  $("cleanDelay").value = c.hours;
  $("cleanBadge").textContent = c.hours === "" ? "Off" : "On";
  $("cleanBadge").classList.toggle("on", c.hours !== "");
  $("cleanRun").disabled = c.hours === "";
  $("cleanLast").textContent = c.last_run
    ? `Last check ${new Date(c.last_run.at).toLocaleString()}: removed ${c.last_run.removed} file${c.last_run.removed === 1 ? "" : "s"}.` : "";
}

function cleanMsg(text, isErr = false) {
  $("cleanMsg").hidden = !text; $("cleanMsg").textContent = text; $("cleanMsg").classList.toggle("err", isErr);
}

async function initClean() {
  renderClean(await api("/api/admin/cleanup"));
  $("cleanDelay").onchange = async () => {
    const hours = $("cleanDelay").value;
    if (hours === "0" && !confirm("Remove each video's file as soon as it's posted? People won't be able to download or re-post it from here afterwards.")) {
      return renderClean(await api("/api/admin/cleanup"));
    }
    try {
      renderClean(await api("/api/admin/cleanup", { method: "PUT", body: { hours } }));
      cleanMsg(hours ? "Saved. It runs within 15 minutes, or click Run now." : "Auto-clean is off.");
    } catch (err) { cleanMsg(err.message, true); }
  };
  $("cleanRun").onclick = async () => {
    $("cleanRun").disabled = true;
    try {
      const r = await api("/api/admin/cleanup/run", { method: "POST" });
      renderClean(r);
      cleanMsg(`Done. Removed ${r.removed} file${r.removed === 1 ? "" : "s"}.`);
      loadStats();
    } catch (err) { cleanMsg(err.message, true); $("cleanRun").disabled = false; }
  };
}

// ---------- add / edit / delete users ----------
let editing = null;  // the user being edited, or null when adding

function openUser(u) {
  editing = u || null;
  const self = u && u.email === me.email;
  $("userDlgTitle").textContent = u ? `Edit ${u.email}` : "Add user";
  $("uEmail").value = u ? u.email : "";
  $("uName").value = u ? u.name || "" : "";
  $("uPassword").value = "";
  $("uPasswordLabel").textContent = u ? "New password" : "Password";
  $("uPassword").placeholder = u ? "Leave blank to keep the current one" : "At least 8 characters";
  $("uPasswordNote").textContent = u
    ? "Setting a new password signs them out on every device."
    : "Share it with them privately. They can sign in with Google instead if their email matches.";
  const roles = isAdmin() ? ["user", "manager", "admin"] : ["user"];
  $("uRole").innerHTML = roles.map((r) => `<option value="${r}">${ROLE_NAMES[r]}</option>`).join("");
  $("uRole").value = u ? u.role : "user";
  $("uPlan").innerHTML = inOrder(planInfo).map(([k, p]) => `<option value="${k}">${esc(p.name)} (${p.videos} videos/month)</option>`).join("");
  $("uPlan").value = u ? u.plan : "free";
  $("uRole").disabled = self || roles.length === 1;
  const describe = () => ($("uRoleNote").textContent = self
    ? "You can't change your own role. Ask another admin."
    : ROLE_HELP[$("uRole").value]);
  $("uRole").onchange = describe;
  describe();
  $("userError").hidden = true;
  $("userSave").disabled = false;
  $("userDlg").showModal();
  $("uEmail").focus();
}

$("userForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = { email: $("uEmail").value, name: $("uName").value, plan: $("uPlan").value };
  if ($("uPassword").value) body.password = $("uPassword").value;
  if (!$("uRole").disabled) body.role = $("uRole").value;
  if (editing && body.role === editing.role) delete body.role;
  if (body.role === "admin" && (!editing || editing.role !== "admin") &&
      !confirm(`Make ${body.email} an admin? They'll have full access, including roles and site settings.`)) return;
  $("userSave").disabled = true;
  try {
    if (editing) await api(`/api/admin/users/${editing.id}`, { method: "PATCH", body });
    else await api("/api/admin/users", { method: "POST", body: { ...body, role: body.role || "user" } });
    $("userDlg").close();
    await loadStats();
  } catch (err) {
    $("userError").hidden = false;
    $("userError").textContent = err.message;
    $("userSave").disabled = false;
  }
});

async function removeUser(u) {
  const what = u.videos ? `Their ${u.videos} video${u.videos === 1 ? "" : "s"} and saved keys will be permanently deleted.`
    : "Their saved keys and settings will be permanently deleted.";
  if (!confirm(`Delete ${u.email}? ${what} Anything already posted on YouTube stays there.`)) return;
  try {
    await api(`/api/admin/users/${u.id}`, { method: "DELETE" });
    await loadStats();
  } catch (err) { alert(err.message); }
}

document.querySelectorAll("[data-close]").forEach((b) => (b.onclick = () => b.closest("dialog").close()));

(async () => {
  me = await initTopbar();
  planInfo = (await api("/api/plans")).plans.reduce((all, p) => ({ ...all, [p.key]: p }), {});
  loadRequests();
  $("userFilter").addEventListener("input", renderUsers);
  $("refresh").onclick = loadStats;
  $("addUser").onclick = () => openUser(null);
  const jobs = [loadStats()];
  if (isAdmin()) {  // site settings are for admins only
    $("services").innerHTML = plansCard() + paymentsCard() + cleanCard() + SERVICES.map(card).join("");
    jobs.push(initPlans(), initPayments(), initClean(), ...SERVICES.map(async (s) => wire(s)(await api(`/api/admin/${s.key}`))));
  }
  await Promise.all(jobs);
})();
