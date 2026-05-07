const DEFAULT_FEAR_ICON_URL = "/static/assets/fear/shrine-point.png";

const state = {
    config: null,
    analytics: null,
    editingRun: null,
};

const userNameById = new Map();
const weaponByName = new Map();
const boonByName = new Map();
const chartColors = [
    "#d6a94c",
    "#7f5fc7",
    "#52b788",
    "#c93b3b",
    "#56cfe1",
    "#f4a261",
];

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("run-form").addEventListener("submit", submitRun);
    document.getElementById("run-delete").addEventListener("click", deleteEditingRun);
    document.getElementById("open-run-modal").addEventListener("click", () => {
        resetRunForm();
        openRunModal();
    });
    document.getElementById("close-run-modal").addEventListener("click", closeRunModal);
    document.getElementById("run-modal").addEventListener("click", (event) => {
        if (event.target.id === "run-modal") {
            closeRunModal();
        }
    });
    document.addEventListener("click", () => closeAssetPickers());
    loadDashboard();
});

async function loadDashboard() {
    setStatus("Loading the crossroads...", "");

    let config;
    let analytics;
    try {
        [config, analytics] = await Promise.all([
            fetchJson("/api/config/public"),
            fetchJson("/api/analytics"),
        ]);
    } catch (error) {
        setStatus(error.message, "error");
        return;
    }

    state.config = config;
    state.analytics = analytics;
    syncFearIconFromConfig(config);
    userNameById.clear();
    weaponByName.clear();
    boonByName.clear();
    config.users.forEach((user) => userNameById.set(user.id, user.display_name));
    config.weapons.forEach((weapon) => weaponByName.set(weapon.name, weapon));
    config.boons.forEach((boon) => boonByName.set(boon.name, boon));

    renderForm(config);
    renderUsers(analytics.users);
    renderAnalytics(analytics);
    renderRecentRuns(analytics.recent_runs);
    setStatus("", "");
}

function syncFearIconFromConfig(config) {
    const img = document.querySelector(".fear-field-label .fear-icon");
    if (!img || !config?.fear?.image_url) {
        return;
    }
    img.src = config.fear.image_url;
}

function fearIconUrl() {
    return state.config?.fear?.image_url || DEFAULT_FEAR_ICON_URL;
}

function runDisplayPoints(run) {
    const raw = Number(run?.computed_win_score);
    if (!Number.isFinite(raw)) {
        return "—";
    }
    return String(Math.round(raw * 100));
}

async function refreshAnalytics(dateRangeDays) {
    const analytics = await fetchJson(`/api/analytics?date_range_days=${dateRangeDays}`);
    state.analytics = analytics;
    renderUsers(analytics.users);
    renderAnalytics(analytics);
    renderRecentRuns(analytics.recent_runs);
}

function renderForm(config) {
    renderAssetPicker({
        pickerId: "side-picker",
        inputId: "side",
        selectedId: "side-selected",
        options: config.sides.map((side) => ({
            value: side.id,
            label: side.label,
        })),
        emptyLabel: null,
    });
    renderAssetPicker({
        pickerId: "weapon-picker",
        inputId: "weapon",
        selectedId: "weapon-selected",
        options: config.weapons.map((weapon) => ({
            value: weapon.name,
            label: weapon.name,
            image_url: weapon.image_url,
        })),
        emptyLabel: "No weapon selected",
    });

    const boons = document.getElementById("boons");
    boons.innerHTML = config.boons
        .map(
            (boon) => `
                <label class="boon-option">
                    <input type="checkbox" name="boons" value="${escapeHtml(boon.name)}">
                    ${optionImage(boon, "boon-icon")}
                    <span>${escapeHtml(boon.name)}</span>
                </label>
            `,
        )
        .join("");
}

function renderUsers(users) {
    const cards = document.getElementById("user-cards");
    cards.innerHTML = users
        .map(
            (user) => `
                <article class="user-card">
                    <h3>${escapeHtml(user.display_name)}</h3>
                    <p class="score">${user.total}</p>
                    <div class="stat-row">
                        <span>Topside</span><strong>${user.topside}</strong>
                    </div>
                    <div class="stat-row">
                        <span>Bottomside</span><strong>${user.bottomside}</strong>
                    </div>
                    <div class="stat-row">
                        <span>Weapon</span>
                        <strong>${renderNamedAsset(user.favorite_weapon, weaponByName)}</strong>
                    </div>
                    <div class="pill-list">
                        ${renderPills(user.favorite_boons, boonByName)}
                    </div>
                </article>
            `,
        )
        .join("");
}

