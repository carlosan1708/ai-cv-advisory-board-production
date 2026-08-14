(() => {
  const panels = [...document.querySelectorAll("[data-step-panel]")];
  const indicators = [...document.querySelectorAll("[data-step-indicator]")];
  const reviewForm = document.querySelector("[data-testid='guided-form']");
  const fileInput = document.querySelector("[data-testid='cv-file-input']");
  const uploadZone = document.querySelector("[data-upload-zone]");
  const uploadSelection = document.querySelector("[data-upload-selection]");
  const fileName = document.querySelector("[data-file-name]");
  const fileSize = document.querySelector("[data-file-size]");
  const changeFileButton = document.querySelector("[data-change-file]");
  const uploadError = document.querySelector("[data-upload-error]");
  const cvText = document.querySelector("[data-testid='cv-input']");
  const jobUrl = document.querySelector("[data-testid='job-url-input']");
  const jobText = document.querySelector("[data-testid='job-input']");
  const sourceError = document.querySelector("[data-source-error]");
  const advisorInputs = [...document.querySelectorAll("[data-advisor-option]")];
  const advisorIds = document.querySelector("[data-advisor-ids]");
  const advisorCount = document.querySelector("[data-advisor-count]");
  const advisorError = document.querySelector("[data-advisor-error]");
  const analysisOverlay = document.querySelector("[data-analysis-overlay]");
  const maximumFileSize = 5 * 1024 * 1024;

  const humanFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const fileValidationMessage = (file) => {
    if (!file) return "";
    const extension = file.name.split(".").pop()?.toLowerCase();
    if (!["pdf", "txt"].includes(extension)) return "Choose a PDF or TXT CV.";
    if (file.size > maximumFileSize) return "Choose a CV smaller than 5 MB.";
    if (file.size === 0) return "That file is empty. Choose another CV.";
    return "";
  };

  const renderSelectedFile = (file) => {
    const message = fileValidationMessage(file);
    if (uploadError) uploadError.textContent = message;
    if (message || !file) {
      if (fileInput && message) fileInput.value = "";
      uploadZone?.removeAttribute("hidden");
      if (uploadSelection) uploadSelection.hidden = true;
      return false;
    }
    if (fileName) fileName.textContent = file.name;
    if (fileSize) fileSize.textContent = humanFileSize(file.size);
    uploadZone?.setAttribute("hidden", "");
    if (uploadSelection) uploadSelection.hidden = false;
    return true;
  };

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
      const nextStep = Number(button.dataset.nextStep);
      if (nextStep === 2) {
        const selectedFile = fileInput?.files?.[0];
        if (selectedFile && !renderSelectedFile(selectedFile)) return;
        if (!selectedFile && !cvText?.value.trim()) {
          if (uploadError) uploadError.textContent = "Upload a PDF or TXT CV, or open the fallback to paste its text.";
          fileInput?.focus();
          return;
        }
      }
      if (nextStep === 3 && !validateTarget()) return;
      showStep(nextStep);
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

  fileInput?.addEventListener("change", () => renderSelectedFile(fileInput.files?.[0]));
  changeFileButton?.addEventListener("click", () => fileInput?.click());
  cvText?.addEventListener("input", () => {
    if (uploadError && cvText.value.trim()) uploadError.textContent = "";
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    uploadZone?.addEventListener(eventName, (event) => {
      event.preventDefault();
      uploadZone.classList.add("dragging");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    uploadZone?.addEventListener(eventName, (event) => {
      event.preventDefault();
      uploadZone.classList.remove("dragging");
    });
  });
  uploadZone?.addEventListener("drop", (event) => {
    const droppedFile = event.dataTransfer?.files?.[0];
    if (!droppedFile || !renderSelectedFile(droppedFile) || !fileInput) return;
    const transfer = new DataTransfer();
    transfer.items.add(droppedFile);
    fileInput.files = transfer.files;
  });

  const validateTarget = () => {
    const manualDescription = jobText?.value.trim() || "";
    const url = jobUrl?.value.trim() || "";
    if (sourceError) sourceError.textContent = "";
    if (manualDescription) return true;
    if (!url) {
      if (sourceError) sourceError.textContent = "Add a public job link, or open the fallback to paste the description.";
      jobUrl?.focus();
      return false;
    }
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== "https:") throw new Error("unsupported protocol");
    } catch (_) {
      if (sourceError) sourceError.textContent = "Enter a complete HTTPS job link, such as https://company.com/jobs/role.";
      jobUrl?.focus();
      return false;
    }
    return true;
  };

  jobUrl?.addEventListener("input", () => { if (sourceError) sourceError.textContent = ""; });
  jobText?.addEventListener("input", () => { if (sourceError) sourceError.textContent = ""; });

  const selectedAdvisorInputs = () => advisorInputs.filter((input) => input.checked);
  const renderAdvisorSelection = () => {
    const selected = selectedAdvisorInputs();
    advisorInputs.forEach((input) => {
      const option = input.closest(".advisor-option");
      option?.classList.toggle("selected", input.checked);
      const blocked = selected.length >= 3 && !input.checked;
      input.disabled = blocked;
      option?.classList.toggle("disabled", blocked);
    });
    if (advisorIds) advisorIds.value = selected.map((input) => input.value).join(",");
    if (advisorCount) advisorCount.textContent = String(selected.length);
    if (advisorError && selected.length) advisorError.textContent = "";
  };
  advisorInputs.forEach((input) => input.addEventListener("change", renderAdvisorSelection));
  renderAdvisorSelection();

  const showAnalysisProgress = () => {
    if (!analysisOverlay || !reviewForm) return;
    const layout = reviewForm.closest(".document-review-layout");
    const advisors = analysisOverlay.querySelector("[data-analysis-advisors]");
    const selected = selectedAdvisorInputs();
    advisors?.replaceChildren(...selected.map((input) => {
      const chip = document.createElement("span");
      chip.textContent = input.closest(".advisor-option")?.querySelector("strong")?.textContent || "Advisor";
      return chip;
    }));
    reviewForm.hidden = true;
    analysisOverlay.hidden = false;
    layout?.classList.add("is-analyzing");
    setIndicatorState(4);
    const stages = [
      ["Reading your source documents…", "The board is mapping the role to claims that are actually present in your CV."],
      ["Your specialists are reviewing…", "Each advisor is applying a different professional lens to the same evidence."],
      ["Building a grounded action plan…", "The chair is combining the findings into safe tailoring moves and interview preparation."],
    ];
    let index = 0;
    const title = analysisOverlay.querySelector("[data-analysis-title]");
    const copy = analysisOverlay.querySelector("[data-analysis-copy]");
    const chips = [...analysisOverlay.querySelectorAll("[data-analysis-advisors] span")];
    const advance = () => {
      const stage = stages[index % stages.length];
      if (title) title.textContent = stage[0];
      if (copy) copy.textContent = stage[1];
      chips.forEach((chip, chipIndex) => chip.classList.toggle("active", chipIndex === index % Math.max(1, chips.length)));
      index += 1;
    };
    advance();
    window.setInterval(advance, 2600);
  };

  reviewForm?.addEventListener("submit", (event) => {
    if (!validateTarget()) {
      event.preventDefault();
      return;
    }
    if (!selectedAdvisorInputs().length) {
      event.preventDefault();
      if (advisorError) advisorError.textContent = "Choose at least one advisor for the board review.";
      showStep(3);
      return;
    }
    const submitButton = reviewForm.querySelector("[data-testid='analyze-button']");
    if (!submitButton) return;
    submitButton.setAttribute("aria-busy", "true");
    submitButton.textContent = "Starting your board…";
    showAnalysisProgress();
  });

  const visiblePanel = panels.find((panel) => panel.classList.contains("visible"));
  if (visiblePanel) setIndicatorState(Number(visiblePanel.dataset.stepPanel));

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
