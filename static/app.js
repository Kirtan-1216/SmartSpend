/**
 * SmartSpend - Modern Fintech Client Application & Financial Copilot
 */

document.addEventListener("DOMContentLoaded", function () {
    // -------------------------------------------------------------------------
    // 1. Sleek Modern Custom Cursor / Pointer Effect
    // -------------------------------------------------------------------------
    initCustomCursor();

    // -------------------------------------------------------------------------
    // 2. Flash Notification Microinteractions
    // -------------------------------------------------------------------------
    initFlashToasts();

    // -------------------------------------------------------------------------
    // 3. KPI Number Count-Up Animation
    // -------------------------------------------------------------------------
    initNumberCountUp();

    // -------------------------------------------------------------------------
    // 4. Financial Copilot: Natural Language Quick Action & Live Preview
    // -------------------------------------------------------------------------
    initSmartCopilotInput();

    // -------------------------------------------------------------------------
    // 5. Data Visualization: Charts with Responsive Fallbacks
    // -------------------------------------------------------------------------
    initDashboardCharts();

    // -------------------------------------------------------------------------
    // 6. Transaction Table Search & Filtering
    // -------------------------------------------------------------------------
    initTransactionFiltering();
});

/**
 * Custom cursor with a small central dot and an elastic trailing ring.
 * Automatically disabled on touch screens and when prefers-reduced-motion is active.
 */
function initCustomCursor() {
    const isTouch = window.matchMedia("(pointer: coarse)").matches || "ontouchstart" in window;
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (isTouch || prefersReducedMotion) {
        return;
    }

    const dot = document.createElement("div");
    dot.className = "custom-cursor-dot";
    const ring = document.createElement("div");
    ring.className = "custom-cursor-ring";

    document.body.appendChild(dot);
    document.body.appendChild(ring);

    let mouseX = -100;
    let mouseY = -100;
    let ringX = -100;
    let ringY = -100;
    let isHovering = false;

    window.addEventListener("mousemove", function (e) {
        mouseX = e.clientX;
        mouseY = e.clientY;
        dot.style.transform = `translate3d(${mouseX}px, ${mouseY}px, 0)`;
    });

    function renderRing() {
        // Smooth trailing interpolation
        ringX += (mouseX - ringX) * 0.18;
        ringY += (mouseY - ringY) * 0.18;
        const scale = isHovering ? " scale(1.6)" : " scale(1)";
        ring.style.transform = `translate3d(${ringX}px, ${ringY}px, 0)${scale}`;
        requestAnimationFrame(renderRing);
    }
    requestAnimationFrame(renderRing);

    // Hover effect on interactive elements
    const interactiveSelectors = "a, button, input, select, textarea, .pill, .stat-card, .clickable, [role='button']";
    document.addEventListener("mouseover", function (e) {
        if (e.target.closest(interactiveSelectors)) {
            isHovering = true;
            ring.classList.add("cursor-hover");
            dot.classList.add("cursor-hover");
        }
    });

    document.addEventListener("mouseout", function (e) {
        if (e.target.closest(interactiveSelectors)) {
            isHovering = false;
            ring.classList.remove("cursor-hover");
            dot.classList.remove("cursor-hover");
        }
    });
}

/**
 * Handle dismissible flash notifications with auto-close and slide animation.
 */
function initFlashToasts() {
    const flashes = document.querySelectorAll(".flash-toast, .flash");
    flashes.forEach(function (flash) {
        // Add close button if not present
        if (!flash.querySelector(".flash-close")) {
            const closeBtn = document.createElement("button");
            closeBtn.className = "flash-close";
            closeBtn.innerHTML = "&times;";
            closeBtn.setAttribute("aria-label", "Close notification");
            closeBtn.addEventListener("click", function () {
                dismissToast(flash);
            });
            flash.appendChild(closeBtn);
        }

        setTimeout(function () {
            dismissToast(flash);
        }, 5000);
    });

    function dismissToast(el) {
        el.style.transition = "opacity 0.4s ease, transform 0.4s ease";
        el.style.opacity = "0";
        el.style.transform = "translateY(-12px)";
        setTimeout(function () {
            if (el.parentNode) el.remove();
        }, 400);
    }
}

/**
 * Smooth count-up animation for numerical statistics on page load.
 */
