const state = {
  profiles: [],
  sources: [],
  jobs: [],
  runs: [],
  selectedProfileId: null,
  selectedJobIds: new Set(),
  filters: {
    search: "",
    sourceId: "all",
    availability: "open",
    status: "all",
  },
};

const els = {
  refreshButton: document.getElementById("refreshButton"),
  connectionPill: document.getElementById("connectionPill"),
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
  searchInput: document.getElementById("searchInput"),
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
  els.profileSelect.addEventListener("change", async (event) => {
    state.selectedProfileId = event.target.value || null;
    state.selectedJobIds.clear();
    await loadRuns();
    renderDashboard();
  });

  els.searchInput.addEventListener("input", (event) => {
    state.filters.search = event.target.value.trim().toLowerCase();
    renderDashboard();
  });
  els.sourceFilter.addEventListener("change", (event) => {
    state.filters.sourceId = event.target.value;
    renderDashboard();
  });
  els.availabilityFilter.addEventListener("change", (event) => {
    state.filters.availability = event.target.value;
    renderDashboard();
  });
  els.statusFilter.addEventListener("change", (event) => {
    state.filters.status = event.target.value;
    renderDashboard();
  });

  els.selectVisibleButton.addEventListener("click", () => {
    const latestRuns = getLatestRunMap();
    for (const job of getFilteredJobs()) {
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
      for (const job of getFilteredJobs()) {
        if (isRunnableJob(job)) {
          state.selectedJobIds.add(job.id);
        }
      }
    } else {
      for (const job of getFilteredJobs()) {
        state.selectedJobIds.delete(job.id);
      }
    }
    renderDashboard();
  });

  els.applySelectedButton.addEventListener("click", async () => {
    await queueSelectedJobs([...state.selectedJobIds]);
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
  renderProfilePanel();
  renderSourceFilter();
  renderSources();
  renderStats();
  renderRuns();
  renderJobs();
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
      return `
        <div class="run-card">
          <div class="run-card-header">
            <h3>${escapeHtml(title)}</h3>
            <span class="badge badge-${escapeHtml(normalizeStatus(run.status))}">${escapeHtml(run.status)}</span>
          </div>
          <p>${escapeHtml(job?.company || "Unknown company")} · ${escapeHtml(formatDate(run.updated_at, true))}</p>
        </div>
      `;
    })
    .join("");
}

function renderJobs() {
  const filteredJobs = getFilteredJobs();
  const latestRuns = getLatestRunMap();

  const selectedVisibleCount = filteredJobs.filter((job) => state.selectedJobIds.has(job.id)).length;
  const runnableVisibleCount = filteredJobs.filter((job) => isRunnableJob(job, latestRuns)).length;
  const allVisibleSelected = runnableVisibleCount > 0 && selectedVisibleCount === runnableVisibleCount;
  els.selectAllCheckbox.checked = allVisibleSelected;
  els.selectAllCheckbox.indeterminate = selectedVisibleCount > 0 && !allVisibleSelected;

  const profile = getActiveProfile();
  els.applySelectedButton.disabled = !profile || !state.selectedJobIds.size;
  els.jobsSummary.textContent = `${filteredJobs.length} jobs shown · ${state.selectedJobIds.size} selected · ${
    profile ? `applying with ${profile.name}` : "choose a resume profile"
  }`;

  if (!filteredJobs.length) {
    els.jobsTableBody.innerHTML = `
      <tr>
        <td colspan="8">
        <div class="empty-state">No jobs match the current filters.</div>
        </td>
      </tr>
    `;
    return;
  }

  els.jobsTableBody.innerHTML = filteredJobs
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
}

function getFilteredJobs() {
  const latestRuns = getLatestRunMap();
  return state.jobs.filter((job) => {
    const haystack = [job.title, job.company, job.location, job.description].filter(Boolean).join(" ").toLowerCase();
    if (state.filters.search && !haystack.includes(state.filters.search)) {
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
