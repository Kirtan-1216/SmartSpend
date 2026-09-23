document.addEventListener("DOMContentLoaded", function () {
    const flashes = document.querySelectorAll(".flash-toast, .flash, .alert, .notification");
    flashes.forEach(function (flash) {
        setTimeout(function () {
            flash.style.transition = "opacity 0.5s ease, transform 0.5s ease";
            flash.style.opacity = "0";
            flash.style.transform = "translateY(-10px)";
            setTimeout(function () {
                if (flash.parentNode) {
                    flash.remove();
                }
            }, 500);
        }, 3000);
    });


    const pieCanvas = document.getElementById("pieChart");
    const barCanvas = document.getElementById("barChart");
    if (pieCanvas && barCanvas) {
        fetch("/api/data")
            .then(function (response) { return response.json(); })
            .then(function (data) {
                const pieEmpty = document.getElementById("pieEmpty");
                const barEmpty = document.getElementById("barEmpty");
                const hasCategories = data.categories && Object.keys(data.categories).length > 0;
                const dayValues = data.days ? Object.values(data.days) : [];
                const hasDays = dayValues.some(function (value) { return Number(value) > 0; });

                if (hasCategories) {
                    new Chart(pieCanvas.getContext("2d"), {
                        type: "pie",
                        data: {
                            labels: Object.keys(data.categories),
                            datasets: [{
                                data: Object.values(data.categories),
                                backgroundColor: ["#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6", "#ec4899", "#6366f1"]
                            }]
                        },
                        options: {
                            responsive: true,
                            plugins: {
                                legend: { position: "bottom", labels: { color: "#f8fafc" } },
                                title: { display: true, text: "Spending by category", color: "#f8fafc" }
                            }
                        }
                    });
                } else if (pieEmpty) {
                    pieEmpty.classList.remove("hidden");
                }

                if (data.days) {
                    new Chart(barCanvas.getContext("2d"), {
                        type: "bar",
                        data: {
                            labels: Object.keys(data.days),
                            datasets: [{
                                label: "Daily spending",
                                data: Object.values(data.days),
                                backgroundColor: "#4f46e5",
                                borderRadius: 4
                            }]
                        },
                        options: {
                            responsive: true,
                            plugins: {
                                legend: { display: false },
                                title: { display: true, text: "Last 7 days spending", color: "#f8fafc" }
                            },
                            scales: {
                                x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.1)" } },
                                y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.1)" } }
                            }
                        }
                    });
                    if (!hasDays && barEmpty) {
                        barEmpty.classList.remove("hidden");
                    }
                }
            })
            .catch(function (err) {
                console.error("Error fetching chart data:", err);
            });
    }

    const smartInput = document.getElementById("smart_input");
    const preview = document.getElementById("smart-preview");
    const csrf = document.querySelector("#smart-form input[name='csrf_token']");
    if (smartInput && preview) {
        let timer = null;
        smartInput.addEventListener("input", function () {
            clearTimeout(timer);
            timer = setTimeout(function () {
                const text = smartInput.value.trim();
                if (!text) {
                    preview.textContent = "";
                    return;
                }
                fetch("/api/parse", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRF-Token": csrf ? csrf.value : ""
                    },
                    body: JSON.stringify({ text: text })
                })
                    .then(function (response) { return response.json(); })
                    .then(function (parsed) {
                        if (parsed.amount > 0) {
                            preview.textContent = "Detected: " + parsed.tx_type + " ₹" + parsed.amount + " / " + parsed.category + " / " + parsed.date;
                        } else {
                            preview.textContent = "Could not detect an amount yet.";
                        }
                    })
                    .catch(function () {
                        preview.textContent = "";
                    });
            }, 350);
        });
    }
});
