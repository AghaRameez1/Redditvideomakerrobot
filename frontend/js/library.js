// My videos: play, download, delete, and share to YouTube.
const PLATFORM = { youtube: "YouTube" };
let connections = {};
let videos = [];
let rendering = [];  // videos still being made (from /api/jobs)
let sharing = null; // {video, platform} while the share dialog is open
const polling = new Set();

const fmtDuration = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
const fmtDate = (iso) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

function shareBadge(s) {
  const name = PLATFORM[s.platform];
  if (s.status === "done" && s.scheduled_for && new Date(s.scheduled_for) > new Date()) {
    const when = new Date(s.scheduled_for).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
    return `<a class="chip scheduled" href="${esc(s.url)}" target="_blank" rel="noopener" title="Uploaded; YouTube publishes it then">${name} · goes live ${when}</a>`;
  }
  if (s.status === "done") return `<a class="chip done" href="${esc(s.url)}" target="_blank" rel="noopener">${name} ✓ View</a>`;
  if (s.status === "error") return `<span class="chip error" title="${esc(s.error || "")}">${name} failed</span>`;
  return `<span class="chip busy">${name} ${s.status === "processing" ? "processing" : "uploading"} ${s.percent}%</span>`;
}

function shareButton(v, platform) {
  const c = connections[platform];
  if (!c?.available) return "";  // not set up on this server: don't offer it
  if (!c.connected || c.expired) {
    return `<a class="ghost small btnlink" href="/settings#connections">Connect ${PLATFORM[platform]}</a>`;
  }
  return `<button type="button" class="ghost small" data-share="${platform}" data-id="${v.id}">Share to ${PLATFORM[platform]}</button>`;
}

// The newest successful post per platform: {youtube: share}.
const postedLinks = (v) => Object.fromEntries([...v.shares].reverse().filter((s) => s.status === "done").map((s) => [s.platform, s]));

// Badges: every live post, plus the newest attempt per platform if it's still running or failed after that.
function badges(v) {
  const posted = postedLinks(v);
  const latest = Object.values(Object.fromEntries([...v.shares].reverse().map((s) => [s.platform, s])));
  return [...Object.values(posted), ...latest.filter((s) => s.status !== "done")].map(shareBadge).join("");
}

function render() {
  $("empty").hidden = videos.length > 0 || rendering.length > 0;
  $("grid").innerHTML = rendering.map(renderingCard).join("") + videos.map((v) => {
    const posted = Object.values(postedLinks(v));
    const postLink = !v.has_file && posted[0];  // file gone: the thumbnail opens the post instead
    return `
    <article class="vcard">
      ${v.has_file ? `<button type="button" class="thumb" data-play="${v.id}" aria-label="Play ${esc(v.title)}">`
        : postLink ? `<a class="thumb" href="${esc(postLink.url)}" target="_blank" rel="noopener" aria-label="Watch on ${PLATFORM[postLink.platform]}">`
        : `<div class="thumb gone">`}
        ${v.has_thumb ? `<img src="/api/library/${v.id}/thumb" alt="" loading="lazy">` : ""}
        <span class="dur">${fmtDuration(v.duration)}</span>
      ${v.has_file ? "</button>" : postLink ? "</a>" : "</div>"}
      <div class="vbody">
        <h3 title="${esc(v.title)}">${esc(v.title)}</h3>
        <p class="meta">${fmtDate(v.created_at)}${v.has_file ? "" : " · file removed from this computer"}</p>
        <div class="chips">${badges(v)}</div>
        <div class="vactions">
          ${v.has_file ? `${shareButton(v, "youtube")}
          <a class="ghost small btnlink" href="/api/library/${v.id}/file?download=1">Download</a>` : ""}
          <button type="button" class="danger small del" data-del="${v.id}" aria-label="Delete ${esc(v.title)}">Delete</button>
        </div>
      </div>
    </article>`;
  }).join("");

  document.querySelectorAll("[data-play]").forEach((b) => (b.onclick = () => play(b.dataset.play)));
  document.querySelectorAll("[data-share]").forEach((b) => (b.onclick = () => openShare(Number(b.dataset.id), b.dataset.share)));
  document.querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => remove(Number(b.dataset.del))));
  // Keep watching anything still uploading, including after a page reload.
  videos.flatMap((v) => v.shares).filter((s) => s.status === "uploading" || s.status === "processing")
    .forEach((s) => watch(s.id));
}

