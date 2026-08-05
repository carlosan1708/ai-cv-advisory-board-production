(() => {
  const panels = [...document.querySelectorAll("[data-step-panel]")];
  const indicators = [...document.querySelectorAll("[data-step-indicator]")];
  if (!panels.length) return;

  const showStep = (step) => {
    panels.forEach((panel) => panel.classList.toggle("visible", panel.dataset.stepPanel === step));
    indicators.forEach((indicator) => {
      const value = Number(indicator.dataset.stepIndicator);
      indicator.classList.toggle("active", value === Number(step));
      indicator.classList.toggle("complete", value < Number(step));
    });
    document.querySelector(`[data-step-panel="${step}"] h1`)?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  document.querySelectorAll("[data-next-step]").forEach((button) => {
    button.addEventListener("click", () => {
      const currentPanel = button.closest("[data-step-panel]");
      const required = currentPanel?.querySelector("textarea[required]");
      if (required && !required.value.trim()) {
        required.setCustomValidity("Paste your CV content before continuing.");
        required.reportValidity();
        required.addEventListener("input", () => required.setCustomValidity(""), { once: true });
        return;
      }
      showStep(button.dataset.nextStep);
    });
  });

  document.querySelectorAll("[data-previous-step]").forEach((button) => {
    button.addEventListener("click", () => showStep(button.dataset.previousStep));
  });
})();
