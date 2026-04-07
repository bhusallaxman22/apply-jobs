const state = {
  profiles: [],
  sources: [],
  jobs: [],
  runs: [],
  selectedProfileId: null,
  selectedLogRunId: null,
  selectedLogScreenshotIndex: null,
  selectedReviewRunId: null,
  selectedJobIds: new Set(),
  reviewNotesDrafts: {},
  filters: {
    titleQuery: "",
    locationQuery: "",
    companyQuery: "",
    sourceId: "all",
    availability: "open",
    status: "all",
  },
  sort: {
    key: "updated_at",
    direction: "desc",
  },
  pagination: {
    page: 1,
    pageSize: 25,
  },
};

const PROFILE_SETTING_DEFAULTS = Object.freeze({
  currentEmployee: "No",
  gender: "Male",
  hispanicLatino: "No - Not Hispanic or Latino",
  ethnicity: "Asian",
  veteranStatus: "",
  disabilityStatus: "",
});

const els = {
  refreshButton: document.getElementById("refreshButton"),
  connectionPill: document.getElementById("connectionPill"),
  profileForm: document.getElementById("profileForm"),
  profileNameInput: document.getElementById("profileNameInput"),
  fullNameInput: document.getElementById("fullNameInput"),
  emailInput: document.getElementById("emailInput"),
  phoneInput: document.getElementById("phoneInput"),
  locationInput: document.getElementById("locationInput"),
  countryInput: document.getElementById("countryInput"),
  linkedinInput: document.getElementById("linkedinInput"),
  resumeFileInput: document.getElementById("resumeFileInput"),
  resumeMarkdownInput: document.getElementById("resumeMarkdownInput"),
  currentEmployeeInput: document.getElementById("currentEmployeeInput"),
  genderInput: document.getElementById("genderInput"),
  hispanicInput: document.getElementById("hispanicInput"),
  ethnicityInput: document.getElementById("ethnicityInput"),
  veteranInput: document.getElementById("veteranInput"),
  disabilityInput: document.getElementById("disabilityInput"),
  profilesCount: document.getElementById("profilesCount"),
  profileSelect: document.getElementById("profileSelect"),
  profileDetails: document.getElementById("profileDetails"),
  profileSettingsForm: document.getElementById("profileSettingsForm"),
  profileCurrentEmployeeInput: document.getElementById("profileCurrentEmployeeInput"),
  profileGenderInput: document.getElementById("profileGenderInput"),
  profileHispanicInput: document.getElementById("profileHispanicInput"),
  profileEthnicityInput: document.getElementById("profileEthnicityInput"),
  profileVeteranInput: document.getElementById("profileVeteranInput"),
  profileDisabilityInput: document.getElementById("profileDisabilityInput"),
  saveProfileSettingsButton: document.getElementById("saveProfileSettingsButton"),
  answerBankCount: document.getElementById("answerBankCount"),
  answerForm: document.getElementById("answerForm"),
  answerPromptInput: document.getElementById("answerPromptInput"),
  answerValueInput: document.getElementById("answerValueInput"),
  answerSafeInput: document.getElementById("answerSafeInput"),
  answerList: document.getElementById("answerList"),
  sourceForm: document.getElementById("sourceForm"),
  sourceUrlInput: document.getElementById("sourceUrlInput"),
  sourceNameInput: document.getElementById("sourceNameInput"),
  sourceList: document.getElementById("sourceList"),
  syncAllButton: document.getElementById("syncAllButton"),
  statsGrid: document.getElementById("statsGrid"),
  runList: document.getElementById("runList"),
  titleSearchInput: document.getElementById("titleSearchInput"),
  locationSearchInput: document.getElementById("locationSearchInput"),
  companySearchInput: document.getElementById("companySearchInput"),
  sourceFilter: document.getElementById("sourceFilter"),
  availabilityFilter: document.getElementById("availabilityFilter"),
  statusFilter: document.getElementById("statusFilter"),
  selectVisibleButton: document.getElementById("selectVisibleButton"),
  clearSelectionButton: document.getElementById("clearSelectionButton"),
  applySelectedButton: document.getElementById("applySelectedButton"),
  selectAllCheckbox: document.getElementById("selectAllCheckbox"),
  jobsSummary: document.getElementById("jobsSummary"),
  jobsTableBody: document.getElementById("jobsTableBody"),
  batchResult: document.getElementById("batchResult"),
  pageSizeSelect: document.getElementById("pageSizeSelect"),
  paginationSummary: document.getElementById("paginationSummary"),
  previousPageButton: document.getElementById("previousPageButton"),
  nextPageButton: document.getElementById("nextPageButton"),
  logDeskSection: document.getElementById("logDeskSection"),
  logSummary: document.getElementById("logSummary"),
  logRunSelect: document.getElementById("logRunSelect"),
  logEmptyState: document.getElementById("logEmptyState"),
  logContent: document.getElementById("logContent"),
  logMeta: document.getElementById("logMeta"),
  openLogJobLink: document.getElementById("openLogJobLink"),
  openLogScreenshotLink: document.getElementById("openLogScreenshotLink"),
  logCheckpointList: document.getElementById("logCheckpointList"),
  logScreenshot: document.getElementById("logScreenshot"),
  logScreenshotEmpty: document.getElementById("logScreenshotEmpty"),
  logTimeline: document.getElementById("logTimeline"),
  reviewDeskSection: document.getElementById("reviewDeskSection"),
  reviewSummary: document.getElementById("reviewSummary"),
  reviewRunSelect: document.getElementById("reviewRunSelect"),
  reviewEmptyState: document.getElementById("reviewEmptyState"),
  reviewContent: document.getElementById("reviewContent"),
  reviewNotesInput: document.getElementById("reviewNotesInput"),
  approveReviewButton: document.getElementById("approveReviewButton"),
  rejectReviewButton: document.getElementById("rejectReviewButton"),
  openReviewJobLink: document.getElementById("openReviewJobLink"),
  openReviewLiveBrowserLink: document.getElementById("openReviewLiveBrowserLink"),
  openReviewResumeLink: document.getElementById("openReviewResumeLink"),
  openReviewScreenshotLink: document.getElementById("openReviewScreenshotLink"),
  reviewMeta: document.getElementById("reviewMeta"),
  reviewQuestions: document.getElementById("reviewQuestions"),
  reviewFields: document.getElementById("reviewFields"),
  reviewScreenshot: document.getElementById("reviewScreenshot"),
  reviewScreenshotEmpty: document.getElementById("reviewScreenshotEmpty"),
  reviewResumeEmpty: document.getElementById("reviewResumeEmpty"),
  reviewResumePreview: document.getElementById("reviewResumePreview"),
};

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await loadDashboardData();
  window.setInterval(() => {
    loadDashboardData({ silent: true }).catch(() => {});
  }, 10000);
});

