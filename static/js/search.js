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
      <a class="plant-row animate-rise" href="/plants/${encodeURIComponent(plant.id)}" style="--i:${index}">
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
      </a>`
    )
    .join("");
}

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
