const form = document.getElementById("scan-form");
const input = document.getElementById("image-input");
const preview = document.getElementById("preview");
const previewWrap = document.getElementById("preview-wrap");
const uploadPrompt = document.getElementById("upload-prompt");
const uploadZone = document.getElementById("upload-zone");
const clearPhotoBtn = document.getElementById("clear-photo");
const statusEl = document.getElementById("scan-status");
const submitBtn = document.getElementById("submit-btn");
const btnLabel = document.getElementById("btn-label");
const btnSpinner = document.getElementById("btn-spinner");
const resultEl = document.getElementById("result");
const notesEl = document.getElementById("notes");

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function listHtml(items) {
  if (!items || !items.length) return "<p class='clip'>None noted.</p>";
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function showPreview(file) {
  if (!file) return;
  const url = URL.createObjectURL(file);
  preview.src = url;
  previewWrap.classList.remove("hidden");
  uploadPrompt.classList.add("hidden");
}

function clearPhoto(event) {
  event?.preventDefault();
  event?.stopPropagation();
  input.value = "";
  preview.removeAttribute("src");
  previewWrap.classList.add("hidden");
  uploadPrompt.classList.remove("hidden");
}

function setFile(file) {
  if (!file || !file.type.startsWith("image/")) {
    statusEl.textContent = "Please choose an image file.";
    return;
  }
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  showPreview(file);
  statusEl.textContent = "";
}

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  btnLabel.textContent = isLoading ? "Checking…" : "Check my plant";
  btnSpinner.classList.toggle("hidden", !isLoading);
}

function resetScan() {
  clearPhoto();
  if (notesEl) notesEl.value = "";
  resultEl.classList.add("hidden");
  resultEl.innerHTML = "";
  document.getElementById("scan-layout")?.classList.remove("has-result");
  statusEl.textContent = "";
  uploadZone?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderResult(data) {
  const confidence = Math.round((data.confidence || 0) * 100);
  const healthPill = data.is_healthy
    ? `<span class="pill ok">Looks healthy</span>`
    : `<span class="pill warn">Needs attention</span>`;
  const mockPill = data.is_mock
    ? `<span class="pill mock">Demo mode — cozy tips until OpenAI is connected</span>`
    : "";
  const catalogLink = data.matched_plant_id
    ? `<a class="catalog-link" href="/plants/${encodeURIComponent(data.matched_plant_id)}">Open care guide →</a>`
    : "";

  const issues = (data.issues || [])
    .map(
      (issue) => `
      <article class="issue">
        <h3>${escapeHtml(issue.name)} <span class="pill">${escapeHtml(issue.severity || "moderate")}</span></h3>
        <p class="result-summary">${escapeHtml(issue.description || "")}</p>
        <div class="issue-cols">
          <div>
            <h4>Possible causes</h4>
            ${listHtml(issue.causes)}
          </div>
          <div>
            <h4>Treatment</h4>
            ${listHtml(issue.treatments)}
          </div>
        </div>
      </article>`
    )
    .join("");

  const tips = data.care_tips?.length
    ? `<section class="care-block"><h2>Care tips</h2>${listHtml(data.care_tips)}</section>`
    : "";

  const saveBlock = data.signed_in
    ? `
    <section class="save-collection">
      <h3 class="font-display">Save to your collection</h3>
      <label class="field">
        <span>Nickname</span>
        <input id="save-nickname" type="text" value="${escapeHtml(data.plant_common_name || "My plant")}" />
      </label>
      <button type="button" class="btn btn-primary" id="save-to-collection">Add to collection</button>
      <p id="save-status" class="scan-status"></p>
    </section>`
    : `<p class="clip"><a class="catalog-link" href="/auth/signin">Sign in</a> to save this plant to your collection.</p>`;

  resultEl.innerHTML = `
    <h2>${escapeHtml(data.plant_common_name || "Unknown plant")}</h2>
    <p class="sci">${escapeHtml(data.plant_scientific_name || "")}</p>
    ${catalogLink}
    <div class="result-meta">
      ${healthPill}
      <span class="pill">${confidence}% confidence</span>
      ${mockPill}
    </div>
    <p class="result-summary">${escapeHtml(data.summary || "")}</p>
    ${issues || "<p class='clip'>No specific issues flagged.</p>"}
    ${tips}
    ${saveBlock}
    <button type="button" class="btn btn-ghost dark" id="scan-another">Scan another cutie</button>
  `;
  resultEl.classList.remove("hidden");
  resultEl.classList.add("animate-rise");
  document.getElementById("scan-layout")?.classList.add("has-result");
  document.getElementById("scan-another")?.addEventListener("click", resetScan);
  bindSaveToCollection(data);
}

async function bindSaveToCollection(data) {
  const btn = document.getElementById("save-to-collection");
  if (!btn) return;
  const saveStatus = document.getElementById("save-status");
  btn.addEventListener("click", async () => {
    const file = input.files?.[0];
    if (!file) {
      saveStatus.textContent = "Photo missing — scan again to save.";
      return;
    }
    btn.disabled = true;
    saveStatus.textContent = "Saving to your collection…";
    const body = new FormData();
    body.append("image", file);
    body.append("nickname", document.getElementById("save-nickname")?.value || data.plant_common_name || "My plant");
    body.append("catalog_plant_id", data.matched_plant_id || "");
    body.append("species_name", data.plant_common_name || "");
    body.append("scientific_name", data.plant_scientific_name || "");
    body.append("notes", notesEl?.value || data.summary || "");
    try {
      const response = await fetch("/api/collection/from-scan", { method: "POST", body });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not save.");
      saveStatus.innerHTML = `Saved! <a class="catalog-link" href="${payload.url}">View in collection →</a>`;
    } catch (err) {
      saveStatus.textContent = err.message || "Save failed.";
      btn.disabled = false;
    }
  });
}

input?.addEventListener("change", () => {
  const file = input.files?.[0];
  if (file) showPreview(file);
});

clearPhotoBtn?.addEventListener("click", clearPhoto);

["dragenter", "dragover"].forEach((eventName) => {
  uploadZone?.addEventListener(eventName, (event) => {
    event.preventDefault();
    uploadZone.classList.add("is-dragover");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  uploadZone?.addEventListener(eventName, (event) => {
    event.preventDefault();
    uploadZone.classList.remove("is-dragover");
  });
});

uploadZone?.addEventListener("drop", (event) => {
  const file = event.dataTransfer?.files?.[0];
  if (file) setFile(file);
});

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = input.files?.[0];
  if (!file) {
    statusEl.textContent = "Choose or take a photo first.";
    return;
  }

  setLoading(true);
  statusEl.textContent = "Looking over your plant…";
  resultEl.classList.add("hidden");

  const body = new FormData();
  body.append("image", file);
  body.append("notes", notesEl?.value || "");

  try {
    const response = await fetch("/api/diagnose", { method: "POST", body });
    const data = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map((d) => d.msg).join(", ")
        : data.detail;
      throw new Error(detail || "Diagnosis failed.");
    }
    renderResult(data);
    statusEl.textContent = data.is_mock
      ? "Showing demo diagnosis. Add OPENAI_API_KEY for live AI results."
      : "Diagnosis complete.";
    resultEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    statusEl.textContent = err.message || "Something went wrong.";
  } finally {
    setLoading(false);
  }
});

const params = new URLSearchParams(window.location.search);
const prefillNotes = params.get("notes");
if (prefillNotes && notesEl && !notesEl.value) {
  notesEl.value = prefillNotes;
}