function bindEvents() {
  els.refreshButton.addEventListener("click", () => loadDashboardData());
  els.profileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await createProfileFromForm();
  });
  els.profileSettingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveActiveProfileSettings();
  });
  els.answerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await createAnswerEntry();
  });
  els.profileSelect.addEventListener("change", async (event) => {
    state.selectedProfileId = event.target.value || null;
    state.selectedReviewRunId = null;
    state.selectedJobIds.clear();
    await loadRuns();
    renderDashboard();
  });

  els.titleSearchInput.addEventListener("input", (event) => {
    state.filters.titleQuery = event.target.value.trim().toLowerCase();
    state.pagination.page = 1;
    renderDashboard();
  });
  els.locationSearchInput.addEventListener("input", (event) => {
    state.filters.locationQuery = event.target.value.trim().toLowerCase();
    state.pagination.page = 1;
    renderDashboard();
  });
  els.companySearchInput.addEventListener("input", (event) => {
    state.filters.companyQuery = event.target.value.trim().toLowerCase();
    state.pagination.page = 1;
    renderDashboard();
  });
  els.sourceFilter.addEventListener("change", (event) => {
    state.filters.sourceId = event.target.value;
    state.pagination.page = 1;
    renderDashboard();
  });
  els.availabilityFilter.addEventListener("change", (event) => {
    state.filters.availability = event.target.value;
    state.pagination.page = 1;
    renderDashboard();
  });
  els.statusFilter.addEventListener("change", (event) => {
    state.filters.status = event.target.value;
    state.pagination.page = 1;
    renderDashboard();
  });

  els.selectVisibleButton.addEventListener("click", () => {
    const latestRuns = getLatestRunMap();
    for (const job of getPaginatedJobs()) {
      if (isRunnableJob(job, latestRuns)) {
        state.selectedJobIds.add(job.id);
      }
    }
    renderDashboard();
  });

  els.clearSelectionButton.addEventListener("click", () => {
    state.selectedJobIds.clear();
    renderDashboard();
  });

  els.selectAllCheckbox.addEventListener("change", (event) => {
    if (event.target.checked) {
      for (const job of getPaginatedJobs()) {
        if (isRunnableJob(job)) {
          state.selectedJobIds.add(job.id);
        }
      }
    } else {
      for (const job of getPaginatedJobs()) {
        state.selectedJobIds.delete(job.id);
      }
    }
    renderDashboard();
  });

  els.applySelectedButton.addEventListener("click", async () => {
    await queueSelectedJobs([...state.selectedJobIds]);
  });
  els.pageSizeSelect.addEventListener("change", (event) => {
    state.pagination.pageSize = Number(event.target.value) || 25;
    state.pagination.page = 1;
    renderDashboard();
  });
  els.previousPageButton.addEventListener("click", () => {
    state.pagination.page = Math.max(1, state.pagination.page - 1);
    renderDashboard();
  });
  els.nextPageButton.addEventListener("click", () => {
    const totalPages = getPaginationMeta().totalPages;
    state.pagination.page = Math.min(totalPages, state.pagination.page + 1);
    renderDashboard();
  });

  els.logRunSelect.addEventListener("change", (event) => {
    selectLogRun(event.target.value || null);
  });

  els.reviewRunSelect.addEventListener("change", (event) => {
    selectReviewRun(event.target.value || null);
  });
  els.reviewNotesInput.addEventListener("input", (event) => {
    if (!state.selectedReviewRunId) {
      return;
    }
    state.reviewNotesDrafts[state.selectedReviewRunId] = event.target.value;
  });
  els.approveReviewButton.addEventListener("click", async () => {
    await submitReviewDecision("approve");
  });
  els.rejectReviewButton.addEventListener("click", async () => {
    await submitReviewDecision("reject");
  });

  els.syncAllButton.addEventListener("click", async () => {
    if (!state.sources.length) {
      setBatchMessage("Add a source before running sync.", "warning");
      return;
    }
    for (const source of state.sources) {
      await syncSource(source.id, { refreshAfter: false });
    }
    await loadDashboardData();
  });

  els.sourceForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const sourceUrl = els.sourceUrlInput.value.trim();
    const name = els.sourceNameInput.value.trim();
    if (!sourceUrl) {
      return;
    }
    try {
      setConnectionState("Adding source…");
      await fetchJson("/sources", {
        method: "POST",
        body: JSON.stringify({
          source_url: sourceUrl,
          name: name || null,
          auto_sync: true,
        }),
      });
      els.sourceForm.reset();
      await loadDashboardData();
      setBatchMessage("Source added and synced.", "success");
    } catch (error) {
      setBatchMessage(getErrorMessage(error), "error");
      setConnectionState("Failed to add source");
    }
  });

  document.querySelectorAll("[data-sort-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.sortKey;
      if (state.sort.key === key) {
        state.sort.direction = state.sort.direction === "asc" ? "desc" : "asc";
      } else {
        state.sort.key = key;
        state.sort.direction = key === "updated_at" ? "desc" : "asc";
      }
      state.pagination.page = 1;
      renderDashboard();
    });
  });
}

async function loadDashboardData({ silent = false } = {}) {
  if (!silent) {
    setConnectionState("Refreshing data…");
  }

  try {
    const [profiles, sources, jobs] = await Promise.all([
      fetchJson("/profiles"),
      fetchJson("/sources"),
      fetchJson("/jobs"),
    ]);

    state.profiles = profiles;
    state.sources = sources;
    state.jobs = jobs;

    if (!state.selectedProfileId || !profiles.some((profile) => profile.id === state.selectedProfileId)) {
      state.selectedProfileId = profiles[0]?.id ?? null;
    }

    state.selectedJobIds = new Set([...state.selectedJobIds].filter((jobId) => jobs.some((job) => job.id === jobId)));
    clampPagination(getFilteredJobs().length);
    await loadRuns();
    renderDashboard();
    setConnectionState(`Synced ${formatDate(new Date().toISOString(), true)}`);
  } catch (error) {
    renderDashboard();
    setConnectionState("Dashboard refresh failed");
    setBatchMessage(getErrorMessage(error), "error");
  }
}

async function loadRuns() {
  const url = state.selectedProfileId ? `/runs?profile_id=${encodeURIComponent(state.selectedProfileId)}` : "/runs";
  state.runs = await fetchJson(url);
  syncSelectedLogRun();
  syncSelectedReviewRun();
}

async function queueSelectedJobs(jobIds) {
  if (!state.selectedProfileId) {
    setBatchMessage("Choose a resume profile before queueing jobs.", "warning");
    return;
  }
  if (!jobIds.length) {
    setBatchMessage("Select at least one job first.", "warning");
    return;
  }

  try {
    setConnectionState("Queueing selected jobs…");
    const result = await fetchJson("/runs/bulk", {
      method: "POST",
      body: JSON.stringify({
        profile_id: state.selectedProfileId,
        job_ids: jobIds,
      }),
    });
    const succeeded = result.created_count;
    const skipped = result.skipped_count;
    for (const run of result.created_runs) {
      state.selectedJobIds.delete(run.job_id);
    }
    await loadRuns();
    renderDashboard();
    setBatchMessage(`Queued ${succeeded} job${succeeded === 1 ? "" : "s"}${skipped ? `, skipped ${skipped}.` : "."}`, "success");
    setConnectionState(`Queued ${succeeded} job${succeeded === 1 ? "" : "s"}`);
  } catch (error) {
    setBatchMessage(getErrorMessage(error), "error");
    setConnectionState("Queue request failed");
  }
}

async function submitReviewDecision(decision) {
  const selectedRun = getSelectedReviewRun();
  if (!selectedRun) {
    setBatchMessage("Choose a review run first.", "warning");
    return;
  }

  const runStatus = normalizeStatus(selectedRun.status);
  const resumeCaptcha = runStatus === "captcha_required" && decision === "approve";
  const notes = els.reviewNotesInput.value.trim();
  state.reviewNotesDrafts[selectedRun.id] = notes;

  try {
    setConnectionState(
      resumeCaptcha
        ? "Signaling CAPTCHA resume..."
        : decision === "approve"
          ? "Starting approved submission..."
          : "Rejecting review...",
    );
    const endpoint = resumeCaptcha
      ? `/runs/${encodeURIComponent(selectedRun.id)}/captcha/resume`
      : `/runs/${encodeURIComponent(selectedRun.id)}/${decision}`;
    await fetchJson(endpoint, {
      method: "POST",
      body: JSON.stringify({ notes: notes || null }),
    });
    await loadRuns();
    renderDashboard();
    setBatchMessage(
      resumeCaptcha
        ? "Resume signal sent. Solve the challenge in the live browser, then wait for the run to continue."
        : decision === "approve"
          ? "Review approved. Automatic submission started."
          : "Review rejected. You can update the profile and queue again.",
      resumeCaptcha || decision === "approve" ? "success" : "warning",
    );
    setConnectionState(
      resumeCaptcha
        ? "CAPTCHA resume requested"
        : decision === "approve"
          ? "Approved submission queued"
          : "Review rejected",
    );
  } catch (error) {
    setBatchMessage(getErrorMessage(error), "error");
    setConnectionState("Review decision failed");
  }
}

