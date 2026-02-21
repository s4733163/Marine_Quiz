
const BACKEND_URL = "http://127.0.0.1:5000";

// DOM refs
const loginView = document.getElementById("loginView");
const dashView = document.getElementById("dashView");
const loginEmail = document.getElementById("loginEmail");
const loginPassword = document.getElementById("loginPassword");
const loginBtn = document.getElementById("loginBtn");
const loginHint = document.getElementById("loginHint");
const adminInfo = document.getElementById("adminInfo");
const adminLabel = document.getElementById("adminLabel");
const logoutBtn = document.getElementById("logoutBtn");
const summaryRow = document.getElementById("summaryRow");
const searchInput = document.getElementById("searchInput");
const rankFilter = document.getElementById("rankFilter");
const userCount = document.getElementById("userCount");
const userList = document.getElementById("userList");

let allUsers = [];   // full data from server

// ── Helpers ────────────────────────────────────────────
function esc(s) {
    return String(s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function fmtDate(iso) {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleString(undefined, {
            day: "2-digit", month: "short", year: "numeric",
            hour: "2-digit", minute: "2-digit"
        });
    } catch { return iso; }
}
function setHint(msg, err) {
    loginHint.textContent = msg;
    loginHint.className = "hint" + (err ? " err" : "");
}

// ── Login ───────────────────────────────────────────────
loginBtn.addEventListener("click", doLogin);
[loginEmail, loginPassword].forEach(el =>
    el.addEventListener("keydown", e => { if (e.key === "Enter") doLogin(); })
);

async function doLogin() {
    const email = loginEmail.value.trim();
    const password = loginPassword.value.trim();

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        setHint("Enter a valid email.", true); return;
    }
    if (!password) { setHint("Enter your password.", true); return; }

    loginBtn.disabled = true;
    loginHint.className = "hint";
    loginHint.innerHTML = '<span class="spinner"></span>Authenticating…';

    try {
        const resp = await fetch(`${BACKEND_URL}/get_stats`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        const data = await resp.json();

        if (data.ok) {
            showDashboard(data);
        } else {
            setHint(data.message || "Login failed.", true);
        }
    } catch {
        setHint("Cannot reach the server. Is the backend running?", true);
    } finally {
        loginBtn.disabled = false;
    }
}

// ── Logout ──────────────────────────────────────────────
logoutBtn.addEventListener("click", () => {
    dashView.classList.remove("active");
    loginView.style.display = "";
    adminInfo.style.display = "none";
    loginPassword.value = "";
    allUsers = [];
    setHint("Enter admin email and password.", false);
});

// ── Dashboard ───────────────────────────────────────────
function showDashboard(data) {
    allUsers = data.users || [];

    // Admin bar
    adminLabel.textContent = `${data.admin.username} (${data.admin.email})`;
    adminInfo.style.display = "flex";

    // Summary
    const totalUsers = data.total_users || 0;
    const totalAtt = data.total_attempts || 0;
    const totalPasses = data.total_passes || 0;
    const passRate = totalAtt ? Math.round(totalPasses / totalAtt * 100) : 0;

    summaryRow.innerHTML = `
        <div class="sum-card"><span class="val">${totalUsers}</span><div class="lbl">Registered Users</div></div>
        <div class="sum-card"><span class="val">${totalAtt}</span><div class="lbl">Total Attempts</div></div>
        <div class="sum-card"><span class="val">${totalPasses}</span><div class="lbl">Total Passes</div></div>
        <div class="sum-card"><span class="val">${passRate}%</span><div class="lbl">Overall Pass Rate</div></div>
      `;

    // Populate rank filter
    const ranks = new Set();
    allUsers.forEach(u => u.attempts.forEach(a => ranks.add(a.rank)));
    rankFilter.innerHTML = '<option value="">All Ranks</option>';
    [...ranks].sort().forEach(r => {
        const o = document.createElement("option");
        o.value = r; o.textContent = r;
        rankFilter.appendChild(o);
    });

    // Show
    loginView.style.display = "none";
    dashView.classList.add("active");

    renderUsers();
}

// ── Filter + render ─────────────────────────────────────
searchInput.addEventListener("input", renderUsers);
rankFilter.addEventListener("change", renderUsers);

function renderUsers() {
    const q = searchInput.value.trim().toLowerCase();
    const rank = rankFilter.value;

    const filtered = allUsers.filter(u => {
        const nameMatch = !q ||
            u.username.toLowerCase().includes(q) ||
            u.email.toLowerCase().includes(q);
        const rankMatch = !rank ||
            u.attempts.some(a => a.rank === rank);
        return nameMatch && rankMatch;
    });

    userCount.textContent = `${filtered.length} user${filtered.length !== 1 ? "s" : ""}`;
    userList.innerHTML = "";

    if (!filtered.length) {
        userList.innerHTML = `<div class="empty">No users match the current filter.</div>`;
        return;
    }

    filtered.forEach(u => {
        const attempts = rank
            ? u.attempts.filter(a => a.rank === rank)
            : u.attempts;

        const totalAtt = attempts.length;
        const passes = attempts.filter(a => a.pass).length;
        const bestPct = totalAtt ? Math.max(...attempts.map(a => a.pct)) : 0;

        const block = document.createElement("div");
        block.className = "user-block";

        block.innerHTML = `
          <div class="user-head">
            <span class="user-name">${esc(u.username)}</span>
            <span class="user-email">${esc(u.email)}</span>
            <div class="user-meta">
              <span class="badge">${totalAtt} attempt${totalAtt !== 1 ? "s" : ""}</span>
              <span class="badge">${passes} pass${passes !== 1 ? "es" : ""}</span>
              <span class="badge">Best: ${bestPct}%</span>
            </div>
            <span class="chevron">▼</span>
          </div>
          <div class="user-body" id="ub_${esc(u.email)}"></div>
        `;

        // Toggle
        block.querySelector(".user-head").addEventListener("click", () => {
            const wasOpen = block.classList.contains("open");
            block.classList.toggle("open");
            if (!wasOpen) renderAttempts(block.querySelector(".user-body"), attempts);
        });

        userList.appendChild(block);
    });
}

function renderAttempts(container, attempts) {
    if (container.dataset.rendered) return;
    container.dataset.rendered = "1";

    if (!attempts.length) {
        container.innerHTML = `<div class="empty" style="padding:18px">No attempts for this filter.</div>`;
        return;
    }

    attempts.forEach((a, i) => {
        const row = document.createElement("div");
        row.className = "attempt-row";

        const secRows = a.sections.map(s => `
          <tr>
            <td>${esc(s.name)}</td>
            <td>${s.correct} / ${s.total}</td>
            <td>
              <span class="bar-wrap"><span class="bar-fill" style="width:${s.pct}%"></span></span>
              ${s.pct}%
            </td>
          </tr>`).join("");

        row.innerHTML = `
          <div class="attempt-head">
            <span class="att-rank">${esc(a.rank)}</span>
            <span class="att-date">${fmtDate(a.attempted_at)}</span>
            <span class="att-score">${a.total_correct} / ${a.total_questions} correct &nbsp;(${a.pct}%)</span>
            <span class="pass-badge ${a.pass ? "pass" : "fail"}">${a.pass ? "PASS" : "FAIL"}</span>
            <span class="att-chevron">▼</span>
          </div>
          <div class="attempt-body">
            <table class="sec-table">
              <thead><tr><th>Section</th><th>Correct / Total</th><th>Score</th></tr></thead>
              <tbody>${secRows}</tbody>
            </table>
          </div>`;

        row.querySelector(".attempt-head").addEventListener("click", () =>
            row.classList.toggle("open")
        );

        // Auto-expand the latest attempt
        if (i === 0) row.classList.add("open");

        container.appendChild(row);
    });
}