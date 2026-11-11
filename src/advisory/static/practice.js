(() => {
  const state = { applications: [] };
  let authToken = "";
  const $ = (selector, root = document) => root.querySelector(selector);
  const json = (data) => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

  async function api(url, options = {}) {
    options.headers = { ...(options.headers || {}), ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) };
    const response = await fetch(url, options);
    if (response.status === 401 && authToken) throw new Error("Your sign-in expired. Reload the page and sign in again.");
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail;
      throw new Error((Array.isArray(detail) ? detail.map((item) => item.msg).join(" ") : typeof detail === "object" && detail ? detail.message : detail) || "Something went wrong. Try again.");
    }
    return payload;
  }

  const deck = window.PracticeDeck.mount($("[data-practice-deck]"), { api });

  $("[data-practice-application]").addEventListener("change", (event) => {
    const id = event.target.value;
    history.replaceState(null, "", id ? `/practice?application=${encodeURIComponent(id)}` : "/practice");
    deck.load(id).catch((error) => deck.setError(error.message));
  });

  async function load() {
    state.applications = await api("/api/applications");
    const select = $("[data-practice-application]");
    select.replaceChildren(new Option(state.applications.length ? "Choose an application" : "No applications yet", ""));
    state.applications.forEach((item) => select.add(new Option(`${item.role} — ${item.company}`, item.id)));
    const requested = new URLSearchParams(location.search).get("application");
    const id = state.applications.some((item) => item.id === requested) ? requested : state.applications.length === 1 ? state.applications[0].id : "";
    select.value = id;
    $("[data-loading-workspace]").hidden = true;
    await deck.load(id);
  }
  async function enter(session) {
    if (session.access !== "approved") throw new Error("Workspace access is not approved");
    if (session.role === "admin") $("[data-admin-link]").hidden = false;
    const gate = $("[data-auth-gate]"); if (gate) gate.hidden = true;
    await load();
  }
  const gate = $("[data-auth-gate]");
  const failLoad = (error) => { $("[data-loading-workspace]").textContent = error.message; };
  if (!gate) api("/api/session").then(enter).catch(failLoad);
  else window.addEventListener("load", () => {
    const errorNode = $("[data-auth-error]", gate);
    api("/api/session").then(enter).catch(() => {
      if (!window.google?.accounts?.id) { errorNode.textContent = "Google sign-in could not be loaded."; return; }
      google.accounts.id.initialize({ client_id: gate.dataset.clientId, callback: async (response) => {
        authToken = response.credential;
        try {
          const session = await api("/api/session/login", { method: "POST", ...json({ credential: response.credential }) });
          if (session.access === "approved") { await enter(session); return; }
          const access = $("[data-access-state]", gate); access.hidden = false;
          $("[data-access-title]", access).textContent = session.access === "rejected" ? "Access was not approved" : "Approval is required";
          $("[data-access-copy]", access).textContent = "Request access from the workspace administrator.";
          $("[data-request-access]", access).onclick = async () => { await api("/api/access-request", { method: "POST" }); $("[data-request-access]", access).textContent = "Request sent"; };
        } catch (error) { errorNode.textContent = error.message; }
      } });
      google.accounts.id.renderButton($("[data-google-signin]", gate), { theme: "outline", size: "large" });
    });
  });
})();
