(() => {
  const advisors = Object.fromEntries(JSON.parse(document.getElementById("advisors-data").textContent).map((item) => [item.id, item]));
  const statusLabels = { interested: "Interested", applied: "Applied", interviewing: "Interviewing", offer: "Offer", closed: "Closed" };
  const answerSourceLabels = { application_form: "Application form", recruiter: "Recruiter call", interview: "Interview", cv_interview: "CV interview", other: "Other" };
  const applicationId = document.querySelector("[data-application-id]").dataset.applicationId;
  const state = { app: null, cvs: [], notes: [], questions: [], newVersion: null, tab: "report", reportLoaded: false, answersLoaded: false, practiceLoaded: false };
  let authToken = "";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
  const json = (data) => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  const base = `/api/applications/${encodeURIComponent(applicationId)}`;
  const reviewHref = () => `/review?application=${encodeURIComponent(applicationId)}`;
  const formatDate = (value) => new Date(value.length === 10 ? `${value}T00:00:00` : value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

  async function api(url, options = {}) {
    options.headers = { ...(options.headers || {}), ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) };
    const response = await fetch(url, options);
    if (response.status === 401 && authToken) throw new Error("Your sign-in expired. Reload the page and sign in again.");
    if (response.status === 204) return null;
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail;
      throw new Error((Array.isArray(detail) ? detail.map((item) => item.msg).join(" ") : typeof detail === "object" && detail ? detail.message : detail) || "Something went wrong. Try again.");
    }
    return payload;
  }
  async function withBusy(button, label, work) {
    const original = button.innerHTML; button.disabled = true; button.textContent = label;
    try { return await work(); } finally { button.disabled = false; button.innerHTML = original; }
  }
  const cvLabel = (id) => state.cvs.find((item) => item.id === id)?.label || "";

  // ---------- Header ----------
  function renderHead() {
    const app = state.app;
    document.title = `${app.role} at ${app.company} | AI CV Advisory Board`;
    $("[data-app-role]").textContent = app.role;
    $("[data-app-company]").textContent = app.company;
    $("[data-app-mark]").textContent = app.company.slice(0, 2).toUpperCase();
    $("[data-app-status]").value = app.status;
    const facts = $("[data-app-facts]"); facts.replaceChildren();
    const fact = (term, value, opts = {}) => {
      const wrap = el("div", opts.empty ? "is-empty" : ""); const dd = el("dd");
      if (opts.href) { const link = el("a", "", value); link.href = opts.href; link.target = "_blank"; link.rel = "noopener noreferrer"; dd.append(link); } else dd.textContent = value;
      wrap.append(el("dt", "", term), dd); facts.append(wrap);
    };
    const label = cvLabel(app.cv_version_id);
    fact("CV", label || "Not attached yet", { empty: !label });
    if (app.job_url) fact("Posting", new URL(app.job_url).hostname.replace(/^www\./, ""), { href: app.job_url });
    else if (app.job_description_filename) fact("Posting", app.job_description_filename);
    else fact("Posting", "Not added yet", { empty: true });
    if (app.has_board_review && app.fit_score !== null && app.fit_score !== undefined) fact("Board fit", `${app.fit_score}/100`);
    if (app.applied_date) fact("Applied", formatDate(app.applied_date));
    if (app.next_action) fact("Next", app.next_action_due ? `${app.next_action} · ${formatDate(app.next_action_due)}` : app.next_action);

    const step = window.AdvisoryReport.nextStep(app);
    $("[data-next-step]").hidden = !step;
    if (step) {
      $("[data-next-title]").textContent = step.title; $("[data-next-hint]").textContent = step.hint;
      const action = $("[data-next-action]"); action.textContent = step.label; action.href = step.href;
    }
    $('[data-tab="answers"]').textContent = app.answer_count ? `Answers · ${app.answer_count}` : "Answers";
    $('[data-tab="practice"]').textContent = app.practice_count ? `Practice · ${app.practice_count}` : "Practice";
    $$("[data-run-review]").forEach((link) => { link.href = reviewHref(); });
  }
  function setApp(app) { state.app = app; renderHead(); }

  $("[data-app-status]").addEventListener("change", async (event) => {
    const select = event.currentTarget; const previous = state.app.status;
    try { setApp(await api(base, { method: "PATCH", ...json({ status: select.value }) })); }
    catch (error) { select.value = previous; window.alert(error.message); }
  });
  // Links to another tab of this page switch tabs in place.
  $("[data-next-action]").addEventListener("click", (event) => {
    const url = new URL(event.currentTarget.href);
    if (url.pathname === location.pathname && url.searchParams.get("tab")) { event.preventDefault(); showTab(url.searchParams.get("tab")); }
  });

  // ---------- Tabs ----------
  const tabs = ["report", "improve", "answers", "practice", "details"];
  function showTab(tab) {
    state.tab = tabs.includes(tab) ? tab : "report";
    $$("[data-tab]").forEach((button) => { const on = button.dataset.tab === state.tab; button.classList.toggle("active", on); button.setAttribute("aria-selected", String(on)); });
    $$("[data-panel]").forEach((panel) => { panel.hidden = panel.dataset.panel !== state.tab; });
    history.replaceState(null, "", `${location.pathname}?tab=${state.tab}`);
    const loaders = { report: loadReport, improve: prepareInterview, answers: loadAnswers, practice: loadPractice, details: fillDetails };
    Promise.resolve(loaders[state.tab]()).catch((error) => window.alert(error.message));
  }
  $$("[data-tab]").forEach((button) => button.addEventListener("click", () => showTab(button.dataset.tab)));

  // ---------- Report ----------
  async function loadReport() {
    if (state.reportLoaded) return;
    const hasReport = state.app.has_board_review;
    $("[data-report-empty]").hidden = hasReport; $("[data-report]").hidden = !hasReport;
    if (!hasReport) {
      const app = state.app;
      const missing = [!app.cv_version_id && "choose the CV", !(app.job_url || app.job_description_filename) && "add the job posting"].filter(Boolean);
      $("[data-report-empty-copy]").textContent = missing.length
        ? `The board compares your CV with this posting and saves the report here. You'll ${missing.join(" and ")} first.`
        : "Your CV and the posting are saved. The board compares them and keeps the report here.";
      return;
    }
    const result = await api(`${base}/board-review`);
    const saved = result.board_review;
    $("[data-report-meta]").textContent = `${cvLabel(saved.cv_version_id) || "Saved CV"} · ${new Date(saved.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} · ${saved.degraded ? "rule-based" : saved.model}`;
    window.AdvisoryReport.render($("[data-report-body]"), saved, advisors);
    state.reportLoaded = true;
  }

  // ---------- Improve CV (interview) ----------
  function prepareInterview() {
    const hasCv = Boolean(state.app.cv_version_id);
    $("[data-start-interview]").hidden = !hasCv || !$("[data-interview-form]").hidden || !$("[data-draft]").hidden || !$("[data-draft-saved]").hidden;
    $("[data-interview-intro]").textContent = hasCv
      ? `The AI asks about real work "${cvLabel(state.app.cv_version_id)}" doesn't show yet, then drafts a revised CV using only your CV and your answers. You edit the draft before anything is saved, and your original version is never changed.`
      : "Attach a CV to this application first (Details tab), then come back to improve it.";
  }
  function showNotice(text) { const node = $("[data-interview-notice]"); node.textContent = text || ""; node.hidden = !text; }
  $("[data-start-interview]").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    $("[data-interview-error]").textContent = "";
    try {
      await withBusy(button, "Preparing questions…", async () => {
        const body = new FormData(); body.append("application_id", applicationId);
        const result = await api(`/api/cv-versions/${state.app.cv_version_id}/interview`, { method: "POST", body });
        state.questions = result.questions; showNotice(result.notice);
        const container = $("[data-questions]"); container.replaceChildren();
        result.questions.forEach((item, index) => {
          const label = el("label", "interview-question");
          const title = el("span", "interview-question-title"); title.append(el("span", "interview-index", String(index + 1)), el("strong", "", item.question));
          const area = el("textarea"); area.rows = 4; area.maxLength = 1500; area.placeholder = "Your answer — specific facts, numbers, tools, outcomes."; area.dataset.answerIndex = String(index);
          label.append(title); if (item.purpose) label.append(el("small", "", item.purpose)); label.append(area); container.append(label);
        });
        $("[data-interview-form]").hidden = false;
      });
      button.hidden = true;
      $("[data-interview-form] textarea")?.focus();
    } catch (error) { $("[data-interview-error]").textContent = error.message; $("[data-interview-form]").hidden = false; }
  });
  $("[data-interview-form]").addEventListener("submit", async (event) => {
    event.preventDefault();
    const answers = state.questions.map((item, index) => ({ question: item.question, answer: $(`[data-answer-index="${index}"]`).value.trim() }));
    if (!answers.some((item) => item.answer)) { $("[data-interview-error]").textContent = "Answer at least one question."; return; }
    $("[data-interview-error]").textContent = "";
    try {
      await withBusy($("[data-write-draft]"), "Writing your revised CV…", async () => {
        const result = await api(`/api/cv-versions/${state.app.cv_version_id}/interview/draft`, { method: "POST", ...json({ application_id: applicationId, answers }) });
        showNotice(result.notice);
        $("[data-draft-changes]").replaceChildren(...result.draft.changes.map((change) => el("li", "", change)));
        $("[data-draft-text]").value = result.draft.cv_text;
        $("[data-draft-label]").value = `${cvLabel(state.app.cv_version_id) || "CV"} · ${state.app.company}`.slice(0, 100);
        $("[data-draft]").hidden = false;
        $("[data-draft]").scrollIntoView({ behavior: "smooth", block: "start" });
      });
      state.answersLoaded = false;
      setApp(await api(base));
    } catch (error) { $("[data-interview-error]").textContent = error.message; }
  });
  $("[data-save-draft]").addEventListener("click", async (event) => {
    const text = $("[data-draft-text]").value.trim(); const label = $("[data-draft-label]").value.trim();
    const error = $("[data-draft-error]"); error.textContent = "";
    if (!text || !label) { error.textContent = "Add a label and keep some CV text before saving."; return; }
    try {
      await withBusy(event.currentTarget, "Saving…", async () => {
        const body = new FormData(); body.append("label", label); body.append("cv_text", text);
        const version = await api(`/api/cv-versions/${state.app.cv_version_id}/revisions`, { method: "POST", body });
        state.cvs.unshift(version); state.newVersion = version;
        const attach = $("[data-draft-attach]").checked;
        if (attach) setApp(await api(base, { method: "PATCH", ...json({ cv_version_id: version.id }) }));
        $("[data-draft-saved-copy]").textContent = `"${version.label}" is a new version in your library${attach ? " and is now the CV for this application" : ""}. Your original CV is unchanged.`;
        $("[data-draft]").hidden = true; $("[data-interview-form]").hidden = true; $("[data-draft-saved]").hidden = false;
        renderCvSelect();
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
  $("[data-print-draft]").addEventListener("click", () => {
    const view = window.open("", "_blank"); if (!view) return;
    view.document.title = $("[data-draft-label]").value || "CV";
    const pre = view.document.createElement("pre"); pre.textContent = $("[data-draft-text]").value;
    pre.setAttribute("style", "white-space: pre-wrap; font: 11pt/1.45 Georgia, 'Times New Roman', serif; margin: 18mm; color: #111;");
    view.document.body.append(pre); view.focus(); view.print();
  });

  // ---------- Answers ----------
  async function loadAnswers() {
    if (state.answersLoaded) return;
    state.notes = await api(`${base}/answers`); state.answersLoaded = true;
    resetAnswerEditor(); renderAnswers();
  }
  function resetAnswerEditor() {
    $("[data-answer-id]").value = ""; $("[data-answer-question]").value = ""; $("[data-answer-text]").value = "";
    $("[data-answer-source]").value = "application_form"; $("[data-answer-editor-title]").textContent = "Add an answer";
    $("[data-answer-cancel-edit]").hidden = true; $("[data-answers-error]").textContent = "";
  }
  function syncAnswerCount() { state.app.answer_count = state.notes.length; renderHead(); }
  function renderAnswers() {
    const list = $("[data-answers-list]"); list.replaceChildren();
    const query = $("[data-answers-search]").value.trim().toLowerCase();
    $("[data-answers-empty]").hidden = state.notes.length > 0;
    state.notes.filter((note) => !query || `${note.question} ${note.answer}`.toLowerCase().includes(query)).forEach((note) => {
      const item = el("article", "answer-item");
      const head = el("div", "answer-head"); head.append(el("span", "answer-source", answerSourceLabels[note.source] || note.source), el("small", "", formatDate(note.updated_at)));
      const actions = el("div", "answer-actions");
      const copy = el("button", "text-action", "Copy"); copy.type = "button";
      copy.addEventListener("click", async () => { try { await navigator.clipboard.writeText(note.answer); copy.textContent = "Copied"; setTimeout(() => { copy.textContent = "Copy"; }, 1500); } catch (_) { copy.textContent = "Copy failed"; } });
      const edit = el("button", "text-action", "Edit"); edit.type = "button";
      edit.addEventListener("click", () => {
        $("[data-answer-id]").value = note.id; $("[data-answer-question]").value = note.question; $("[data-answer-text]").value = note.answer; $("[data-answer-source]").value = note.source;
        $("[data-answer-editor-title]").textContent = "Edit answer"; $("[data-answer-cancel-edit]").hidden = false;
        $("[data-answer-question]").focus();
      });
      const remove = el("button", "text-action danger-text", "Delete"); remove.type = "button";
      remove.addEventListener("click", async () => {
        if (!window.confirm("Delete this answer?")) return;
        try { await api(`${base}/answers/${note.id}`, { method: "DELETE" }); state.notes = state.notes.filter((item) => item.id !== note.id); syncAnswerCount(); renderAnswers(); }
        catch (error) { $("[data-answers-error]").textContent = error.message; }
      });
      actions.append(copy, edit, remove);
      item.append(head, el("strong", "", note.question), el("p", "", note.answer || "(no answer recorded)"), actions); list.append(item);
    });
  }
  $("[data-answers-search]").addEventListener("input", renderAnswers);
  $("[data-answer-question]").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); $("[data-answer-save]").click(); } });
  $("[data-answer-cancel-edit]").addEventListener("click", resetAnswerEditor);
  $("[data-answer-save]").addEventListener("click", async (event) => {
    const error = $("[data-answers-error]"); error.textContent = "";
    const id = $("[data-answer-id]").value;
    const payload = { question: $("[data-answer-question]").value.trim(), answer: $("[data-answer-text]").value.trim(), source: $("[data-answer-source]").value };
    if (!payload.question) { error.textContent = "Add the question you were asked."; return; }
    const button = event.currentTarget; button.disabled = true;
    try {
      const note = await api(id ? `${base}/answers/${id}` : `${base}/answers`, { method: id ? "PATCH" : "POST", ...json(payload) });
      state.notes = id ? state.notes.map((item) => (item.id === id ? note : item)) : [...state.notes, note];
      resetAnswerEditor(); syncAnswerCount(); renderAnswers();
    } catch (exc) { error.textContent = exc.message; }
    finally { button.disabled = false; }
  });

  // ---------- Practice ----------
  const deckRoot = $("[data-practice-deck]");
  const deck = window.PracticeDeck.mount(deckRoot, { api, onChange: (_, payload) => { state.app.practice_count = payload.cards.length; renderHead(); } });
  deckRoot.addEventListener("practice:answer-saved", () => { state.answersLoaded = false; state.app.answer_count += 1; renderHead(); });
  async function loadPractice() { if (state.practiceLoaded) return; await deck.load(applicationId); state.practiceLoaded = true; }

  // ---------- Details ----------
  const form = $("[data-details-form]");
  const detailFields = ["company", "role", "cv_version_id", "job_url", "applied_date", "next_action_due", "next_action", "notes"];
  function renderCvSelect() {
    const select = $("[data-details-cv]"); select.replaceChildren(new Option("Not attached yet", ""));
    state.cvs.forEach((version) => select.add(new Option(version.label, version.id)));
    select.value = state.app.cv_version_id || "";
  }
  function fillDetails() {
    renderCvSelect();
    detailFields.forEach((name) => { form.elements[name].value = state.app[name] ?? ""; });
    form.elements.job_file.value = "";
    $("[data-job-file-current]").hidden = !state.app.job_description_filename;
    $("[data-job-file-name]").textContent = state.app.job_description_filename || "";
    $("[data-details-error]").textContent = ""; $("[data-details-ok]").textContent = "";
  }
  function invalidate() { state.reportLoaded = false; }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form)); delete data.job_file;
    ["applied_date", "next_action_due", "cv_version_id"].forEach((name) => { if (!data[name]) data[name] = null; });
    const file = form.elements.job_file.files?.[0];
    const error = $("[data-details-error]"); const ok = $("[data-details-ok]"); error.textContent = ""; ok.textContent = "";
    const button = event.submitter || form.querySelector('button[type="submit"]');
    try {
      await withBusy(button, "Saving…", async () => {
        let app = await api(base, { method: "PATCH", ...json(data) });
        if (file) {
          button.textContent = "Reading job description…";
          const body = new FormData(); body.append("job_file", file);
          app = await api(`${base}/job-description`, { method: "POST", body });
        }
        setApp(app); invalidate();
      });
      fillDetails(); ok.textContent = "Saved.";
    } catch (exc) { error.textContent = exc.message; }
  });
  $("[data-remove-job-file]").addEventListener("click", async () => {
    try { setApp(await api(`${base}/job-description`, { method: "DELETE" })); fillDetails(); }
    catch (exc) { $("[data-details-error]").textContent = exc.message; }
  });
  $("[data-delete-application]").addEventListener("click", async () => {
    if (!window.confirm(`Remove ${state.app.role} at ${state.app.company}? This cannot be undone. Your CV versions are kept.`)) return;
    try { await api(base, { method: "DELETE" }); location.href = "/dashboard"; }
    catch (exc) { $("[data-details-error]").textContent = exc.message; }
  });

  // ---------- Start ----------
  async function load() {
    const [app, cvs] = await Promise.all([api(base), api("/api/cv-versions")]);
    state.cvs = cvs; setApp(app);
    $("[data-loading-workspace]").hidden = true; $("[data-app]").hidden = false;
    showTab(new URLSearchParams(location.search).get("tab") || "report");
  }
  async function enter(session) {
    if (session.access !== "approved") throw new Error("Workspace access is not approved");
    if (session.role === "admin") $("[data-admin-link]").hidden = false;
    const gate = $("[data-auth-gate]"); if (gate) gate.hidden = true;
    await load();
  }
  const gate = $("[data-auth-gate]");
  const failLoad = (error) => {
    const message = error.message === "Application not found" ? "This application no longer exists. Go back to the dashboard." : error.message;
    $("[data-loading-workspace]").textContent = message;
    if (gate && !gate.hidden) $("[data-auth-error]", gate).textContent = message;
  };
  if (!gate) api("/api/session").then(enter).catch(failLoad);
  else window.addEventListener("load", () => {
    const errorNode = $("[data-auth-error]", gate);
    api("/api/session").then((session) => enter(session).catch(failLoad), () => {
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
