// Settings: AI keys per provider, and account actions.

function renderProviders(list) {
  $("providers").innerHTML = list.map((p) => `
    <div class="provider" data-p="${esc(p.key)}">
      <div class="provider-head">
        <strong>${esc(p.label)}</strong>
        <span class="badge ${p.saved ? "on" : ""}">${p.saved ? `Key saved ····${esc(p.hint)}` : "No key"}</span>
      </div>
      ${p.saved ? `
        <label>Model</label>
        <select class="model">${p.models.map((m) =>
          `<option value="${esc(m)}" ${m === p.model ? "selected" : ""}>${esc(m)}</option>`).join("")}</select>
        <div class="actions">
          <button type="button" class="ghost small replace">Replace key</button>
          <button type="button" class="ghost small remove">Remove key</button>
        </div>` : ""}
      <form class="keyform" ${p.saved ? "hidden" : ""}>
        <label>API key <a class="meta" href="${esc(p.key_url)}" target="_blank" rel="noopener">Get a key ↗</a></label>
        <div class="keyrow">
          <input type="password" class="apikey" autocomplete="off" spellcheck="false" placeholder="Paste your key">
          <button type="submit" class="primary small">Save</button>
        </div>
      </form>
      <p class="meta status" hidden></p>
    </div>`).join("");

  $("providers").querySelectorAll(".provider").forEach((el) => {
    const provider = el.dataset.p;
    const status = (msg, isErr = false) => {
      const s = el.querySelector(".status");
      s.hidden = !msg; s.textContent = msg; s.classList.toggle("err", isErr);
    };

    el.querySelector(".keyform").addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = e.target.querySelector("button");
      btn.disabled = true;
      status("Checking the key…");
      try {
        renderProviders(await api(`/api/settings/keys/${provider}`, {
          method: "PUT", body: { api_key: el.querySelector(".apikey").value } }));
      } catch (err) { status(err.message, true); btn.disabled = false; }
    });

    el.querySelector(".model")?.addEventListener("change", async (e) => {
      try {
        await api(`/api/settings/keys/${provider}`, { method: "PATCH", body: { model: e.target.value } });
        status("Model saved.");
      } catch (err) { status(err.message, true); }
    });

    el.querySelector(".replace")?.addEventListener("click", () => {
      el.querySelector(".keyform").hidden = false;
      el.querySelector(".apikey").focus();
    });

    el.querySelector(".remove")?.addEventListener("click", async () => {
      if (!confirm("Remove this key? The AI writer won't be able to use this provider.")) return;
      renderProviders(await api(`/api/settings/keys/${provider}`, { method: "DELETE" }));
    });
  });
}

const CONNECT_NOTES = {
  youtube: "Needs a YouTube channel. Uploads stay private until this app passes Google's review.",
};

