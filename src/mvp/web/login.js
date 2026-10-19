"use strict";
document.getElementById("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const button = document.getElementById("login-submit");
  const error = document.getElementById("login-error");
  button.disabled = true;
  error.hidden = true;
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({username: document.getElementById("username").value,
                            password: document.getElementById("password").value})
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(typeof data.detail === "string" ? data.detail : "登录失败，请稍后重试");
    }
    // Each browser session belongs to the newly authenticated user.
    sessionStorage.removeItem("studio-active-job");
    location.replace("/");
  } catch (exc) {
    error.textContent = exc.message || "暂时无法连接服务";
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
});