function initNumberCountUp() {
    const numbers = document.querySelectorAll("[data-counter]");
    if (!numbers.length) return;

    numbers.forEach(function (el) {
        const target = parseFloat(el.getAttribute("data-counter") || "0");
        const prefix = el.getAttribute("data-prefix") || "₹";
        const decimals = parseInt(el.getAttribute("data-decimals") || "2", 10);
        const duration = 900;
        const startTime = performance.now();

        function updateNumber(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // Ease-out cubic
            const ease = 1 - Math.pow(1 - progress, 3);
            const currentVal = target * ease;

            el.textContent = `${prefix}${currentVal.toLocaleString("en-IN", {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals,
            })}`;

            if (progress < 1) {
                requestAnimationFrame(updateNumber);
            } else {
                el.textContent = `${prefix}${target.toLocaleString("en-IN", {
                    minimumFractionDigits: decimals,
                    maximumFractionDigits: decimals,
                })}`;
            }
        }
        requestAnimationFrame(updateNumber);
    });
}

/**
 * Natural language command bar with live parsing preview and interactive confirm chip.
 */
function initSmartCopilotInput() {
    const input = document.getElementById("smart_input");
    const previewContainer = document.getElementById("smart-preview-container");
    const previewChip = document.getElementById("smart-preview-chip");
    const csrf = document.querySelector("input[name='csrf_token']");
    const pills = document.querySelectorAll(".copilot-suggestion-pill");

    if (!input || !previewContainer) return;

    let debounceTimer = null;

    input.addEventListener("input", function () {
        clearTimeout(debounceTimer);
        const text = input.value.trim();
        if (!text) {
            previewContainer.classList.add("hidden");
            return;
        }

        debounceTimer = setTimeout(function () {
            fetch("/api/parse", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrf ? csrf.value : "",
                },
                body: JSON.stringify({ text: text }),
            })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data && data.amount > 0) {
                        const typeBadge = data.tx_type === "income" ? "income-badge" : "expense-badge";
                        const typeLabel = data.tx_type === "income" ? "Income" : "Expense";
                        const formattedAmt = parseFloat(data.amount).toLocaleString("en-IN", {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                        });

                        previewChip.innerHTML = `
                            <span class="preview-badge ${typeBadge}">${typeLabel}</span>
                            <span class="preview-amt">₹${formattedAmt}</span>
                            <span class="preview-dot">·</span>
                            <span class="preview-cat">${data.category}</span>
                            <span class="preview-dot">·</span>
                            <span class="preview-date">${data.date}</span>
                        `;
                        previewContainer.classList.remove("hidden");
                    } else {
                        previewChip.innerHTML = `<span class="preview-hint">Keep typing... (e.g. 'Spent 500 on dinner yesterday')</span>`;
                        previewContainer.classList.remove("hidden");
                    }
                })
                .catch(function () {
                    previewContainer.classList.add("hidden");
                });
        }, 300);
    });

    // Suggestion pills autofill
    pills.forEach(function (pill) {
        pill.addEventListener("click", function () {
            const promptText = pill.getAttribute("data-prompt");
            if (promptText) {
                input.value = promptText;
                input.focus();
                input.dispatchEvent(new Event("input"));
            }
        });
    });
}

/**
 * Chart.js financial charts with modern fintech gradients and empty states.
 */
