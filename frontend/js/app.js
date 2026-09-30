// Script Studio frontend. Talks to the backend JSON API only ($, esc and api() come from common.js).

const PRESETS = {
  classic: {},
  captions: { card: false, outline: true, bold: true, font_size: 78, text_color: "#ffffff",
              blur: 10, dim: 15, position: 62 },
  light: { card_color: "#ffffff", card_opacity: 92, text_color: "#111111", font_size: 58, width: 78 },
  bold: { card: false, outline: true, bold: true, font_size: 92, text_color: "#ffe14d",
          outline_color: "#000000", position: 72, dim: 10 },
};

let DEFAULT_STYLE = {};
let FIELDS = [];

// ---------- setup ----------
async function init() {
  await initTopbar();
  loadUsage();
  const opts = await api("/api/options");
  DEFAULT_STYLE = opts.default_style;
  FIELDS = Object.keys(DEFAULT_STYLE);

  fillSelect("voice", opts.voices.map((v) => [v.key, v.label]));
  fillSelect("background", opts.backgrounds.map((b) => [b.key, b.key + (b.downloaded ? "" : " (downloads first)")]),
             "minecraft", (o, i) => (o.dataset.ready = opts.backgrounds[i].downloaded ? "1" : "0"));
  fillSelect("music", [...opts.music.map((m) => [m.key, m.key + (m.downloaded ? "" : " (downloads first)")]),
                       ["none", "No music"]]);
  fillSelect("tone", opts.tones.map((t) => [t, t[0].toUpperCase() + t.slice(1)]));
  // Only AIs the user has saved a key for; remember their last pick.
  let lastAi = null;
  try { lastAi = localStorage.getItem("studioAi"); } catch (_) {}
  fillSelect("provider", opts.ai_providers.map((p) => [p.key, p.label]), lastAi);
  $("aiBox").hidden = opts.ai_providers.length === 0;  // shown only once the user has saved an AI key
  $("provider").addEventListener("change", () => { try { localStorage.setItem("studioAi", $("provider").value); } catch (_) {} });
  $("generate").addEventListener("click", generateScript);
  $("topic").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); generateScript(); } });

  let saved = null;
  try { saved = JSON.parse(localStorage.getItem("studioStyle") || "null"); } catch (_) {}
  writeStyle({ ...DEFAULT_STYLE, ...(saved || {}) });

  document.querySelectorAll("[data-preset]").forEach((b) => (b.onclick = () => writeStyle({ ...DEFAULT_STYLE, ...PRESETS[b.dataset.preset] })));
  FIELDS.forEach((k) => $(k).addEventListener("input", refresh));
  $("background").addEventListener("change", loadPreviewBackground);
  $("title").addEventListener("input", updateCount);
  $("body").addEventListener("input", updateCount);
  $("form").addEventListener("submit", submit);
  window.addEventListener("resize", refresh);
  document.fonts?.ready.then(refresh);

  loadPreviewBackground();
}

function fillSelect(id, items, selected, each) {
  const el = $(id);
  el.innerHTML = "";
  items.forEach(([value, label], i) => {
    const o = new Option(label, value, false, value === selected);
    each?.(o, i);
    el.add(o);
  });
}

// ---------- style controls ----------
function readStyle() {
  const s = {};
  for (const k of FIELDS) {
    const el = $(k);
    s[k] = el.type === "checkbox" ? el.checked : el.type === "range" ? Number(el.value) : el.value;
  }
  return s;
}

function writeStyle(s) {
  for (const k of FIELDS) {
    const el = $(k);
    if (el.type === "checkbox") el.checked = !!s[k];
    else el.value = s[k];
  }
  refresh();
}

