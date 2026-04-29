const state = {
    config: null,
    analytics: null,
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
    document.getElementById("open-run-modal").addEventListener("click", openRunModal);
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
            `,
            "wide-card",
        ),
        analyticsCard("Total Victories", `<p class="score">${analytics.total_runs}</p>`),
        analyticsCard("Quick Stats", renderExtraMetrics(analytics.extra_metrics)),
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
                <article class="run-item">
                    <div class="run-title">
                        <span>${escapeHtml(userNameById.get(run.user_id) || run.user_id)}</span>
                        <span>${formatSide(run.side)}</span>
                    </div>
                    <div class="muted">
                        ${renderNamedAsset(run.weapon, weaponByName)} · ${formatDate(run.created_at)}
                    </div>
                    <div class="pill-list">${renderPills(run.boons, boonByName)}</div>
                    ${run.notes ? `<p>${escapeHtml(run.notes)}</p>` : ""}
                </article>
            `,
        )
        .join("");
}

async function submitRun(event) {
    event.preventDefault();

    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const payload = {
        access_code: document.getElementById("access-code").value,
        side: document.getElementById("side").value,
        weapon: document.getElementById("weapon").value || null,
        boons: [...form.querySelectorAll('input[name="boons"]:checked')].map(
            (input) => input.value,
        ),
        notes: document.getElementById("notes").value || null,
    };

    button.disabled = true;
    setStatus("Recording victory...", "");

    try {
        const response = await fetch("/api/runs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || "Could not record victory.");
        }

        await loadDashboard();
        form.reset();
        setSelectedAsset("side", "side-selected", getSideOptions(), getSideOptions()[0].value);
        setSelectedAsset("weapon", "weapon-selected", getWeaponOptions(), "");
        setStatus("Victory recorded.", "success");
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