async function load() {
  const [list, stats, jobs] = await Promise.all([api("/api/library"), api("/api/library/stats"), api("/api/jobs")]);
  videos = list;
  rendering = jobs;
  if (rendering.length) watchRenders();
  render();
  renderStats(stats);
}

function renderStats(s) {
  $("stats").hidden = s.videos === 0;
  $("stats").innerHTML = statTiles([
    ["Videos", s.videos, s.this_week ? `${s.this_week} this week` : ""],
    ["Total length", fmtMinutes(s.seconds)],
    ["Posted to YouTube", s.posted, s.videos ? `${Math.round((100 * s.posted) / s.videos)}% of your videos` : ""],
    ["Space used", fmtBytes(s.disk_bytes)],
  ]);
  const h = s.auto_clean_hours;
  $("cleanNote").hidden = h === null;
  if (h !== null) {
    const when = h === 0 ? "once they're posted" : `${h === 24 ? "1 day" : `${h / 24} days`} after they're posted`;
    $("cleanNote").textContent = `To save space, video files are removed from this computer ${when}. The YouTube link stays here, so download anything you want to keep.`;
  }
}

function play(id) {
  $("playerVideo").src = `/api/library/${id}/file`;
  $("player").showModal();
  $("playerVideo").play().catch(() => {});
}

// ---------- delete ----------
let deleting = null;

function remove(id) {
  const v = deleting = videos.find((x) => x.id === id);
  const posted = Object.keys(postedLinks(v)).map((p) => PLATFORM[p]);
  const canKeepLinks = v.has_file && posted.length > 0;
  $("delTitle").textContent = `Delete "${v.title}"?`;
  $("delText").textContent = canKeepLinks
    ? `It's posted on ${posted.join(" and ")}. You can keep it in My videos with its link and only remove the file from this computer, or delete it completely. Either way the post stays on ${posted.join(" and ")}.`
    : `This removes it from My videos for good.${posted.length ? ` The post on ${posted.join(" and ")} stays there.` : " It isn't posted anywhere, so this is the only copy."}`;
  $("delKeep").hidden = !canKeepLinks;
  $("delAll").textContent = canKeepLinks ? "Delete completely" : "Delete";
  $("delError").hidden = true;
  $("delDlg").showModal();
}

async function runDelete(path, button) {
  button.disabled = true;
  try {
    await api(`/api/library/${deleting.id}/${path}`, { method: "POST" });
    $("delDlg").close();
    load();
  } catch (err) {
    $("delError").hidden = false;
    $("delError").textContent = err.message;
  }
  button.disabled = false;
}
$("delKeep").onclick = () => runDelete("remove-file", $("delKeep"));
$("delAll").onclick = () => runDelete("delete", $("delAll"));

// ---------- sharing ----------
function openShare(id, platform) {
  const v = videos.find((x) => x.id === id);
  sharing = { video: v, platform };
  $("shareTitle").textContent = `Share to ${PLATFORM[platform]}`;
  $("shareError").hidden = true;
  $("shareGo").disabled = false;
  document.querySelector("input[name=when][value=now]").checked = true;
  setWhen();
  $("ytTitle").value = v.title;
  $("ytDesc").value = v.default_text + "\n\n#Shorts";
  updateCounts();
  $("shareDlg").showModal();
}

function updateCounts() {
  $("ytTitleCount").textContent = `${$("ytTitle").value.length}/100`;
}
$("ytTitle").addEventListener("input", updateCounts);

