(() => {
  const advisors = Object.fromEntries(JSON.parse(document.getElementById("advisors-data").textContent).map((item) => [item.id, item]));
  const state = { cvs: [], applications: [], cvId: "", application: null, jobText: "", saved: null, questions: [] };
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

  // ---------- Steps ----------
  function showStep(step) {
    $$("[data-step]").forEach((panel) => {
      const value = Number(panel.dataset.step);
      if (value === 4) panel.hidden = step !== 4;
      else panel.classList.toggle("visible", value === step);
    });
    $("[data-review-progress]").hidden = true;
    $$("[data-step-indicator]").forEach((indicator) => {
      const value = Number(indicator.dataset.stepIndicator);
      indicator.classList.toggle("active", value === step);
      indicator.classList.toggle("complete", value < step);
      if (value === step) indicator.setAttribute("aria-current", "step"); else indicator.removeAttribute("aria-current");
    });
    $(`[data-step="${step}"] h2`)?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  async function withBusy(button, label, work) {
    const original = button.innerHTML; button.disabled = true; button.textContent = label;
    try { return await work(); } finally { button.disabled = false; button.innerHTML = original; }
  }

  // ---------- Step 1: CV ----------
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
  $('[data-next="1"]').addEventListener("click", async (event) => {
    setError(1, "");
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
      if (!state.cvId) { setError(1, "Choose a CV from your library or upload one."); return; }
      showStep(2);
    } catch (error) { setError(1, error.message); }
  });

  // ---------- Step 2: Job ----------
  const jobMode = () => $$("[data-job-mode]").find((input) => input.checked)?.value || "existing";
  const selectedApplication = () => state.applications.find((app) => app.id === $("[data-application-select]").value);
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

  function renderApplications(selectedId = "") {
    const select = $("[data-application-select]");
    select.replaceChildren(new Option(state.applications.length ? "Choose an application" : "No applications yet", ""));
    state.applications.forEach((item) => select.add(new Option(`${item.role} — ${item.company}`, item.id)));
    select.value = selectedId;
    if (!state.applications.length) { $$("[data-job-mode]").find((input) => input.value === "new").checked = true; }
    updateJobMode();
  }
  function describeSavedJob() {
    const item = jobMode() === "existing" ? selectedApplication() : null;
    const parts = [];
    if (item?.job_description_filename) parts.push(`Job description: ${item.job_description_filename}`);
    if (item?.job_url) parts.push(`Link: ${item.job_url}`);
    const savedTab = $('[data-source-tab="saved"]');
    savedTab.hidden = parts.length === 0;
    $("[data-job-saved]").textContent = parts.length ? `${parts.join(" · ")}. Nothing else needed — or pick another source to replace it.` : "";
    if (parts.length) setSource("saved"); else if (activeSource === "saved") setSource("link");
  }
  function updateJobMode() {
    const mode = jobMode();
    $("[data-existing-fields]").hidden = mode !== "existing";
    $("[data-new-fields]").hidden = mode !== "new";
    describeSavedJob();
  }
  $$("[data-job-mode]").forEach((input) => input.addEventListener("change", updateJobMode));
  $("[data-application-select]").addEventListener("change", describeSavedJob);

  function fillIdentity(result) {
    [["[data-new-company]", result.company], ["[data-new-role]", result.role]].forEach(([selector, value]) => {
      const input = $(selector);
      if (value && (!input.value.trim() || input.dataset.autofilled === "true")) { input.value = value; input.dataset.autofilled = "true"; }
    });
  }
  $$("[data-new-company], [data-new-role]").forEach((input) => input.addEventListener("input", () => { input.dataset.autofilled = "false"; }));

  async function previewJob() {
    const body = new FormData();
    if (activeSource === "link") {
      const url = $("[data-job-url]").value.trim();
      try { if (new URL(url).protocol !== "https:") return null; } catch (_) { return null; }
      body.append("job_url", url);
    } else if (activeSource === "file") {
      const file = $("[data-job-file]").files?.[0]; if (!file) return null;
      body.append("job_file", file);
    } else if (activeSource === "text") {
      const text = $("[data-job-text]").value.trim(); if (text.length < 40) return null;
      body.append("job_text", text);
    } else return null;
    const token = ++previewToken;
    previewStatus("Reading the posting…");
    try {
      const result = await api("/api/job-preview", { method: "POST", body });
      if (token !== previewToken) return null;
      fillIdentity(result);
      const found = [result.role, result.company].filter(Boolean).join(" at ");
      previewStatus(found ? `Posting read: ${found}.` : "Posting read. Add the company and role below.", "ok");
      return result;
    } catch (error) {
      if (token !== previewToken) return null;
      previewStatus(error.message, "error");
      return { failed: true, message: error.message };
    }
  }
  let previewTimer = 0;
  $("[data-job-url]").addEventListener("input", () => { clearTimeout(previewTimer); previewTimer = window.setTimeout(previewJob, 700); });
  $("[data-job-file]").addEventListener("change", previewJob);
  $("[data-job-text]").addEventListener("blur", previewJob);

  $('[data-next="2"]').addEventListener("click", async (event) => {
    setError(2, "");
    const mode = jobMode();
    const jobUrl = activeSource === "link" ? $("[data-job-url]").value.trim() : "";
    const jobFile = activeSource === "file" ? $("[data-job-file]").files?.[0] : null;
    state.jobText = activeSource === "text" ? $("[data-job-text]").value.trim() : "";
    if (jobUrl) { try { if (new URL(jobUrl).protocol !== "https:") throw new Error(); } catch (_) { setError(2, "Enter a complete HTTPS job link, such as https://company.com/jobs/role."); return; } }
    const hasNewSource = Boolean(jobUrl || jobFile || state.jobText);
    if (activeSource !== "saved" && !hasNewSource) {
      setError(2, activeSource === "link" ? "Add the job link, or choose PDF or Paste text." : activeSource === "file" ? "Choose the posting file." : "Paste the job description.");
      return;
    }
    try {
      await withBusy(event.currentTarget, "Saving…", async () => {
        let application;
        if (mode === "new") {
          let company = $("[data-new-company]").value.trim(); let role = $("[data-new-role]").value.trim();
          if (!company || !role) { const result = await previewJob(); if (result && !result.failed) { company = $("[data-new-company]").value.trim(); role = $("[data-new-role]").value.trim(); } }
          if (!company || !role) throw new Error("We couldn't read the company and role from the posting. Please type them in.");
          application = await api("/api/applications", { method: "POST", ...jsonBody({ company, role, cv_version_id: state.cvId, job_url: jobUrl }) });
          state.applications.unshift(application);
        } else {
          const current = selectedApplication();
          if (!current) throw new Error("Choose an application, or switch to a new one.");
          application = await api(`/api/applications/${current.id}`, { method: "PATCH", ...jsonBody({ cv_version_id: state.cvId, ...(jobUrl ? { job_url: jobUrl } : {}) }) });
        }
        if (jobFile) {
          const body = new FormData(); body.append("job_file", jobFile);
          application = await api(`/api/applications/${application.id}/job-description`, { method: "POST", body });
          $("[data-job-file]").value = "";
        } else if (jobUrl && application.job_description_filename) {
          // A new link replaces an older saved description, so the review reads the link.
          application = await api(`/api/applications/${application.id}/job-description`, { method: "DELETE" });
        }
        state.application = application;
        state.applications = state.applications.map((item) => (item.id === application.id ? application : item));
      });
      showStep(3);
    } catch (error) { setError(2, error.message); }
  });

  // ---------- Step 3: Board ----------
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
    if (selected.length) setError(3, "");
  }
  advisorInputs.forEach((input) => input.addEventListener("change", renderAdvisors));
  $$("[data-advisor-preset]").forEach((button) => button.addEventListener("click", () => {
    const ids = new Set(button.dataset.advisorPreset.split(","));
    advisorInputs.forEach((input) => { input.checked = ids.has(input.value); });
    renderAdvisors();
  }));
  $$("[data-back]").forEach((button) => button.addEventListener("click", () => showStep(Number(button.dataset.back))));
  $("[data-run-review]").addEventListener("click", async () => {
    const ids = selectedAdvisors();
    if (!ids.length) { setError(3, "Choose at least one specialist."); return; }
    setError(3, "");
    $('[data-step="3"]').classList.remove("visible");
    $("[data-review-progress]").hidden = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
    try {
      const body = new FormData(); body.append("advisor_ids", ids.join(",")); body.append("job_text", state.jobText);
      const result = await api(`/api/applications/${state.application.id}/board-review`, { method: "POST", body });
      state.application = result.application;
      state.applications = state.applications.map((item) => (item.id === result.application.id ? result.application : item));
      state.jobText = "";
      openReport(result.board_review);
      history.replaceState(null, "", `/review?application=${encodeURIComponent(state.application.id)}`);
    } catch (error) {
      showStep(3); setError(3, error.message);
    }
  });

  // ---------- Step 4: Report ----------
  const bandOf = (score) => (score >= 75 ? "strong" : score >= 45 ? "partial" : "weak");
  function section(className, overline, title) {
    const node = el("section", className);
    const heading = el("div", "result-section-heading compact"); const inner = el("div");
    inner.append(el("span", "overline", overline), el("h2", "", title)); heading.append(inner); node.append(heading);
    return node;
  }
  function numberedItem(tag, index, children) { const item = el(tag); item.append(el("span", "", String(index)), ...children); return item; }

  function openReport(saved) {
    state.saved = saved;
    state.cvId = saved.cv_version_id;
    const review = saved.review; const assessment = saved.assessment; const app = state.application;
    const cvLabel = state.cvs.find((item) => item.id === saved.cv_version_id)?.label || "Saved CV";
    $("[data-report-title]").textContent = `${app.role} at ${app.company}`;
    $("[data-practice-link]").href = `/practice?application=${encodeURIComponent(app.id)}`;
    $("[data-report-meta]").textContent = `${cvLabel} · ${new Date(saved.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} · ${saved.degraded ? "rule-based" : saved.model}`;
    const body = $("[data-report-body]"); body.replaceChildren();

    if (saved.notice) {
      const notice = el("div", "ai-degraded-notice"); notice.setAttribute("role", "status");
      const copy = el("div"); copy.append(el("strong", "", "AI panel unavailable for this run"), el("p", "", saved.notice));
      notice.append(el("span", "", "i"), copy); body.append(notice);
    }

    const useAiLedger = !saved.degraded && Array.isArray(review.requirements) && review.requirements.length > 0;
    const ledgerItems = useAiLedger
      ? review.requirements.map((item) => ({ term: item.requirement, matched: item.supported, evidence: item.evidence ? [item.evidence] : [] }))
      : assessment.requirements;
    const matched = ledgerItems.filter((item) => item.matched);
    const decision = el("section", "decision-card primary-decision");
    const score = el("div", "result-score");
    const scoreValue = el("div"); scoreValue.append(el("strong", "", String(review.fit_score)), el("small", "", "/100"));
    const band = bandOf(review.fit_score);
    score.append(el("span", "", saved.degraded ? "Evidence match" : "AI panel fit"), scoreValue, el("span", `band-badge band-${band}`, `${band} match`), el("small", "secondary-score", `Keyword evidence check: ${assessment.score}/100`));
    const copy = el("div", "decision-copy");
    copy.append(el("span", "overline", "Board consensus"), el("p", "", review.summary));
    const facts = el("div", "decision-facts");
    [[matched.length, "Requirements supported"], [ledgerItems.length - matched.length, "Evidence gaps"]].forEach(([value, label]) => { const fact = el("div"); fact.append(el("strong", "", String(value)), el("span", "", label)); facts.append(fact); });
    decision.append(score, copy, facts); body.append(decision);

    const board = el("section", "board-report");
    if (review.advisor_findings?.length) {
      const verdicts = section("advisor-verdicts", "Your selected specialists", "One finding per advisor");
      const grid = el("div", "advisor-verdict-grid");
      review.advisor_findings.forEach((finding) => {
        const advisor = advisors[finding.advisor_id] || { initials: "AI", name: "Board advisor", role: "Specialist" };
        const card = el("article", "advisor-verdict");
        const head = el("div", "advisor-verdict-heading"); const who = el("div");
        who.append(el("strong", "", advisor.name), el("small", "", advisor.role)); head.append(el("span", "advisor-avatar", advisor.initials), who);
        const evidence = el("div", "verdict-evidence"); evidence.append(el("span", "", "Evidence used"));
        if (finding.evidence.length) finding.evidence.forEach((quote) => evidence.append(el("q", "", quote))); else evidence.append(el("p", "", "No direct CV line supports this point yet."));
        const action = el("div", "verdict-action"); action.append(el("span", "", "→"), el("p", "", finding.recommendation));
        card.append(head, el("h3", "", finding.headline), el("p", "", finding.finding), evidence, action); grid.append(card);
      });
      verdicts.append(grid); board.append(verdicts);
    }
    const actions = el("div", "board-action-grid");
    const tailoring = section("tailoring-plan", "Tailor before sending", "Safe, high-impact edits");
    const moves = el("div", "tailoring-list");
    (review.tailoring_moves.length ? review.tailoring_moves : review.next_actions.map((change) => ({ section: "Next action", change, reason: "" }))).forEach((move, index) => {
      const content = el("div"); content.append(el("strong", "", move.section), el("p", "", move.change)); if (move.reason) content.append(el("small", "", move.reason));
      moves.append(numberedItem("article", index + 1, [content]));
    });
    tailoring.append(moves);
    const prep = section("interview-prep", "Interview preparation", "Questions to prepare");
    const list = el("ol");
    review.interview_questions.forEach((question, index) => list.append(numberedItem("li", index + 1, [el("p", "", question)])));
    prep.append(list); actions.append(tailoring, prep); board.append(actions); body.append(board);

    const ledger = el("section", "evidence-ledger");
    const ledgerHead = el("div", "result-section-heading compact"); const ledgerTitle = el("div");
    ledgerTitle.append(el("span", "overline", "Evidence ledger"), el("h2", "", "Priority requirement evidence")); ledgerHead.append(ledgerTitle, el("span", "", `${ledgerItems.length} reviewed`));
    const rows = el("div", "evidence-list");
    ledgerItems.forEach((requirement) => {
      const row = el("article", `evidence-row ${requirement.matched ? "is-supported" : "is-missing"}`);
      const status = el("div", "evidence-status"); status.append(el("span", "", requirement.matched ? "✓" : "−"));
      const detail = el("div"); const head = el("div", "requirement-heading");
      head.append(el("h3", "requirement-name", requirement.term), el("span", "", requirement.matched ? "Supported" : "Missing evidence"));
      detail.append(head, el("p", "", requirement.matched ? `“${requirement.evidence[0]}”` : "No direct CV line was found for this requirement."));
      row.append(status, detail); rows.append(row);
    });
    ledger.append(ledgerHead, rows); body.append(ledger);

    resetInterview();
    $("[data-draft-attach-label]").textContent = `Use this version for ${app.role} at ${app.company}`;
    showStep(4);
  }
  $("[data-new-review]").addEventListener("click", () => {
    if (state.application) { $$("[data-job-mode]").find((input) => input.value === "existing").checked = true; updateJobMode(); renderApplications(state.application.id); }
    renderCvOptions(); showStep(1);
  });

  // ---------- Interview ----------
  function resetInterview() {
    state.questions = [];
    $("[data-interview-form]").hidden = true; $("[data-draft]").hidden = true; $("[data-draft-saved]").hidden = true;
    $("[data-start-interview]").hidden = false; $("[data-interview-notice]").hidden = true;
    $("[data-questions]").replaceChildren(); $("[data-interview-error]").textContent = ""; $("[data-draft-error]").textContent = "";
  }
  function showNotice(text) { const node = $("[data-interview-notice]"); node.textContent = text || ""; node.hidden = !text; }
  $("[data-start-interview]").addEventListener("click", async (event) => {
    $("[data-interview-error]").textContent = "";
    try {
      await withBusy(event.currentTarget, "Preparing questions…", async () => {
        const body = new FormData(); if (state.application) body.append("application_id", state.application.id);
        const result = await api(`/api/cv-versions/${state.cvId}/interview`, { method: "POST", body });
        state.questions = result.questions; showNotice(result.notice);
        const container = $("[data-questions]"); container.replaceChildren();
        result.questions.forEach((item, index) => {
          const label = el("label", "interview-question");
          const title = el("span", "interview-question-title"); title.append(el("span", "interview-index", String(index + 1)), el("strong", "", item.question));
          const area = el("textarea"); area.rows = 4; area.maxLength = 1500; area.placeholder = "Your answer — specific facts, numbers, tools, outcomes."; area.dataset.answerIndex = String(index);
          label.append(title); if (item.purpose) label.append(el("small", "", item.purpose)); label.append(area); container.append(label);
        });
        $("[data-interview-form]").hidden = false; event.currentTarget.hidden = true;
        $("[data-interview-form] textarea")?.focus();
      });
    } catch (error) { $("[data-interview-error]").textContent = error.message; $("[data-interview-form]").hidden = false; }
  });
  $("[data-interview-form]").addEventListener("submit", async (event) => {
    event.preventDefault();
    const answers = state.questions.map((item, index) => ({ question: item.question, answer: $(`[data-answer-index="${index}"]`).value.trim() }));
    if (!answers.some((item) => item.answer)) { $("[data-interview-error]").textContent = "Answer at least one question."; return; }
    $("[data-interview-error]").textContent = "";
    try {
      await withBusy($("[data-write-draft]"), "Writing your revised CV…", async () => {
        const result = await api(`/api/cv-versions/${state.cvId}/interview/draft`, { method: "POST", ...jsonBody({ application_id: state.application?.id || null, answers }) });
        showNotice(result.notice);
        $("[data-draft-changes]").replaceChildren(...result.draft.changes.map((change) => el("li", "", change)));
        $("[data-draft-text]").value = result.draft.cv_text;
        const base = state.cvs.find((item) => item.id === state.cvId)?.label || "CV";
        $("[data-draft-label]").value = `${base} · ${state.application ? state.application.company : "revised"}`.slice(0, 100);
        $("[data-draft]").hidden = false;
        $("[data-draft]").scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } catch (error) { $("[data-interview-error]").textContent = error.message; }
  });
  $("[data-save-draft]").addEventListener("click", async (event) => {
    const text = $("[data-draft-text]").value.trim(); const label = $("[data-draft-label]").value.trim();
    const error = $("[data-draft-error]"); error.textContent = "";
    if (!text || !label) { error.textContent = "Add a label and keep some CV text before saving."; return; }
    try {
      await withBusy(event.currentTarget, "Saving…", async () => {
        const body = new FormData(); body.append("label", label); body.append("cv_text", text);
        const version = await api(`/api/cv-versions/${state.cvId}/revisions`, { method: "POST", body });
        state.cvs.unshift(version);
        let attached = false;
        if (state.application && $("[data-draft-attach]").checked) {
          state.application = await api(`/api/applications/${state.application.id}`, { method: "PATCH", ...jsonBody({ cv_version_id: version.id }) });
          attached = true;
        }
        state.newVersion = version;
        $("[data-draft-saved-copy]").textContent = `"${version.label}" is a new version in your library${attached ? ` and is now attached to ${state.application.role} at ${state.application.company}` : ""}. Your original CV is unchanged.`;
        $("[data-draft]").hidden = true; $("[data-interview-form]").hidden = true; $("[data-draft-saved]").hidden = false;
      });
    } catch (exc) { error.textContent = exc.message; }
  });
  $("[data-draft-download]").addEventListener("click", async (event) => {
    event.preventDefault();
    const version = state.newVersion; if (!version) return;
    const response = await fetch(`/api/cv-versions/${version.id}/download`, { headers: authToken ? { Authorization: `Bearer ${authToken}` } : {} });
    if (!response.ok) return;
    const url = URL.createObjectURL(await response.blob()); const link = document.createElement("a");
    link.href = url; link.download = version.filename; link.click(); URL.revokeObjectURL(url);
  });
  $("[data-review-new-version]").addEventListener("click", () => {
    if (!state.newVersion) return;
    state.cvId = state.newVersion.id; renderCvOptions();
    if (state.application) { $$("[data-job-mode]").find((input) => input.value === "existing").checked = true; updateJobMode(); renderApplications(state.application.id); }
    showStep(3);
  });
  $("[data-print-draft]").addEventListener("click", () => {
    const view = window.open("", "_blank");
    if (!view) return;
    view.document.title = $("[data-draft-label]").value || "CV";
    const pre = view.document.createElement("pre");
    pre.textContent = $("[data-draft-text]").value;
    pre.setAttribute("style", "white-space: pre-wrap; font: 11pt/1.45 Georgia, 'Times New Roman', serif; margin: 18mm; color: #111;");
    view.document.body.append(pre);
    view.focus(); view.print();
  });

  // ---------- Start ----------
  async function load() {
    const [cvs, applications] = await Promise.all([api("/api/cv-versions"), api("/api/applications")]);
    state.cvs = cvs; state.applications = applications;
    state.cvId = state.cvId || cvs[0]?.id || "";
    renderCvOptions(); renderApplications(); updateJobMode(); renderAdvisors();
    $("[data-loading-workspace]").hidden = true;
    const requested = new URLSearchParams(location.search).get("application");
    if (requested) {
      const app = applications.find((item) => item.id === requested);
      if (app) {
        state.application = app;
        if (app.cv_version_id) state.cvId = app.cv_version_id;
        renderCvOptions(); renderApplications(app.id);
        if (app.has_board_review) {
          try { const result = await api(`/api/applications/${app.id}/board-review`); state.application = result.application; openReport(result.board_review); return; }
          catch (_) { /* fall through to the guided steps */ }
        }
      }
    }
    showStep(1);
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