function initDashboardCharts() {
    const pieCanvas = document.getElementById("pieChart");
    const barCanvas = document.getElementById("barChart");
    if (!pieCanvas || !barCanvas) return;

    fetch("/api/data")
        .then(function (response) { return response.json(); })
        .then(function (data) {
            const pieEmpty = document.getElementById("pieEmpty");
            const barEmpty = document.getElementById("barEmpty");
            const categories = data.categories || {};
            const catKeys = Object.keys(categories);
            const catVals = Object.values(categories);
            const hasCategories = catKeys.length > 0 && catVals.some(function (v) { return Number(v) > 0; });

            // 1. Donut Chart for Categories
            if (hasCategories) {
                if (pieEmpty) pieEmpty.classList.add("hidden");
                const colors = [
                    "#6366f1", "#06b6d4", "#10b981", "#f59e0b",
                    "#ec4899", "#8b5cf6", "#3b82f6", "#14b8a6",
                    "#f97316", "#e11d48", "#84cc16", "#a855f7"
                ];

                new Chart(pieCanvas.getContext("2d"), {
                    type: "doughnut",
                    data: {
                        labels: catKeys,
                        datasets: [{
                            data: catVals,
                            backgroundColor: colors.slice(0, catKeys.length),
                            borderColor: "#0f172a",
                            borderWidth: 2,
                            hoverOffset: 6,
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: "68%",
                        plugins: {
                            legend: {
                                position: "bottom",
                                labels: {
                                    color: "#cbd5e1",
                                    font: { family: "'Inter', sans-serif", size: 12 },
                                    padding: 14,
                                    usePointStyle: true,
                                    pointStyle: "circle",
                                },
                            },
                            tooltip: {
                                backgroundColor: "rgba(15, 23, 42, 0.95)",
                                titleColor: "#f8fafc",
                                bodyColor: "#cbd5e1",
                                borderColor: "rgba(255, 255, 255, 0.1)",
                                borderWidth: 1,
                                padding: 12,
                                boxPadding: 6,
                                usePointStyle: true,
                                callbacks: {
                                    label: function (ctx) {
                                        const val = parseFloat(ctx.raw || 0);
                                        const total = catVals.reduce(function (a, b) { return a + b; }, 0);
                                        const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
                                        return ` ${ctx.label}: ₹${val.toLocaleString("en-IN", { minimumFractionDigits: 2 })} (${pct}%)`;
                                    },
                                },
                            },
                        },
                    },
                });
            } else if (pieEmpty) {
                pieEmpty.classList.remove("hidden");
            }

            // 2. Bar Chart for 7-Day Spending
            if (data.days) {
                const dayLabels = Object.keys(data.days).map(function (d) {
                    const parts = d.split("-");
                    return parts.length === 3 ? `${parts[2]}/${parts[1]}` : d;
                });
                const dayValues = Object.values(data.days);
                const hasDays = dayValues.some(function (v) { return Number(v) > 0; });

                if (hasDays) {
                    if (barEmpty) barEmpty.classList.add("hidden");
                    const ctx = barCanvas.getContext("2d");
                    const gradient = ctx.createLinearGradient(0, 0, 0, 260);
                    gradient.addColorStop(0, "rgba(99, 102, 241, 0.85)");
                    gradient.addColorStop(1, "rgba(99, 102, 241, 0.2)");

                    new Chart(ctx, {
                        type: "bar",
                        data: {
                            labels: dayLabels,
                            datasets: [{
                                label: "Daily Spend",
                                data: dayValues,
                                backgroundColor: gradient,
                                hoverBackgroundColor: "#818cf8",
                                borderRadius: 6,
                                borderSkipped: false,
                            }],
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    backgroundColor: "rgba(15, 23, 42, 0.95)",
                                    titleColor: "#f8fafc",
                                    bodyColor: "#cbd5e1",
                                    borderColor: "rgba(255, 255, 255, 0.1)",
                                    borderWidth: 1,
                                    padding: 12,
                                    callbacks: {
                                        label: function (ctx) {
                                            return ` ₹${parseFloat(ctx.raw).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
                                        },
                                    },
                                },
                            },
                            scales: {
                                x: {
                                    grid: { display: false },
                                    ticks: { color: "#94a3b8", font: { family: "'Inter', sans-serif", size: 11 } },
                                },
                                y: {
                                    grid: { color: "rgba(255, 255, 255, 0.05)" },
                                    ticks: {
                                        color: "#94a3b8",
                                        font: { family: "'Inter', sans-serif", size: 11 },
                                        callback: function (val) { return `₹${val}`; },
                                    },
                                },
                            },
                        },
                    });
                } else if (barEmpty) {
                    barEmpty.classList.remove("hidden");
                }
            }
        })
        .catch(function (err) {
            console.error("[SmartSpend] Error loading chart telemetry:", err);
        });
}

/**
 * Filter transactions table by Type (All / Expense / Income) and live keyword search.
 */
function initTransactionFiltering() {
    const filterTabs = document.querySelectorAll(".tx-filter-tab");
    const searchInput = document.getElementById("tx-search-input");
    const rows = document.querySelectorAll(".tx-table tbody tr");
    const emptyMsg = document.getElementById("tx-filter-empty");

    if (!rows.length) return;

    let activeFilter = "all";

    function applyFilters() {
        const query = searchInput ? searchInput.value.toLowerCase().trim() : "";
        let visibleCount = 0;

        rows.forEach(function (row) {
            const txType = (row.getAttribute("data-tx-type") || "").toLowerCase();
            const textContent = row.textContent.toLowerCase();

            const matchesType = (activeFilter === "all") || (txType === activeFilter);
            const matchesQuery = !query || textContent.includes(query);

            if (matchesType && matchesQuery) {
                row.style.display = "";
                visibleCount++;
            } else {
                row.style.display = "none";
            }
        });

        if (emptyMsg) {
            if (visibleCount === 0) {
                emptyMsg.classList.remove("hidden");
            } else {
                emptyMsg.classList.add("hidden");
            }
        }
    }

    filterTabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
            filterTabs.forEach(function (t) { t.classList.remove("active"); });
            tab.classList.add("active");
            activeFilter = tab.getAttribute("data-filter") || "all";
            applyFilters();
        });
    });

    if (searchInput) {
        searchInput.addEventListener("input", applyFilters);
    }
}
