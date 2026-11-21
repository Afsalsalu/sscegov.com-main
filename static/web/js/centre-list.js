document.addEventListener("DOMContentLoaded", function () {
    const searchInput = document.getElementById("searchInput");
    const downloadUserListPdf = document.getElementById("downloadUserListPdf");
    const searchForm = searchInput?.form;
    let searchSubmitTimer;

    function updatePdfDownloadUrl() {
      if (!downloadUserListPdf || !searchInput) {
        return;
      }

      const exportUrl = new URL(
        downloadUserListPdf.dataset.exportUrl,
        window.location.origin
      );
      const searchValue = searchInput.value.trim();

      if (searchValue) {
        exportUrl.searchParams.set("search", searchValue);
      } else {
        exportUrl.searchParams.delete("search");
      }
      downloadUserListPdf.href = `${exportUrl.pathname}${exportUrl.search}`;
    }

    searchInput?.addEventListener("input", function () {
      updatePdfDownloadUrl();
      window.clearTimeout(searchSubmitTimer);
      searchSubmitTimer = window.setTimeout(function () {
        const currentSearch = new URL(window.location.href).searchParams.get("search") || "";
        if (searchInput.value.trim() !== currentSearch) {
          searchForm?.requestSubmit();
        }
      }, 400);
    });

    updatePdfDownloadUrl();
  });