function renderConnections(list) {
  $("connList").innerHTML = list.map((c) => {
    let status, action;
    if (!c.available) {
      status = `<span class="badge">Not set up on this server</span>`;
      action = `<p class="meta">The site owner needs to add ${esc(c.setup)}.</p>`;
    } else if (c.connected && !c.expired) {
      const until = c.expires_at
        ? new Date(c.expires_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
      status = `<span class="badge on">Connected: ${esc(c.account)}</span>`;
      action = `<p class="meta">${until ? `Access lasts about 60 days. Reconnect before ${until} to keep sharing.` : ""}</p>
        <div class="actions"><button type="button" class="ghost small" data-disconnect="${c.platform}">Disconnect</button></div>`;
    } else {
      status = `<span class="badge">${c.expired ? "Expired" : "Not connected"}</span>`;
      action = `<p class="meta">${esc(CONNECT_NOTES[c.platform])}</p>
        <div class="actions"><a class="primary small btnlink" href="/connect/${c.platform}">${c.expired ? "Reconnect" : "Connect"} ${esc(c.label)}</a></div>`;
    }
    return `<div class="provider"><div class="provider-head"><strong>${esc(c.label)}</strong>${status}</div>${action}</div>`;
  }).join("");

  document.querySelectorAll("[data-disconnect]").forEach((b) => (b.onclick = async () => {
    if (!confirm("Disconnect? You'll need to connect again to share videos there.")) return;
    renderConnections(await api(`/api/connections/${b.dataset.disconnect}/disconnect`, { method: "POST" }));
  }));
}

function showConnectResult() {
  const q = new URLSearchParams(location.search);
  const platform = q.get("connected") || q.get("error");
  if (!platform) return;
  const name = "YouTube";
  $("connMsg").hidden = false;
  $("connMsg").classList.toggle("err", q.has("error"));
  $("connMsg").textContent = q.has("error") ? q.get("msg") || `Couldn't connect ${name}.` : `${name} connected.`;
  history.replaceState(null, "", "/settings#connections");  // don't show it again on reload
}

async function init() {
  const user = await initTopbar();
  renderConnections(await api("/api/connections"));
  showConnectResult();
  const methods = [user.has_password && "email and password", user.google && "Google"].filter(Boolean);
  $("accountInfo").textContent = `Signed in as ${user.email}, using ${methods.join(" and ")}.`;
  renderProviders(await api("/api/settings/keys"));

  $("logoutAll").onclick = async () => {
    await api("/api/auth/logout-everywhere", { method: "POST" });
    location.href = "/login";
  };
  $("deleteAccount").onclick = async () => {
    if (!confirm("Delete your account? Your saved keys and every video you made will be permanently deleted.")) return;
    try {
      await api("/api/auth/delete-account", { method: "POST" });
      location.href = "/login";
    } catch (err) { $("accountError").hidden = false; $("accountError").textContent = err.message; }
  };
}

init();

// ---------- plan & billing ----------
let billingData = null, billingPeriod = "monthly";
const fmtMoney = (n) => `$${Number.isInteger(n) ? n : n.toFixed(2)}`;

function renderBilling(b) {
  billingData = b;
  const u = b.usage;
  $("planBadge").textContent = u.staff ? `${b.plan.name} · staff, unlimited` : `${b.plan.name} plan`;
  const resets = new Date(u.resets_at).toLocaleDateString(undefined, { day: "numeric", month: "short" });
  $("usage").innerHTML = u.limit === null
    ? `<p class="meta">You've made ${u.used} video${u.used === 1 ? "" : "s"} this month. No limit for staff accounts.</p>`
    : `<div class="usage-row"><span>${u.used} of ${u.limit} videos used this month</span><span class="meta">Resets ${resets}</span></div>
       <div class="bar"><div class="fill${u.left === 0 ? " full" : ""}" style="width:${Math.min(100, (100 * u.used) / u.limit)}%"></div></div>
       ${u.watermark ? `<p class="meta">Free videos carry a small “Made with Script Studio” label. Paid plans remove it.</p>` : ""}`;

  const req = b.request;
  $("planList").innerHTML = b.plans.map((p) => {
    const current = p.key === b.plan.key;
    const asked = req && req.plan === p.key;
    const price = p.monthly === 0 ? "Free" : billingPeriod === "yearly" ? `${fmtMoney(p.yearly)}/year` : `${fmtMoney(p.monthly)}/month`;
    let action = "";
    if (current) action = `<span class="badge on">Current plan</span>`;
    else if (asked) action = `<span class="badge">Requested (${req.period})</span>
      <button type="button" class="ghost small" data-cancel>Cancel</button>`;
    else if (p.monthly > 0) action = `<button type="button" class="primary small" data-ask="${p.key}">Choose ${esc(p.name)}</button>`;
    return `<div class="plan-row${current ? " current" : ""}">
      <div><strong>${esc(p.name)}</strong> <span class="meta">${p.videos} videos a month${p.watermark ? " · with label" : ""}</span></div>
      <div class="plan-price">${price}</div>
      <div class="plan-action">${action}</div>
    </div>`;
  }).join("");

  document.querySelectorAll("[data-ask]").forEach((btn) => (btn.onclick = async () => {
    try {
      renderBilling(await api("/api/billing/request", { method: "POST", body: { plan: btn.dataset.ask, period: billingPeriod } }));
      billingMsg("Request sent. You'll see the new plan here once it's switched on.");
    } catch (err) { billingMsg(err.message, true); }
  }));
  document.querySelectorAll("[data-cancel]").forEach((btn) => (btn.onclick = async () => {
    renderBilling(await api("/api/billing/request", { method: "DELETE" }));
    billingMsg("Request cancelled.");
  }));
}

function billingMsg(text, isErr = false) {
  $("billingMsg").hidden = !text; $("billingMsg").textContent = text; $("billingMsg").classList.toggle("err", isErr);
}

document.querySelectorAll("#billing [data-period]").forEach((b) => (b.onclick = () => {
  billingPeriod = b.dataset.period;
  document.querySelectorAll("#billing [data-period]").forEach((x) => {
    x.classList.toggle("on", x === b); x.setAttribute("aria-checked", String(x === b));
  });
  renderBilling(billingData);
}));

api("/api/billing").then(renderBilling);
