(() => {
  const statuses = ["interested", "applied", "interviewing", "offer", "closed"];
  const labels = { interested: "Interested", applied: "Applied", interviewing: "Interviewing", offer: "Offer", closed: "Closed" };
  const state = { applications: [], cvs: [], archives: [], filter: "all" };
  let authToken = "";
  const board = document.querySelector("[data-board]");
  const empty = document.querySelector("[data-empty]");
  const appDialog = document.querySelector("[data-application-dialog]");
  const cvDialog = document.querySelector("[data-cv-dialog]");
  const archiveDialog = document.querySelector("[data-archive-dialog]");
  const historyDialog = document.querySelector("[data-history-dialog]");

  async function api(url, options = {}) {
    options.headers = { ...(options.headers || {}), ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) };
    const response = await fetch(url, options);
    if (response.status === 401 && authToken) {
      authToken = "";
      throw new Error("Your sign-in expired. Reload the page and sign in again.");
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const detail = payload.detail;
      throw new Error((typeof detail === "object" ? detail.message : detail) || "Something went wrong. Try again.");
    }
    return response.status === 204 ? null : response.json();
  }

  function cvLabel(id) {
    return state.cvs.find((item) => item.id === id)?.label || "";
  }

  function renderCard(application) {
    const card = document.querySelector("#application-card-template").content.firstElementChild.cloneNode(true);
    const pageUrl = `/applications/${encodeURIComponent(application.id)}`;
    card.dataset.id = application.id;
    const open = card.querySelector(".card-open");
    open.textContent = application.role; open.href = pageUrl;
    card.querySelector(".company-name").textContent = application.company;
    card.querySelector(".company-mark").textContent = application.company.slice(0, 2).toUpperCase();
    card.querySelector(".card-date").textContent = new Date(application.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    const fit = card.querySelector(".card-fit");
    if (application.has_board_review && application.fit_score !== null && application.fit_score !== undefined) { fit.textContent = `Fit ${application.fit_score}`; fit.hidden = false; }
    card.querySelector(".next-action").textContent = application.next_action ? `Next · ${application.next_action}` : "";
    const due = card.querySelector(".card-due");
    if (application.next_action_due && application.status !== "closed") {
      const dueDate = new Date(`${application.next_action_due}T00:00:00`);
      const today = new Date(); today.setHours(0, 0, 0, 0);
      const overdue = dueDate < today;
      due.textContent = `${overdue ? "Overdue" : "Due"} · ${dueDate.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
      due.classList.toggle("overdue", overdue);
      due.hidden = false;
    }
    const attachment = card.querySelector(".cv-attachment");
    const versionLabel = cvLabel(application.cv_version_id);
    attachment.textContent = versionLabel ? `CV · ${versionLabel}` : "No CV attached";
    attachment.classList.toggle("empty", !versionLabel);
    const step = window.AdvisoryReport.nextStep(application);
    const nextButton = card.querySelector(".card-next-button");
    nextButton.hidden = !step;
    if (step) {
      nextButton.textContent = step.label; nextButton.href = step.href;
      nextButton.setAttribute("aria-label", `${step.label}: ${application.role} at ${application.company}`);
    }
    // The whole card opens the application page; its own controls keep working.
    card.addEventListener("click", (event) => {
      if (event.target.closest("a, button, select, label")) return;
      location.href = pageUrl;
    });
    const select = card.querySelector("select");
    select.setAttribute("aria-label", `Move ${application.role} at ${application.company}`);
    statuses.forEach((status) => select.add(new Option(labels[status], status, false, status === application.status)));
    select.addEventListener("change", () => moveApplication(application.id, select.value));
    card.addEventListener("dragstart", () => { card.classList.add("dragging"); card.dataset.dragging = "true"; });
    card.addEventListener("dragend", () => { card.classList.remove("dragging"); delete card.dataset.dragging; });
    return card;
  }

  function render() {
    board.replaceChildren();
    empty.hidden = state.applications.length > 0;
    board.hidden = state.applications.length === 0;
    statuses.forEach((status) => {
      const column = document.createElement("section");
      column.className = "kanban-column";
      column.dataset.status = status;
      const shown = state.filter === "all" ? status !== "closed" : state.filter === status;
      column.classList.toggle("mobile-visible", shown);
      const applications = state.applications.filter((item) => item.status === status && (state.filter === "all" || item.status === state.filter));
      column.innerHTML = `<header class="column-heading"><h3>${labels[status]}</h3><span>${applications.length}</span></header><div class="column-cards"></div>`;
      applications.forEach((item) => column.querySelector(".column-cards").append(renderCard(item)));
      column.addEventListener("dragover", (event) => { event.preventDefault(); column.classList.add("drag-over"); });
      column.addEventListener("dragleave", () => column.classList.remove("drag-over"));
      column.addEventListener("drop", (event) => {
        event.preventDefault(); column.classList.remove("drag-over");
        const dragging = document.querySelector("[data-dragging]");
        if (dragging) moveApplication(dragging.dataset.id, status);
      });
      board.append(column);
    });
    ["applied", "interviewing", "offer"].forEach((status) => {
      document.querySelector(`[data-count="${status}"]`).textContent = state.applications.filter((item) => item.status === status).length;
    });
    document.querySelector("[data-clear-filter]").hidden = state.filter === "all";
    document.querySelectorAll("[data-filter]").forEach((button) => button.classList.toggle("active", button.dataset.filter === state.filter));
  }

  async function moveApplication(id, status) {
    const original = state.applications.find((item) => item.id === id);
    if (!original || original.status === status) return;
    const previous = original.status; original.status = status; render();
    try { Object.assign(original, await api(`/api/applications/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) })); }
    catch (error) { original.status = previous; render(); window.alert(error.message); }
    render();
  }

  function renderCvLibrary() {
    const container = document.querySelector("[data-cv-library]");
    container.replaceChildren();
    state.cvs.forEach((version) => {
      const row = document.createElement("article");
      row.innerHTML = `<div><strong></strong><br><small></small></div><a class="text-action">Download</a>`;
      row.querySelector("strong").textContent = version.label;
      row.querySelector("small").textContent = `${version.filename} · ${Math.ceil(version.byte_count / 1024)} KB`;
      const download = row.querySelector("a");
      download.href = `/api/cv-versions/${version.id}/download`;
      if (authToken) download.addEventListener("click", async (event) => {
        event.preventDefault();
        const response = await fetch(download.href, { headers: { Authorization: `Bearer ${authToken}` } });
        if (!response.ok) return;
        const objectUrl = URL.createObjectURL(await response.blob());
        const link = document.createElement("a"); link.href = objectUrl; link.download = version.filename; link.click();
        URL.revokeObjectURL(objectUrl);
      });
      container.append(row);
    });
    document.querySelectorAll("[data-cv-select]").forEach((select) => {
      const selected = select.value; select.replaceChildren(new Option("Not attached yet", ""));
      state.cvs.forEach((version) => select.add(new Option(version.label, version.id)));
      select.value = selected;
    });
  }

  function renderHistory() {
    const list = historyDialog.querySelector("[data-history-list]");
    const emptyHistory = historyDialog.querySelector("[data-history-empty]");
    historyDialog.querySelector("[data-history-index]").hidden = false;
    historyDialog.querySelector("[data-history-detail]").hidden = true;
    list.replaceChildren();
    emptyHistory.hidden = state.archives.length > 0;
    state.archives.forEach((archive) => {
      const row = document.createElement("article");
      const created = new Date(archive.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
      row.innerHTML = `<div><strong></strong><span></span><small></small></div><button class="button button-secondary button-small" type="button"></button>`;
      row.querySelector("strong").textContent = archive.label;
      row.querySelector("span").textContent = `${archive.application_count} applications · ${archive.cv_version_count} CV versions`;
      row.querySelector("small").textContent = `Archived ${created}`;
      const view = row.querySelector("button");
      view.textContent = "View";
      view.addEventListener("click", async () => {
        view.disabled = true; view.textContent = "Opening…";
        historyDialog.querySelector("[data-history-error]").textContent = "";
        try { renderHistoryDetail(await api(`/api/workspace-archives/${archive.id}`)); }
        catch (error) { historyDialog.querySelector("[data-history-error]").textContent = error.message; }
        finally { view.disabled = false; view.textContent = "View"; }
      });
      list.append(row);
    });
  }

  function addArchivedDownload(link, version, archiveId) {
    link.href = `/api/workspace-archives/${archiveId}/cv-versions/${version.id}/download`;
    if (!authToken) return;
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      const response = await fetch(link.href, { headers: { Authorization: `Bearer ${authToken}` } });
      if (!response.ok) return;
      const objectUrl = URL.createObjectURL(await response.blob());
      const download = document.createElement("a");
      download.href = objectUrl; download.download = version.filename; download.click();
      URL.revokeObjectURL(objectUrl);
    });
  }

  function renderHistoryDetail(detail) {
    const archive = detail.archive;
    const index = historyDialog.querySelector("[data-history-index]");
    const panel = historyDialog.querySelector("[data-history-detail]");
    const applications = panel.querySelector("[data-history-applications]");
    const cvs = panel.querySelector("[data-history-cvs]");
    const cvNames = new Map(detail.cv_versions.map((version) => [version.id, version.label]));
    index.hidden = true; panel.hidden = false;
    panel.querySelector("[data-history-title]").textContent = archive.label;
    panel.querySelector("[data-history-meta]").textContent = `Archived ${new Date(archive.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}`;
    applications.replaceChildren();
    detail.applications.forEach((application) => {
      const row = document.createElement("article");
      row.innerHTML = `<div><strong></strong><span></span><small></small></div><span class="history-status"></span>`;
      row.querySelector("strong").textContent = application.role;
      row.querySelector("div span").textContent = application.company;
      const attachedCv = cvNames.get(application.cv_version_id);
      row.querySelector("small").textContent = attachedCv ? `CV · ${attachedCv}` : "No CV attached";
      row.querySelector(".history-status").textContent = labels[application.status] || application.status;
      applications.append(row);
    });
    if (!detail.applications.length) applications.textContent = "No applications in this archive.";
    cvs.replaceChildren();
    detail.cv_versions.forEach((version) => {
      const row = document.createElement("article");
      row.innerHTML = `<div><strong></strong><span></span></div><a class="text-action">Download</a>`;
      row.querySelector("strong").textContent = version.label;
      row.querySelector("span").textContent = `${version.filename} · ${Math.ceil(version.byte_count / 1024)} KB`;
      addArchivedDownload(row.querySelector("a"), version, archive.id);
      cvs.append(row);
    });
    if (!detail.cv_versions.length) cvs.textContent = "No CV versions in this archive.";
  }

  async function openHistory(event) {
    event?.preventDefault();
    historyDialog.querySelector("[data-history-error]").textContent = "";
    state.archives = await api("/api/workspace-archives");
    renderHistory();
    historyDialog.showModal();
    history.replaceState(null, "", "#history");
  }

  const applicationFields = ["company", "role", "status", "cv_version_id", "job_url", "applied_date", "next_action_due", "next_action", "notes"];
  function openApplicationDialog(application = null) {
    const form = appDialog.querySelector("[data-application-form]");
    form.reset();
    form.elements.application_id.value = application?.id || "";
    applicationFields.forEach((name) => { if (application) form.elements[name].value = application[name] ?? ""; });
    appDialog.querySelector("[data-application-overline]").textContent = application ? "Edit opportunity" : "New opportunity";
    appDialog.querySelector("[data-application-heading]").textContent = application ? `${application.role} at ${application.company}` : "Add an application";
    appDialog.querySelector("[data-application-submit]").textContent = application ? "Save changes" : "Add application";
    appDialog.querySelector("[data-application-optional]").open = Boolean(application);
    renderJobFile(application);
    document.querySelector("[data-application-error]").textContent = "";
    appDialog.showModal();
  }
  function renderJobFile(application) {
    const current = appDialog.querySelector("[data-job-file-current]");
    current.hidden = !application?.job_description_filename;
    appDialog.querySelector("[data-job-file-name]").textContent = application?.job_description_filename || "";
  }
  function replaceApplication(updated) {
    state.applications = state.applications.map((item) => (item.id === updated.id ? updated : item));
  }
  async function uploadJobFile(id, file) {
    const body = new FormData(); body.append("job_file", file);
    const updated = await api(`/api/applications/${id}/job-description`, { method: "POST", body });
    replaceApplication(updated);
    return updated;
  }
  appDialog.querySelector("[data-remove-job-file]").addEventListener("click", async () => {
    const id = appDialog.querySelector("[data-application-form]").elements.application_id.value;
    const error = document.querySelector("[data-application-error]"); error.textContent = "";
    try {
      const updated = await api(`/api/applications/${id}/job-description`, { method: "DELETE" });
      replaceApplication(updated); renderJobFile(updated); render();
    } catch (exc) { error.textContent = exc.message; }
  });
  function applicationPayload(form) {
    const data = Object.fromEntries(new FormData(form));
    delete data.application_id; delete data.job_file;
    ["applied_date", "next_action_due", "cv_version_id"].forEach((name) => { if (!data[name]) data[name] = null; });
    return data;
  }
  document.querySelectorAll("[data-open-application]").forEach((button) => button.addEventListener("click", () => openApplicationDialog()));
  document.querySelectorAll("[data-open-cv]").forEach((button) => button.addEventListener("click", () => cvDialog.showModal()));
  document.querySelectorAll("[data-open-history]").forEach((button) => button.addEventListener("click", (event) => openHistory(event).catch((error) => window.alert(error.message))));
  historyDialog.querySelector("[data-history-back]").addEventListener("click", renderHistory);
  historyDialog.addEventListener("close", () => {
    if (location.hash === "#history") history.replaceState(null, "", "/dashboard");
  });
  document.querySelectorAll("[data-open-archive]").forEach((button) => button.addEventListener("click", () => {
    const total = state.applications.length + state.cvs.length;
    archiveDialog.querySelector("[data-archive-summary]").textContent = total
      ? `${state.applications.length} applications and ${state.cvs.length} CV versions will be archived.`
      : "This workspace is already empty.";
    archiveDialog.querySelector("button[type=submit]").disabled = total === 0;
    archiveDialog.querySelector("[data-archive-error]").textContent = "";
    archiveDialog.showModal();
  }));
  document.querySelectorAll('.tracker-dialog button[value="cancel"]').forEach((button) => button.addEventListener("click", (event) => {
    event.preventDefault(); button.closest("dialog").close();
  }));
  document.querySelector("[data-application-form]").addEventListener("submit", async (event) => {
    if (event.submitter?.value === "cancel") return;
    event.preventDefault(); const form = event.currentTarget; const id = form.elements.application_id.value; const data = applicationPayload(form);
    const jobFile = form.elements.job_file.files?.[0];
    const submitButton = form.querySelector("[data-application-submit]");
    document.querySelector("[data-application-error]").textContent = "";
    submitButton.disabled = true;
    try {
      let saved;
      if (id) {
        saved = await api(`/api/applications/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
        replaceApplication(saved);
      } else {
        saved = await api("/api/applications", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
        state.applications.unshift(saved);
        form.elements.application_id.value = saved.id;
      }
      if (jobFile) {
        submitButton.textContent = "Reading job description…";
        try { await uploadJobFile(saved.id, jobFile); }
        catch (uploadError) {
          render(); renderJobFile(saved);
          submitButton.textContent = "Save changes";
          form.elements.job_file.value = "";
          throw new Error(`Application saved, but the job file was not: ${uploadError.message}`);
        }
      }
      form.reset(); appDialog.close(); render();
    }
    catch (error) { document.querySelector("[data-application-error]").textContent = error.message; }
    finally { submitButton.disabled = false; if (submitButton.textContent.startsWith("Reading")) submitButton.textContent = "Save changes"; }
  });
  document.querySelector("[data-cv-form]").addEventListener("submit", async (event) => {
    if (event.submitter?.value === "cancel") return;
    event.preventDefault(); const form = event.currentTarget; document.querySelector("[data-cv-error]").textContent = "";
    try { state.cvs.unshift(await api("/api/cv-versions", { method: "POST", body: new FormData(form) })); form.reset(); renderCvLibrary(); render(); }
    catch (error) { document.querySelector("[data-cv-error]").textContent = error.message; }
  });
  archiveDialog.querySelector("[data-archive-form]").addEventListener("submit", async (event) => {
    if (event.submitter?.value === "cancel") return;
    event.preventDefault();
    const form = event.currentTarget;
    const button = event.submitter;
    button.disabled = true; button.textContent = "Archiving…";
    archiveDialog.querySelector("[data-archive-error]").textContent = "";
    try {
      await api("/api/workspace-archives", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: new FormData(form).get("label") }),
      });
      form.reset();
      archiveDialog.close();
      await refreshWorkspace();
      await openHistory();
    } catch (error) {
      archiveDialog.querySelector("[data-archive-error]").textContent = error.message;
    } finally {
      button.disabled = false; button.textContent = "Archive and start fresh";
    }
  });
  document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => { state.filter = button.dataset.filter; document.querySelector("[data-mobile-filter]").value = state.filter; render(); }));
  document.querySelector("[data-clear-filter]").addEventListener("click", () => { state.filter = "all"; render(); });
  document.querySelector("[data-mobile-filter]").addEventListener("change", (event) => { state.filter = event.target.value; render(); });

  async function refreshWorkspace() {
    const [applications, cvs] = await Promise.all([api("/api/applications"), api("/api/cv-versions")]);
    state.applications = applications; state.cvs = cvs;
    renderCvLibrary(); render();
  }

  function start() { refreshWorkspace().then(() => {
    if (location.hash === "#history") openHistory().catch((error) => { empty.querySelector("p").textContent = error.message; });
  }).catch((error) => { empty.querySelector("p").textContent = error.message; }); }

  const authGate = document.querySelector("[data-auth-gate]");
  if (!authGate) start();
  else window.addEventListener("load", () => {
    const clientId = authGate.dataset.clientId;
    const errorNode = authGate.querySelector("[data-auth-error]");
    async function enter(session) {
      if (session.access === "approved") {
        authGate.hidden = true;
        document.querySelector("[data-admin-link]").hidden = session.role !== "admin";
        start(); return;
      }
      const stateNode = authGate.querySelector("[data-access-state]");
      stateNode.hidden = false;
      stateNode.querySelector("[data-access-title]").textContent = session.access === "rejected" ? "Access was not approved" : "Approval is required";
      stateNode.querySelector("[data-access-copy]").textContent = session.access === "rejected" ? "Contact the administrator if you believe this is a mistake." : "Send a request to the administrator. Your private workspace stays locked until approval.";
      const requestButton = stateNode.querySelector("[data-request-access]");
      requestButton.hidden = session.access === "rejected";
      requestButton.onclick = async () => { requestButton.disabled = true; try { await api("/api/access-request", { method: "POST" }); requestButton.textContent = "Request sent"; } catch (error) { requestButton.disabled = false; errorNode.textContent = error.message; } };
    }
    api("/api/session").then(enter).catch(() => {
      if (!clientId || !window.google?.accounts?.id) { errorNode.textContent = "Google sign-in could not be loaded."; return; }
      google.accounts.id.initialize({ client_id: clientId, callback: async (response) => {
        authToken = response.credential; errorNode.textContent = "";
        try {
          const session = await api("/api/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ credential: response.credential }) });
          await enter(session);
        } catch (error) { errorNode.textContent = error.message; }
      }});
      google.accounts.id.renderButton(authGate.querySelector("[data-google-signin]"), { theme: "outline", size: "large", shape: "rectangular" });
    });
  });
})();
