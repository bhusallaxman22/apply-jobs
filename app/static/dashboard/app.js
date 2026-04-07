const state = {
  profiles: [],
  sources: [],
  jobs: [],
  runs: [],
  selectedProfileId: null,
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

const els = {
  refreshButton: document.getElementById("refreshButton"),
  connectionPill: document.getElementById("connectionPill"),
  profileForm: document.getElementById("profileForm"),
  profileNameInput: document.getElementById("profileNameInput"),
  fullNameInput: document.getElementById("fullNameInput"),
  emailInput: document.getElementById("emailInput"),
  phoneInput: document.getElementById("phoneInput"),
  locationInput: document.getElementById("locationInput"),
  resumeFileInput: document.getElementById("resumeFileInput"),
  resumeMarkdownInput: document.getElementById("resumeMarkdownInput"),
  profilesCount: document.getElementById("profilesCount"),
  profileSelect: document.getElementById("profileSelect"),
  profileDetails: document.getElementById("profileDetails"),
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
  reviewDeskSection: document.getElementById("reviewDeskSection"),
  reviewSummary: document.getElementById("reviewSummary"),
  reviewRunSelect: document.getElementById("reviewRunSelect"),
  reviewEmptyState: document.getElementById("reviewEmptyState"),
  reviewContent: document.getElementById("reviewContent"),
  reviewNotesInput: document.getElementById("reviewNotesInput"),
  approveReviewButton: document.getElementById("approveReviewButton"),
  rejectReviewButton: document.getElementById("rejectReviewButton"),
  openReviewJobLink: document.getElementById("openReviewJobLink"),
  openReviewResumeLink: document.getElementById("openReviewResumeLink"),
  openReviewScreenshotLink: document.getElementById("openReviewScreenshotLink"),
  reviewMeta: document.getElementById("reviewMeta"),
  reviewFields: document.getElementById("reviewFields"),
  reviewScreenshot: document.getElementById("reviewScreenshot"),
  reviewScreenshotEmpty: document.getElementById("reviewScreenshotEmpty"),
  reviewResumeEmpty: document.getElementById("reviewResumeEmpty"),
  reviewResumeFrame: document.getElementById("reviewResumeFrame"),
};

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await loadDashboardData();
  window.setInterval(() => {
    loadDashboardData({ silent: true }).catch(() => {});
  }, 20000);
});