$("shareForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const { video, platform } = sharing;
  const body = { title: $("ytTitle").value, description: $("ytDesc").value, privacy: $("ytPrivacy").value };
  if (scheduling()) {
    if (!$("ytWhen").value) { $("shareError").hidden = false; $("shareError").textContent = "Pick a date and time."; return; }
    body.publish_at = new Date($("ytWhen").value).toISOString();  // the browser's local time, sent as UTC
  }
  $("shareGo").disabled = true;
  try {
    const { share_id } = await api(`/api/library/${video.id}/share/${platform}`, { method: "POST", body });
    $("shareDlg").close();
    await load();
    watch(share_id);
  } catch (err) {
    $("shareError").hidden = false;
    $("shareError").textContent = err.message;
    $("shareGo").disabled = false;
  }
});

async function watch(shareId) {
  if (polling.has(shareId)) return;
  polling.add(shareId);
  try {
    for (;;) {
      await new Promise((r) => setTimeout(r, 2000));
      const s = await api(`/api/shares/${shareId}`);
      const video = videos.find((v) => v.shares.some((x) => x.id === shareId));
      const entry = video?.shares.find((x) => x.id === shareId);
      if (entry) Object.assign(entry, s);
      render();
      if (s.status === "done" || s.status === "error") break;
    }
  } finally {
    polling.delete(shareId);
  }
}

// ---------- dialogs ----------
document.querySelectorAll("[data-close]").forEach((b) => (b.onclick = () => b.closest("dialog").close()));
$("player").addEventListener("close", () => { $("playerVideo").pause(); $("playerVideo").removeAttribute("src"); });

(async () => {
  await initTopbar();
  const list = await api("/api/connections");
  connections = Object.fromEntries(list.map((c) => [c.platform, c]));
  const notConnected = list.filter((c) => c.available && (!c.connected || c.expired));
  if (notConnected.length) {
    $("connNote").hidden = false;
    $("connNote").innerHTML = `To share with one click, <a href="/settings#connections">connect ${notConnected.map((c) => c.label).join(" and ")}</a> in Settings.`;
  }
  await load();
})();

// ---------- scheduling ----------
const scheduling = () => document.querySelector("input[name=when]:checked")?.value === "later";
const localInput = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

function setWhen() {
  const later = scheduling();
  $("ytWhen").hidden = $("ytWhenNote").hidden = !later;
  $("ytPrivacyRow").hidden = later;  // a scheduled video goes public at its time
  $("shareGo").textContent = later ? "Schedule" : "Post";
  const soon = new Date(Date.now() + 20 * 60000), max = new Date(Date.now() + 180 * 86400000);
  $("ytWhen").min = localInput(soon);
  $("ytWhen").max = localInput(max);
  if (later && !$("ytWhen").value) {
    const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1); tomorrow.setHours(9, 0, 0, 0);
    $("ytWhen").value = localInput(tomorrow);  // a sensible default: tomorrow 9 am
  }
}
document.querySelectorAll("input[name=when]").forEach((r) => (r.onchange = setWhen));

// ---------- videos still rendering ----------
let watchingRenders = false;

function renderingCard(j) {
  return `
    <article class="vcard rendering">
      <div class="thumb gone"><span class="render-pct">${j.percent}%</span></div>
      <div class="vbody">
        <h3 title="${esc(j.title)}">${esc(j.title)}</h3>
        <p class="meta">${j.status === "queued" ? "Waiting its turn" : esc(j.stage)}…</p>
        <div class="bar"><div class="fill" style="width:${j.percent}%"></div></div>
      </div>
    </article>`;
}

async function watchRenders() {
  if (watchingRenders) return;
  watchingRenders = true;
  try {
    while (rendering.length) {
      await new Promise((r) => setTimeout(r, 2000));
      const before = rendering.length;
      rendering = await api("/api/jobs");
      if (rendering.length < before) await load();  // one finished: show it in the grid
      else render();
    }
  } finally {
    watchingRenders = false;
  }
}
