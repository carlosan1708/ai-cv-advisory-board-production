(() => {
  let token = "";
  const body = document.body;
  const gate = document.querySelector("[data-admin-auth]");
  const accessList = document.querySelector("[data-access-list]");

  async function api(url, options = {}) {
    options.headers = { ...(options.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail;
      throw new Error((typeof detail === "object" ? detail.message : detail) || "Request failed");
    }
    return payload;
  }

  function money(microUsd) {
    const dollars = microUsd / 1000000;
    return dollars > 0 && dollars < 0.01 ? `$${dollars.toFixed(4)}` : `$${dollars.toFixed(2)}`;
  }

  function percent(budget) {
    return budget.limit_micro_usd ? Math.min(100, budget.used_micro_usd / budget.limit_micro_usd * 100) : 0;
  }

  function renderAccess(records) {
    accessList.replaceChildren();
    document.querySelector("[data-admin-empty]").hidden = records.length > 0;
    records.forEach((record) => {
      const row = document.querySelector("#access-row").content.firstElementChild.cloneNode(true);
      row.querySelector("[data-email]").textContent = record.email;
      row.querySelector("[data-subject]").textContent = record.subject ? "Google identity linked" : "Pre-approved email";
      row.querySelector("[data-status]").textContent = record.status;
      row.querySelector("[data-approve]").hidden = record.status === "approved";
      row.querySelector("[data-reject]").hidden = record.status === "rejected";
      row.querySelector("[data-approve]").onclick = () => decide(record.id, "approved");
      row.querySelector("[data-reject]").onclick = () => decide(record.id, "rejected");
      accessList.append(row);
    });
  }

  function renderUsage(data) {
    document.querySelector("[data-project-spend]").textContent = money(data.project.used_micro_usd);
    document.querySelector("[data-project-period]").textContent = `${data.month} · ${money(data.project.remaining_micro_usd)} headroom`;
    document.querySelector("[data-free-spend]").textContent = money(data.free.used_micro_usd);
    document.querySelector("[data-free-remaining]").textContent = `${money(data.free.remaining_micro_usd)} remaining`;
    document.querySelector("[data-member-spend]").textContent = money(data.member_used_micro_usd);
    document.querySelector("[data-member-count]").textContent = `${data.members.length} linked ${data.members.length === 1 ? "identity" : "identities"}`;
    document.querySelector("[data-review-count]").textContent = data.reviews_this_month;
    document.querySelector("[data-model-name]").textContent = data.model;
    document.querySelector("[data-privacy-note]").textContent = data.privacy_note;

    const projectPercent = percent(data.project);
    const freePercent = percent(data.free);
    document.querySelector("[data-project-progress]").value = projectPercent;
    document.querySelector("[data-free-progress]").value = freePercent;
    document.querySelector("[data-project-caption]").textContent = `${money(data.project.used_micro_usd)} of ${money(data.project.limit_micro_usd)}`;
    document.querySelector("[data-free-caption]").textContent = `${money(data.free.used_micro_usd)} of ${money(data.free.limit_micro_usd)}`;

    const memberList = document.querySelector("[data-member-usage]");
    memberList.replaceChildren();
    document.querySelector("[data-member-empty]").hidden = data.members.length > 0;
    data.members.forEach((member) => {
      const row = document.querySelector("#member-usage-row").content.firstElementChild.cloneNode(true);
      row.querySelector("[data-member-email]").textContent = member.email;
      row.querySelector("[data-member-caption]").textContent = `${Math.round(percent(member))}% of monthly allowance`;
      row.querySelector("[data-member-total]").textContent = money(member.used_micro_usd);
      memberList.append(row);
    });

    const reviewList = document.querySelector("[data-review-list]");
    reviewList.replaceChildren();
    document.querySelector("[data-review-empty]").hidden = data.recent_reviews.length > 0;
    const typeLabels = { job_match: "Free job match", application: "Application review", cv: "Standalone CV review" };
    data.recent_reviews.forEach((review) => {
      const row = document.querySelector("#review-row").content.firstElementChild.cloneNode(true);
      const status = row.querySelector("[data-review-status]");
      status.textContent = review.status === "gemini" ? "AI" : "!";
      status.dataset.state = review.status;
      row.querySelector("[data-review-title]").textContent = typeLabels[review.review_type] || "AI review";
      const panel = review.advisor_ids.length ? ` · ${review.advisor_ids.join(", ")}` : "";
      row.querySelector("[data-review-detail]").textContent = `${review.owner_label} · ${review.status}${panel}`;
      row.querySelector("[data-review-score]").textContent = review.score == null ? "—" : review.score;
      row.querySelector("[data-review-band]").textContent = review.band || "No score";
      row.querySelector("[data-review-cost]").textContent = money(review.actual_micro_usd);
      row.querySelector("[data-review-tokens]").textContent = `${review.input_tokens + review.output_tokens} tokens · ${review.duration_ms} ms`;
      const time = row.querySelector("[data-review-time]");
      time.dateTime = review.created_at;
      time.textContent = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(review.created_at));
      reviewList.append(row);
    });
  }

  async function load() {
    const [records, usage] = await Promise.all([api("/api/admin/access"), api("/api/admin/usage")]);
    renderAccess(records);
    renderUsage(usage);
  }

  async function decide(id, status) {
    await api(`/api/admin/access/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
    await load();
  }

  async function bootstrap() {
    const session = await api("/api/session");
    if (session.role !== "admin") throw new Error("Administrator access is required");
    gate.hidden = true;
    await load();
  }

  document.querySelector("[data-invite-form]").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const error = document.querySelector("[data-invite-error]");
    error.textContent = "";
    try {
      await api("/api/admin/access", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(form))) });
      form.reset();
      await load();
    } catch (exc) { error.textContent = exc.message; }
  });
  document.querySelector("[data-refresh]").onclick = () => load();
  if (body.dataset.authMode !== "google") bootstrap().catch((error) => { document.querySelector("[data-invite-error]").textContent = error.message; });
  else window.addEventListener("load", () => {
    const error = gate.querySelector("[data-auth-error]");
    api("/api/session").then((session) => {
      if (session.role !== "admin") throw new Error("Administrator access is required");
      gate.hidden = true;
      return load();
    }).catch(() => {
      if (!body.dataset.clientId || !window.google?.accounts?.id) { error.textContent = "Google sign-in could not be loaded."; return; }
      google.accounts.id.initialize({ client_id: body.dataset.clientId, callback: async (response) => {
        token = response.credential;
        try {
          await api("/api/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ credential: response.credential }) });
          await bootstrap();
        } catch (exc) { error.textContent = exc.message; }
      } });
      google.accounts.id.renderButton(gate.querySelector("[data-google-signin]"), { theme: "outline", size: "large" });
    });
  });
})();