// ---------- live preview (mirrors engine/cards.py and engine/render.py) ----------
function rgba(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function previewText() {
  const first = $("body").value.trim().split(/(?<=[.!?])\s+/)[0];
  return first || $("title").value.trim() || "Your dashboard is green but users are complaining.";
}

function refresh() {
  if (!FIELDS.length) return;
  const s = readStyle();
  document.querySelectorAll("output[data-for]").forEach((o) => (o.textContent = $(o.dataset.for).value + (o.dataset.unit || "")));
  $("outline_color").disabled = !s.outline;
  $("card_color").disabled = $("card_opacity").disabled = !s.card;
  try { localStorage.setItem("studioStyle", JSON.stringify(s)); } catch (_) {}

  const phone = $("phone"), card = $("pcard");
  const k = phone.clientWidth / 1080; // video pixels -> preview pixels
  const pad = (s.card ? s.font_size * 0.7 : s.font_size * 0.2) * k;
  $("pbg").style.filter = `blur(${s.blur * k}px)`;
  $("pdim").style.opacity = s.dim / 100; // same as the render: brightness x (1 - dim)

  Object.assign(card.style, {
    fontSize: s.font_size * k + "px", fontWeight: s.bold ? 700 : 500, color: s.text_color,
    maxWidth: s.width + "%", width: "max-content", padding: pad + "px",
    background: s.card ? rgba(s.card_color, s.card_opacity / 100) : "transparent",
    borderRadius: s.font_size * 0.45 * k + "px",
  });
  const st = s.outline ? Math.max(2, s.font_size / 14) * k : 0;
  card.style.textShadow = st
    ? [...Array(16)].map((_, i) => {
        const a = (i * Math.PI) / 8;
        return `${(Math.cos(a) * st).toFixed(2)}px ${(Math.sin(a) * st).toFixed(2)}px 0 ${s.outline_color}`;
      }).join(",")
    : "none";
  card.textContent = previewText();

  // Centre at `position`%, but never off-screen.
  const H = phone.clientHeight, h = card.offsetHeight;
  card.style.top = Math.max(0, Math.min(H - h, (H * s.position) / 100 - h / 2)) + "px";
}

function loadPreviewBackground() {
  const opt = $("background").selectedOptions[0];
  const img = $("pbg");
  if (opt?.dataset.ready === "1") {
    img.onload = () => { img.hidden = false; $("pnote").textContent = "Close to the final look. The video uses a moving background."; refresh(); };
    img.onerror = () => { img.hidden = true; refresh(); };
    img.src = `/api/preview/${encodeURIComponent(opt.value)}`;
  } else {
    img.hidden = true;
    $("pnote").textContent = "This background isn't downloaded yet, so the preview uses a placeholder.";
    refresh();
  }
}

function updateCount() {
  const words = ($("title").value + " " + $("body").value).trim().split(/\s+/).filter(Boolean).length;
  $("count").textContent = `${words} words · about ${Math.round(words / 2.5)} seconds`; // ~150 wpm
  refresh();
}

// ---------- AI script writer ----------
function aiStatus(msg, isError = false) {
  const el = $("aiStatus");
  el.hidden = !msg;
  el.textContent = msg || "";
  el.classList.toggle("err", isError);
}

async function generateScript() {
  const topic = $("topic").value.trim();
  if (!topic) return aiStatus("Describe what the video should be about first.", true);
  if (($("title").value.trim() || $("body").value.trim()) &&
      !confirm("Replace the current title and script with a new AI draft?")) return;

  const btn = $("generate");
  btn.disabled = true;
  btn.textContent = "Writing…";
  aiStatus("Writing your script. This usually takes 10–30 seconds.");
  try {
    const data = await api("/api/script", {
      method: "POST",
      body: { topic, provider: $("provider").value, tone: $("tone").value, seconds: Number($("seconds").value) },
    });
    $("title").value = data.title;
    $("body").value = data.body;
    updateCount();
    aiStatus("Draft ready. Edit anything you like, then create the video.");
  } catch (err) {
    aiStatus(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate script";
  }
}

// ---------- rendering ----------
async function submit(e) {
  e.preventDefault();
  $("go").disabled = true;
  $("progressCard").hidden = false;
  $("result").innerHTML = "";
  setProgress(0, "Starting");

  try {
    const data = await api("/api/jobs", {
      method: "POST",
      body: {
        title: $("title").value, body: $("body").value, voice: $("voice").value,
        background: $("background").value, music: $("music").value, style: readStyle(),
      },
    });
    poll(data.id);
  } catch (err) {
    showError(err.message);
  }
}

function setProgress(pct, stage) {
  $("fill").style.width = pct + "%";
  $("pct").textContent = pct + "%";
  $("stage").textContent = stage;
}

function showError(msg) {
  const upgrade = /Upgrade in Settings/.test(msg) ? ` <a href="/settings#billing">See plans</a>` : "";
  $("result").innerHTML = `<p class="err">${esc(msg)}${upgrade}</p>`;
  $("go").disabled = false;
  loadUsage();
}

async function poll(id) {
  let job;
  try {
    job = await api(`/api/jobs/${id}`);
  } catch (err) {
    return showError(err.message);
  }
  setProgress(job.percent, job.stage);

  if (job.status === "done") {
    const url = `/api/library/${job.video_id}/file`;
    $("result").innerHTML = `
      <video src="${url}" controls playsinline></video>
      <div class="actions">
        <a class="primary" href="/videos">Open in My videos</a>
        <a class="ghost btnlink" href="${url}?download=1">Download</a>
      </div>
      <p class="meta">Saved to My videos. Share it to YouTube from there.</p>`;
    $("go").disabled = false;
    loadPreviewBackground(); // a first-time download is now available for the preview
    loadUsage();
  } else if (job.status === "error") {
    showError(`Failed: ${job.error || "unknown error"}`);
  } else {
    setTimeout(() => poll(id), 1000);
  }
}


// How many videos the plan has left this month, under the Create button.
async function loadUsage() {
  try {
    const { usage: u, plan } = await api("/api/billing");
    if (u.limit === null) return;
    $("usageLine").hidden = false;
    $("usageLine").innerHTML = u.left === 0
      ? `You've used all ${u.limit} videos on the ${esc(plan.name)} plan this month. <a href="/settings#billing">Upgrade</a>`
      : `${u.left} of ${u.limit} videos left this month on ${esc(plan.name)}.${plan.key === "free" ? ` <a href="/settings#billing">Upgrade</a>` : ""}`;
  } catch (_) { /* the page still works without it */ }
}
init();
