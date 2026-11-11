// Shared renderer for a saved board report (used by the application page).
window.AdvisoryReport = (() => {
  const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
  const bandOf = (score) => (score >= 75 ? "strong" : score >= 45 ? "partial" : "weak");
  function section(className, overline, title) {
    const node = el("section", className);
    const heading = el("div", "result-section-heading compact"); const inner = el("div");
    inner.append(el("span", "overline", overline), el("h2", "", title)); heading.append(inner); node.append(heading);
    return node;
  }
  function numberedItem(tag, index, children) { const item = el(tag); item.append(el("span", "", String(index)), ...children); return item; }

  function ledgerItems(saved) {
    const review = saved.review;
    const useAi = !saved.degraded && Array.isArray(review.requirements) && review.requirements.length > 0;
    return useAi
      ? review.requirements.map((item) => ({ term: item.requirement, matched: item.supported, evidence: item.evidence ? [item.evidence] : [] }))
      : saved.assessment.requirements;
  }

  function render(body, saved, advisors) {
    const review = saved.review; const assessment = saved.assessment;
    body.replaceChildren();
    if (saved.notice) {
      const notice = el("div", "ai-degraded-notice"); notice.setAttribute("role", "status");
      const copy = el("div"); copy.append(el("strong", "", "AI panel unavailable for this run"), el("p", "", saved.notice));
      notice.append(el("span", "", "i"), copy); body.append(notice);
    }
    const items = ledgerItems(saved);
    const matched = items.filter((item) => item.matched);
    const decision = el("section", "decision-card primary-decision");
    const score = el("div", "result-score");
    const scoreValue = el("div"); scoreValue.append(el("strong", "", String(review.fit_score)), el("small", "", "/100"));
    const band = bandOf(review.fit_score);
    score.append(el("span", "", saved.degraded ? "Evidence match" : "AI panel fit"), scoreValue, el("span", `band-badge band-${band}`, `${band} match`), el("small", "secondary-score", `Keyword evidence check: ${assessment.score}/100`));
    const copy = el("div", "decision-copy");
    copy.append(el("span", "overline", "Board consensus"), el("p", "", review.summary));
    const facts = el("div", "decision-facts");
    [[matched.length, "Requirements supported"], [items.length - matched.length, "Evidence gaps"]].forEach(([value, label]) => { const fact = el("div"); fact.append(el("strong", "", String(value)), el("span", "", label)); facts.append(fact); });
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
    ledgerTitle.append(el("span", "overline", "Evidence ledger"), el("h2", "", "Priority requirement evidence")); ledgerHead.append(ledgerTitle, el("span", "", `${items.length} reviewed`));
    const rows = el("div", "evidence-list");
    items.forEach((requirement) => {
      const row = el("article", `evidence-row ${requirement.matched ? "is-supported" : "is-missing"}`);
      const status = el("div", "evidence-status"); status.append(el("span", "", requirement.matched ? "✓" : "−"));
      const detail = el("div"); const head = el("div", "requirement-heading");
      head.append(el("h3", "requirement-name", requirement.term), el("span", "", requirement.matched ? "Supported" : "Missing evidence"));
      detail.append(head, el("p", "", requirement.matched ? `“${requirement.evidence[0]}”` : "No direct CV line was found for this requirement."));
      row.append(status, detail); rows.append(row);
    });
    ledger.append(ledgerHead, rows); body.append(ledger);
  }

  // The single most useful next action for an application (shared by the dashboard card and the application page).
  function nextStep(app) {
    const page = (tab) => `/applications/${encodeURIComponent(app.id)}?tab=${tab}`;
    const review = `/review?application=${encodeURIComponent(app.id)}`;
    if (app.status === "offer" || app.status === "closed") return null;
    if (!app.has_board_review) {
      const missing = [!app.cv_version_id && "the CV", !(app.job_url || app.job_description_filename) && "the job posting"].filter(Boolean);
      return { title: "Get the board's review", hint: missing.length ? `You'll add ${missing.join(" and ")} first.` : "Your CV and the posting are saved — one click to run it.", label: "Get board review", href: review };
    }
    if (app.status === "interested") return { title: "Tailor your CV, then apply", hint: "Answer a few questions and get a revised CV built from the report.", label: "Improve CV", href: page("improve") };
    if (app.status === "applied") return { title: "Get ready for the first call", hint: app.answer_count ? "Practise the questions this role is likely to ask." : "Log what you wrote on the form, then practise likely questions.", label: app.practice_count ? `Practise · ${app.practice_count} cards` : "Start practising", href: page("practice") };
    return { title: "Practise for the interview", hint: "Cards you find hard come back sooner.", label: app.practice_count ? `Practise · ${app.practice_count} cards` : "Start practising", href: page("practice") };
  }

  return { render, nextStep };
})();
