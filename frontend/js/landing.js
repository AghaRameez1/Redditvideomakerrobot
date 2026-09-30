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
