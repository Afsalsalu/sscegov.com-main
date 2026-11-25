document.addEventListener("DOMContentLoaded", function () {
  const modal = document.getElementById("serviceExportModal");
  const openButton = document.getElementById("openServiceExport");
  const closeButton = document.getElementById("closeServiceExport");
  const cancelButton = document.getElementById("cancelServiceExport");
  const form = document.getElementById("serviceExportForm");
  const searchInput = document.getElementById("searchInput");
  const exportSearch = document.getElementById("serviceExportSearch");
  const fields = Array.from(document.querySelectorAll(".service-export-field"));
  const submitButtons = Array.from(document.querySelectorAll(".service-export-submit"));
  const requiredField = fields.find(field => field.dataset.required === "true");

  if (!modal || !openButton || !form || !fields.length) {
    return;
  }

  function syncExportButtons() {
    if (requiredField && !requiredField.checked) {
      requiredField.checked = true;
    }
    const hasSelectedField = fields.some(field => field.checked);
    submitButtons.forEach(button => {
      button.disabled = !hasSelectedField;
    });
  }

  function closeModal() {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
    modal.setAttribute("aria-hidden", "true");
  }

  function openModal() {
    if (searchInput && exportSearch) {
      exportSearch.value = searchInput.value.trim();
    }
    syncExportButtons();
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    modal.setAttribute("aria-hidden", "false");
    closeButton?.focus();
  }

  fields.forEach(field => {
    field.addEventListener("change", syncExportButtons);
  });

  document.getElementById("selectAllServiceFields")?.addEventListener("click", function () {
    fields.forEach(field => {
      field.checked = true;
    });
    syncExportButtons();
  });

  document.getElementById("clearAllServiceFields")?.addEventListener("click", function () {
    fields.forEach(field => {
      field.checked = field.dataset.required === "true";
    });
    syncExportButtons();
  });

  form.addEventListener("submit", function (event) {
    syncExportButtons();
    if (!fields.some(field => field.checked)) {
      event.preventDefault();
      return;
    }

    if (searchInput && exportSearch) {
      exportSearch.value = searchInput.value.trim();
    }

    const submitter = event.submitter;
    if (submitter?.dataset.exportUrl) {
      form.action = submitter.dataset.exportUrl;
    }
  });

  openButton.addEventListener("click", openModal);
  closeButton?.addEventListener("click", closeModal);
  cancelButton?.addEventListener("click", closeModal);
  modal.addEventListener("click", function (event) {
    if (event.target === modal) {
      closeModal();
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && modal.getAttribute("aria-hidden") === "false") {
      closeModal();
    }
  });

  syncExportButtons();
});