function renderAnalytics(analytics) {
    const container = document.getElementById("analytics");
    container.innerHTML = [
        analyticsCard(
            "Runs Over Time",
            `
                <div class="range-control">
                    <label>
                        Date Range
                        <input
                            id="analytics-range"
                            type="number"
                            min="1"
                            max="365"
                            value="${analytics.date_range_days}"
                        >
                    </label>
                    <button id="analytics-range-apply" type="button">Apply</button>
                </div>
                ${renderLineChart(analytics)}
                ${renderWinScoreStackedByUser(analytics)}
            `,
            "wide-card",
        ),
        analyticsCard("Total Victories", `<p class="score">${analytics.total_runs}</p>`),
        analyticsCard("Quick Stats", renderExtraMetrics(analytics.extra_metrics)),
        analyticsCard(
            "Win Score Leaderboard",
            renderWinScoreLeaderboard(analytics.win_score_leaderboard),
        ),
        analyticsCard("Fear", renderFearAnalytics(analytics.fear)),
        analyticsCard(
            "Victories by Realm",
            renderVictoryBarChart(analytics.by_side),
            "chart-card",
        ),
        analyticsCard(
            "Victories by Weapon",
            renderVictoryBarChart(analytics.by_weapon, weaponByName),
            "chart-card",
        ),
        analyticsCard(
            "Victories by Boon",
            renderVictoryBarChart(analytics.by_boon, boonByName),
            "chart-card",
        ),
    ].join("");

    document
        .getElementById("analytics-range-apply")
        .addEventListener("click", applyAnalyticsRange);
    document.getElementById("analytics-range").addEventListener("change", applyAnalyticsRange);
}

function renderRecentRuns(runs) {
    const container = document.getElementById("recent-runs");
    if (!runs.length) {
        container.innerHTML = '<p class="muted">No victories logged yet.</p>';
        return;
    }

    container.innerHTML = runs
        .map(
            (run) => `
                <article
                    class="run-item"
                    data-run-id="${escapeHtml(run.id)}"
                >
                    <div class="run-title">
                        <span>${escapeHtml(userNameById.get(run.user_id) || run.user_id)}</span>
                        <span>${formatSide(run.side)}</span>
                    </div>
                    <div class="muted">
                        ${renderNamedAsset(run.weapon, weaponByName)} · ${formatDate(run.created_at)}
                        · Score ${runDisplayPoints(run)}
                    </div>
                    ${
                        Number(run.fear) > 0
                            ? `<div class="run-fear-row"><img class="fear-icon" src="${escapeHtml(fearIconUrl())}" alt="" width="18" height="18"><span>Fear ${escapeHtml(String(run.fear))}</span></div>`
                            : ""
                    }
                    <div class="pill-list">${renderPills(run.boons, boonByName)}</div>
                    ${run.notes ? `<p>${escapeHtml(run.notes)}</p>` : ""}
                    <button
                        class="edit-run-button"
                        type="button"
                        data-run-id="${escapeHtml(run.id)}"
                    >
                        Edit
                    </button>
                </article>
            `,
        )
        .join("");
    container.onclick = (event) => openRunFromEvent(event, runs);
}

async function submitRun(event) {
    event.preventDefault();

    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const fearField = form.querySelector('input[name="fear"]');
    const fearRaw = (
        fearField && "value" in fearField ? fearField.value : ""
    )
        .toString()
        .trim();
    let fear = 0;
    if (fearRaw !== "") {
        const parsed = Number.parseInt(fearRaw, 10);
        if (Number.isFinite(parsed)) {
            fear = Math.min(99, Math.max(0, parsed));
        }
    }

    const payload = {
        access_code: document.getElementById("access-code").value,
        side: document.getElementById("side").value,
        weapon: document.getElementById("weapon").value || null,
        boons: [...form.querySelectorAll('input[name="boons"]:checked')].map(
            (input) => input.value,
        ),
        notes: document.getElementById("notes").value || null,
        fear,
    };

    button.disabled = true;
    setStatus("Recording victory...", "");

    try {
        const editingRun = state.editingRun;
        const response = await fetch(editingRun ? `/api/runs/${editingRun.id}` : "/api/runs", {
            method: editingRun ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || "Could not record victory.");
        }

        await loadDashboard();
        resetRunForm();
        setStatus(editingRun ? "Victory updated." : "Victory recorded.", "success");
        closeRunModal();
    } catch (error) {
        setStatus(error.message, "error");
    } finally {
        button.disabled = false;
    }
}

function openRunModal() {
    const modal = document.getElementById("run-modal");
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    document.getElementById("access-code").focus();
}

function closeRunModal() {
    const modal = document.getElementById("run-modal");
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    closeAssetPickers();
}

