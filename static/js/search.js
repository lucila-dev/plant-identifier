const input = document.getElementById("plant-search");
const resultsEl = document.getElementById("search-results");
const chips = document.querySelectorAll(".chip[data-query]");
let timer = null;

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderResults(items) {
  if (!items.length) {
    resultsEl.innerHTML =
      '<p class="empty-state">Hmm, no plant by that name. Try another spelling?</p>';
    return;
  }

  resultsEl.innerHTML = items
    .map(
      (plant, index) => `
      <div class="plant-row animate-rise" style="--i:${index}">
        <a class="plant-row-link" href="/plants/${encodeURIComponent(plant.id)}">
          <div class="plant-row-thumb">
            <img src="${escapeHtml(plant.image_url || "/static/images/plant-placeholder.svg")}" alt="" loading="lazy" />
          </div>
          <div class="plant-row-text">
            <h2>${escapeHtml(plant.primary_name)}</h2>
            <p class="sci">${escapeHtml(plant.scientific_name)}</p>
            ${
              plant.watering_frequency
                ? `<p class="watering-freq">Water ${escapeHtml(
                    String(plant.watering_frequency).toLowerCase()
                  )}</p>`
                : ""
            }
            <p class="clip">${escapeHtml(plant.description)}</p>
          </div>
        </a>
        <button
          type="button"
          class="quick-add-btn"
          data-id="${escapeHtml(plant.id)}"
          data-name="${escapeHtml(plant.primary_name)}"
          data-sci="${escapeHtml(plant.scientific_name)}"
          aria-label="Quick add ${escapeHtml(plant.primary_name)} to your collection"
        >
          <span class="quick-add-icon" aria-hidden="true">+</span>
          <span class="quick-add-label">Add</span>
        </button>
      </div>`
    )
    .join("");
}

let toastTimer = null;

function showToast(message, href) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.innerHTML = href
    ? `${escapeHtml(message)} <a href="${escapeHtml(href)}">View →</a>`
    : escapeHtml(message);
  toast.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 4000);
}

function markAdded(btn) {
  btn.classList.add("is-added");
  btn.disabled = true;
  btn.setAttribute("aria-label", "Already in your collection");
  const label = btn.querySelector(".quick-add-label");
  const icon = btn.querySelector(".quick-add-icon");
  if (label) label.textContent = "Added";
  if (icon) icon.textContent = "\u2713";
}

async function quickAdd(btn) {
  if (btn.disabled || btn.classList.contains("is-added")) return;
  const { id, name, sci } = btn.dataset;
  const label = btn.querySelector(".quick-add-label");
  const original = label ? label.textContent : "Add";
  btn.disabled = true;
  if (label) label.textContent = "Adding…";

  const body = new FormData();
  body.append("catalog_plant_id", id || "");
  body.append("nickname", name || "");
  body.append("species_name", name || "");
  body.append("scientific_name", sci || "");

  try {
    const response = await fetch("/api/collection/quick-add", {
      method: "POST",
      body,
    });
    if (response.status === 401) {
      window.location.href = "/auth/signin?next=/search";
      return;
    }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Could not add that plant.");
    }
    markAdded(btn);
    showToast(
      payload.status === "exists"
        ? `${name} is already in your collection.`
        : `Added ${name} to your collection.`,
      payload.url
    );
  } catch (err) {
    if (label) label.textContent = original;
    btn.disabled = false;
    showToast(err.message || "Couldn't add that plant. Try again?");
  }
}

resultsEl?.addEventListener("click", (event) => {
  const btn = event.target.closest(".quick-add-btn");
  if (!btn) return;
  event.preventDefault();
  event.stopPropagation();
  quickAdd(btn);
});

async function runSearch(query) {
  const url = `/api/plants/search?q=${encodeURIComponent(query)}&limit=24`;
  const response = await fetch(url);
  const data = await response.json();
  renderResults(data.results || []);
}

function commitSearch(query) {
  input.value = query;
  runSearch(query).catch(() => {
    resultsEl.innerHTML =
      '<p class="empty-state">Search is temporarily unavailable.</p>';
  });
  const next = query ? `/search?q=${encodeURIComponent(query)}` : "/search";
  history.replaceState(null, "", next);
}

input?.addEventListener("input", () => {
  clearTimeout(timer);
  const q = input.value.trim();
  timer = setTimeout(() => commitSearch(q), 180);
});

chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    commitSearch(chip.dataset.query || "");
    input.focus();
  });
});
