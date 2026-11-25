
const fileTable = document.getElementById("fileTable");

function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024)
        return (bytes / 1024).toFixed(2) + " KB";

    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
}

async function loadDashboard() {
    try {
        const response = await fetch("/api/status");
        if (!response.ok) throw new Error("Unable to load status");

        const data = await response.json();

        document.getElementById("totalFiles").textContent =
            data.total_files;

        document.getElementById("storageUsed").textContent =
            data.storage_mb + " MB";

        document.getElementById("dashboardStatus").textContent =
            "Online";

        await loadFiles();

    } catch (error) {
        document.getElementById("dashboardStatus").textContent =
            "Offline";

        fileTable.textContent = "Unable to load dashboard data.";
        console.error(error);
    }
}

async function loadFiles() {
    const response = await fetch("/api/files");
    if (!response.ok) throw new Error("Unable to load files");

    const data = await response.json();

    fileTable.replaceChildren();

    if (data.files.length === 0) {
        const row = fileTable.insertRow();
        const cell = row.insertCell();
        cell.colSpan = 3;
        cell.textContent = "No files available on server.";
        return;
    }

    data.files.forEach(file => {
        const row = fileTable.insertRow();

        const nameCell = row.insertCell();
        nameCell.textContent = "📄 " + file.filename;

        const sizeCell = row.insertCell();
        sizeCell.textContent = formatSize(file.size);

        const actionCell = row.insertCell();

        const downloadBtn = document.createElement("button");
        downloadBtn.textContent = "Download";
        downloadBtn.className = "action-btn";
        downloadBtn.addEventListener("click", () => {
            window.location.href =
                "/api/download/" + encodeURIComponent(file.filename);
        });

        const deleteBtn = document.createElement("button");
        deleteBtn.textContent = "Delete";
        deleteBtn.className = "action-btn delete-btn";

        deleteBtn.addEventListener("click", async () => {
            if (!confirm(`Are you sure you want to delete ${file.filename}?`)) {
                return;
            }

            try {
                const result = await fetch(
                    "/api/delete/" + encodeURIComponent(file.filename),
                    { method: "POST" }
                );

                const data = await result.json();

                if (!result.ok) {
                    throw new Error(data.message || "Delete failed");
                }

                alert(data.message);
                await loadDashboard();

            } catch (error) {
                alert(error.message);
            }
        });

        actionCell.append(downloadBtn, deleteBtn);
    });
}

document.getElementById("refreshBtn")
    .addEventListener("click", loadDashboard);

loadDashboard();