function openEditRunModal(run) {
    state.editingRun = run;
    document.getElementById("run-modal-eyebrow").textContent = "Revise a Victory";
    document.getElementById("run-modal-title").textContent = "Edit Run";
    document.getElementById("run-submit").textContent = "Save Changes";
    document.getElementById("run-delete").hidden = false;
    document.getElementById("access-code").value = "";
    setSelectedAsset("side", "side-selected", getSideOptions(), run.side);
    setSelectedAsset("weapon", "weapon-selected", getWeaponOptions(), run.weapon || "");
    document.getElementById("notes").value = run.notes || "";
    document.getElementById("fear").value =
        run.fear != null && Number(run.fear) > 0 ? String(run.fear) : "";
    document.querySelectorAll('input[name="boons"]').forEach((input) => {
        input.checked = run.boons.includes(input.value);
    });
    setStatus("Enter this runner's access code to save changes.", "");
    openRunModal();
}

function resetRunForm() {
    state.editingRun = null;
    document.getElementById("run-modal-eyebrow").textContent = "Log a Victory";
    document.getElementById("run-modal-title").textContent = "Add Run";
    document.getElementById("run-submit").textContent = "Record Victory";
    document.getElementById("run-delete").hidden = true;
    document.getElementById("run-form").reset();
    setSelectedAsset("side", "side-selected", getSideOptions(), getSideOptions()[0].value);
    setSelectedAsset("weapon", "weapon-selected", getWeaponOptions(), "");
    setStatus("", "");
}

function openRunFromEvent(event, runs) {
    const button = event.target.closest(".edit-run-button");
    if (!button) {
        return;
    }

    event.preventDefault();
    const run = runs.find((runItem) => runItem.id === button.dataset.runId);
    if (run) {
        openEditRunModal(run);
    }
}

async function deleteEditingRun() {
    const editingRun = state.editingRun;
    const accessCode = document.getElementById("access-code").value.trim();
    if (!editingRun) {
        return;
    }

    if (!accessCode) {
        setStatus("Enter this runner's access code to delete the run.", "error");
        return;
    }

    const confirmed = window.confirm("Delete this run? This cannot be undone.");
    if (!confirmed) {
        return;
    }

    try {
        const response = await fetch(`/api/runs/${editingRun.id}`, {
            method: "DELETE",
            headers: { "X-Access-Code": accessCode },
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || "Could not delete run.");
        }

        await loadDashboard();
        resetRunForm();
        closeRunModal();
    } catch (error) {
        setStatus(error.message, "error");
    }
}

function renderAssetPicker({
    pickerId,
    inputId,
    selectedId,
    options,
    emptyLabel,
}) {
    const picker = document.getElementById(pickerId);
    const currentValue =
        document.getElementById(inputId).value ||
        (emptyLabel === null ? options[0]?.value || "" : "");
    const allOptions =
        emptyLabel === null
            ? options
            : [{ value: "", label: emptyLabel }, ...options];

    picker.innerHTML = `
        <button
            class="asset-select-trigger"
            type="button"
            aria-expanded="false"
            aria-haspopup="listbox"
        >
            <span id="${selectedId}"></span>
            <span class="asset-select-caret">v</span>
        </button>
        <div class="asset-select-menu" role="listbox">
            ${allOptions
                .map((optionData) => assetPickerOption(optionData))
                .join("")}
        </div>
    `;

    picker
        .querySelector(".asset-select-trigger")
        .addEventListener("click", (event) => toggleAssetPicker(event, picker));

    picker.querySelectorAll(".asset-select-option").forEach((item) => {
        item.addEventListener("click", () => {
            setSelectedAsset(inputId, selectedId, allOptions, item.dataset.value);
            closeAssetPickers();
        });
    });

    setSelectedAsset(inputId, selectedId, allOptions, currentValue);
}

function assetPickerOption(optionData) {
    return `
        <button
            class="asset-select-option"
            type="button"
            role="option"
            data-value="${escapeHtml(optionData.value)}"
        >
            ${renderAssetChoice(optionData)}
        </button>
    `;
}

function renderAssetChoice(optionData) {
    if (!optionData.value) {
        return `<span class="asset-select-empty">${escapeHtml(optionData.label)}</span>`;
    }

    return `
        ${optionImage(optionData, "asset-option-icon")}
        <span>${escapeHtml(optionData.label)}</span>
    `;
}

function setSelectedAsset(inputId, selectedId, options, value) {
    const input = document.getElementById(inputId);
    const selected = document.getElementById(selectedId);
    const optionData = options.find((optionItem) => optionItem.value === value);

    input.value = optionData?.value || "";
    selected.innerHTML = renderAssetChoice(optionData || options[0]);
}

function toggleAssetPicker(event, picker) {
    event.stopPropagation();
    closeAssetPickers(picker);
    const isOpen = picker.classList.toggle("open");
    picker
        .querySelector(".asset-select-trigger")
        .setAttribute("aria-expanded", String(isOpen));
}

