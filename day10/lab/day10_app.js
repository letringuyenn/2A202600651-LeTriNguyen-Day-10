const metricKeys = [
  "unknown_doc_ids",
  "missing_content_rows",
  "stale_refund_rows_removed",
  "stale_hr_rows_removed",
  "normalized_dates",
  "duplicate_rows_removed",
  "noise_prefixes_stripped",
];

const actionConfig = {
  summary: { url: "/api/summary", method: "GET", label: "Refreshing summary" },
  pipeline: {
    url: "/api/run-pipeline",
    method: "POST",
    label: "Running ETL pipeline",
  },
  eval: {
    url: "/api/run-eval",
    method: "POST",
    label: "Running retrieval eval",
  },
  grading: {
    url: "/api/run-grading",
    method: "POST",
    label: "Running grading",
  },
  freshness: {
    url: "/api/run-freshness",
    method: "POST",
    label: "Checking freshness",
  },
};

const $ = (id) => document.getElementById(id);
let loadedQuestionMode = "official";
let loadedQuestions = [];

function displayValue(value, fallback = "--") {
  return value === null || value === undefined || value === "" ? fallback : value;
}

function setStatus(id, value) {
  const element = $(id);
  element.textContent = displayValue(value);
  element.classList.remove("pass", "fail");
  const normalized = String(value || "").toUpperCase();
  if (["PASS", "OK"].includes(normalized)) {
    element.classList.add("pass");
  } else if (["FAIL", "WARN"].includes(normalized)) {
    element.classList.add("fail");
  }
}

function renderMetrics(metrics) {
  const root = $("cleaningMetrics");
  root.replaceChildren();
  metricKeys.forEach((key) => {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    const value = document.createElement("dd");
    term.textContent = key;
    value.textContent =
      metrics && metrics[key] !== undefined
        ? metrics[key]
        : "Not available in manifest";
    row.append(term, value);
    root.append(row);
  });
}

function renderArtifacts(artifacts) {
  const root = $("artifactList");
  root.replaceChildren();
  Object.entries(artifacts || {}).forEach(([key, path]) => {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    const value = document.createElement("dd");
    term.textContent = key;
    value.textContent = displayValue(path, "Not generated");
    row.append(term, value);
    root.append(row);
  });
}

function boolLabel(value, positiveWhenFalse = false) {
  const ok = positiveWhenFalse ? value === false : value === true;
  return {
    text: value === null || value === undefined ? "N/A" : String(value),
    className: ok ? "ok" : "bad",
  };
}

function renderGrading(grading) {
  const total = grading?.total_questions || 0;
  const passed = grading?.passed_questions || 0;
  $("gradingResult").textContent = total ? `${passed}/${total}` : "--";
  $("gradingResult").className = total && total === passed ? "pass" : "";
  $("gradingHeadline").textContent = total
    ? `${passed}/${total} passed`
    : "No grading result loaded";

  const signals = $("gradingSignals");
  signals.replaceChildren();
  if (total) {
    const allTop1 = grading.top1_doc_matches_count === total;
    const allContains = grading.rows.every(
      (record) => record.contains_expected === true,
    );
    const noForbidden = grading.rows.every(
      (record) => record.hits_forbidden === false,
    );
    [
      `top1_doc_matches=${allTop1}`,
      `contains_expected=${allContains}`,
      `hits_forbidden=${noForbidden ? "False" : "True"}`,
    ].forEach((text) => {
      const signal = document.createElement("span");
      signal.className = "signal";
      signal.textContent = text;
      signals.append(signal);
    });
  }

  const body = $("gradingRows");
  body.replaceChildren();
  if (!grading?.rows?.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "empty-state";
    cell.textContent = "Run grading or refresh summary to load results.";
    row.append(cell);
    body.append(row);
    return;
  }

  grading.rows.forEach((record) => {
    const row = document.createElement("tr");
    const values = [
      { text: record.id },
      { text: record.top1_doc_id },
      boolLabel(record.top1_doc_matches),
      boolLabel(record.contains_expected),
      boolLabel(record.hits_forbidden, true),
    ];
    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = displayValue(value.text);
      if (value.className) cell.className = value.className;
      row.append(cell);
    });
    body.append(row);
  });
}

