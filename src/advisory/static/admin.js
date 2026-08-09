(() => {
  let token = "";
  const body = document.body;
  const gate = document.querySelector("[data-admin-auth]");
  const list = document.querySelector("[data-access-list]");
  async function api(url, options = {}) {
    options.headers = { ...(options.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) { const detail = payload.detail; throw new Error((typeof detail === "object" ? detail.message : detail) || "Request failed"); }
    return payload;
  }
  function render(records) {
    list.replaceChildren(); document.querySelector("[data-admin-empty]").hidden = records.length > 0;
    records.forEach((record) => {
      const row = document.querySelector("#access-row").content.firstElementChild.cloneNode(true);
      row.querySelector("[data-email]").textContent = record.email;
      row.querySelector("[data-subject]").textContent = record.subject ? "Google identity linked" : "Pre-approved email";
      row.querySelector("[data-status]").textContent = record.status;
      row.querySelector("[data-approve]").hidden = record.status === "approved";
      row.querySelector("[data-reject]").hidden = record.status === "rejected";
      row.querySelector("[data-approve]").onclick = () => decide(record.id, "approved");
      row.querySelector("[data-reject]").onclick = () => decide(record.id, "rejected");
      list.append(row);
    });
  }
  async function load() { render(await api("/api/admin/access")); }
  async function decide(id, status) { await api(`/api/admin/access/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }); await load(); }
  async function bootstrap() { const session = await api("/api/session"); if (session.role !== "admin") throw new Error("Administrator access is required"); gate.hidden = true; await load(); }
  document.querySelector("[data-invite-form]").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; const error = document.querySelector("[data-invite-error]"); error.textContent = ""; try { await api("/api/admin/access", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(form))) }); form.reset(); await load(); } catch (exc) { error.textContent = exc.message; } });
  document.querySelector("[data-refresh]").onclick = () => load();
  if (body.dataset.authMode !== "google") bootstrap().catch((error) => { document.querySelector("[data-invite-error]").textContent = error.message; });
  else window.addEventListener("load", () => { const error = gate.querySelector("[data-auth-error]"); api("/api/session").then((session) => { if (session.role !== "admin") throw new Error("Administrator access is required"); gate.hidden = true; return load(); }).catch(() => { if (!body.dataset.clientId || !window.google?.accounts?.id) { error.textContent = "Google sign-in could not be loaded."; return; } google.accounts.id.initialize({ client_id: body.dataset.clientId, callback: async (response) => { token = response.credential; try { await api("/api/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ credential: response.credential }) }); await bootstrap(); } catch (exc) { error.textContent = exc.message; } } }); google.accounts.id.renderButton(gate.querySelector("[data-google-signin]"), { theme: "outline", size: "large" }); }); });
})();
