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
      <td><span class="badge ${u.role === "user" ? "" : "on"}">${ROLE_NAMES[u.role] || esc(u.role)}</span></td>
      <td>${fmtDay(u.created_at)}</td>
      <td class="num">${u.videos}${u.videos ? `<div class="meta">${fmtMinutes(u.seconds)}</div>` : ""}</td>
      <td class="num">${u.posts || "–"}</td>
      <td>${u.last_video ? fmtDay(u.last_video) : "–"}</td>
      <td>${u.ai_keys.length ? esc(u.ai_keys.map((k) => ({ anthropic: "Claude", openai: "ChatGPT", gemini: "Gemini" }[k] || k)).join(", ")) : "–"}</td>
      <td>${u.youtube ? "Connected" : "–"}</td>
      <td class="num">${u.disk_bytes ? fmtBytes(u.disk_bytes) : "–"}</td>
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
    ["Disk used", fmtBytes(t.disk_bytes), "videos and thumbnails"],
  ]);
  bars($("signupChart"), s.signups_by_day, "sign-up");
  bars($("videoChart"), s.videos_by_day, "video");
  users = s.users;
  renderUsers();
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
  const body = { email: $("uEmail").value, name: $("uName").value };
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
  $("userFilter").addEventListener("input", renderUsers);
  $("refresh").onclick = loadStats;
  $("addUser").onclick = () => openUser(null);
  const jobs = [loadStats()];
  if (isAdmin()) {  // site settings are for admins only
    $("services").innerHTML = cleanCard() + SERVICES.map(card).join("");
    jobs.push(initClean(), ...SERVICES.map(async (s) => wire(s)(await api(`/api/admin/${s.key}`))));
  }
  await Promise.all(jobs);
})();