function bindEvents() {
  els.refreshButton.addEventListener("click", () => loadDashboardData());
  els.profileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await createProfileFromForm();
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

  const notes = els.reviewNotesInput.value.trim();
  state.reviewNotesDrafts[selectedRun.id] = notes;

  try {
    setConnectionState(decision === "approve" ? "Approving review…" : "Rejecting review…");
    await fetchJson(`/runs/${encodeURIComponent(selectedRun.id)}/${decision}`, {
      method: "POST",
      body: JSON.stringify({ notes: notes || null }),
    });
    await loadRuns();
    renderDashboard();
    setBatchMessage(
      decision === "approve" ? "Review approved." : "Review rejected. You can update the profile and queue again.",
      decision === "approve" ? "success" : "warning",
    );
    setConnectionState(decision === "approve" ? "Review approved" : "Review rejected");
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
    data: {
      identity: {
        full_name: els.fullNameInput.value.trim(),
        email: els.emailInput.value.trim(),
        phone: els.phoneInput.value.trim(),
        location: els.locationInput.value.trim(),
      },
    },
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
  renderSourceFilter();
  renderSources();
  renderStats();
  renderRuns();
  renderJobs();
  renderPagination();
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
    return;
  }

  const identity = profile.data?.identity || {};
  const documents = profile.data?.documents || {};
  const answersCount = Array.isArray(profile.answers) ? profile.answers.length : 0;
  const sourcePath = documents.resume_markdown_path || documents.resume_source_text_path || documents.resume_typst_path || "No source file";
  const resumePath = documents.resume_pdf || profile.resume_path || "No PDF uploaded";

  els.profileDetails.className = "profile-details";
  els.profileDetails.innerHTML = `
    <div class="profile-card">
      <h3>${escapeHtml(profile.name)}</h3>
      <p>${escapeHtml(identity.email || "No email on file")} · ${escapeHtml(identity.phone || "No phone on file")}</p>
      <p>${escapeHtml(identity.location || "No location on file")}</p>
      <p class="mono-path">${escapeHtml(resumePath)}</p>
      <p class="mono-path">${escapeHtml(sourcePath)}</p>
      <p>${answersCount} saved answer${answersCount === 1 ? "" : "s"} available for autofill.</p>
    </div>
  `;
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
    ["In progress", filteredJobs.filter((job) => ["queued", "running"].includes(getApplyStatus(job, latestRuns))).length],
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
      const reviewButton =
        normalizeStatus(run.status) === "review"
          ? `<div class="source-card-actions"><button class="button button-secondary small-button" type="button" data-review-run="${escapeHtml(run.id)}">Open review</button></div>`
          : "";
      return `
        <div class="run-card">
          <div class="run-card-header">
            <h3>${escapeHtml(title)}</h3>
            <span class="badge badge-${escapeHtml(normalizeStatus(run.status))}">${escapeHtml(run.status)}</span>
          </div>
          <p>${escapeHtml(job?.company || "Unknown company")} · ${escapeHtml(formatDate(run.updated_at, true))}</p>
          ${reviewButton}
        </div>
      `;
    })
    .join("");

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
                latestRun && applyStatus === "review"
                  ? `<button class="button button-secondary small-button" type="button" data-review-run="${escapeHtml(latestRun.id)}">Review</button>`
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

  els.jobsTableBody.querySelectorAll("[data-review-run]").forEach((button) => {
    button.addEventListener("click", () => {
      selectReviewRun(button.dataset.reviewRun);
      els.reviewDeskSection.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function renderReviewDesk() {
  const reviewRuns = getReviewRuns();
  els.reviewSummary.textContent = reviewRuns.length
    ? `${reviewRuns.length} run${reviewRuns.length === 1 ? "" : "s"} awaiting review.`
    : "No review runs pending.";

  if (!reviewRuns.length) {
    els.reviewRunSelect.innerHTML = `<option value="">No review runs</option>`;
    els.reviewRunSelect.disabled = true;
    els.reviewEmptyState.hidden = false;
    els.reviewContent.hidden = true;
    els.reviewNotesInput.value = "";
    els.reviewMeta.innerHTML = "";
    els.reviewFields.innerHTML = "";
    els.reviewResumeFrame.src = "about:blank";
    els.reviewScreenshot.removeAttribute("src");
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
    return;
  }

  const job = getJobById(selectedRun.job_id);
  const pendingReview = selectedRun.pending_review || {};
  const tailoredResume = pendingReview.tailored_resume || selectedRun.artifacts?.tailored_resume || null;
  const fields = pendingReview.fields || selectedRun.extracted_fields || [];
  const notes = state.reviewNotesDrafts[selectedRun.id] ?? pendingReview.notes ?? "";
  const jobTitle = job?.title || selectedRun.result?.page_title || selectedRun.job_id;
  const jobCompany = job?.company || selectedRun.result?.company || "Unknown company";
  const finalUrl = pendingReview.final_url || selectedRun.result?.final_url || job?.url || "";
  const jobUrl = job?.url || finalUrl || "";
  const screenshotUrl = hasReviewScreenshot(selectedRun) ? getReviewScreenshotUrl(selectedRun) : "";
  const resumeUrl = tailoredResume?.pdf_path ? getReviewResumeUrl(selectedRun) : "";

  els.reviewNotesInput.value = notes;
  els.reviewMeta.innerHTML = `
    <div class="review-meta-card">
      <div class="run-card-header">
        <h3>${escapeHtml(jobTitle)}</h3>
        <span class="badge badge-review">review</span>
      </div>
      <p>${escapeHtml(jobCompany)}</p>
      <p>${escapeHtml(finalUrl || "Final review URL not available")}</p>
      <p>Updated ${escapeHtml(formatDate(selectedRun.updated_at, true))}</p>
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

  els.openReviewJobLink.hidden = !jobUrl;
  els.openReviewJobLink.href = jobUrl || "#";
  els.openReviewJobLink.setAttribute("aria-disabled", jobUrl ? "false" : "true");

  if (resumeUrl) {
    els.reviewResumeEmpty.hidden = true;
    els.reviewResumeFrame.hidden = false;
    els.reviewResumeFrame.src = resumeUrl;
    els.openReviewResumeLink.hidden = false;
    els.openReviewResumeLink.href = resumeUrl;
  } else {
    els.reviewResumeEmpty.hidden = false;
    els.reviewResumeFrame.hidden = true;
    els.reviewResumeFrame.src = "about:blank";
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

function getReviewRuns() {
  return [...state.runs]
    .filter((run) => normalizeStatus(run.status) === "review")
    .sort((left, right) => new Date(right.updated_at) - new Date(left.updated_at));
}

function getSelectedReviewRun() {
  return getReviewRuns().find((run) => run.id === state.selectedReviewRunId) || null;
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
  return state.selectedProfileId && job.availability === "open" && !["queued", "running", "review"].includes(status);
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

function getReviewResumeUrl(run) {
  return `/runs/${encodeURIComponent(run.id)}/review/resume?v=${encodeURIComponent(run.updated_at || run.id)}`;
}

function getReviewScreenshotUrl(run) {
  return `/runs/${encodeURIComponent(run.id)}/review/screenshot?v=${encodeURIComponent(run.updated_at || run.id)}`;
}

function hasReviewScreenshot(run) {
  return Boolean(run.artifacts?.latest_screenshot);
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
