// Home page: cycle the phone preview through a sample script in each caption style.
const LINES = [
  ["Your dashboard is green.", "classic"],
  ["But users are complaining.", "captions"],
  ["The disk was filling up.", "light"],
  ["Nobody's alert moved.", "bold"],
  ["Check yours today.", "classic"],
];

document.getElementById("year").textContent = new Date().getFullYear();

const caption = document.getElementById("caption");
const text = document.getElementById("captionText");
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
let i = 0;

function show([line, look]) {
  caption.className = `caption ${look}`;
  text.textContent = line;
}

show(LINES[0]);
if (!still) {
  setInterval(() => {
    caption.classList.add("out");
    setTimeout(() => { i = (i + 1) % LINES.length; show(LINES[i]); }, 350);
  }, 2200);
}

// ---------- pricing (prices come from the server, so admin changes show here) ----------
const PERKS = {
  free: (p) => [`${p.videos} videos a month`, "Small “Made with Script Studio” label", "All voices, backgrounds and styles"],
  creator: (p) => [`${p.videos} videos a month`, "No watermark", "One-click YouTube upload", "Video library and stats"],
  pro: (p) => [`${p.videos} videos a month`, "No watermark", "Everything in Creator", "Room to post several a day"],
};
let period = "monthly", plans = [];

const money = (n) => `$${Number.isInteger(n) ? n : n.toFixed(2)}`;

function renderPlans() {
  document.getElementById("plans").innerHTML = plans.map((p) => {
    const price = period === "yearly" ? p.yearly : p.monthly;
    const featured = p.key === "creator";
    const perks = (PERKS[p.key] || PERKS.creator)(p).map((t) => `<li>${t}</li>`).join("");
    const per = p.monthly === 0 ? "forever" : period === "yearly" ? "per year" : "per month";
    const sub = p.monthly && period === "yearly" ? `<span class="per-month">${money(p.yearly / 12)} a month, billed yearly</span>` : "";
    return `
      <article class="plan${featured ? " featured" : ""}">
        ${featured ? `<span class="tag">Most popular</span>` : ""}
        <h3>${p.name}</h3>
        <p class="price"><strong>${money(price)}</strong> <span>${per}</span></p>
        ${sub}
        <ul>${perks}</ul>
        <a class="btn ${featured ? "primary" : "ghost"}" href="/login?mode=signup">${p.monthly ? `Get ${p.name}` : "Start free"}</a>
      </article>`;
  }).join("");
}

document.querySelectorAll("[data-period]").forEach((b) => (b.onclick = () => {
  period = b.dataset.period;
  document.querySelectorAll("[data-period]").forEach((x) => {
    x.classList.toggle("on", x === b);
    x.setAttribute("aria-checked", String(x === b));
  });
  renderPlans();
}));

fetch("/api/plans").then((r) => r.json()).then((d) => { plans = d.plans; renderPlans(); })
  .catch(() => { document.getElementById("pricing").hidden = true; });
