const ADMIN_PASSWORD_KEY = "hadesAdminPassword";

const DEFAULT_FEAR_ICON_URL = "/static/assets/fear/shrine-point.png";

const state = {
    users: [],
    runs: [],
    config: null,
    publicConfig: null,
};

document.addEventListener("DOMContentLoaded", () => {
    document
        .getElementById("admin-login-form")
        .addEventListener("submit", submitLogin);
    document.getElementById("logout-admin").addEventListener("click", logout);
    document.getElementById("refresh-admin").addEventListener("click", loadAdmin);
    document.getElementById("export-backup").addEventListener("click", exportBackup);
    document.getElementById("import-backup").addEventListener("click", pickImportBackup);
    document
        .getElementById("import-backup-file")
        .addEventListener("change", importBackupFromFile);
    document.getElementById("add-user-form").addEventListener("submit", addUser);
    document
        .getElementById("admin-config-form")
        .addEventListener("submit", saveConfig);
    document.getElementById("admin-users").addEventListener("submit", saveUser);
    document.getElementById("admin-users").addEventListener("click", handleUserClick);
    document.getElementById("admin-runs").addEventListener("submit", saveRun);
    document.getElementById("admin-runs").addEventListener("click", handleRunClick);

    if (getPassword()) {
        showAdmin();
        loadAdmin();
    } else {
        showLogin();
    }
});

async function submitLogin(event) {
    event.preventDefault();
    const password = document.getElementById("admin-password").value.trim();
    setLoginStatus("Unlocking...", "");

    try {
        await fetchJson("/api/admin/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password }),
        });
        sessionStorage.setItem(ADMIN_PASSWORD_KEY, password);
        document.getElementById("admin-password").value = "";
        showAdmin();
        await loadAdmin();
    } catch (error) {
        setLoginStatus(error.message, "error");
    }
}

async function loadAdmin() {
    setAdminStatus("Loading admin data...", "");

    try {
        const [users, runs, config, publicConfig] = await Promise.all([
            adminFetch("/api/admin/users"),
            adminFetch("/api/admin/runs"),
            adminFetch("/api/admin/config"),
            fetchJson("/api/config/public"),
        ]);
        state.users = users;
        state.runs = runs;
        state.config = config;
        state.publicConfig = publicConfig;
        renderUsers();
        renderRuns();
        renderConfig();
        setAdminStatus("Admin data loaded.", "success");
    } catch (error) {
        if (error.status === 403) {
            logout();
            setLoginStatus("Admin session expired or password is invalid.", "error");
            return;
        }

        setAdminStatus(error.message, "error");
    }
}