async function createProfileFromForm() {
  const profileName = els.profileNameInput.value.trim();
  if (!profileName) {
    setBatchMessage("Profile label is required.", "warning");
    return;
  }

  const payload = {
    name: profileName,
    data: buildCreatedProfileData(),
    answers: [],
  };

  try {
    setConnectionState("Creating profile…");
    const createdProfile = await fetchJson("/profiles", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    const resumeFile = els.resumeFileInput.files?.[0];
    const markdownFile = els.resumeMarkdownInput.files?.[0];
    if (resumeFile) {
      const formData = new FormData();
      formData.append("resume", resumeFile);
      if (markdownFile) {
        formData.append("resume_markdown", markdownFile);
      }
      await fetchMultipart(`/profiles/${encodeURIComponent(createdProfile.id)}/resume`, formData);
    }

    els.profileForm.reset();
    state.selectedProfileId = createdProfile.id;
    await loadDashboardData();
    setBatchMessage("Profile created successfully.", "success");
  } catch (error) {
    setBatchMessage(getErrorMessage(error), "error");
    setConnectionState("Profile creation failed");
  }
}

function buildCreatedProfileData() {
  return (
    pruneEmptyData({
      identity: {
        full_name: valueOrNull(els.fullNameInput.value),
        email: valueOrNull(els.emailInput.value),
        phone: valueOrNull(els.phoneInput.value),
        location: valueOrNull(els.locationInput.value),
        country: valueOrNull(els.countryInput.value),
        linkedin: valueOrNull(els.linkedinInput.value),
      },
      application_preferences: {
        current_employee: valueOrNull(els.currentEmployeeInput.value),
      },
      eeo: {
        gender: valueOrNull(els.genderInput.value),
        hispanic_latino: valueOrNull(els.hispanicInput.value),
        ethnicity: valueOrNull(els.ethnicityInput.value),
        veteran_status: valueOrNull(els.veteranInput.value),
        disability_status: valueOrNull(els.disabilityInput.value),
      },
    }) || {}
  );
}

async function saveActiveProfileSettings() {
  const profile = getActiveProfile();
  if (!profile) {
    setBatchMessage("Choose a profile before saving profile settings.", "warning");
    return;
  }

  try {
    setConnectionState("Saving profile settings…");
    await fetchJson(`/profiles/${encodeURIComponent(profile.id)}`, {
      method: "PUT",
      body: JSON.stringify({
        data: buildUpdatedProfileData(profile.data),
      }),
    });
    await loadDashboardData({ silent: true });
    setBatchMessage("Profile settings saved.", "success");
    setConnectionState("Profile settings updated");
  } catch (error) {
    setBatchMessage(getErrorMessage(error), "error");
    setConnectionState("Saving profile settings failed");
  }
}

function buildUpdatedProfileData(baseData = {}) {
  const nextData = deepClone(baseData);
  setNestedString(nextData, ["application_preferences", "current_employee"], valueOrNull(els.profileCurrentEmployeeInput.value));
  setNestedString(nextData, ["eeo", "gender"], valueOrNull(els.profileGenderInput.value));
  setNestedString(nextData, ["eeo", "hispanic_latino"], valueOrNull(els.profileHispanicInput.value));
  setNestedString(nextData, ["eeo", "ethnicity"], valueOrNull(els.profileEthnicityInput.value));
  setNestedString(nextData, ["eeo", "veteran_status"], valueOrNull(els.profileVeteranInput.value));
  setNestedString(nextData, ["eeo", "disability_status"], valueOrNull(els.profileDisabilityInput.value));
  return pruneEmptyData(nextData) || {};
}

async function createAnswerEntry() {
  const profile = getActiveProfile();
  if (!profile) {
    setBatchMessage("Choose a profile before adding answer-bank entries.", "warning");
    return;
  }

  const prompt = els.answerPromptInput.value.trim();
  const answer = els.answerValueInput.value.trim();
  if (!prompt || !answer) {
    setBatchMessage("Prompt and answer are required.", "warning");
    return;
  }

  try {
    setConnectionState("Saving answer bank entry…");
    await fetchJson(`/profiles/${encodeURIComponent(profile.id)}/answers`, {
      method: "POST",
      body: JSON.stringify({
        prompt,
        answer,
        safe_to_autofill: els.answerSafeInput.checked,
      }),
    });
    els.answerForm.reset();
    els.answerSafeInput.checked = true;
    await loadDashboardData({ silent: true });
    setBatchMessage("Answer bank entry saved.", "success");
    setConnectionState("Answer bank updated");
  } catch (error) {
    setBatchMessage(getErrorMessage(error), "error");
    setConnectionState("Saving answer failed");
  }
}

async function updateAnswerEntry(answerId, payload) {
  const profile = getActiveProfile();
  if (!profile) {
    setBatchMessage("Choose a profile before editing answer-bank entries.", "warning");
    return;
  }

  try {
    setConnectionState("Updating answer bank entry…");
    await fetchJson(`/profiles/${encodeURIComponent(profile.id)}/answers/${encodeURIComponent(answerId)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    await loadDashboardData({ silent: true });
    setBatchMessage("Answer bank entry updated.", "success");
    setConnectionState("Answer bank updated");
  } catch (error) {
    setBatchMessage(getErrorMessage(error), "error");
    setConnectionState("Updating answer failed");
  }
}

async function deleteAnswerEntry(answerId) {
  const profile = getActiveProfile();
  if (!profile) {
    setBatchMessage("Choose a profile before deleting answer-bank entries.", "warning");
    return;
  }

  try {
    setConnectionState("Deleting answer bank entry…");
    await fetchJson(`/profiles/${encodeURIComponent(profile.id)}/answers/${encodeURIComponent(answerId)}`, {
      method: "DELETE",
    });
    await loadDashboardData({ silent: true });
    setBatchMessage("Answer bank entry deleted.", "success");
    setConnectionState("Answer bank updated");
  } catch (error) {
    setBatchMessage(getErrorMessage(error), "error");
    setConnectionState("Deleting answer failed");
  }
}

async function saveReviewQuestionAnswer(prompt, answer, safeToAutofill = true) {
  const profile = getActiveProfile();
  if (!profile) {
    setBatchMessage("Choose a profile before saving answers.", "warning");
    return;
  }

  const normalizedPrompt = normalizePrompt(prompt);
  const existing = (profile.answers || []).find((entry) => normalizePrompt(entry.prompt) === normalizedPrompt);
  if (existing) {
    await updateAnswerEntry(existing.id, {
      prompt,
      answer,
      safe_to_autofill: safeToAutofill,
    });
    return;
  }

  await createAnswerEntryFromValues({
    prompt,
    answer,
    safeToAutofill,
  });
}

async function createAnswerEntryFromValues({ prompt, answer, safeToAutofill }) {
  const profile = getActiveProfile();
  if (!profile) {
    setBatchMessage("Choose a profile before adding answer-bank entries.", "warning");
    return;
  }

  try {
    setConnectionState("Saving answer bank entry…");
    await fetchJson(`/profiles/${encodeURIComponent(profile.id)}/answers`, {
      method: "POST",
      body: JSON.stringify({
        prompt,
        answer,
        safe_to_autofill: safeToAutofill,
      }),
    });
    await loadDashboardData({ silent: true });
    setBatchMessage("Answer bank entry saved.", "success");
    setConnectionState("Answer bank updated");
  } catch (error) {
    setBatchMessage(getErrorMessage(error), "error");
    setConnectionState("Saving answer failed");
  }
}

async function syncSource(sourceId, { refreshAfter = true } = {}) {
  try {
    setConnectionState("Syncing source…");
    await fetchJson(`/sources/${encodeURIComponent(sourceId)}/sync`, { method: "POST" });
    if (refreshAfter) {
      await loadDashboardData();
    }
  } catch (error) {
    setBatchMessage(getErrorMessage(error), "error");
    setConnectionState("Source sync failed");
  }
}

function renderDashboard() {
  clampPagination(getFilteredJobs().length);
  renderProfilePanel();
  renderAnswerBank();
  renderSourceFilter();
  renderSources();
  renderStats();
  renderRuns();
  renderJobs();
  renderPagination();
  renderLogDesk();
  renderReviewDesk();
  renderSortIndicators();
}

function renderProfilePanel() {
  els.profilesCount.textContent = `${state.profiles.length} profile${state.profiles.length === 1 ? "" : "s"}`;

  const options = state.profiles
    .map((profile) => {
      const selected = profile.id === state.selectedProfileId ? "selected" : "";
      return `<option value="${escapeHtml(profile.id)}" ${selected}>${escapeHtml(profile.name)}</option>`;
    })
    .join("");

  els.profileSelect.innerHTML = options || `<option value="">No profiles available</option>`;
  els.profileSelect.disabled = !state.profiles.length;

  const profile = getActiveProfile();
  if (!profile) {
    els.profileDetails.className = "profile-details empty-state";
    els.profileDetails.textContent = "Create a profile and upload a resume to enable applications.";
    setProfileSettingsFormDisabled(true);
    populateProfileSettingsForm();
    return;
  }

  const identity = profile.data?.identity || {};
  const documents = profile.data?.documents || {};
  const answersCount = Array.isArray(profile.answers) ? profile.answers.length : 0;
  const sourcePath = documents.resume_markdown_path || documents.resume_source_text_path || documents.resume_typst_path || "No source file";
  const resumePath = documents.resume_pdf || profile.resume_path || "No PDF uploaded";
  const disclosureSummary = formatDisclosureSummary(profile.data);

  els.profileDetails.className = "profile-details";
  els.profileDetails.innerHTML = `
    <div class="profile-card">
      <h3>${escapeHtml(profile.name)}</h3>
      <p>${escapeHtml(identity.email || "No email on file")} · ${escapeHtml(identity.phone || "No phone on file")}</p>
      <p>${escapeHtml(identity.location || "No location on file")}</p>
      <p class="mono-path">${escapeHtml(resumePath)}</p>
      <p class="mono-path">${escapeHtml(sourcePath)}</p>
      <p>${answersCount} saved answer${answersCount === 1 ? "" : "s"} available for autofill.</p>
      <p>${escapeHtml(disclosureSummary)}</p>
    </div>
  `;
  setProfileSettingsFormDisabled(false);
  populateProfileSettingsForm(profile.data);
}

function renderAnswerBank() {
  const profile = getActiveProfile();
  const answers = [...(profile?.answers || [])].sort((left, right) => new Date(right.updated_at) - new Date(left.updated_at));
  els.answerBankCount.textContent = `${answers.length} entr${answers.length === 1 ? "y" : "ies"}`;

  els.answerForm.querySelectorAll("input, textarea, button").forEach((element) => {
    element.disabled = !profile;
  });

  if (!profile) {
    els.answerList.className = "answer-list empty-state";
    els.answerList.textContent = "Choose a profile to manage saved answers.";
    return;
  }

  if (!answers.length) {
    els.answerList.className = "answer-list empty-state";
    els.answerList.textContent = "No saved answers yet. Add responses for long-form questions here.";
    return;
  }

  els.answerList.className = "answer-list";
  els.answerList.innerHTML = answers
    .map(
      (entry) => `
        <article class="answer-card" data-answer-id="${escapeHtml(entry.id)}">
          <div class="answer-card-header">
            <span class="badge badge-${entry.safe_to_autofill ? "approved" : "review"}">
              ${escapeHtml(entry.safe_to_autofill ? "safe" : "review")}
            </span>
            <span class="job-meta">Updated ${escapeHtml(formatDate(entry.updated_at, true))}</span>
          </div>
          <label class="field-label" for="answer-prompt-${escapeHtml(entry.id)}">Prompt</label>
          <textarea id="answer-prompt-${escapeHtml(entry.id)}" class="input answer-textarea" data-answer-field="prompt">${escapeHtml(entry.prompt)}</textarea>
          <label class="field-label" for="answer-value-${escapeHtml(entry.id)}">Answer</label>
          <textarea id="answer-value-${escapeHtml(entry.id)}" class="input answer-textarea answer-textarea-large" data-answer-field="answer">${escapeHtml(entry.answer)}</textarea>
          <label class="checkbox-row">
            <input type="checkbox" data-answer-field="safe" ${entry.safe_to_autofill ? "checked" : ""} />
            <span>Allow safe autofill</span>
          </label>
          <div class="answer-card-actions">
            <button class="button button-secondary small-button" type="button" data-answer-save="${escapeHtml(entry.id)}">Save</button>
            <button class="button button-secondary small-button danger-button" type="button" data-answer-delete="${escapeHtml(entry.id)}">Delete</button>
          </div>
        </article>
      `,
    )
    .join("");

  els.answerList.querySelectorAll("[data-answer-save]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest("[data-answer-id]");
      if (!card) {
        return;
      }
      const prompt = card.querySelector('[data-answer-field="prompt"]').value.trim();
      const answer = card.querySelector('[data-answer-field="answer"]').value.trim();
      const safeToAutofill = card.querySelector('[data-answer-field="safe"]').checked;
      if (!prompt || !answer) {
        setBatchMessage("Prompt and answer are required.", "warning");
        return;
      }
      await updateAnswerEntry(button.dataset.answerSave, {
        prompt,
        answer,
        safe_to_autofill: safeToAutofill,
      });
    });
  });

  els.answerList.querySelectorAll("[data-answer-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteAnswerEntry(button.dataset.answerDelete);
    });
  });
}

function renderSourceFilter() {
  const sourceOptions = [
    `<option value="all">All sources</option>`,
    `<option value="manual">Manual jobs</option>`,
    ...state.sources.map((source) => {
      const selected = source.id === state.filters.sourceId ? "selected" : "";
      return `<option value="${escapeHtml(source.id)}" ${selected}>${escapeHtml(source.name)}</option>`;
    }),
  ];
  els.sourceFilter.innerHTML = sourceOptions.join("");
  els.sourceFilter.value = state.filters.sourceId;
}

function renderSources() {
  if (!state.sources.length) {
    els.sourceList.className = "source-list empty-state";
    els.sourceList.textContent = "Add a Greenhouse or Lever board URL to start importing jobs.";
    return;
  }

  const sourceCards = state.sources
    .map((source) => {
      const openCount = state.jobs.filter((job) => job.source_id === source.id && job.availability === "open").length;
      return `
        <div class="source-card">
          <div class="source-card-header">
            <div>
              <h3>${escapeHtml(source.name)}</h3>
              <p>${escapeHtml(source.platform)} · ${openCount} open jobs</p>
            </div>
            <span class="badge badge-${escapeHtml(source.last_error ? "failed" : "open")}">${escapeHtml(source.last_error ? "error" : "ready")}</span>
          </div>
          <p>${escapeHtml(source.source_url || source.source_token)}</p>
          <p>${escapeHtml(source.last_sync_at ? `Last sync ${formatDate(source.last_sync_at, true)}` : "Never synced")}</p>
          <div class="source-card-actions">
            <button class="button button-secondary small-button" type="button" data-source-sync="${escapeHtml(source.id)}">Sync</button>
            <button class="button button-secondary small-button" type="button" data-source-filter="${escapeHtml(source.id)}">Filter</button>
          </div>
        </div>
      `;
    })
    .join("");

  els.sourceList.className = "source-list";
  els.sourceList.innerHTML = sourceCards;
  els.sourceList.querySelectorAll("[data-source-sync]").forEach((button) => {
    button.addEventListener("click", async () => {
      await syncSource(button.dataset.sourceSync);
    });
  });
  els.sourceList.querySelectorAll("[data-source-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      state.filters.sourceId = button.dataset.sourceFilter;
      state.pagination.page = 1;
      els.sourceFilter.value = state.filters.sourceId;
      renderDashboard();
    });
  });
}

function renderStats() {
  const filteredJobs = getFilteredJobs();
  const latestRuns = getLatestRunMap();
  const stats = [
    ["Open jobs", state.jobs.filter((job) => job.availability === "open").length],
    ["Filtered", filteredJobs.length],
    ["Selected", state.selectedJobIds.size],
    ["In progress", filteredJobs.filter((job) => ["queued", "running", "submitting"].includes(getApplyStatus(job, latestRuns))).length],
    ["Captcha blocked", filteredJobs.filter((job) => getApplyStatus(job, latestRuns) === "captcha_required").length],
    ["Needs review", filteredJobs.filter((job) => getApplyStatus(job, latestRuns) === "review").length],
    ["Done", filteredJobs.filter((job) => ["completed", "approved"].includes(getApplyStatus(job, latestRuns))).length],
    ["Failed", filteredJobs.filter((job) => ["failed", "rejected"].includes(getApplyStatus(job, latestRuns))).length],
    ["Ready", filteredJobs.filter((job) => isRunnableJob(job)).length],
  ];

  els.statsGrid.innerHTML = stats
    .map(
      ([label, value]) => `
        <div class="stat-card">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(String(value))}</strong>
        </div>
      `,
    )
    .join("");
}

function renderRuns() {
  if (!state.runs.length) {
    els.runList.className = "run-list empty-state";
    els.runList.textContent = state.selectedProfileId
      ? "No runs for the selected profile yet."
      : "Choose a resume profile to inspect run activity.";
    return;
  }

  const jobsById = new Map(state.jobs.map((job) => [job.id, job]));
  els.runList.className = "run-list";
  els.runList.innerHTML = state.runs
    .slice(0, 8)
    .map((run) => {
      const job = jobsById.get(run.job_id);
      const title = job?.title || job?.url || run.job_id;
      const actionButtons = [
        `<button class="button button-secondary small-button" type="button" data-log-run="${escapeHtml(run.id)}">Open log</button>`,
      ];
      if (["review", "captcha_required"].includes(normalizeStatus(run.status))) {
        actionButtons.push(
          `<button class="button button-secondary small-button" type="button" data-review-run="${escapeHtml(run.id)}">${
            normalizeStatus(run.status) === "captcha_required" ? "Solve CAPTCHA" : "Open review"
          }</button>`,
        );
      }
      return `
        <div class="run-card">
          <div class="run-card-header">
            <h3>${escapeHtml(title)}</h3>
            <span class="badge badge-${escapeHtml(normalizeStatus(run.status))}">${escapeHtml(run.status)}</span>
          </div>
          <p>${escapeHtml(job?.company || "Unknown company")} · ${escapeHtml(formatDate(run.updated_at, true))}</p>
          <div class="source-card-actions">${actionButtons.join("")}</div>
        </div>
      `;
    })
    .join("");

  els.runList.querySelectorAll("[data-log-run]").forEach((button) => {
    button.addEventListener("click", () => {
      selectLogRun(button.dataset.logRun);
      els.logDeskSection.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  els.runList.querySelectorAll("[data-review-run]").forEach((button) => {
    button.addEventListener("click", () => {
      selectReviewRun(button.dataset.reviewRun);
      els.reviewDeskSection.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function renderJobs() {
  const filteredJobs = getFilteredJobs();
  const paginatedJobs = getPaginatedJobs(filteredJobs);
  const latestRuns = getLatestRunMap();

  const selectedVisibleCount = paginatedJobs.filter((job) => state.selectedJobIds.has(job.id)).length;
  const runnableVisibleCount = paginatedJobs.filter((job) => isRunnableJob(job, latestRuns)).length;
  const allVisibleSelected = runnableVisibleCount > 0 && selectedVisibleCount === runnableVisibleCount;
  els.selectAllCheckbox.checked = allVisibleSelected;
  els.selectAllCheckbox.indeterminate = selectedVisibleCount > 0 && !allVisibleSelected;

  const profile = getActiveProfile();
  els.applySelectedButton.disabled = !profile || !state.selectedJobIds.size;
  const paginationMeta = getPaginationMeta(filteredJobs.length);
  els.jobsSummary.textContent = `${filteredJobs.length} jobs matched · page ${paginationMeta.page} of ${paginationMeta.totalPages} · ${state.selectedJobIds.size} selected · ${
    profile ? `applying with ${profile.name}` : "choose a resume profile"
  }`;

  if (!paginatedJobs.length) {
    els.jobsTableBody.innerHTML = `
      <tr>
        <td colspan="8">
        <div class="empty-state">No jobs match the current filters.</div>
        </td>
      </tr>
    `;
    return;
  }

  els.jobsTableBody.innerHTML = paginatedJobs
    .map((job) => {
      const latestRun = latestRuns.get(job.id);
      const applyStatus = getApplyStatus(job, latestRuns);
      const selected = state.selectedJobIds.has(job.id) ? "checked" : "";
      const disabled = !isRunnableJob(job, latestRuns) || !profile ? "disabled" : "";
      const company = job.company || "Unknown company";
      const location = job.location || "Location not specified";
      const sourceLabel = getSourceLabel(job);
      const title = job.title || job.url;
      const snippet = job.description || "";

      return `
        <tr>
          <td class="checkbox-cell">
            <input type="checkbox" data-job-select="${escapeHtml(job.id)}" ${selected} ${disabled} aria-label="Select ${escapeHtml(title)}" />
          </td>
          <td>
            <p class="job-title">${escapeHtml(title)}</p>
            <p class="job-snippet">${escapeHtml(snippet.slice(0, 180) || "No description imported.")}</p>
          </td>
          <td>
            <div class="stack">
              <span>${escapeHtml(company)}</span>
              ${
                job.employment_type
                  ? `<span class="job-meta">${escapeHtml(job.employment_type)}</span>`
                  : `<span class="job-meta">Employment type not listed</span>`
              }
            </div>
          </td>
          <td>${escapeHtml(location)}</td>
          <td>
            <div class="stack">
              <span class="badge badge-${escapeHtml(normalizeStatus(applyStatus))}">${escapeHtml(applyStatus)}</span>
              ${
                latestRun
                  ? `<span class="job-meta">${escapeHtml(formatDate(latestRun.updated_at, true))}</span>`
                  : `<span class="job-meta">No run yet</span>`
              }
            </div>
          </td>
          <td>
            <div class="stack">
              <span>${escapeHtml(sourceLabel)}</span>
              <span class="job-meta">${escapeHtml(job.platform)}</span>
            </div>
          </td>
          <td>${escapeHtml(formatDate(job.updated_at, true))}</td>
          <td>
            <div class="stack">
              <button class="button button-secondary small-button" type="button" data-run-job="${escapeHtml(job.id)}" ${disabled}>Queue</button>
              ${
                latestRun
                  ? `<button class="button button-secondary small-button" type="button" data-log-run="${escapeHtml(latestRun.id)}">Logs</button>`
                  : ""
              }
              ${
                latestRun && ["review", "captcha_required"].includes(applyStatus)
                  ? `<button class="button button-secondary small-button" type="button" data-review-run="${escapeHtml(latestRun.id)}">${
                      applyStatus === "captcha_required" ? "Solve" : "Review"
                    }</button>`
                  : ""
              }
              <a class="link" href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer">Open job</a>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");

  els.jobsTableBody.querySelectorAll("[data-job-select]").forEach((input) => {
    input.addEventListener("change", (event) => {
      const jobId = event.target.dataset.jobSelect;
      if (event.target.checked) {
        state.selectedJobIds.add(jobId);
      } else {
        state.selectedJobIds.delete(jobId);
      }
      renderDashboard();
    });
  });

  els.jobsTableBody.querySelectorAll("[data-run-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      await queueSelectedJobs([button.dataset.runJob]);
    });
  });

  els.jobsTableBody.querySelectorAll("[data-log-run]").forEach((button) => {
    button.addEventListener("click", () => {
      selectLogRun(button.dataset.logRun);
      els.logDeskSection.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  els.jobsTableBody.querySelectorAll("[data-review-run]").forEach((button) => {
    button.addEventListener("click", () => {
      selectReviewRun(button.dataset.reviewRun);
      els.reviewDeskSection.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function renderLogDesk() {
  const logRuns = getLogRuns();
  const activeCount = logRuns.filter((run) => ["queued", "running", "submitting", "captcha_required"].includes(normalizeStatus(run.status))).length;
  els.logSummary.textContent = logRuns.length
    ? `${logRuns.length} run${logRuns.length === 1 ? "" : "s"} available · ${activeCount} active.`
    : "No runs available.";

  if (!logRuns.length) {
    els.logRunSelect.innerHTML = `<option value="">No runs</option>`;
    els.logRunSelect.disabled = true;
    els.logEmptyState.hidden = false;
    els.logContent.hidden = true;
    els.logMeta.innerHTML = "";
    els.logCheckpointList.innerHTML = "";
    els.logTimeline.innerHTML = "";
    els.logScreenshot.removeAttribute("src");
    return;
  }

  const selectedRun = getSelectedLogRun();
  els.logRunSelect.innerHTML = logRuns
    .map((run) => {
      const selected = run.id === selectedRun?.id ? "selected" : "";
      return `<option value="${escapeHtml(run.id)}" ${selected}>${escapeHtml(formatReviewRunLabel(run))}</option>`;
    })
    .join("");
  els.logRunSelect.disabled = false;
  els.logEmptyState.hidden = true;
  els.logContent.hidden = false;

  if (!selectedRun) {
    return;
  }

  const job = getJobById(selectedRun.job_id);
  const jobTitle = job?.title || selectedRun.result?.page_title || selectedRun.job_id;
  const jobCompany = job?.company || selectedRun.result?.company || "Unknown company";
  const currentUrl = selectedRun.result?.current_url || selectedRun.result?.final_url || job?.url || "";
  const screenshotEntries = getLogScreenshotEntries(selectedRun);
  const selectedScreenshot = getSelectedLogScreenshot(selectedRun, screenshotEntries);
  const notes = selectedRun.pending_review?.notes || "";

  els.logMeta.innerHTML = `
    <div class="review-meta-card">
      <div class="run-card-header">
        <h3>${escapeHtml(jobTitle)}</h3>
        <span class="badge badge-${escapeHtml(normalizeStatus(selectedRun.status))}">${escapeHtml(selectedRun.status)}</span>
      </div>
      <p>${escapeHtml(jobCompany)}</p>
      <p>${escapeHtml(currentUrl || "Current URL not available yet")}</p>
      <p>Updated ${escapeHtml(formatDate(selectedRun.updated_at, true))}</p>
      ${notes ? `<p>${escapeHtml(`Notes: ${notes}`)}</p>` : ""}
      ${selectedRun.error_message ? `<p class="job-meta review-warning">${escapeHtml(selectedRun.error_message)}</p>` : ""}
    </div>
  `;

  if (screenshotEntries.length) {
    els.logCheckpointList.innerHTML = screenshotEntries
      .map((entry, index) => {
        const active = selectedScreenshot?.index === index ? "is-active" : "";
        return `
          <button class="log-checkpoint-button ${active}" type="button" data-log-screenshot="${escapeHtml(String(index))}">
            <strong>${escapeHtml(entry.reason || `Checkpoint ${index + 1}`)}</strong>
            <span>${escapeHtml(formatDateTime(entry.captured_at || selectedRun.updated_at))}</span>
          </button>
        `;
      })
      .join("");
    els.logCheckpointList.querySelectorAll("[data-log-screenshot]").forEach((button) => {
      button.addEventListener("click", () => {
        selectLogScreenshot(Number(button.dataset.logScreenshot));
      });
    });
  } else {
    els.logCheckpointList.innerHTML = `<div class="empty-state">No timed checkpoints have been captured for this run yet.</div>`;
  }

  const screenshotUrl = selectedScreenshot ? getLogScreenshotUrl(selectedRun, selectedScreenshot.index) : getReviewScreenshotUrl(selectedRun);
  if (selectedScreenshot || selectedRun.artifacts?.latest_screenshot) {
    els.logScreenshot.hidden = false;
    els.logScreenshotEmpty.hidden = true;
    els.logScreenshot.src = screenshotUrl;
    els.openLogScreenshotLink.hidden = false;
    els.openLogScreenshotLink.href = screenshotUrl;
  } else {
    els.logScreenshot.hidden = true;
    els.logScreenshotEmpty.hidden = false;
    els.logScreenshot.removeAttribute("src");
    els.openLogScreenshotLink.hidden = true;
    els.openLogScreenshotLink.href = "#";
  }

  els.openLogJobLink.hidden = !job?.url;
  els.openLogJobLink.href = job?.url || "#";

  const decisions = Array.isArray(selectedRun.decisions) ? selectedRun.decisions : [];
  if (!decisions.length) {
    els.logTimeline.innerHTML = `<div class="empty-state">No log entries have been recorded for this run yet.</div>`;
    return;
  }

  els.logTimeline.innerHTML = decisions
    .map((entry) => {
      const headlineParts = [entry.source || "system", entry.action || "event", entry.target || null].filter(Boolean);
      const detail = entry.note || entry.value || "No additional detail recorded.";
      return `
        <article class="log-entry">
          <div class="log-entry-header">
            <strong>${escapeHtml(headlineParts.join(" · "))}</strong>
            <span class="job-meta">${escapeHtml(formatDateTime(entry.logged_at || selectedRun.updated_at))}</span>
          </div>
          <p>${escapeHtml(detail)}</p>
        </article>
      `;
    })
    .join("");
}

function renderReviewDesk() {
  const reviewRuns = getReviewRuns();
  const reviewCount = reviewRuns.filter((run) => normalizeStatus(run.status) === "review").length;
  const captchaCount = reviewRuns.filter((run) => normalizeStatus(run.status) === "captcha_required").length;
  els.reviewSummary.textContent = reviewRuns.length
    ? `${reviewRuns.length} manual run${reviewRuns.length === 1 ? "" : "s"} pending · ${reviewCount} review · ${captchaCount} captcha.`
    : "No review or CAPTCHA runs pending.";

  if (!reviewRuns.length) {
    els.reviewRunSelect.innerHTML = `<option value="">No manual runs</option>`;
    els.reviewRunSelect.disabled = true;
    els.reviewEmptyState.hidden = false;
    els.reviewContent.hidden = true;
    els.reviewNotesInput.value = "";
    els.reviewMeta.innerHTML = "";
    els.reviewQuestions.innerHTML = "";
    els.reviewFields.innerHTML = "";
    els.reviewResumePreview.textContent = "";
    els.reviewScreenshot.removeAttribute("src");
    els.openReviewLiveBrowserLink.hidden = true;
    els.openReviewLiveBrowserLink.href = "#";
    return;
  }

  const selectedRun = getSelectedReviewRun();
  const options = reviewRuns
    .map((run) => {
      const selected = run.id === selectedRun?.id ? "selected" : "";
      return `<option value="${escapeHtml(run.id)}" ${selected}>${escapeHtml(formatReviewRunLabel(run))}</option>`;
    })
    .join("");

  els.reviewRunSelect.innerHTML = options;
  els.reviewRunSelect.disabled = false;
  els.reviewEmptyState.hidden = true;
  els.reviewContent.hidden = false;

  if (!selectedRun) {
    els.openReviewLiveBrowserLink.hidden = true;
    els.openReviewLiveBrowserLink.href = "#";
    return;
  }

  const job = getJobById(selectedRun.job_id);
  const pendingReview = selectedRun.pending_review || {};
  const normalizedStatus = normalizeStatus(selectedRun.status);
  const isCaptchaRun = normalizedStatus === "captcha_required";
  const tailoredResume = pendingReview.tailored_resume || selectedRun.artifacts?.tailored_resume || null;
  const fields = pendingReview.fields || selectedRun.extracted_fields || [];
  const notes = state.reviewNotesDrafts[selectedRun.id] ?? pendingReview.notes ?? "";
  const jobTitle = job?.title || selectedRun.result?.page_title || selectedRun.job_id;
  const jobCompany = job?.company || selectedRun.result?.company || "Unknown company";
  const finalUrl = pendingReview.final_url || selectedRun.result?.final_url || job?.url || "";
  const jobUrl = job?.url || finalUrl || "";
  const screenshotUrl = hasReviewScreenshot(selectedRun) ? getReviewScreenshotUrl(selectedRun) : "";
  const resumeUrl = tailoredResume?.pdf_path ? getReviewResumeUrl(selectedRun) : "";
  const resumePreviewText = tailoredResume?.rendered_markdown || "";
  const resumeDecisionNote = getResumeDecisionNote(selectedRun);
  const submissionError = pendingReview.submission_error || selectedRun.error_message || "";
  const manualBrowserUrl = pendingReview.manual_browser_url || "";
  const manualBrowserNote = pendingReview.manual_browser_note || "";

  els.reviewNotesInput.value = notes;
  els.approveReviewButton.textContent = isCaptchaRun ? "Resume after CAPTCHA" : "Approve & submit";
  els.rejectReviewButton.textContent = isCaptchaRun ? "Stop run" : "Reject";
  els.reviewMeta.innerHTML = `
    <div class="review-meta-card">
      <div class="run-card-header">
        <h3>${escapeHtml(jobTitle)}</h3>
        <span class="badge badge-${escapeHtml(normalizedStatus)}">${escapeHtml(selectedRun.status)}</span>
      </div>
      <p>${escapeHtml(jobCompany)}</p>
      <p>${escapeHtml(finalUrl || "Final review URL not available")}</p>
      <p>Updated ${escapeHtml(formatDate(selectedRun.updated_at, true))}</p>
      <p>${escapeHtml(isCaptchaRun ? manualBrowserNote || "Solve the challenge in the live browser, then resume the run." : resumeDecisionNote || "Tailored resume generation status not recorded.")}</p>
      ${submissionError ? `<p class="job-meta review-warning">${escapeHtml(`Last submit attempt failed: ${submissionError}`)}</p>` : ""}
    </div>
  `;

  if (fields.length) {
    els.reviewFields.innerHTML = fields
      .map((field) => {
        const value = field.current_value || field.value || field.profile_path || field.answer_prompt || "No captured value";
        const detail = [
          field.field_type ? `Type: ${field.field_type}` : null,
          field.safe_to_autofill ? "Safe autofill" : "Needs review",
          field.selector ? `Selector: ${field.selector}` : null,
        ]
          .filter(Boolean)
          .join(" · ");
        return `
          <div class="review-field-card">
            <h4>${escapeHtml(field.label || "Unnamed field")}</h4>
            <p>${escapeHtml(value)}</p>
            <p>${escapeHtml(detail)}</p>
          </div>
        `;
      })
      .join("");
  } else {
    els.reviewFields.innerHTML = `<div class="empty-state">No extracted fields were recorded for this run.</div>`;
  }

  renderReviewQuestions(selectedRun, fields);

  els.openReviewJobLink.hidden = !jobUrl;
  els.openReviewJobLink.href = jobUrl || "#";
  els.openReviewJobLink.setAttribute("aria-disabled", jobUrl ? "false" : "true");

  if (manualBrowserUrl) {
    els.openReviewLiveBrowserLink.hidden = false;
    els.openReviewLiveBrowserLink.href = manualBrowserUrl;
  } else {
    els.openReviewLiveBrowserLink.hidden = true;
    els.openReviewLiveBrowserLink.href = "#";
  }

  if (resumeUrl) {
    els.reviewResumeEmpty.hidden = true;
    els.reviewResumePreview.hidden = false;
    els.reviewResumePreview.textContent = resumePreviewText || "Resume PDF is available. Use Open resume to view it.";
    els.openReviewResumeLink.hidden = false;
    els.openReviewResumeLink.href = resumeUrl;
  } else {
    els.reviewResumeEmpty.hidden = false;
    els.reviewResumePreview.hidden = true;
    els.reviewResumePreview.textContent = "";
    els.openReviewResumeLink.hidden = true;
    els.openReviewResumeLink.href = "#";
  }

  if (screenshotUrl) {
    els.reviewScreenshot.hidden = false;
    els.reviewScreenshotEmpty.hidden = true;
    els.reviewScreenshot.src = screenshotUrl;
    els.openReviewScreenshotLink.hidden = false;
    els.openReviewScreenshotLink.href = screenshotUrl;
  } else {
    els.reviewScreenshot.hidden = true;
    els.reviewScreenshotEmpty.hidden = false;
    els.reviewScreenshot.removeAttribute("src");
    els.openReviewScreenshotLink.hidden = true;
    els.openReviewScreenshotLink.href = "#";
  }
}

function renderReviewQuestions(run, fields) {
  const questions = getOutstandingReviewQuestions(run, fields);
  if (!questions.length) {
    els.reviewQuestions.innerHTML = `<div class="empty-state">No unresolved long-form job questions for this run.</div>`;
    return;
  }

  els.reviewQuestions.innerHTML = questions
    .map(
      (field, index) => `
        <article class="review-question-card" data-review-question="${escapeHtml(field.selector || field.label || String(index))}">
          <h4>${escapeHtml(field.label || "Unnamed question")}</h4>
          <p class="job-meta">${escapeHtml(field.selector || field.name || field.placeholder || field.field_type)}</p>
          <textarea class="input answer-textarea answer-textarea-large" data-review-question-answer placeholder="Type the answer for this specific prompt."></textarea>
          <label class="checkbox-row">
            <input type="checkbox" data-review-question-safe checked />
            <span>Save as safe autofill answer</span>
          </label>
          <div class="answer-card-actions">
            <button class="button button-secondary small-button" type="button" data-save-review-answer="${escapeHtml(field.label || "")}">Save answer</button>
          </div>
        </article>
      `,
    )
    .join("");

  els.reviewQuestions.querySelectorAll("[data-save-review-answer]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest("[data-review-question]");
      if (!card) {
        return;
      }
      const answer = card.querySelector("[data-review-question-answer]").value.trim();
      const safeToAutofill = card.querySelector("[data-review-question-safe]").checked;
      const prompt = button.dataset.saveReviewAnswer;
      if (!prompt || !answer) {
        setBatchMessage("Answer text is required before saving.", "warning");
        return;
      }
      await saveReviewQuestionAnswer(prompt, answer, safeToAutofill);
    });
  });
}

function renderPagination() {
  const filteredJobs = getFilteredJobs();
  const { page, totalPages, startIndex, endIndex, totalItems } = getPaginationMeta(filteredJobs.length);
  els.pageSizeSelect.value = String(state.pagination.pageSize);
  els.paginationSummary.textContent = totalItems
    ? `Showing ${startIndex + 1}-${endIndex} of ${totalItems} · page ${page} of ${totalPages}`
    : "Showing 0 results";
  els.previousPageButton.disabled = page <= 1;
  els.nextPageButton.disabled = page >= totalPages;
}

function syncSelectedLogRun() {
  const logRuns = getLogRuns();
  if (!logRuns.some((run) => run.id === state.selectedLogRunId)) {
    state.selectedLogRunId = logRuns.find((run) => ["queued", "running", "submitting"].includes(normalizeStatus(run.status)))?.id || logRuns[0]?.id || null;
    state.selectedLogScreenshotIndex = null;
  }
}

function syncSelectedReviewRun() {
  const reviewRuns = getReviewRuns();
  if (!reviewRuns.some((run) => run.id === state.selectedReviewRunId)) {
    state.selectedReviewRunId = reviewRuns[0]?.id ?? null;
  }
  if (state.selectedReviewRunId && state.reviewNotesDrafts[state.selectedReviewRunId] === undefined) {
    const selectedRun = reviewRuns.find((run) => run.id === state.selectedReviewRunId);
    state.reviewNotesDrafts[state.selectedReviewRunId] = selectedRun?.pending_review?.notes ?? "";
  }
}

function selectLogRun(runId) {
  state.selectedLogRunId = runId;
  state.selectedLogScreenshotIndex = null;
  renderDashboard();
}

function selectLogScreenshot(index) {
  state.selectedLogScreenshotIndex = Number.isFinite(index) ? index : null;
  renderDashboard();
}

function selectReviewRun(runId) {
  state.selectedReviewRunId = runId;
  if (runId && state.reviewNotesDrafts[runId] === undefined) {
    const run = state.runs.find((entry) => entry.id === runId);
    state.reviewNotesDrafts[runId] = run?.pending_review?.notes ?? "";
  }
  renderDashboard();
}

function getFilteredJobs() {
  const latestRuns = getLatestRunMap();
  const filtered = state.jobs.filter((job) => {
    const titleHaystack = [job.title, job.description].filter(Boolean).join(" ").toLowerCase();
    const locationHaystack = [job.location].filter(Boolean).join(" ").toLowerCase();
    const companyHaystack = [job.company].filter(Boolean).join(" ").toLowerCase();

    if (state.filters.titleQuery && !titleHaystack.includes(state.filters.titleQuery)) {
      return false;
    }

    if (state.filters.locationQuery && !locationHaystack.includes(state.filters.locationQuery)) {
      return false;
    }

    if (state.filters.companyQuery && !companyHaystack.includes(state.filters.companyQuery)) {
      return false;
    }

    if (state.filters.sourceId !== "all") {
      if (state.filters.sourceId === "manual") {
        if (job.source_id) {
          return false;
        }
      } else if (job.source_id !== state.filters.sourceId) {
        return false;
      }
    }

    if (state.filters.availability !== "all" && job.availability !== state.filters.availability) {
      return false;
    }

    const applyStatus = getApplyStatus(job, latestRuns);
    if (state.filters.status !== "all" && applyStatus !== state.filters.status) {
      return false;
    }

    return true;
  });
  return sortJobs(filtered, latestRuns);
}

function getPaginatedJobs(filteredJobs = getFilteredJobs()) {
  const { startIndex, endIndex } = getPaginationMeta(filteredJobs.length);
  return filteredJobs.slice(startIndex, endIndex);
}

function getLatestRunMap() {
  const sortedRuns = [...state.runs].sort((left, right) => new Date(right.created_at) - new Date(left.created_at));
  const latestByJob = new Map();
  for (const run of sortedRuns) {
    if (!latestByJob.has(run.job_id)) {
      latestByJob.set(run.job_id, run);
    }
  }
  return latestByJob;
}

function getLogRuns() {
  return [...state.runs].sort((left, right) => new Date(right.updated_at) - new Date(left.updated_at));
}

function getSelectedLogRun() {
  return getLogRuns().find((run) => run.id === state.selectedLogRunId) || null;
}

function getReviewRuns() {
  return [...state.runs]
    .filter((run) => ["review", "captcha_required"].includes(normalizeStatus(run.status)))
    .sort((left, right) => new Date(right.updated_at) - new Date(left.updated_at));
}

function getSelectedReviewRun() {
  return getReviewRuns().find((run) => run.id === state.selectedReviewRunId) || null;
}

function getLogScreenshotEntries(run) {
  return Array.isArray(run?.artifacts?.progress_screenshots) ? run.artifacts.progress_screenshots : [];
}

function getSelectedLogScreenshot(run, screenshotEntries = getLogScreenshotEntries(run)) {
  if (!screenshotEntries.length) {
    return null;
  }
  if (
    state.selectedLogScreenshotIndex !== null &&
    state.selectedLogScreenshotIndex >= 0 &&
    state.selectedLogScreenshotIndex < screenshotEntries.length
  ) {
    return { ...screenshotEntries[state.selectedLogScreenshotIndex], index: state.selectedLogScreenshotIndex };
  }
  const lastIndex = screenshotEntries.length - 1;
  return { ...screenshotEntries[lastIndex], index: lastIndex };
}

function getOutstandingReviewQuestions(run, fields) {
  const populatedPrompts = new Set(
    (getActiveProfile()?.answers || []).map((entry) => normalizePrompt(entry.prompt)),
  );
  return fields.filter((field) => {
    const label = field.label || "";
    const normalized = normalizePrompt(label);
    const fieldType = String(field.field_type || "").toLowerCase();
    const hasValue = Boolean((field.current_value || "").trim());
    const sensitive = isSensitivePrompt(label);
    const longForm = ["textarea", "text"].includes(fieldType);
    const alreadyHandled = Boolean(field.answer_prompt || field.profile_path);
    return longForm && !hasValue && !sensitive && !alreadyHandled && !populatedPrompts.has(normalized);
  });
}

function getApplyStatus(job, latestRuns) {
  if (job.availability === "closed") {
    return "closed";
  }
  const run = latestRuns.get(job.id);
  return run ? normalizeStatus(run.status) : "not-started";
}

function isRunnableJob(job, latestRuns = getLatestRunMap()) {
  const status = getApplyStatus(job, latestRuns);
  return state.selectedProfileId && job.availability === "open" && !["queued", "running", "review", "submitting", "captcha_required"].includes(status);
}

function getSourceLabel(job) {
  if (!job.source_id) {
    return "Manual";
  }
  const source = state.sources.find((entry) => entry.id === job.source_id);
  return source ? source.name : "Imported source";
}

function getJobById(jobId) {
  return state.jobs.find((job) => job.id === jobId) || null;
}

function formatReviewRunLabel(run) {
  const job = getJobById(run.job_id);
  const title = job?.title || run.result?.page_title || run.job_id;
  const company = job?.company || run.result?.company || "Unknown company";
  return `${title} · ${company} · ${formatDate(run.updated_at, true)}`;
}

function getLogScreenshotUrl(run, screenshotIndex) {
  return `/runs/${encodeURIComponent(run.id)}/progress-screenshots/${encodeURIComponent(screenshotIndex)}?v=${encodeURIComponent(run.updated_at || run.id)}`;
}

function getReviewResumeUrl(run) {
  return `/runs/${encodeURIComponent(run.id)}/review/resume?v=${encodeURIComponent(run.updated_at || run.id)}`;
}

function getReviewScreenshotUrl(run) {
  return `/runs/${encodeURIComponent(run.id)}/review/screenshot?v=${encodeURIComponent(run.updated_at || run.id)}`;
}

function hasReviewScreenshot(run) {
  return Boolean(run.artifacts?.latest_screenshot);
}

function getResumeDecisionNote(run) {
  const decisions = Array.isArray(run.decisions) ? run.decisions : [];
  const decision = decisions.find((entry) => entry && entry.source === "resume_customizer");
  return decision?.note || null;
}

function normalizePrompt(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isSensitivePrompt(value) {
  const normalized = normalizePrompt(value);
  return ["gender", "sex", "race", "ethnicity", "hispanic", "latino", "disability", "veteran", "pronoun", "sexual orientation", "date of birth", "dob", "age"].some(
    (token) => normalized.includes(token),
  );
}

function getPaginationMeta(totalItems = getFilteredJobs().length) {
  const pageSize = Math.max(1, state.pagination.pageSize);
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const page = Math.min(Math.max(1, state.pagination.page), totalPages);
  const startIndex = totalItems ? (page - 1) * pageSize : 0;
  const endIndex = totalItems ? Math.min(startIndex + pageSize, totalItems) : 0;
  return {
    page,
    pageSize,
    totalPages,
    totalItems,
    startIndex,
    endIndex,
  };
}

function clampPagination(totalItems = getFilteredJobs().length) {
  const { page, totalPages } = getPaginationMeta(totalItems);
  state.pagination.page = Math.min(page, totalPages);
}

function sortJobs(jobs, latestRuns) {
  const direction = state.sort.direction === "asc" ? 1 : -1;
  return [...jobs].sort((left, right) => {
    const leftValue = sortValueForJob(left, latestRuns, state.sort.key);
    const rightValue = sortValueForJob(right, latestRuns, state.sort.key);
    if (leftValue < rightValue) {
      return -1 * direction;
    }
    if (leftValue > rightValue) {
      return 1 * direction;
    }
    return 0;
  });
}

function sortValueForJob(job, latestRuns, key) {
  if (key === "title") {
    return String(job.title || job.url || "").toLowerCase();
  }
  if (key === "company") {
    return String(job.company || "").toLowerCase();
  }
  if (key === "location") {
    return String(job.location || "").toLowerCase();
  }
  if (key === "status") {
    return getApplyStatus(job, latestRuns);
  }
  if (key === "source") {
    return getSourceLabel(job).toLowerCase();
  }
  if (key === "updated_at") {
    return new Date(job.updated_at || 0).getTime();
  }
  return "";
}

function renderSortIndicators() {
  document.querySelectorAll("[data-sort-key]").forEach((button) => {
    button.classList.remove("sort-asc", "sort-desc");
    if (button.dataset.sortKey === state.sort.key) {
      button.classList.add(state.sort.direction === "asc" ? "sort-asc" : "sort-desc");
    }
  });
}

function formatDisclosureSummary(data = {}) {
  const applicationPreferences = data?.application_preferences || {};
  const eeo = data?.eeo || {};
  const configured = [
    applicationPreferences.current_employee ? `Current employee: ${applicationPreferences.current_employee}` : null,
    eeo.gender ? `Gender: ${eeo.gender}` : null,
    eeo.hispanic_latino ? `Hispanic / Latino: ${eeo.hispanic_latino}` : null,
    eeo.ethnicity ? `Ethnicity: ${eeo.ethnicity}` : null,
    eeo.veteran_status ? `Veteran: ${eeo.veteran_status}` : null,
    eeo.disability_status ? `Disability: ${eeo.disability_status}` : null,
  ].filter(Boolean);
  if (!configured.length) {
    return "No explicit company or EEO answers saved yet.";
  }
  return `Explicit settings · ${configured.join(" · ")}`;
}

function populateProfileSettingsForm(data = {}) {
  const applicationPreferences = data?.application_preferences || {};
  const eeo = data?.eeo || {};
  setSelectValue(els.profileCurrentEmployeeInput, applicationPreferences.current_employee, PROFILE_SETTING_DEFAULTS.currentEmployee);
  setSelectValue(els.profileGenderInput, eeo.gender, PROFILE_SETTING_DEFAULTS.gender);
  setSelectValue(els.profileHispanicInput, eeo.hispanic_latino, PROFILE_SETTING_DEFAULTS.hispanicLatino);
  setSelectValue(els.profileEthnicityInput, eeo.ethnicity, PROFILE_SETTING_DEFAULTS.ethnicity);
  setSelectValue(els.profileVeteranInput, eeo.veteran_status, PROFILE_SETTING_DEFAULTS.veteranStatus);
  setSelectValue(els.profileDisabilityInput, eeo.disability_status, PROFILE_SETTING_DEFAULTS.disabilityStatus);
}

function setProfileSettingsFormDisabled(disabled) {
  els.profileSettingsForm.querySelectorAll("select, button").forEach((element) => {
    element.disabled = disabled;
  });
}

function getActiveProfile() {
  return state.profiles.find((profile) => profile.id === state.selectedProfileId) || null;
}

function normalizeStatus(status) {
  return status ? String(status).toLowerCase() : "not-started";
}

function setConnectionState(text) {
  els.connectionPill.textContent = text;
}

function setBatchMessage(message, tone = "info") {
  if (!message) {
    els.batchResult.textContent = "";
    els.batchResult.style.background = "transparent";
    return;
  }
  els.batchResult.textContent = message;
  const tones = {
    success: "var(--success-bg)",
    warning: "var(--warning-bg)",
    error: "var(--danger-bg)",
    info: "rgba(255, 247, 231, 0.78)",
  };
  els.batchResult.style.background = tones[tone] || tones.info;
}

function formatDate(value, compact = false) {
  if (!value) {
    return "Unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: compact ? "short" : "long",
    day: "numeric",
    hour: compact ? "numeric" : undefined,
    minute: compact ? "2-digit" : undefined,
  }).format(date);
}

function formatDateTime(value) {
  if (!value) {
    return "Unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function getErrorMessage(error) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Request failed.";
}

function valueOrNull(value) {
  const text = String(value ?? "").trim();
  return text || null;
}

function deepClone(value) {
  return JSON.parse(JSON.stringify(value || {}));
}

function setNestedString(target, path, value) {
  let current = target;
  for (let index = 0; index < path.length - 1; index += 1) {
    const key = path[index];
    if (!current[key] || typeof current[key] !== "object" || Array.isArray(current[key])) {
      current[key] = {};
    }
    current = current[key];
  }
  const finalKey = path[path.length - 1];
  if (value) {
    current[finalKey] = value;
    return;
  }
  delete current[finalKey];
}

function pruneEmptyData(value) {
  if (Array.isArray(value)) {
    const nextItems = value
      .map((item) => pruneEmptyData(item))
      .filter((item) => item !== undefined);
    return nextItems.length ? nextItems : undefined;
  }

  if (value && typeof value === "object") {
    const nextObject = {};
    Object.entries(value).forEach(([key, entryValue]) => {
      const prunedValue = pruneEmptyData(entryValue);
      if (prunedValue !== undefined) {
        nextObject[key] = prunedValue;
      }
    });
    return Object.keys(nextObject).length ? nextObject : undefined;
  }

  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? trimmed : undefined;
  }

  if (value === null || value === undefined) {
    return undefined;
  }

  return value;
}

function setSelectValue(select, value, fallback = "") {
  if (!select) {
    return;
  }
  select.querySelectorAll('option[data-dynamic="true"]').forEach((option) => option.remove());
  const desiredValue = value ?? fallback;
  const optionValues = [...select.options].map((option) => option.value);
  if (desiredValue && !optionValues.includes(desiredValue)) {
    const dynamicOption = document.createElement("option");
    dynamicOption.value = desiredValue;
    dynamicOption.textContent = `Custom: ${desiredValue}`;
    dynamicOption.dataset.dynamic = "true";
    select.append(dynamicOption);
  }
  const availableValues = [...select.options].map((option) => option.value);
  if (availableValues.includes(desiredValue)) {
    select.value = desiredValue;
    return;
  }
  if (availableValues.includes(fallback)) {
    select.value = fallback;
    return;
  }
  select.value = availableValues[0] || "";
}

async function fetchJson(url, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch {
      try {
        detail = await response.text();
      } catch {
        detail = `${response.status} ${response.statusText}`;
      }
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

async function fetchMultipart(url, formData) {
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  return response.json();
}
