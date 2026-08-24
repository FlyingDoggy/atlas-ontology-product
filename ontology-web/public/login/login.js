(function () {
  "use strict";
  const form = document.getElementById("login-form");
  const username = document.getElementById("username");
  const password = document.getElementById("password");
  const submit = document.getElementById("submit-button");
  const message = document.getElementById("form-message");
  const toggle = document.getElementById("toggle-password");
  const options = Array.from(document.querySelectorAll("[data-destination]"));
  const allowed = new Set(["/ontology-agent/", "/ontology-studio/"]);

  function safeDestination(value) {
    try {
      const parsed = new URL(value || "/ontology-agent/", window.location.origin);
      return parsed.origin === window.location.origin && allowed.has(parsed.pathname)
        ? parsed.pathname
        : "/ontology-agent/";
    } catch (_) {
      return "/ontology-agent/";
    }
  }

  let destination = safeDestination(new URLSearchParams(window.location.search).get("next"));
  function selectDestination(next) {
    destination = safeDestination(next);
    options.forEach(function (option) {
      const selected = option.dataset.destination === destination;
      option.classList.toggle("is-selected", selected);
      option.setAttribute("aria-pressed", String(selected));
    });
  }
  options.forEach(function (option) {
    option.addEventListener("click", function () { selectDestination(option.dataset.destination); });
  });
  selectDestination(destination);

  toggle.addEventListener("click", function () {
    const showing = password.type === "text";
    password.type = showing ? "password" : "text";
    toggle.textContent = showing ? "Show" : "Hide";
    toggle.setAttribute("aria-label", showing ? "Show password" : "Hide password");
    password.focus();
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    message.textContent = "";
    if (!username.value.trim() || !password.value) {
      message.textContent = "Enter your username and password.";
      (!username.value.trim() ? username : password).focus();
      return;
    }
    submit.disabled = true;
    submit.querySelector("span").textContent = "Signing in…";
    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.value.trim(), password: password.value }),
      });
      if (!response.ok) {
        message.textContent = response.status === 401 ? "Incorrect username or password." : "The sign-in service is temporarily unavailable.";
        password.select();
        return;
      }
      window.location.replace(destination);
    } catch (_) {
      message.textContent = "Unable to reach the sign-in service. Check your connection and try again.";
    } finally {
      submit.disabled = false;
      submit.querySelector("span").textContent = "Sign in";
    }
  });

  fetch("/auth/session", { credentials: "same-origin", cache: "no-store" })
    .then(function (response) { return response.ok ? response.json() : { authenticated: false }; })
    .then(function (payload) { payload.authenticated ? window.location.replace(destination) : username.focus(); })
    .catch(function () { username.focus(); });
})();