function closeAssetPickers(exceptPicker = null) {
    document.querySelectorAll(".asset-select").forEach((picker) => {
        if (picker === exceptPicker) {
            return;
        }

        picker.classList.remove("open");
        picker
            .querySelector(".asset-select-trigger")
            ?.setAttribute("aria-expanded", "false");
    });
}

function getSideOptions() {
    return state.config.sides.map((side) => ({
        value: side.id,
        label: side.label,
    }));
}

function getWeaponOptions() {
    return [
        { value: "", label: "No weapon selected" },
        ...state.config.weapons.map((weapon) => ({
            value: weapon.name,
            label: weapon.name,
            image_url: weapon.image_url,
        })),
    ];
}

function analyticsCard(title, body, extraClass = "") {
    return `
        <article class="analytics-card ${extraClass}">
            <h3>${escapeHtml(title)}</h3>
            ${body}
        </article>
    `;
}

async function applyAnalyticsRange() {
    const input = document.getElementById("analytics-range");
    const value = Math.max(1, Math.min(365, Number(input.value) || 7));
    input.value = value;

    try {
        await refreshAnalytics(value);
    } catch (error) {
        setStatus(error.message, "error");
    }
}

function renderLineChart(analytics) {
    const buckets = analytics.daily_runs;
    if (!buckets.length) {
        return '<p class="muted">No trend data available.</p>';
    }

    const series = state.config.users.flatMap((user, index) => {
        const color = chartColors[index % chartColors.length];
        return [
            {
                label: `${user.display_name} Topside`,
                color,
                dash: "",
                values: buckets.map((bucket) => bucket.by_user_topside[user.id] || 0),
            },
            {
                label: `${user.display_name} Bottomside`,
                color,
                dash: "8 6",
                values: buckets.map((bucket) => bucket.by_user_bottomside[user.id] || 0),
            },
            {
                label: `${user.display_name} Cumulative`,
                color,
                dash: "2 5",
                values: buckets.map((bucket) => bucket.by_user_cumulative[user.id] || 0),
            },
        ];
    });
    const maxValue = Math.max(1, ...series.flatMap((item) => item.values));
    const width = 760;
    const height = 280;
    const padding = { top: 18, right: 26, bottom: 42, left: 42 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const xForIndex = (index) =>
        padding.left + (chartWidth * index) / Math.max(1, buckets.length - 1);
    const yForValue = (value) =>
        padding.top + chartHeight - (chartHeight * value) / maxValue;
    const gridLines = [0, 0.25, 0.5, 0.75, 1]
        .map((ratio) => {
            const y = padding.top + chartHeight - chartHeight * ratio;
            const value = Math.round(maxValue * ratio);
            return `
                <line class="chart-grid" x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}"></line>
                <text class="chart-axis-label" x="${padding.left - 10}" y="${y + 4}" text-anchor="end">${value}</text>
            `;
        })
        .join("");
    const paths = series
        .map((item) => {
            const points = item.values
                .map((value, index) => `${xForIndex(index)},${yForValue(value)}`)
                .join(" ");
            return `
                <polyline
                    class="chart-line"
                    points="${points}"
                    stroke="${item.color}"
                    stroke-dasharray="${item.dash}"
                ></polyline>
            `;
        })
        .join("");
    const labels = buckets
        .map((bucket, index) => {
            if (buckets.length > 12 && index % Math.ceil(buckets.length / 6) !== 0) {
                return "";
            }

            return `
                <text
                    class="chart-axis-label"
                    x="${xForIndex(index)}"
                    y="${height - 14}"
                    text-anchor="middle"
                >${formatShortDate(bucket.date)}</text>
            `;
        })
        .join("");

    return `
        <div class="chart-wrap">
            <svg class="line-chart" viewBox="0 0 ${width} ${height}" role="img">
                <title>Runs over the last ${analytics.date_range_days} days</title>
                ${gridLines}
                <line class="chart-axis" x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}"></line>
                <line class="chart-axis" x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}"></line>
                ${paths}
                ${labels}
            </svg>
        </div>
        <div class="chart-legend chart-style-legend">
            ${[
                { label: "Topside", dash: "" },
                { label: "Bottomside", dash: "8 6" },
                { label: "Cumulative", dash: "2 5" },
            ]
                .map(
                    (item) => `
                        <span>
                            <svg viewBox="0 0 42 10" aria-hidden="true">
                                <line
                                    x1="2"
                                    y1="5"
                                    x2="40"
                                    y2="5"
                                    stroke="currentColor"
                                    stroke-width="3"
                                    stroke-linecap="round"
                                    stroke-dasharray="${item.dash}"
                                ></line>
                            </svg>
                            ${escapeHtml(item.label)}
                        </span>
                    `,
                )
                .join("")}
        </div>
        <div class="chart-legend chart-user-legend">
            ${state.config.users
                .map(
                    (user, index) => `
                        <span>
                            <i style="background: ${chartColors[index % chartColors.length]}"></i>
                            ${escapeHtml(user.display_name)}
                        </span>
                    `,
                )
                .join("")}
        </div>
    `;
}

function winScoreBarBottomPath(x, w, botTop, baselineY, rMax) {
    const r = Math.min(rMax, w / 2, Math.max(0, (baselineY - botTop) / 2 - 0.01));
    if (r < 0.5) {
        return `M ${x} ${botTop} L ${x + w} ${botTop} L ${x + w} ${baselineY} L ${x} ${baselineY} Z`;
    }
    return `M ${x} ${botTop} L ${x + w} ${botTop} L ${x + w} ${baselineY - r} A ${r} ${r} 0 0 1 ${x + w - r} ${baselineY} L ${x + r} ${baselineY} A ${r} ${r} 0 0 1 ${x} ${baselineY - r} L ${x} ${botTop} Z`;
}

function winScoreBarTopPath(x, w, topY, joinY, rMax) {
    const r = Math.min(rMax, w / 2, Math.max(0, (joinY - topY) / 2 - 0.01));
    if (r < 0.5) {
        return `M ${x} ${topY} L ${x + w} ${topY} L ${x + w} ${joinY} L ${x} ${joinY} Z`;
    }
    return `M ${x + r} ${topY} A ${r} ${r} 0 0 1 ${x} ${topY + r} L ${x} ${joinY} L ${x + w} ${joinY} L ${x + w} ${topY + r} A ${r} ${r} 0 0 1 ${x + w - r} ${topY} L ${x + r} ${topY} Z`;
}

function winScoreBarTopSoloPath(x, w, topY, baselineY, rMax) {
    const r = Math.min(rMax, w / 2, Math.max(0, (baselineY - topY) / 2 - 0.01));
    if (r < 0.5) {
        return `M ${x} ${topY} L ${x + w} ${topY} L ${x + w} ${baselineY} L ${x} ${baselineY} Z`;
    }
    return `M ${x + r} ${topY} A ${r} ${r} 0 0 1 ${x} ${topY + r} L ${x} ${baselineY} L ${x + w} ${baselineY} L ${x + w} ${topY + r} A ${r} ${r} 0 0 1 ${x + w - r} ${topY} L ${x + r} ${topY} Z`;
}

function renderWinScoreStackedByUser(analytics) {
    const rows = analytics.win_score_stacked_by_user || [];
    const caption =
        "Win score totals by player — all-time cumulative display points (not affected by the date range above).";

    if (!rows.length) {
        return `
            <div class="win-score-stack-section">
                <p class="muted win-score-stack-caption">${escapeHtml(caption)}</p>
                <p class="muted">No runs yet.</p>
            </div>
        `;
    }

    const width = 760;
    const height = 312;
    const padding = { top: 22, right: 18, bottom: 44, left: 46 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const baselineY = padding.top + chartHeight;

    const totals = rows.map(
        (r) => r.topside_display_points + r.bottomside_display_points,
    );
    const maxTotal = Math.max(1, ...totals);

    const bottomFill = "var(--violet)";
    const topFill = "var(--gold)";
    const n = rows.length;
    const gap = Math.min(14, Math.max(6, Math.floor(chartWidth / (n * 8))));
    const barWidth = Math.max(
        16,
        (chartWidth - gap * (n + 1)) / n,
    );

    const gridLines = [0, 0.25, 0.5, 0.75, 1]
        .map((ratio) => {
            const y = padding.top + chartHeight - chartHeight * ratio;
            const tickVal = Math.round(maxTotal * ratio);
            return `
                <line
                    class="chart-grid win-score-v-grid"
                    x1="${padding.left}"
                    y1="${y}"
                    x2="${width - padding.right}"
                    y2="${y}"
                ></line>
                <text
                    class="chart-axis-label win-score-v-axis-label"
                    x="${padding.left - 8}"
                    y="${y + 4}"
                    text-anchor="end"
                >${tickVal}</text>
            `;
        })
        .join("");

    const bars = rows
        .map((row, index) => {
            const botPts = row.bottomside_display_points;
            const topPts = row.topside_display_points;
            const totalPts = botPts + topPts;
            const totalBarH =
                maxTotal > 0 ? (totalPts / maxTotal) * chartHeight : 0;
            let botH = 0;
            let topH = 0;
            if (totalPts > 0) {
                botH = (botPts / totalPts) * totalBarH;
                topH = (topPts / totalPts) * totalBarH;
            }
            const x = padding.left + gap + index * (barWidth + gap);
            const rx = Math.min(6, barWidth / 2);
            const botY = baselineY - botH;
            const topY = baselineY - botH - topH;

            let shapes = "";
            if (botH > 0 && topH > 0) {
                const db = winScoreBarBottomPath(x, barWidth, botY, baselineY, rx);
                const dt = winScoreBarTopPath(x, barWidth, topY, botY, rx);
                shapes = `
                    <path class="win-score-v-segment win-score-v-bottom" fill="${bottomFill}" d="${db}"></path>
                    <path class="win-score-v-segment win-score-v-top" fill="${topFill}" d="${dt}"></path>`;
            } else if (botH > 0) {
                const db = winScoreBarBottomPath(x, barWidth, botY, baselineY, rx);
                shapes = `<path class="win-score-v-segment win-score-v-bottom" fill="${bottomFill}" d="${db}"></path>`;
            } else if (topH > 0) {
                const dt = winScoreBarTopSoloPath(x, barWidth, topY, baselineY, rx);
                shapes = `<path class="win-score-v-segment win-score-v-top" fill="${topFill}" d="${dt}"></path>`;
            }

            const minSegLabelH = 16;
            const botLabel =
                botH >= minSegLabelH
                    ? `<text
                    class="win-score-v-seg-label win-score-v-seg-label--bottom"
                    x="${x + barWidth / 2}"
                    y="${botY + botH / 2}"
                    text-anchor="middle"
                    dominant-baseline="middle"
                >${botPts}</text>`
                    : "";
            const topLabel =
                topH >= minSegLabelH
                    ? `<text
                    class="win-score-v-seg-label win-score-v-seg-label--top"
                    x="${x + barWidth / 2}"
                    y="${topY + topH / 2}"
                    text-anchor="middle"
                    dominant-baseline="middle"
                >${topPts}</text>`
                    : "";

            const label =
                row.display_name.length > 12
                    ? `${escapeHtml(row.display_name.slice(0, 11))}…`
                    : escapeHtml(row.display_name);

            return `
                ${shapes}
                ${botLabel}
                ${topLabel}
                <text
                    class="win-score-v-x-label"
                    x="${x + barWidth / 2}"
                    y="${height - 16}"
                    text-anchor="middle"
                >${label}</text>
            `;
        })
        .join("");

    return `
        <div class="win-score-stack-section">
            <p class="muted win-score-stack-caption">${escapeHtml(caption)}</p>
            <div class="chart-wrap win-score-stack-wrap">
                <svg
                    class="win-score-stacked-chart win-score-stacked-chart--vertical"
                    viewBox="0 0 ${width} ${height}"
                    role="img"
                >
                    <title>All-time win score by player, topside vs bottomside</title>
                    ${gridLines}
                    <line
                        class="chart-axis"
                        x1="${padding.left}"
                        y1="${padding.top}"
                        x2="${padding.left}"
                        y2="${baselineY}"
                    ></line>
                    <line
                        class="chart-axis"
                        x1="${padding.left}"
                        y1="${baselineY}"
                        x2="${width - padding.right}"
                        y2="${baselineY}"
                    ></line>
                    ${bars}
                </svg>
            </div>
            <div class="chart-legend win-score-stack-legend">
                <span class="win-score-stack-legend-item">
                    <i class="win-score-swatch" style="background: ${bottomFill}"></i>
                    Bottomside sum
                </span>
                <span class="win-score-stack-legend-item">
                    <i class="win-score-swatch" style="background: ${topFill}"></i>
                    Topside sum
                </span>
            </div>
        </div>
    `;
}

function renderVictoryBarChart(values, assetMap = new Map()) {
    const entries = Object.entries(values).sort((a, b) => b[1] - a[1]);
    if (!entries.length) {
        return '<p class="muted">No data yet.</p>';
    }

    const width = 520;
    const rowHeight = 34;
    const labelWidth = 210;
    const valueWidth = 42;
    const height = entries.length * rowHeight + 12;
    const maxValue = Math.max(1, ...entries.map((entry) => entry[1]));

    return `
        <div class="bar-chart-wrap">
            <svg class="victory-bar-chart" viewBox="0 0 ${width} ${height}" role="img">
                ${entries
                    .map(([label, value], index) => {
                        const y = index * rowHeight + 8;
                        const asset = assetMap.get(label);
                        const icon = asset?.image_url
                            ? `
                                <image
                                    href="${escapeHtml(asset.image_url)}"
                                    x="0"
                                    y="${y - 2}"
                                    width="24"
                                    height="24"
                                    preserveAspectRatio="xMidYMid meet"
                                ></image>
                            `
                            : "";
                        const labelX = asset?.image_url ? 32 : 0;
                        const barWidth =
                            ((width - labelWidth - valueWidth - 18) * value) / maxValue;
                        return `
                            ${icon}
                            <text class="bar-label" x="${labelX}" y="${y + 18}">
                                ${escapeHtml(formatSide(label))}
                            </text>
                            <rect
                                class="bar-track"
                                x="${labelWidth}"
                                y="${y}"
                                width="${width - labelWidth - valueWidth - 18}"
                                height="20"
                                rx="10"
                            ></rect>
                            <rect
                                class="bar-fill"
                                x="${labelWidth}"
                                y="${y}"
                                width="${barWidth}"
                                height="20"
                                rx="10"
                            ></rect>
                            <text class="bar-value" x="${width - valueWidth}" y="${y + 16}">
                                ${value}
                            </text>
                        `;
                    })
                    .join("")}
            </svg>
        </div>
    `;
}

function renderFearAnalytics(fear) {
    if (!fear) {
        return '<p class="muted">No fear data yet.</p>';
    }

    const icon = `<img class="fear-icon fear-analytics-icon" src="${escapeHtml(fearIconUrl())}" alt="" width="20" height="20">`;
    const avgLeader = fear.highest_avg_fear_user
        ? `${escapeHtml(fear.highest_avg_fear_user.display_name)} (avg ${fear.highest_avg_fear_user.avg_fear})`
        : "—";
    const maxLeader = fear.highest_max_fear_user
        ? `${escapeHtml(fear.highest_max_fear_user.display_name)} (max ${fear.highest_max_fear_user.max_fear})`
        : "—";
    const bucketParts = Object.entries(fear.fear_buckets || {}).map(
        ([label, count]) => `${escapeHtml(label)}: ${count}`,
    );
    const bucketsText = bucketParts.length ? bucketParts.join(" · ") : "—";

    const highestSingle =
        fear.max_fear_display_name != null && fear.max_fear_display_name !== ""
            ? `${fear.max_fear} (${escapeHtml(fear.max_fear_display_name)})`
            : String(fear.max_fear);

    return `
        <div class="metric-list fear-analytics">
            <div class="fear-analytics-title">${icon}<span>Fear overview</span></div>
            <div><span>Average fear (all runs)</span><strong>${fear.avg_fear}</strong></div>
            <div><span>Highest single fear</span><strong>${highestSingle}</strong></div>
            <div><span>Runs with fear &gt; 0</span><strong>${fear.runs_with_fear_positive} (${fear.pct_runs_fear_positive}%)</strong></div>
            <div><span>Avg fear · Topside</span><strong>${fear.avg_fear_topside}</strong></div>
            <div><span>Avg fear · Bottomside</span><strong>${fear.avg_fear_bottomside}</strong></div>
            <div><span>Max fear · Topside</span><strong>${fear.max_fear_topside}</strong></div>
            <div><span>Max fear · Bottomside</span><strong>${fear.max_fear_bottomside}</strong></div>
            <div><span>Highest avg fear</span><strong>${avgLeader}</strong></div>
            <div><span>Highest max fear</span><strong>${maxLeader}</strong></div>
            <div><span>Distribution</span><strong>${bucketsText}</strong></div>
        </div>
    `;
}

function renderWinScoreLeaderboard(wsl) {
    if (!wsl || !wsl.by_user) {
        return '<p class="muted">No leaderboard data.</p>';
    }

    const avgLeader = wsl.highest_avg_score_user
        ? `${escapeHtml(wsl.highest_avg_score_user.display_name)} (avg ${wsl.highest_avg_score_user.avg_display_points})`
        : "—";
    const maxLeader = wsl.highest_max_score_user
        ? `${escapeHtml(wsl.highest_max_score_user.display_name)} (max ${wsl.highest_max_score_user.max_display_points})`
        : "—";
    const bucketParts = Object.entries(wsl.score_buckets || {}).map(
        ([label, count]) => `${escapeHtml(label)}: ${count}`,
    );
    const bucketsText = bucketParts.length ? bucketParts.join(" · ") : "—";

    const highestSingle =
        wsl.max_score_display_name != null && wsl.max_score_display_name !== ""
            ? `${wsl.max_single_display_points} (${escapeHtml(wsl.max_score_display_name)})`
            : String(wsl.max_single_display_points ?? "—");

    const totalsRows = wsl.by_user
        .map(
            (u) => `
                <div>
                    <span>${escapeHtml(u.display_name)}</span>
                    <strong>${u.display_points_total}</strong>
                </div>
            `,
        )
        .join("");
    const s = wsl.settings || {};
    return `
        <div class="metric-list fear-analytics win-score-analytics">
            <div class="fear-analytics-title win-score-analytics-title">
                <span class="win-score-analytics-mark" aria-hidden="true">★</span>
                <span>Win Score Leaderboard</span>
            </div>
            <div><span>Average score (all runs)</span><strong>${wsl.avg_score}</strong></div>
            <div><span>Highest single score</span><strong>${highestSingle}</strong></div>
            <div><span>Highest max score</span><strong>${maxLeader}</strong></div>
            <div><span>Highest avg score</span><strong>${avgLeader}</strong></div>
            <div><span>Avg score · Topside</span><strong>${wsl.avg_score_topside}</strong></div>
            <div><span>Avg score · Bottomside</span><strong>${wsl.avg_score_bottomside}</strong></div>
            <div><span>Max score · Topside</span><strong>${wsl.max_score_topside}</strong></div>
            <div><span>Max score · Bottomside</span><strong>${wsl.max_score_bottomside}</strong></div>
            <div><span>Score distribution</span><strong>${bucketsText}</strong></div>
            <p class="muted win-score-totals-label">Totals by player</p>
            ${totalsRows}
            <div class="muted win-score-settings-footnote">
                Display points use stored per-run scores (×100). Weights:
                fear ${escapeHtml(String(s.fear_weight ?? ""))},
                topside ${escapeHtml(String(s.run_amount_topside ?? ""))},
                bottomside ${escapeHtml(String(s.run_amount_bottomside ?? ""))}.
                Grand total: ${wsl.grand_total_display_points}.
            </div>
        </div>
    `;
}

function renderExtraMetrics(metrics) {
    if (!metrics) {
        return '<p class="muted">No extra metrics yet.</p>';
    }

    const leader = metrics.current_leader
        ? `${escapeHtml(metrics.current_leader.display_name)} (${metrics.current_leader.total})`
        : "No leader yet";
    const momentum = [...metrics.recent_momentum]
        .sort((a, b) => b.total - a.total)
        .map((item) => `${escapeHtml(item.display_name)}: ${item.total}`)
        .join(" · ");

    return `
        <div class="metric-list">
            <div><span>Current Leader</span><strong>${leader}</strong></div>
            <div><span>Recent Momentum</span><strong>${momentum || "No recent wins"}</strong></div>
            ${metrics.user_stats
                .map(
                    (item) => `
                        <div>
                            <span>${escapeHtml(item.display_name)}</span>
                            <strong>
                                ${item.weapon_variety} weapons ·
                                ${item.boon_variety} boons ·
                                ${item.topside_percent}% top /
                                ${item.bottomside_percent}% bottom
                            </strong>
                        </div>
                    `,
                )
                .join("")}
        </div>
    `;
}

function renderBars(values, totalOverride = null) {
    const entries = Object.entries(values).sort((a, b) => b[1] - a[1]);
    if (!entries.length) {
        return '<p class="muted">No data yet.</p>';
    }

    const max = totalOverride || Math.max(...entries.map((entry) => entry[1]));
    return entries
        .map(([label, value]) => {
            const width = max ? Math.round((value / max) * 100) : 0;
            return `
                <div class="bar-row">
                    <span>${escapeHtml(formatSide(label))}</span>
                    <div class="bar"><span style="width: ${width}%"></span></div>
                    <strong>${value}</strong>
                </div>
            `;
        })
        .join("");
}

function renderPills(values, assetMap = new Map()) {
    if (!values.length) {
        return '<span class="muted">No boons yet</span>';
    }

    return values
        .map((value) => {
            const asset = assetMap.get(value);
            return `
                <span class="pill">
                    ${optionImage(asset, "pill-icon")}
                    ${escapeHtml(value)}
                </span>
            `;
        })
        .join("");
}

function renderNamedAsset(value, assetMap) {
    if (!value) {
        return "None yet";
    }

    const asset = assetMap.get(value);
    return `${optionImage(asset, "inline-icon")}${escapeHtml(value)}`;
}

function optionImage(optionData, className) {
    if (!optionData || !optionData.image_url) {
        return "";
    }

    return `
        <img
            class="${className}"
            src="${escapeHtml(optionData.image_url)}"
            alt=""
            loading="lazy"
        >
    `;
}

async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
    }

    return response.json();
}

function option(value, label) {
    return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
}

function formatSide(side) {
    if (side === "topside") {
        return "Topside";
    }

    if (side === "bottomside") {
        return "Bottomside";
    }

    return side;
}

function formatDate(value) {
    return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(new Date(value));
}

function formatShortDate(value) {
    return new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
    }).format(new Date(`${value}T00:00:00`));
}

function setStatus(message, statusClass) {
    const status = document.getElementById("form-status");
    status.textContent = message;
    status.className = statusClass ? `status ${statusClass}` : "status";
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
