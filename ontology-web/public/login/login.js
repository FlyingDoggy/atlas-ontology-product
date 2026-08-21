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
    toggle.textContent = showing ? "显示" : "隐藏";
    password.focus();
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    message.textContent = "";
    if (!username.value.trim() || !password.value) {
      message.textContent = "请输入用户名和密码。";
      (!username.value.trim() ? username : password).focus();
      return;
    }
    submit.disabled = true;
    submit.querySelector("span").textContent = "正在登录…";
    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.value.trim(), password: password.value }),
      });
      if (!response.ok) {
        message.textContent = response.status === 401 ? "用户名或密码不正确。" : "登录服务暂不可用。";
        password.select();
        return;
      }
      window.location.replace(destination);
    } catch (_) {
      message.textContent = "无法连接登录网关，请检查网络后重试。";
    } finally {
      submit.disabled = false;
      submit.querySelector("span").textContent = "继续";
    }
  });

  fetch("/auth/session", { credentials: "same-origin", cache: "no-store" })
    .then(function (response) { return response.ok ? response.json() : { authenticated: false }; })
    .then(function (payload) { payload.authenticated ? window.location.replace(destination) : username.focus(); })
    .catch(function () { username.focus(); });
})();
