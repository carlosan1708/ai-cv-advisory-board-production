(() => {
  const panels = [...document.querySelectorAll("[data-step-panel]")];
  const indicators = [...document.querySelectorAll("[data-step-indicator]")];

  const setIndicatorState = (activeStep) => {
    indicators.forEach((indicator) => {
      const value = Number(indicator.dataset.stepIndicator);
      indicator.classList.toggle("active", value === activeStep);
      indicator.classList.toggle("complete", value < activeStep);
      if (value === activeStep) {
        indicator.setAttribute("aria-current", "step");
      } else {
        indicator.removeAttribute("aria-current");
      }
    });
  };

  const showStep = (step) => {
    const stepNumber = Number(step);
    panels.forEach((panel) => panel.classList.toggle("visible", Number(panel.dataset.stepPanel) === stepNumber));
    setIndicatorState(stepNumber);
    document.querySelector(`[data-step-panel="${step}"] h2`)?.focus({ preventScroll: true });
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

  document.querySelectorAll("[data-char-count]").forEach((counter) => {
    const input = document.getElementById(counter.dataset.charCount);
    if (!input) return;
    const update = () => { counter.textContent = input.value.length.toLocaleString(); };
    update();
    input.addEventListener("input", update);
  });

  const reviewForm = document.querySelector("[data-testid='guided-form']");
  reviewForm?.addEventListener("submit", () => {
    const submitButton = reviewForm.querySelector("[data-testid='analyze-button']");
    if (!submitButton || !reviewForm.checkValidity()) return;
    submitButton.setAttribute("aria-busy", "true");
    submitButton.textContent = "Running board review...";
  });

  document.querySelectorAll("[data-download-json]").forEach((button) => {
    button.addEventListener("click", () => {
      const source = document.querySelector("[data-testid='json-result']");
      if (!source) return;
      const blob = new Blob([source.textContent], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = button.dataset.downloadJson || "assessment.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    });
  });
})();