function splitCommaSeparated(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function renderQuestionRows() {
  const body = $("customQuestionRows");
  body.replaceChildren();
  if (!loadedQuestions.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "empty-state";
    cell.textContent = "No questions loaded.";
    row.append(cell);
    body.append(row);
    return;
  }

  loadedQuestions.forEach((question, index) => {
    const row = document.createElement("tr");
    [
      question.id,
      question.question,
      question.expect_top1_doc_id,
      question.must_contain_any.join(", "),
      question.must_not_contain.join(", ") || "--",
    ].forEach((text) => {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.append(cell);
    });
    const actionCell = document.createElement("td");
    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "secondary table-button";
    editButton.textContent = loadedQuestionMode === "official" ? "View" : "Edit";
    editButton.addEventListener("click", () => populateQuestionForm(index));
    actionCell.append(editButton);
    row.append(actionCell);
    body.append(row);
  });
}

function setQuestionFormReadOnly(readOnly) {
  $("customQuestionForm")
    .querySelectorAll("input, textarea, select, button[type='submit']")
    .forEach((element) => {
      element.disabled = readOnly;
    });
  $("questionFormTitle").textContent = readOnly
    ? "Official question (read-only)"
    : "Add or edit a custom question";
}

function populateQuestionForm(index) {
  const question = loadedQuestions[index];
  if (!question) return;
  $("customQuestionId").value = question.id;
  $("customQuestionText").value = question.question;
  $("customExpectedDocId").value = question.expect_top1_doc_id;
  $("customMustContain").value = question.must_contain_any.join(", ");
  $("customMustNotContain").value = question.must_not_contain.join(", ");
  $("customCriteria").value = question.grading_criteria.join("\n");
}

function clearQuestionForm() {
  $("customQuestionForm").reset();
  if (loadedQuestionMode === "custom") {
    $("customQuestionId").focus();
  }
}

async function loadQuestionSet(mode) {
  $("customGradingMessage").textContent = `Loading ${mode} questions...`;
  try {
    const response = await fetch(`/api/grading/questions?mode=${mode}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Could not load questions.");
    loadedQuestionMode = mode;
    loadedQuestions = payload.questions;
    $("gradingMode").value = mode;
    setQuestionFormReadOnly(payload.read_only);
    clearQuestionForm();
    renderQuestionRows();
    $("customGradingMessage").textContent =
      `${payload.count} ${mode} questions loaded` +
      (payload.warnings.length ? ` · ${payload.warnings.join(" ")}` : "");
  } catch (error) {
    $("customGradingMessage").textContent = error.message;
  }
}

function formQuestion() {
  return {
    id: $("customQuestionId").value.trim(),
    question: $("customQuestionText").value.trim(),
    expect_top1_doc_id: $("customExpectedDocId").value,
    must_contain_any: splitCommaSeparated($("customMustContain").value),
    must_not_contain: splitCommaSeparated($("customMustNotContain").value),
    grading_criteria: $("customCriteria")
      .value.split("\n")
      .map((item) => item.trim())
      .filter(Boolean),
  };
}

function addOrUpdateCustomQuestion(event) {
  event.preventDefault();
  if (loadedQuestionMode !== "custom") {
    $("customGradingMessage").textContent =
      "Official questions are read-only. Load custom questions first.";
    return;
  }
  const question = formQuestion();
  if (!question.id || !question.question) {
    $("customGradingMessage").textContent = "ID and question are required.";
    return;
  }
  const existingIndex = loadedQuestions.findIndex(
    (item) => item.id === question.id,
  );
  if (existingIndex >= 0) {
    loadedQuestions[existingIndex] = question;
    $("customGradingMessage").textContent = `Updated ${question.id} in the local list.`;
  } else {
    loadedQuestions.push(question);
    $("customGradingMessage").textContent = `Added ${question.id} to the local list.`;
  }
  renderQuestionRows();
  clearQuestionForm();
}

async function saveCustomQuestions() {
  if (loadedQuestionMode !== "custom") {
    $("customGradingMessage").textContent =
      "Official questions cannot be saved. Load custom questions first.";
    return;
  }
  const button = $("saveCustomQuestions");
  button.disabled = true;
  try {
    const response = await fetch("/api/grading/questions/custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(loadedQuestions),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Save failed.");
    loadedQuestions = payload.questions;
    renderQuestionRows();
    $("customGradingMessage").textContent =
      `Saved ${payload.count} custom questions to ${payload.path}.`;
  } catch (error) {
    $("customGradingMessage").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function renderCustomResults(grading) {
  const total = grading?.total ?? grading?.total_questions ?? 0;
  const passed = grading?.passed ?? grading?.passed_questions ?? 0;
  const failed = grading?.failed ?? total - passed;
  $("customResultHeadline").textContent = total
    ? `${passed}/${total} passed`
    : "No custom grading result";

  const signals = $("customResultSignals");
  signals.replaceChildren();
  if (total) {
    [`total ${total}`, `passed ${passed}`, `failed ${failed}`].forEach((text) => {
      const signal = document.createElement("span");
      signal.className = "signal";
      signal.textContent = text;
      signals.append(signal);
    });
  }

  const body = $("customResultRows");
  body.replaceChildren();
  if (!grading?.rows?.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "empty-state";
    cell.textContent = "Run or refresh custom grading to load results.";
    row.append(cell);
    body.append(row);
    return;
  }

  grading.rows.forEach((record) => {
    const row = document.createElement("tr");
    [
      { text: record.id },
      { text: record.top1_doc_id },
      boolLabel(record.top1_doc_matches),
      boolLabel(record.contains_expected),
      boolLabel(record.hits_forbidden, true),
      boolLabel(record.passed),
    ].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = displayValue(value.text);
      if (value.className) cell.className = value.className;
      row.append(cell);
    });
    body.append(row);
  });
}

async function runOrRefreshCustomGrading(run) {
  const button = run ? $("runCustomGrading") : $("refreshCustomResults");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = run ? "Running custom grading..." : "Refreshing...";
  try {
    const response = await fetch(
      run ? "/api/run-custom-grading" : "/api/grading/results?mode=custom",
      { method: run ? "POST" : "GET" },
    );
    const payload = await response.json();
    const grading = payload.grading || payload;
    renderCustomResults(grading);
    if (run) showLogs(payload, "custom-grading");
    $("customGradingMessage").textContent = payload.ok
      ? `Custom grading: ${grading.passed}/${grading.total} passed.`
      : "Custom grading result is not available.";
    await loadArtifacts();
  } catch (error) {
    $("customGradingMessage").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

function renderSummary(summary) {
  if (!summary?.ok) {
    $("lastAction").textContent = summary?.error || "Summary unavailable";
    return;
  }
  setStatus("qualityStatus", summary.quality_status);
  $("rawRecords").textContent = displayValue(summary.raw_records);
  $("cleanedRecords").textContent = displayValue(summary.cleaned_records);
  $("quarantineRecords").textContent = displayValue(summary.quarantine_records);
  setStatus("publishStatus", summary.publish_status);
  setStatus("freshnessStatus", summary.freshness?.status);
  $("latestRunId").textContent = displayValue(summary.run_id);
  $("manifestPath").textContent = displayValue(summary.latest_manifest);
  renderMetrics(summary.cleaning_stats);
  renderGrading(summary.grading);
}

function showLogs(result, action) {
  $("stdoutLog").textContent = result?.stdout || "No stdout.";
  $("stderrLog").textContent = result?.stderr || "No stderr.";
  $("logSummary").textContent = `${action} · return code ${displayValue(
    result?.returncode,
    "N/A",
  )}`;
  $("logDetails").open = action !== "summary";
}

async function loadArtifacts() {
  try {
    const response = await fetch("/api/artifacts");
    const payload = await response.json();
    renderArtifacts(payload.artifacts);
  } catch (error) {
    renderArtifacts({ error: error.message });
  }
}

async function loadHealth() {
  const badge = $("serviceBadge");
  try {
    const response = await fetch("/api/health");
    const payload = await response.json();
    if (payload.ok) {
      badge.classList.add("online");
      badge.lastChild.textContent = " API Online";
    }
  } catch {
    badge.classList.remove("online");
    badge.lastChild.textContent = " API Offline";
  }
}

async function runAction(button, action) {
  const config = actionConfig[action];
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = `${config.label}...`;
  $("lastAction").textContent = `${config.label}...`;

  try {
    const response = await fetch(config.url, { method: config.method });
    const payload = await response.json();
    const summary = action === "summary" ? payload : payload.summary;
    renderSummary(summary);
    if (payload.grading) renderGrading(payload.grading);
    showLogs(payload, action);
    await loadArtifacts();

    const actionSucceeded = payload.ok !== false;
    $("lastAction").textContent = actionSucceeded
      ? `${config.label} completed`
      : `${config.label} failed`;
  } catch (error) {
    $("lastAction").textContent = `${config.label} failed`;
    showLogs(
      { returncode: null, stdout: "", stderr: error.message },
      action,
    );
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", () => {
    runAction(button, button.dataset.action);
  });
});

$("gradingMode").addEventListener("change", (event) => {
  loadQuestionSet(event.target.value);
});
$("loadOfficialQuestions").addEventListener("click", () =>
  loadQuestionSet("official"),
);
$("loadCustomQuestions").addEventListener("click", () =>
  loadQuestionSet("custom"),
);
$("newCustomQuestion").addEventListener("click", async () => {
  if (loadedQuestionMode !== "custom") await loadQuestionSet("custom");
  clearQuestionForm();
});
$("saveCustomQuestions").addEventListener("click", saveCustomQuestions);
$("runCustomGrading").addEventListener("click", () =>
  runOrRefreshCustomGrading(true),
);
$("refreshCustomResults").addEventListener("click", () =>
  runOrRefreshCustomGrading(false),
);
$("customQuestionForm").addEventListener("submit", addOrUpdateCustomQuestion);

async function bootstrap() {
  renderMetrics(null);
  await Promise.all([
    loadHealth(),
    loadArtifacts(),
    loadQuestionSet("official"),
    runOrRefreshCustomGrading(false),
  ]);
  const summaryButton = document.querySelector('[data-action="summary"]');
  await runAction(summaryButton, "summary");
}

bootstrap();
