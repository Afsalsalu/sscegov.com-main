document.addEventListener("DOMContentLoaded", function () {
    const searchInput = document.getElementById("searchInput");
    const tableRows = document.querySelectorAll("tbody tr");
    const downloadUserListPdf = document.getElementById("downloadUserListPdf");

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

    searchInput.addEventListener("input", function () {
      const filterText = searchInput.value.toLowerCase();

      tableRows.forEach(row => {
        const ownerCentre = row.querySelector("h6")?.textContent.toLowerCase();
        const username = row.cells[2]?.textContent.toLowerCase();
        if (
          (ownerCentre && ownerCentre.includes(filterText)) ||
          (username && username.includes(filterText))
        ) {
          row.style.display = ""; // Show the row
        } else {
          row.style.display = "none"; // Hide the row
        }
      });
      updatePdfDownloadUrl();
    });

    updatePdfDownloadUrl();
  });
