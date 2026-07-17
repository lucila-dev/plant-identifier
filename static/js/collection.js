(function () {
  const root = document.querySelector("[data-collection]");
  if (!root) return;

  const grid = document.getElementById("collection-grid");
  const toggleBtn = document.getElementById("select-toggle");
  const toolbar = document.getElementById("select-toolbar");
  const countEl = document.getElementById("select-count");
  const selectAllBtn = document.getElementById("select-all");
  const cancelBtn = document.getElementById("select-cancel");
  const deleteBtn = document.getElementById("delete-selected");

  if (!grid || !toggleBtn || !toolbar) return;

  const cards = () => Array.from(grid.querySelectorAll(".collection-card"));
  const inputs = () => Array.from(grid.querySelectorAll(".card-select-input"));
  const selectedIds = () =>
    inputs()
      .filter((i) => i.checked)
      .map((i) => i.value);

  let selectMode = false;

  let toast = document.querySelector(".toast");
  function showToast(message) {
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "toast";
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => {
      toast.classList.remove("is-visible");
    }, 2600);
  }

  function updateCounts() {
    const count = selectedIds().length;
    if (countEl) {
      countEl.textContent = count + (count === 1 ? " selected" : " selected");
    }
    if (deleteBtn) deleteBtn.disabled = count === 0;

    cards().forEach((card) => {
      const input = card.querySelector(".card-select-input");
      card.classList.toggle("is-selected", !!(input && input.checked));
    });

    if (selectAllBtn) {
      const all = inputs();
      const allChecked = all.length > 0 && all.every((i) => i.checked);
      selectAllBtn.textContent = allChecked ? "Clear all" : "Select all";
    }
  }

  function enterSelectMode() {
    selectMode = true;
    root.classList.add("select-mode");
    toolbar.hidden = false;
    toggleBtn.hidden = true;
    updateCounts();
  }

  function exitSelectMode() {
    selectMode = false;
    root.classList.remove("select-mode");
    toolbar.hidden = true;
    toggleBtn.hidden = false;
    inputs().forEach((i) => (i.checked = false));
    updateCounts();
  }

  toggleBtn.addEventListener("click", enterSelectMode);
  cancelBtn && cancelBtn.addEventListener("click", exitSelectMode);

  // In select mode, clicking a card toggles selection instead of navigating.
  grid.addEventListener("click", (event) => {
    if (!selectMode) return;
    const card = event.target.closest(".collection-card");
    if (!card) return;
    event.preventDefault();
    const input = card.querySelector(".card-select-input");
    if (!input) return;
    // Let native checkbox handling run when the checkbox itself was clicked.
    if (event.target !== input) {
      input.checked = !input.checked;
    }
    updateCounts();
  });

  grid.addEventListener("change", (event) => {
    if (event.target.classList.contains("card-select-input")) {
      updateCounts();
    }
  });

  selectAllBtn &&
    selectAllBtn.addEventListener("click", () => {
      const all = inputs();
      const allChecked = all.length > 0 && all.every((i) => i.checked);
      all.forEach((i) => (i.checked = !allChecked));
      updateCounts();
    });

  deleteBtn &&
    deleteBtn.addEventListener("click", async () => {
      const ids = selectedIds();
      if (!ids.length) return;

      const label =
        ids.length === 1 ? "this plant" : `these ${ids.length} plants`;
      if (!window.confirm(`Remove ${label} from your collection? This can't be undone.`)) {
        return;
      }

      deleteBtn.disabled = true;
      const originalText = deleteBtn.textContent;
      deleteBtn.textContent = "Deleting…";

      try {
        const res = await fetch("/api/collection/bulk-delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids }),
        });
        if (!res.ok) {
          throw new Error("Request failed");
        }
        const data = await res.json();
        const removed = data.deleted || 0;

        cards().forEach((card) => {
          const input = card.querySelector(".card-select-input");
          if (input && ids.includes(input.value)) {
            card.remove();
          }
        });

        showToast(
          removed === 1 ? "1 plant removed." : `${removed} plants removed.`
        );

        if (!grid.querySelector(".collection-card")) {
          window.location.reload();
          return;
        }
        exitSelectMode();
      } catch (err) {
        showToast("Couldn't delete those plants. Please try again.");
        deleteBtn.textContent = originalText;
        deleteBtn.disabled = false;
      }
    });

  updateCounts();
})();
