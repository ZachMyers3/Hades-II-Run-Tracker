const state = {
    config: null,
    analytics: null,
};

const userNameById = new Map();
const weaponByName = new Map();
const boonByName = new Map();

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("run-form").addEventListener("submit", submitRun);
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

function renderForm(config) {
    const sideSelect = document.getElementById("side");
    sideSelect.innerHTML = config.sides
        .map((side) => option(side.id, side.label))
        .join("");

    const weaponSelect = document.getElementById("weapon");
    weaponSelect.innerHTML = [
        '<option value="">No weapon selected</option>',
        ...config.weapons.map((weapon) => option(weapon.name, weapon.name)),
    ].join("");

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
        analyticsCard("Total Victories", `<p class="score">${analytics.total_runs}</p>`),
        analyticsCard("By Realm", renderBars(analytics.by_side, analytics.total_runs)),
        analyticsCard("By Weapon", renderBars(analytics.by_weapon)),
        analyticsCard("By Boon", renderBars(analytics.by_boon)),
    ].join("");
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
    const button = form.querySelector("button");
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
        setStatus("Victory recorded.", "success");
    } catch (error) {
        setStatus(error.message, "error");
    } finally {
        button.disabled = false;
    }
}

function analyticsCard(title, body) {
    return `
        <article class="analytics-card">
            <h3>${escapeHtml(title)}</h3>
            ${body}
        </article>
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
