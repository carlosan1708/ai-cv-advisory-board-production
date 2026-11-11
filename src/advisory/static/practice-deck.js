// Flash-card deck for one application. Mounted by the Practice page and the application page.
window.PracticeDeck = (() => {
  const levelNames = { 1: "Warm-up", 2: "Role-specific", 3: "Tough" };
  const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
  const json = (data) => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

  function mount(root, { api, onChange = () => {} }) {
    const $ = (selector) => root.querySelector(selector);
    const $$ = (selector) => [...root.querySelectorAll(selector)];
    const state = { applicationId: "", cards: [], stats: null, filter: "due", queue: [], index: 0, flipped: false };
    const setError = (message) => { $("[data-practice-error]").textContent = message || ""; };
    const setNotice = (message) => { const node = $("[data-practice-notice]"); node.textContent = message || ""; node.hidden = !message; };

    function applyDeck(payload) { state.cards = payload.cards; state.stats = payload.stats; onChange(state.applicationId, payload); }

    function renderStats() {
      const stats = state.stats; const strip = $("[data-level-strip]"); strip.replaceChildren();
      stats.levels.forEach((level) => {
        const item = el("div", `level-card${level.level === stats.suggested_level ? " suggested" : ""}`);
        const percent = level.total ? Math.round((level.mastered / level.total) * 100) : 0;
        const bar = el("div", "level-bar"); const fill = el("i"); fill.style.width = `${percent}%`; bar.append(fill);
        item.append(
          el("span", "level-name", `Level ${level.level} · ${level.name}`),
          el("strong", "", level.total ? `${level.mastered}/${level.total} mastered` : "No cards yet"),
          bar,
          el("small", "", level.level === stats.suggested_level ? (level.ready ? "Mastered — great work" : "Suggested level") : level.ready ? "Ready for the next level" : level.due ? `${level.due} due now` : ""),
        );
        strip.append(item);
      });
      $("[data-deck-summary]").textContent = stats.total ? `${stats.due} due now · ${stats.mastered} of ${stats.total} mastered` : "No cards in this deck yet.";
      const select = $("[data-generate-level]");
      if (!select.dataset.touched) select.value = String(stats.suggested_level);
    }

    function buildQueue() {
      const now = Date.now();
      let cards = state.cards;
      if (state.filter === "due") cards = cards.filter((card) => new Date(card.due_at).getTime() <= now);
      else if (["1", "2", "3"].includes(state.filter)) cards = cards.filter((card) => String(card.difficulty) === state.filter);
      state.queue = [...cards].sort((a, b) => new Date(a.due_at) - new Date(b.due_at) || a.difficulty - b.difficulty);
      state.index = 0;
    }

    function renderCard() {
      const card = state.queue[state.index];
      $("[data-flashcard]").hidden = !card;
      $("[data-practice-empty]").hidden = Boolean(card);
      if (!card) {
        const none = state.cards.length === 0;
        $("[data-empty-title]").textContent = none ? "No cards yet." : state.filter === "due" ? "All caught up." : "No cards here.";
        $("[data-empty-copy]").textContent = none
          ? "Pick a level and add cards. Start with Warm-up and move up as cards become easy."
          : state.filter === "due" ? "Nothing is due right now. Practise all cards, or add cards at the next level." : "Add cards at this level, or choose another filter.";
        return;
      }
      state.flipped = false;
      $("[data-card-level]").textContent = `Level ${card.difficulty} · ${levelNames[card.difficulty]}`;
      $("[data-card-level]").dataset.level = String(card.difficulty);
      $("[data-card-progress]").textContent = `${state.index + 1} of ${state.queue.length}`;
      $("[data-card-question]").textContent = card.question;
      $("[data-card-answer]").value = card.my_answer || "";
      $("[data-card-points]").replaceChildren(...(card.key_points.length ? card.key_points : ["No key points — rely on your own example."]).map((point) => el("li", "", point)));
      $("[data-card-back]").hidden = true; $("[data-flip]").hidden = false;
      $("[data-save-answer]").textContent = "Save my answer to the application's Answers";
    }
    function flip() { if (!state.queue[state.index] || state.flipped) return; state.flipped = true; $("[data-card-back]").hidden = false; $("[data-flip]").hidden = true; $('[data-rate="good"]').focus(); }

    async function rate(rating) {
      const card = state.queue[state.index]; if (!card || !state.flipped) return;
      setError("");
      try {
        const payload = await api(`/api/applications/${state.applicationId}/practice/${card.id}/review`, { method: "POST", ...json({ rating, my_answer: $("[data-card-answer]").value }) });
        applyDeck(payload); renderStats();
        if (rating === "again") state.queue.push(payload.card);
        state.queue[state.index] = payload.card; state.index += 1;
        if (state.index >= state.queue.length) buildQueue();
        renderCard();
      } catch (error) { setError(error.message); }
    }

    async function load(applicationId) {
      state.applicationId = applicationId || "";
      setError(""); setNotice("");
      if (!state.applicationId) { $("[data-practice-body]").hidden = true; return; }
      applyDeck(await api(`/api/applications/${state.applicationId}/practice`));
      $("[data-practice-body]").hidden = false;
      renderStats(); buildQueue(); renderCard();
    }

    $("[data-generate-level]").addEventListener("change", (event) => { event.target.dataset.touched = "true"; });
    $("[data-generate]").addEventListener("click", async (event) => {
      const button = event.currentTarget; const label = button.textContent; button.disabled = true; button.textContent = "Writing cards…"; setError("");
      try {
        const payload = await api(`/api/applications/${state.applicationId}/practice/generate`, { method: "POST", ...json({ difficulty: Number($("[data-generate-level]").value), count: 5 }) });
        applyDeck(payload); renderStats();
        setNotice(payload.notice || (payload.added ? `Added ${payload.added} new card${payload.added === 1 ? "" : "s"}.` : "No new cards — the deck already covers these questions. Try another level."));
        state.filter = "due"; $$("[data-filter]").forEach((item) => item.classList.toggle("active", item.dataset.filter === "due"));
        buildQueue(); renderCard();
      } catch (error) { setError(error.message); }
      finally { button.disabled = false; button.textContent = label; }
    });
    $$("[data-filter]").forEach((button) => button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      $$("[data-filter]").forEach((item) => item.classList.toggle("active", item === button));
      buildQueue(); renderCard();
    }));
    $("[data-flip]").addEventListener("click", flip);
    $$("[data-rate]").forEach((button) => button.addEventListener("click", () => rate(button.dataset.rate)));
    $("[data-save-answer]").addEventListener("click", async (event) => {
      const card = state.queue[state.index]; const answer = $("[data-card-answer]").value.trim();
      if (!card) return;
      if (!answer) { setError("Write your answer first."); return; }
      const button = event.currentTarget;
      try {
        await api(`/api/applications/${state.applicationId}/answers`, { method: "POST", ...json({ question: card.question.slice(0, 300), answer, source: "interview" }) });
        button.textContent = "Saved to Answers";
        root.dispatchEvent(new CustomEvent("practice:answer-saved", { bubbles: true }));
      } catch (error) { setError(error.message); }
    });
    $("[data-delete-card]").addEventListener("click", async () => {
      const card = state.queue[state.index]; if (!card || !window.confirm("Delete this card?")) return;
      try {
        applyDeck(await api(`/api/applications/${state.applicationId}/practice/${card.id}`, { method: "DELETE" }));
        state.queue.splice(state.index, 1); if (state.index >= state.queue.length) buildQueue();
        renderStats(); renderCard();
      } catch (error) { setError(error.message); }
    });
    document.addEventListener("keydown", (event) => {
      if ($("[data-flashcard]").hidden || !root.offsetParent || event.target.closest("textarea, input, select")) return;
      if (event.key === " " && !state.flipped) { event.preventDefault(); flip(); }
      const ratings = { 1: "again", 2: "hard", 3: "good", 4: "easy" };
      if (state.flipped && ratings[event.key]) { event.preventDefault(); rate(ratings[event.key]); }
    });

    return { load, setError };
  }

  return { mount };
})();