async function addUser(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = {
        id: form.elements["id"].value.trim(),
        display_name: form.elements["display_name"].value.trim(),
        access_code: form.elements["access_code"].value.trim(),
    };

    try {
        await adminFetch("/api/admin/users", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        form.reset();
        await loadAdmin();
        setAdminStatus("User added.", "success");
    } catch (error) {
        setAdminStatus(error.message, "error");
    }
}

async function saveUser(event) {
    event.preventDefault();
    const form = event.target.closest(".admin-user-form");
    if (!form) {
        return;
    }

    const userId = form.dataset.userId;
    const payload = {
        display_name: form.elements["display_name"].value.trim(),
        access_code: form.elements["access_code"].value.trim(),
    };

    try {
        await adminFetch(`/api/admin/users/${encodeURIComponent(userId)}`, {
            method: "PUT",
            body: JSON.stringify(payload),
        });
        await loadAdmin();
        setAdminStatus("User saved.", "success");
    } catch (error) {
        setAdminStatus(error.message, "error");
    }
}

async function handleUserClick(event) {
    const rotateButton = event.target.closest("[data-action='rotate-user-code']");
    const deleteButton = event.target.closest("[data-action='delete-user']");

    if (rotateButton) {
        await rotateUserCode(rotateButton.dataset.userId);
    }

    if (deleteButton) {
        await deleteUser(deleteButton.dataset.userId);
    }
}

async function rotateUserCode(userId) {
    try {
        await adminFetch(
            `/api/admin/users/${encodeURIComponent(userId)}/rotate-code`,
            { method: "POST" },
        );
        await loadAdmin();
        setAdminStatus("Access code rotated.", "success");
    } catch (error) {
        setAdminStatus(error.message, "error");
    }
}

async function deleteUser(userId) {
    const user = state.users.find((item) => item.id === userId);
    if (user?.run_count > 0) {
        setAdminStatus("Users with logged runs cannot be deleted.", "error");
        return;
    }

    if (!window.confirm(`Delete user ${userId}? This cannot be undone.`)) {
        return;
    }

    try {
        await adminFetch(`/api/admin/users/${encodeURIComponent(userId)}`, {
            method: "DELETE",
        });
        await loadAdmin();
        setAdminStatus("User deleted.", "success");
    } catch (error) {
        setAdminStatus(error.message, "error");
    }
}

async function saveRun(event) {
    event.preventDefault();
    const form = event.target.closest(".admin-run-form");
    if (!form) {
        return;
    }

    const runId = form.dataset.runId;
    const fearRaw = (form.elements["fear"]?.value || "").trim();
    let fear = 0;
    if (fearRaw !== "") {
        const parsed = Number.parseInt(fearRaw, 10);
        if (Number.isFinite(parsed)) {
            fear = Math.min(99, Math.max(0, parsed));
        }
    }

    const payload = {
        user_id: form.elements["user_id"].value,
        side: form.elements["side"].value,
        weapon: form.elements["weapon"].value || null,
        boons: splitCsv(form.elements["boons"].value),
        notes: form.elements["notes"].value || null,
        fear,
    };

    try {
        await adminFetch(`/api/admin/runs/${encodeURIComponent(runId)}`, {
            method: "PUT",
            body: JSON.stringify(payload),
        });
        await loadAdmin();
        setAdminStatus("Run saved.", "success");
    } catch (error) {
        setAdminStatus(error.message, "error");
    }
}

async function handleRunClick(event) {
    const deleteButton = event.target.closest("[data-action='delete-run']");
    if (!deleteButton) {
        return;
    }

    if (!window.confirm("Delete this run? This cannot be undone.")) {
        return;
    }

    try {
        await adminFetch(
            `/api/admin/runs/${encodeURIComponent(deleteButton.dataset.runId)}`,
            { method: "DELETE" },
        );
        await loadAdmin();
        setAdminStatus("Run deleted.", "success");
    } catch (error) {
        setAdminStatus(error.message, "error");
    }
}

async function saveConfig(event) {
    event.preventDefault();

    let weapons;
    let boons;
    let fear;
    try {
        weapons = JSON.parse(document.getElementById("admin-weapons").value);
        boons = JSON.parse(document.getElementById("admin-boons").value);
        fear = JSON.parse(document.getElementById("admin-fear").value);
    } catch (error) {
        setAdminStatus(`Invalid JSON: ${error.message}`, "error");
        return;
    }

    if (
        !fear ||
        typeof fear !== "object" ||
        typeof fear.name !== "string" ||
        !fear.name.trim()
    ) {
        setAdminStatus("Fear JSON must be an object with a non-empty name.", "error");
        return;
    }

    const dateRangeDays = Number(
        document.getElementById("admin-date-range-days").value,
    );
    const weightedMult = Number(
        document.getElementById("admin-weighted-fear-multiplier").value,
    );
    if (!Number.isFinite(weightedMult) || weightedMult < 0) {
        setAdminStatus(
            "Weighted fear multiplier must be a non-negative number.",
            "error",
        );
        return;
    }

    const payload = {
        weapons,
        boons,
        fear,
        analytics: {
            date_range_days: dateRangeDays,
            weighted_victory_fear_multiplier: weightedMult,
        },
    };

    try {
        await adminFetch("/api/admin/config", {
            method: "PUT",
            body: JSON.stringify(payload),
        });
        await loadAdmin();
        setAdminStatus("Config saved.", "success");
    } catch (error) {
        setAdminStatus(error.message, "error");
    }
}

async function exportBackup() {
    try {
        const backup = await adminFetch("/api/admin/export");
        const blob = new Blob([JSON.stringify(backup, null, 2)], {
            type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `hades-ii-backup-${new Date()
            .toISOString()
            .replaceAll(":", "-")}.json`;
        link.click();
        URL.revokeObjectURL(url);
        setAdminStatus("Backup exported.", "success");
    } catch (error) {
        setAdminStatus(error.message, "error");
    }
}

function pickImportBackup() {
    document.getElementById("import-backup-file").click();
}

async function importBackupFromFile(event) {
    const input = event.target;
    const file = input.files?.[0];
    input.value = "";
    if (!file) {
        return;
    }

    let text;
    try {
        text = await file.text();
    } catch (_error) {
        setAdminStatus("Could not read file.", "error");
        return;
    }

    let backup;
    try {
        backup = JSON.parse(text);
    } catch (error) {
        setAdminStatus(`Invalid JSON: ${error.message}`, "error");
        return;
    }

    if (!backup.config || !Array.isArray(backup.runs)) {
        setAdminStatus("Backup must include config and runs arrays.", "error");
        return;
    }

    const hasData = state.users.length > 0 || state.runs.length > 0;
    let confirm_replace = false;
    if (hasData) {
        const ok = window.confirm(
            "Replace all data in the database with this backup? " +
                "This deletes current users, runs, and settings. This cannot be undone.",
        );
        if (!ok) {
            setAdminStatus("Import cancelled.", "");
            return;
        }
        confirm_replace = true;
    }

    try {
        await adminFetch("/api/admin/import", {
            method: "POST",
            body: JSON.stringify({
                config: backup.config,
                runs: backup.runs,
                confirm_replace,
            }),
        });
        await loadAdmin();
        setAdminStatus("Backup imported.", "success");
    } catch (error) {
        setAdminStatus(error.message, "error");
    }
}

function renderUsers() {
    const container = document.getElementById("admin-users");
    if (!state.users.length) {
        container.innerHTML = '<p class="muted">No users configured.</p>';
        return;
    }

    container.innerHTML = state.users
        .map(
            (user) => `
                <article class="admin-item">
                    <form class="admin-user-form" data-user-id="${escapeHtml(user.id)}">
                        <div class="admin-item-heading">
                            <h3>${escapeHtml(user.id)}</h3>
                            <span class="pill">${user.run_count} runs</span>
                        </div>
                        <label>
                            Display Name
                            <input
                                name="display_name"
                                value="${escapeHtml(user.display_name)}"
                                required
                            >
                        </label>
                        <label>
                            Access Code
                            <input
                                name="access_code"
                                value="${escapeHtml(user.access_code)}"
                                required
                            >
                        </label>
                        <div class="modal-actions">
                            <button type="submit">Save User</button>
                            <button
                                type="button"
                                data-action="rotate-user-code"
                                data-user-id="${escapeHtml(user.id)}"
                            >
                                Rotate Code
                            </button>
                            <button
                                class="danger-button"
                                type="button"
                                data-action="delete-user"
                                data-user-id="${escapeHtml(user.id)}"
                                ${user.run_count > 0 ? "disabled" : ""}
                            >
                                Delete
                            </button>
                        </div>
                    </form>
                </article>
            `,
        )
        .join("");
}

function renderRuns() {
    const container = document.getElementById("admin-runs");
    if (!state.runs.length) {
        container.innerHTML = '<p class="muted">No runs logged yet.</p>';
        return;
    }

    container.innerHTML = state.runs
        .map(
            (run) => `
                <article class="admin-item">
                    <form class="admin-run-form" data-run-id="${escapeHtml(run.id)}">
                        <div class="admin-item-heading">
                            <h3>${escapeHtml(userName(run.user_id))}</h3>
                            <span class="muted">${escapeHtml(formatDate(run.created_at))}</span>
                        </div>
                        <label>
                            User
                            <select name="user_id" required>
                                ${state.users
                                    .map((user) =>
                                        option(
                                            user.id,
                                            user.display_name,
                                            run.user_id,
                                        ),
                                    )
                                    .join("")}
                            </select>
                        </label>
                        <label>
                            Realm
                            <select name="side" required>
                                ${option("topside", "Topside", run.side)}
                                ${option("bottomside", "Bottomside", run.side)}
                            </select>
                        </label>
                        <label>
                            Weapon
                            <select name="weapon">
                                ${option("", "No weapon selected", run.weapon || "")}
                                ${state.publicConfig.weapons
                                    .map((weapon) =>
                                        option(weapon.name, weapon.name, run.weapon || ""),
                                    )
                                    .join("")}
                            </select>
                        </label>
                        <label>
                            Boons
                            <input name="boons" value="${escapeHtml(run.boons.join(", "))}">
                        </label>
                        <label>
                            <span class="fear-label-row">
                                <img class="fear-icon" src="${escapeHtml(fearIconSrc())}" alt="" width="18" height="18">
                                Fear
                            </span>
                            <input
                                name="fear"
                                type="number"
                                min="0"
                                max="99"
                                value="${Number(run.fear) > 0 ? escapeHtml(String(run.fear)) : ""}"
                                placeholder="0–99"
                            >
                        </label>
                        <label class="admin-wide-label">
                            Notes
                            <textarea name="notes" rows="2">${escapeHtml(run.notes || "")}</textarea>
                        </label>
                        <div class="modal-actions">
                            <button type="submit">Save Run</button>
                            <button
                                class="danger-button"
                                type="button"
                                data-action="delete-run"
                                data-run-id="${escapeHtml(run.id)}"
                            >
                                Delete Run
                            </button>
                        </div>
                    </form>
                </article>
            `,
        )
        .join("");
}

function renderConfig() {
    document.getElementById("admin-date-range-days").value =
        state.config.analytics.date_range_days;
    document.getElementById("admin-weighted-fear-multiplier").value =
        state.config.analytics.weighted_victory_fear_multiplier ?? 0;
    document.getElementById("admin-weapons").value = JSON.stringify(
        state.config.weapons,
        null,
        2,
    );
    document.getElementById("admin-boons").value = JSON.stringify(
        state.config.boons,
        null,
        2,
    );
    document.getElementById("admin-fear").value = JSON.stringify(
        state.config.fear,
        null,
        2,
    );
}

function fearIconSrc() {
    const url = state.publicConfig?.fear?.image_url;
    return url && String(url).trim() ? String(url).trim() : DEFAULT_FEAR_ICON_URL;
}

async function adminFetch(url, options = {}) {
    const headers = {
        "X-Admin-Password": getPassword(),
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
    };
    return fetchJson(url, { ...options, headers });
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
        let message = `Request failed: ${response.status}`;
        try {
            const error = await response.json();
            message = error.detail || message;
        } catch (_error) {
            // No JSON error body.
        }
        const requestError = new Error(message);
        requestError.status = response.status;
        throw requestError;
    }

    if (response.status === 204) {
        return null;
    }

    return response.json();
}

function showLogin() {
    document.getElementById("login-panel").hidden = false;
    document.getElementById("admin-panel").hidden = true;
    document.getElementById("admin-password").focus();
}

function showAdmin() {
    document.getElementById("login-panel").hidden = true;
    document.getElementById("admin-panel").hidden = false;
}

function logout() {
    sessionStorage.removeItem(ADMIN_PASSWORD_KEY);
    state.users = [];
    state.runs = [];
    state.config = null;
    state.publicConfig = null;
    showLogin();
}

function getPassword() {
    return sessionStorage.getItem(ADMIN_PASSWORD_KEY) || "";
}

function setLoginStatus(message, statusClass) {
    setStatus("login-status", message, statusClass);
}

function setAdminStatus(message, statusClass) {
    setStatus("admin-status", message, statusClass);
}

function setStatus(id, message, statusClass) {
    const status = document.getElementById(id);
    status.textContent = message;
    status.className = statusClass ? `status ${statusClass}` : "status";
}

function splitCsv(value) {
    return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function userName(userId) {
    return state.users.find((user) => user.id === userId)?.display_name || userId;
}

function option(value, label, selectedValue) {
    return `
        <option
            value="${escapeHtml(value)}"
            ${value === selectedValue ? "selected" : ""}
        >
            ${escapeHtml(label)}
        </option>
    `;
}

function formatDate(value) {
    return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(new Date(value));
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
