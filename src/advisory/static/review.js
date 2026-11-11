(() => {
  const advisors = Object.fromEntries(JSON.parse(document.getElementById("advisors-data").textContent).map((item) => [item.id, item]));
  const state = { cvs: [], applications: [], cvId: "", mode: "new" };
  let authToken = "";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };

  async function api(url, options = {}) {
    options.headers = { ...(options.headers || {}), ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) };
    const response = await fetch(url, options);
    if (response.status === 401 && authToken) throw new Error("Your sign-in expired. Reload the page and sign in again.");
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail;
      const message = Array.isArray(detail) ? detail.map((item) => item.msg).join(" ") : typeof detail === "object" && detail ? detail.message : detail;
      throw new Error(message || "Something went wrong. Try again.");
    }
    return payload;
  }
  const jsonBody = (data) => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  const setError = (step, message) => { const node = $(`[data-step-error="${step}"]`); if (node) node.textContent = message || ""; };
  const hostOf = (url) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch (_) { return url; } };
  const hasSavedJob = (app) => Boolean(app && (app.job_url || app.job_description_filename));

  // ---------- Steps ----------
  function showStep(step) {
    $$("[data-step]").forEach((panel) => panel.classList.toggle("visible", Number(panel.dataset.step) === step));
    $("[data-review-progress]").hidden = true;
    $$("[data-step-indicator]").forEach((indicator) => {
      const value = Number(indicator.dataset.stepIndicator);
      indicator.classList.toggle("active", value === step);
      indicator.classList.toggle("complete", value < step);
      if (value === step) indicator.setAttribute("aria-current", "step"); else indicator.removeAttribute("aria-current");
    });
    if (step === 3) renderSummary();
    $(`[data-step="${step}"] h2`)?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  async function withBusy(button, label, work) {
    const original = button.innerHTML; button.disabled = true; button.textContent = label;
    try { return await work(); } finally { button.disabled = false; button.innerHTML = original; }
  }
  $$("[data-back]").forEach((button) => button.addEventListener("click", () => showStep(Number(button.dataset.back))));

  // ---------- Step 1: Job ----------
  const selectedApplication = () => (state.mode === "existing" ? state.applications.find((app) => app.id === $("[data-application-select]").value) : null);
  let activeSource = "link";
  let previewToken = 0;
  const previewStatus = (text, tone = "") => { const node = $("[data-preview-status]"); node.textContent = text; node.dataset.tone = tone; };

  function setSource(source) {
    activeSource = source;
    $$("[data-source-tab]").forEach((tab) => { const on = tab.dataset.sourceTab === source; tab.classList.toggle("active", on); tab.setAttribute("aria-selected", String(on)); });
    $$("[data-source-panel]").forEach((panel) => { panel.hidden = panel.dataset.sourcePanel !== source; });
    previewStatus("");
  }
  $$("[data-source-tab]").forEach((tab) => tab.addEventListener("click", () => setSource(tab.dataset.sourceTab)));
  setSource("link");

  function setMode(mode) {
    state.mode = mode === "existing" && state.applications.length ? "existing" : "new";
    $$("[data-job-mode]").forEach((input) => { input.checked = input.value === state.mode; input.closest("label").classList.toggle("selected", input.checked); });
    $("[data-existing-picker]").hidden = state.mode !== "existing";
    $("[data-new-fields]").hidden = state.mode === "existing";
    updateTarget();
  }
  $$("[data-job-mode]").forEach((input) => input.addEventListener("change", () => { setMode(input.value); setError(1, ""); }));

  function renderApplications(selectedId = "") {
    const select = $("[data-application-select]");
    select.replaceChildren(...state.applications.map((item) => new Option(`${item.role} — ${item.company}`, item.id)));
    if (state.applications.some((item) => item.id === selectedId)) select.value = selectedId;
    const existing = $('[data-job-mode][value="existing"]');
    existing.disabled = state.applications.length === 0;
    $("[data-existing-count]").textContent = state.applications.length
      ? `${state.applications.length} in your pipeline`
      : "None yet";
  }
  function updateTarget() {
    const item = selectedApplication();
    const parts = [];
    if (item?.job_description_filename) parts.push(`File: ${item.job_description_filename}`);
    if (item?.job_url) parts.push(`Link: ${hostOf(item.job_url)}`);
    $('[data-source-tab="saved"]').hidden = parts.length === 0;
    $("[data-job-saved]").textContent = parts.length ? `${parts.join(" · ")}. Nothing else needed — or pick another source to replace it.` : "";
    $("[data-source-hint]").textContent = item && !parts.length ? "This application has no posting yet — add one" : "One is enough";
    if (parts.length) setSource("saved"); else if (activeSource === "saved") setSource("link");
  }
  $("[data-application-select]").addEventListener("change", () => {
    updateTarget();
    const item = selectedApplication(); if (item?.cv_version_id) state.cvId = item.cv_version_id;
  });

  function fillIdentity(result) {
    [["[data-new-company]", result.company], ["[data-new-role]", result.role]].forEach(([selector, value]) => {
      const input = $(selector);
      if (value && (!input.value.trim() || input.dataset.autofilled === "true")) { input.value = value; input.dataset.autofilled = "true"; }
    });
  }
  $$("[data-new-company], [data-new-role]").forEach((input) => input.addEventListener("input", () => { input.dataset.autofilled = "false"; }));

  function jobInput() {
    return {
      url: activeSource === "link" ? $("[data-job-url]").value.trim() : "",
      file: activeSource === "file" ? $("[data-job-file]").files?.[0] || null : null,
      text: activeSource === "text" ? $("[data-job-text]").value.trim() : "",
    };
  }
  async function previewJob() {
    if (state.mode !== "new") return null;
    const body = new FormData(); const job = jobInput();
    if (job.url) { try { if (new URL(job.url).protocol !== "https:") return null; } catch (_) { return null; } body.append("job_url", job.url); }
    else if (job.file) body.append("job_file", job.file);
    else if (job.text.length >= 40) body.append("job_text", job.text);
    else return null;
    const token = ++previewToken;
    previewStatus("Reading the posting…");
    try {
      const result = await api("/api/job-preview", { method: "POST", body });
      if (token !== previewToken) return null;
      fillIdentity(result);
      const found = [result.role, result.company].filter(Boolean).join(" at ");
      previewStatus(found ? `Posting read: ${found}.` : "Posting read.", "ok");
      return result;
    } catch (error) {
      if (token !== previewToken) return null;
      previewStatus(error.message, "error");
      return null;
    }
  }
  let previewTimer = 0;
  $("[data-job-url]").addEventListener("input", () => { clearTimeout(previewTimer); previewTimer = window.setTimeout(previewJob, 700); });
  $("[data-job-file]").addEventListener("change", previewJob);
  $("[data-job-text]").addEventListener("blur", previewJob);

  $('[data-next="1"]').addEventListener("click", async (event) => {
    setError(1, "");
    const job = jobInput(); const item = selectedApplication();
    if (state.mode === "existing" && !item) { setError(1, "Pick the application, or choose “A new posting”."); return; }
    if (job.url) { try { if (new URL(job.url).protocol !== "https:") throw new Error(); } catch (_) { setError(1, "Enter a complete HTTPS job link, such as https://company.com/jobs/role."); return; } }
    if (activeSource !== "saved" && !(job.url || job.file || job.text)) {
      setError(1, activeSource === "link" ? "Add the job link, or choose PDF or Paste text." : activeSource === "file" ? "Choose the posting file." : "Paste the job description.");
      return;
    }
    if (state.mode === "new" && !($("[data-new-company]").value.trim() && $("[data-new-role]").value.trim())) {
      await withBusy(event.currentTarget, "Reading the posting…", previewJob);
    }
    if (item?.cv_version_id) state.cvId = item.cv_version_id;
    renderCvOptions();
    showStep(2);
  });

  // ---------- Step 2: CV ----------
  function renderCvOptions() {
    const list = $("[data-cv-options]"); list.replaceChildren();
    $("[data-cv-empty]").hidden = state.cvs.length > 0;
    if (!state.cvs.length) $("[data-cv-upload-panel]").open = true;
    state.cvs.forEach((version) => {
      const label = el("label", "choice-card");
      const input = el("input"); input.type = "radio"; input.name = "cv_choice"; input.value = version.id; input.checked = version.id === state.cvId;
      input.addEventListener("change", () => { state.cvId = version.id; renderCvOptions(); });
      const copy = el("span", "choice-copy");
      copy.append(el("strong", "", version.label), el("small", "", `${version.filename} · ${new Date(version.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}${version.parent_version_id ? " · revised" : ""}`));
      label.classList.toggle("selected", input.checked);
      label.append(input, el("span", "choice-mark", "CV"), copy);
      list.append(label);
    });
  }
  $('[data-next="2"]').addEventListener("click", async (event) => {
    setError(2, "");
    const file = $("[data-cv-file]").files?.[0];
    try {
      if (file) {
        await withBusy(event.currentTarget, "Uploading CV…", async () => {
          const body = new FormData();
          body.append("label", $("[data-cv-label]").value.trim() || file.name.replace(/\.[^.]+$/, ""));
          body.append("cv_file", file);
          const version = await api("/api/cv-versions", { method: "POST", body });
          state.cvs.unshift(version); state.cvId = version.id;
          $("[data-cv-file]").value = ""; $("[data-cv-label]").value = ""; $("[data-cv-upload-panel]").open = false;
          renderCvOptions();
        });
      }
      if (!state.cvId) { setError(2, "Choose a CV from your library or upload one."); return; }
      showStep(3);
    } catch (error) { setError(2, error.message); }
  });

  // ---------- Step 3: Review ----------
  const advisorInputs = $$("[data-advisor-option]");
  const selectedAdvisors = () => advisorInputs.filter((input) => input.checked).map((input) => input.value);
  function renderAdvisors() {
    const selected = selectedAdvisors();
    advisorInputs.forEach((input) => {
      const option = input.closest(".advisor-option"); const blocked = selected.length >= 3 && !input.checked;
      option.classList.toggle("selected", input.checked); option.classList.toggle("disabled", blocked); input.disabled = blocked;
    });
    $("[data-advisor-count]").textContent = String(selected.length);
    $$("[data-advisor-preset]").forEach((button) => {
      const ids = button.dataset.advisorPreset.split(",");
      const active = ids.length === selected.length && ids.every((id) => selected.includes(id));
      button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active));
    });
    $("[data-run-board]").textContent = selected.length ? selected.map((id) => advisors[id]?.name || id).join(" · ") : "No specialists chosen";
    if (selected.length) setError(3, "");
  }
  advisorInputs.forEach((input) => input.addEventListener("change", renderAdvisors));
  $$("[data-advisor-preset]").forEach((button) => button.addEventListener("click", () => {
    const ids = new Set(button.dataset.advisorPreset.split(","));
    advisorInputs.forEach((input) => { input.checked = ids.has(input.value); });
    renderAdvisors();
  }));

  function renderSummary() {
    const item = selectedApplication(); const job = jobInput();
    const company = $("[data-new-company]").value.trim(); const role = $("[data-new-role]").value.trim();
    $("[data-run-job]").textContent = item ? `${item.role} at ${item.company}` : role || company ? [role || "New role", company].filter(Boolean).join(" at ") : "New application";
    let source = "";
    if (job.url) source = `Link · ${hostOf(job.url)}`;
    else if (job.file) source = `File · ${job.file.name}`;
    else if (job.text) source = `Pasted description · ${job.text.split(/\s+/).length} words`;
    else if (item?.job_description_filename) source = `Saved file · ${item.job_description_filename}`;
    else if (item?.job_url) source = `Saved link · ${hostOf(item.job_url)}`;
    $("[data-run-job-source]").textContent = item ? source : `${source} · added to your pipeline`;
    const version = state.cvs.find((cv) => cv.id === state.cvId);
    $("[data-run-cv]").textContent = version?.label || "Choose a CV";
    $("[data-run-cv-meta]").textContent = version ? `${version.filename} · ${new Date(version.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}` : "";
    renderAdvisors();
  }

  // Creates or updates the application, saves the posting, then runs the board.
  async function saveApplication() {
    const job = jobInput(); let application = selectedApplication();
    if (!application) {
      const company = $("[data-new-company]").value.trim(); const role = $("[data-new-role]").value.trim();
      application = await api("/api/applications", { method: "POST", ...jsonBody({
        company: company || "Unknown company",
        role: role || (job.file ? job.file.name.replace(/\.[^.]+$/, "") : "Untitled role"),
        cv_version_id: state.cvId,
        job_url: job.url,
      }) });
      // From here on it is a tracked application, so a retry never creates a duplicate.
      state.applications.unshift(application); renderApplications(application.id); setMode("existing");
      if (job.url) setSource("link"); else if (job.file) setSource("file"); else if (job.text) setSource("text");
    } else {
      application = await api(`/api/applications/${application.id}`, { method: "PATCH", ...jsonBody({ cv_version_id: state.cvId, ...(job.url ? { job_url: job.url } : {}) }) });
    }
    if (job.file) {
      const body = new FormData(); body.append("job_file", job.file);
      application = await api(`/api/applications/${application.id}/job-description`, { method: "POST", body });
    } else if ((job.url || job.text) && application.job_description_filename) {
      application = await api(`/api/applications/${application.id}/job-description`, { method: "DELETE" });
    }
    state.applications = state.applications.map((item) => (item.id === application.id ? application : item));
    return { application, jobText: job.text };
  }

  $("[data-run-review]").addEventListener("click", async () => {
    const ids = selectedAdvisors();
    if (!ids.length) { $("[data-board-details]").open = true; setError(3, "Choose at least one specialist."); return; }
    if (!state.cvId) { showStep(2); setError(2, "Choose a CV first."); return; }
    setError(3, "");
    $('[data-step="3"]').classList.remove("visible");
    $("[data-review-progress]").hidden = false;
    $("[data-progress-title]").textContent = "Saving the application…";
    window.scrollTo({ top: 0, behavior: "smooth" });
    try {
      const { application, jobText } = await saveApplication();
      $("[data-progress-title]").textContent = "Your board is reviewing the evidence…";
      const body = new FormData(); body.append("advisor_ids", ids.join(",")); body.append("job_text", jobText);
      await api(`/api/applications/${application.id}/board-review`, { method: "POST", body });
      location.href = `/applications/${encodeURIComponent(application.id)}?tab=report`;
    } catch (error) {
      showStep(3); setError(3, error.message);
    }
  });

  // ---------- Start ----------
  async function load() {
    const [cvs, applications] = await Promise.all([api("/api/cv-versions"), api("/api/applications")]);
    state.cvs = cvs; state.applications = applications;
    state.cvId = cvs[0]?.id || "";
    renderApplications(); renderAdvisors();
    $("[data-loading-workspace]").hidden = true;
    const requested = applications.find((item) => item.id === new URLSearchParams(location.search).get("application"));
    if (!requested) { setMode("new"); showStep(1); return; }
    // Started from an application: skip whatever is already known.
    renderApplications(requested.id); setMode("existing");
    if (requested.cv_version_id) state.cvId = requested.cv_version_id;
    renderCvOptions();
    if (!hasSavedJob(requested)) showStep(1);
    else if (!requested.cv_version_id) showStep(2);
    else showStep(3);
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
          const session = await api("/api/session/login", { method: "POST", ...jsonBody({ credential: response.credential }) });
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
