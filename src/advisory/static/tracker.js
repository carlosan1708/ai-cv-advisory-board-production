(() => {
  const statuses = ["interested", "applied", "interviewing", "offer", "closed"];
  const labels = { interested: "Interested", applied: "Applied", interviewing: "Interviewing", offer: "Offer", closed: "Closed" };
  const state = { applications: [], cvs: [], filter: "all" };
  let authToken = "";
  const board = document.querySelector("[data-board]");
  const empty = document.querySelector("[data-empty]");
  const appDialog = document.querySelector("[data-application-dialog]");
  const cvDialog = document.querySelector("[data-cv-dialog]");
  const applicationReviewDialog = document.querySelector("[data-application-review-dialog]");

  async function api(url, options = {}) {
    options.headers = { ...(options.headers || {}), ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) };
    const response = await fetch(url, options);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const detail = payload.detail;
      throw new Error((typeof detail === "object" ? detail.message : detail) || "Something went wrong. Try again.");
    }
    return response.json();
  }

  function cvLabel(id) {
    return state.cvs.find((item) => item.id === id)?.label || "";
  }

  function renderCard(application) {
    const card = document.querySelector("#application-card-template").content.firstElementChild.cloneNode(true);
    card.dataset.id = application.id;
    card.querySelector("h3").textContent = application.role;
    card.querySelector(".company-name").textContent = application.company;
    card.querySelector(".company-mark").textContent = application.company.slice(0, 2).toUpperCase();
    card.querySelector(".card-date").textContent = new Date(application.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    card.querySelector(".next-action").textContent = application.next_action ? `Next · ${application.next_action}` : "";
    const attachment = card.querySelector(".cv-attachment");
    const versionLabel = cvLabel(application.cv_version_id);
    attachment.textContent = versionLabel ? `CV · ${versionLabel}` : "No CV attached";
    attachment.classList.toggle("empty", !versionLabel);
    const aiButton = card.querySelector(".ai-review-button");
    aiButton.hidden = true;
    aiButton.addEventListener("click", async () => {
      aiButton.disabled = true; aiButton.textContent = "Reviewing evidence…";
      try {
        const result = await api(`/api/applications/${application.id}/ai-review`, { method: "POST", body: new FormData() });
        application.fit_score = result.review.fit_score; application.ai_summary = result.review.summary;
        render();
      } catch (error) { aiButton.disabled = false; aiButton.textContent = error.message; }
    });
    const reviewButton = card.querySelector(".application-review-button");
    reviewButton.hidden = !versionLabel;
    reviewButton.addEventListener("click", () => {
      const form = applicationReviewDialog.querySelector("[data-application-review-form]");
      form.reset();
      form.elements.application_id.value = application.id;
      applicationReviewDialog.querySelector("[data-application-review-title]").textContent = `${application.role} at ${application.company}`;
      applicationReviewDialog.querySelector("[data-application-review-cv]").textContent = `Attached CV · ${versionLabel}`;
      applicationReviewDialog.querySelector("[data-application-review-job]").textContent = application.job_url ? "Public job link saved" : "Paste the job description below";
      applicationReviewDialog.querySelector("[data-application-review-error]").textContent = "";
      applicationReviewDialog.showModal();
    });
    card.querySelector(".ai-summary").textContent = application.ai_summary ? `${application.fit_score}% evidence fit · ${application.ai_summary}` : "";
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

  document.querySelectorAll("[data-open-application]").forEach((button) => button.addEventListener("click", () => appDialog.showModal()));
  document.querySelectorAll("[data-open-cv]").forEach((button) => button.addEventListener("click", () => cvDialog.showModal()));
  document.querySelectorAll('.tracker-dialog button[value="cancel"]').forEach((button) => button.addEventListener("click", (event) => {
    event.preventDefault(); button.closest("dialog").close();
  }));
  document.querySelector("[data-application-form]").addEventListener("submit", async (event) => {
    if (event.submitter?.value === "cancel") return;
    event.preventDefault(); const form = event.currentTarget; const data = Object.fromEntries(new FormData(form));
    document.querySelector("[data-application-error]").textContent = "";
    try { state.applications.unshift(await api("/api/applications", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) })); form.reset(); appDialog.close(); render(); }
    catch (error) { document.querySelector("[data-application-error]").textContent = error.message; }
  });
  document.querySelector("[data-cv-form]").addEventListener("submit", async (event) => {
    if (event.submitter?.value === "cancel") return;
    event.preventDefault(); const form = event.currentTarget; document.querySelector("[data-cv-error]").textContent = "";
    try { state.cvs.unshift(await api("/api/cv-versions", { method: "POST", body: new FormData(form) })); form.reset(); renderCvLibrary(); render(); }
    catch (error) { document.querySelector("[data-cv-error]").textContent = error.message; }
  });
  document.querySelector("[data-application-review-form]").addEventListener("submit", async (event) => {
    if (event.submitter?.value === "cancel") return;
    event.preventDefault();
    const form = event.currentTarget; const data = new FormData(form); const id = data.get("application_id");
    const application = state.applications.find((item) => item.id === id);
    const error = document.querySelector("[data-application-review-error]"); error.textContent = "";
    try {
      const result = await api(`/api/applications/${id}/ai-review`, { method: "POST", body: data });
      application.fit_score = result.review.fit_score; application.ai_summary = result.review.summary;
      applicationReviewDialog.close(); render();
    } catch (exc) { error.textContent = exc.message; }
  });
  document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => { state.filter = button.dataset.filter; document.querySelector("[data-mobile-filter]").value = state.filter; render(); }));
  document.querySelector("[data-clear-filter]").addEventListener("click", () => { state.filter = "all"; render(); });
  document.querySelector("[data-mobile-filter]").addEventListener("change", (event) => { state.filter = event.target.value; render(); });

  function start() { Promise.all([api("/api/applications"), api("/api/cv-versions")]).then(([applications, cvs]) => {
    state.applications = applications; state.cvs = cvs;
    renderCvLibrary(); render();
  }).catch((error) => { empty.querySelector("p").textContent = error.message; }); }

  const authGate = document.querySelector("[data-auth-gate]");
  if (!authGate) start();
  else window.addEventListener("load", () => {
    const clientId = authGate.dataset.clientId;
    if (!clientId || !window.google?.accounts?.id) {
      authGate.querySelector("[data-auth-error]").textContent = "Google sign-in could not be loaded.";
      return;
    }
    google.accounts.id.initialize({ client_id: clientId, callback: async (response) => {
      authToken = response.credential;
      const errorNode = authGate.querySelector("[data-auth-error]");
      errorNode.textContent = "";
      try {
        const session = await api("/api/session");
        if (session.access === "approved") {
          authGate.hidden = true;
          document.querySelector("[data-admin-link]").hidden = session.role !== "admin";
          start();
          return;
        }
        const stateNode = authGate.querySelector("[data-access-state]");
        stateNode.hidden = false;
        stateNode.querySelector("[data-access-title]").textContent = session.access === "rejected" ? "Access was not approved" : "Approval is required";
        stateNode.querySelector("[data-access-copy]").textContent = session.access === "rejected" ? "Contact the administrator if you believe this is a mistake." : "Send a request to the administrator. Your private workspace stays locked until approval.";
        const requestButton = stateNode.querySelector("[data-request-access]");
        requestButton.hidden = session.access === "rejected";
        requestButton.onclick = async () => {
          requestButton.disabled = true;
          try { await api("/api/access-request", { method: "POST" }); requestButton.textContent = "Request sent"; }
          catch (error) { requestButton.disabled = false; errorNode.textContent = error.message; }
        };
      } catch (error) { errorNode.textContent = error.message; }
    }});
    google.accounts.id.renderButton(authGate.querySelector("[data-google-signin]"), { theme: "outline", size: "large", shape: "rectangular" });
  });
})();
