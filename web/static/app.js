function openNewRunModal() {
    document.getElementById("newRunModal").style.display = "flex";
}

function closeModal() {
    document.getElementById("newRunModal").style.display = "none";
}

async function startRun(e) {
    e.preventDefault();
    const form = e.target;
    const data = new FormData(form);
    const btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = "Starting...";

    try {
        const resp = await fetch("/api/runs/start", {
            method: "POST",
            body: data,
        });
        const result = await resp.json();
        if (result.status === "started") {
            closeModal();
            location.reload();
        } else {
            alert(result.error || "Failed to start");
            btn.disabled = false;
            btn.textContent = "Start";
        }
    } catch (err) {
        alert("Error: " + err.message);
        btn.disabled = false;
        btn.textContent = "Start";
    }
}

// Poll for running status
let pollTimer = null;

function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(async () => {
        try {
            const resp = await fetch("/api/status");
            const data = await resp.json();
            if (data.status === "running") {
                location.reload();
            }
        } catch (e) {}
    }, 5000);
}

document.addEventListener("DOMContentLoaded", () => {
    const banner = document.querySelector(".running-banner");
    if (banner) startPolling();
});
