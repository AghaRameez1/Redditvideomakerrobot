// Sign-in / create-account page.
let mode = "signin";

const GOOGLE_ERRORS = {
  google_failed: "Google sign-in didn't complete. Try again.",
  google_unverified: "Your Google account's email isn't verified, so it can't be used here.",
  google_off: "Google sign-in isn't set up on this server.",
};

function setMode(next) {
  mode = next;
  const signup = mode === "signup";
  $("tabSignin").classList.toggle("active", !signup);
  $("tabSignup").classList.toggle("active", signup);
  $("tabSignin").setAttribute("aria-selected", String(!signup));
  $("tabSignup").setAttribute("aria-selected", String(signup));
  $("nameRow").hidden = !signup;
  $("emailLabel").classList.toggle("first", !signup);
  $("pwHint").hidden = !signup;
  $("password").autocomplete = signup ? "new-password" : "current-password";
  $("authSubmit").textContent = signup ? "Create account" : "Sign in";
  showError("");
}

function showError(msg) {
  $("authError").hidden = !msg;
  $("authError").textContent = msg;
}

$("tabSignin").onclick = () => setMode("signin");
$("tabSignup").onclick = () => setMode("signup");

$("authForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("authSubmit");
  btn.disabled = true;
  showError("");
  try {
    const body = { email: $("email").value, password: $("password").value };
    if (mode === "signup") body.name = $("name").value;
    await api(mode === "signup" ? "/api/auth/register" : "/api/auth/login", { method: "POST", body });
    location.href = "/";
  } catch (err) {
    showError(err.message);
    btn.disabled = false;
  }
});

if (new URLSearchParams(location.search).get("mode") === "signup") setMode("signup");  // from the home page

(async () => {
  const { google } = await api("/api/auth/config");
  $("google").hidden = $("or").hidden = !google;
  const code = new URLSearchParams(location.search).get("error");
  if (GOOGLE_ERRORS[code]) showError(GOOGLE_ERRORS[code]);
})();
