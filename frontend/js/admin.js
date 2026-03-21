
// Admin Dashboard Logic

const API_BASE = '/api';

// 1. Auth Check
const userStr = localStorage.getItem('user');
if (!userStr) {
    window.location.href = '/';
}
const user = JSON.parse(userStr);
const adminToken = user.admin_token || user.adminToken || localStorage.getItem('admin_token') || '';
if (user.role !== 'ADMIN') {
    alert(" Access Denied: Admins Only");
    localStorage.removeItem('user');
    window.location.href = '/';
}
if (!adminToken) {
    // Backend can allow a dev fallback (ALLOW_INSECURE_ADMIN=1). Keep UI usable in that case.
    console.warn('Admin token missing; relying on backend dev fallback if enabled.');
}

document.getElementById('usernameDisplay').textContent = user.username + ' (Admin)';

function setSidebarState(isOpen) {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const menuToggle = document.getElementById('menuToggle');
    if (sidebar) sidebar.classList.toggle('open', isOpen);
    if (overlay) overlay.classList.toggle('open', isOpen);
    if (menuToggle) menuToggle.classList.toggle('active', isOpen);
    document.body.classList.toggle('sidebar-open', isOpen);
}

// Sidebar Toggle
window.toggleSidebar = () => {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    const isOpen = sidebar.classList.contains('open');
    setSidebarState(!isOpen);
};

window.closeSidebar = () => setSidebarState(false);

// 2. Logout
window.logout = () => {
    localStorage.removeItem('user');
    window.location.href = '/';
}

function getAdminHeaders(extra = {}) {
    return {
        'X-Admin-Token': adminToken,
        'X-Admin-User': user.username,
        ...extra
    };
}

async function adminFetch(url, options = {}) {
    const headers = getAdminHeaders(options.headers || {});
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401 || response.status === 403) {
        alert(' Admin session expired. Please login again.');
        logout();
        throw new Error('Unauthorized admin request');
    }
    return response;
}

// 3. Clock
setInterval(() => {
    document.getElementById('clock').innerText = new Date().toLocaleString();
}, 1000);

// 4. Tab Navigation
window.showTab = (tabName, el = null) => {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));

    // Show selected tab
    document.getElementById(`tab-${tabName}`).classList.add('active');
    const navTarget = el || Array.from(document.querySelectorAll('.nav-item'))
        .find((item) => item.getAttribute('onclick')?.includes(`showTab('${tabName}')`));
    if (navTarget) navTarget.classList.add('active');
    
    const titleMap = {
        dashboard: 'System Administration',
        users: 'User Management',
        health: 'System Health',
        config: 'Configuration',
        logs: 'Login History',
        audit: 'Audit Logs',
        alerts: 'Alert Settings'
    };
    const pageTitle = document.getElementById('pageTitle');
    if (pageTitle) {
        pageTitle.textContent = titleMap[tabName] || 'System Administration';
    }

    // Load data for specific tabs
    if (tabName === 'users') {
        loadUsers();
    } else if (tabName === 'health') {
        loadSystemHealth();
    } else if (tabName === 'logs') {
        loadHistory();
    } else if (tabName === 'config') {
        loadConfig();
    } else if (tabName === 'dashboard') {
        loadDashboardStats();
    } else if (tabName === 'audit') {
        loadAuditLogs();
    } else if (tabName === 'alerts') {
        loadAlertSettings();
    }

    // Close sidebar after selecting a section
    setSidebarState(false);
}

// 5. Load Dashboard Stats
async function loadDashboardStats() {
    try {
        // Load users count
        const usersRes = await adminFetch(`${API_BASE}/admin/users`);
        const usersData = await usersRes.json();
        document.getElementById('stat-users').textContent = usersData.users?.length || 0;

        // Load login history for 24h count
        const historyRes = await adminFetch(`${API_BASE}/admin/history?limit=100`);
        const historyData = await historyRes.json();
        const last24h = historyData.history?.filter(log => {
            const logTime = new Date(log.timestamp);
            const now = new Date();
            return (now - logTime) < 24 * 60 * 60 * 1000;
        });
        document.getElementById('stat-logins').textContent = last24h?.length || 0;

        // Load system health
        const healthRes = await adminFetch(`${API_BASE}/admin/system-health`);
        const healthData = await healthRes.json();

        if (healthData.success) {
            const uptime = healthData.health.server.uptime_seconds;
            const hours = Math.floor(uptime / 3600);
            const minutes = Math.floor((uptime % 3600) / 60);
            document.getElementById('stat-uptime').textContent = `${hours}h ${minutes}m`;
            document.getElementById('stat-db').textContent = healthData.health.mongodb.status;
        }
    } catch (e) {
        console.error("Dashboard stats error", e);
    }
}

// 6. Load Config
async function loadConfig() {
    try {
        const res = await fetch(`${API_BASE}/config`);
        const data = await res.json();
        const conf = data.config || {};

        if (conf.cpu_threshold) document.getElementById('conf-cpu').value = conf.cpu_threshold;
        if (conf.memory_threshold) document.getElementById('conf-mem').value = conf.memory_threshold;
        if (conf.latency_threshold) document.getElementById('conf-lat').value = conf.latency_threshold;
    } catch (e) {
        console.error("Config Load Error", e);
    }
}

// 7. Save Config
window.saveConfig = async () => {
    const newConf = {
        cpu_threshold: parseFloat(document.getElementById('conf-cpu').value),
        memory_threshold: parseFloat(document.getElementById('conf-mem').value),
        latency_threshold: parseFloat(document.getElementById('conf-lat').value),
    };

    try {
        await adminFetch(`${API_BASE}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newConf)
        });
        alert(' Configuration Saved!');
    } catch (e) {
        alert(' Failed to save config');
    }
}

// 12. Audit Logs
let _auditLogsCache = [];

function _renderAuditLogs() {
    const table = document.getElementById('auditLogsTable');
    if (!table) return;

    const filterEl = document.getElementById('auditFilter');
    const q = (filterEl?.value || '').trim().toLowerCase();

    const events = !_auditLogsCache ? [] : _auditLogsCache.filter((ev) => {
        if (!q) return true;
        const hay = [
            ev.actor,
            ev.action,
            ev.ip_address,
            ev.status,
            JSON.stringify(ev.details || {})
        ].join(' ').toLowerCase();
        return hay.includes(q);
    });

    if (!events.length) {
        table.innerHTML = '<tr><td colspan="6" style="padding: 20px; text-align: center; color: #94a3b8;">No audit events</td></tr>';
        return;
    }

    table.innerHTML = events.map((ev) => {
        const ts = ev.timestamp ? new Date(ev.timestamp).toLocaleString() : '-';
        const actor = ev.actor || '-';
        const action = ev.action || '-';
        const details = ev.details ? JSON.stringify(ev.details) : '{}';
        const ip = ev.ip_address || '-';
        const status = (ev.status || 'success').toLowerCase();
        const ok = status === 'success';

        return `
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                <td style="padding:10px; color:#94a3b8;">${ts}</td>
                <td style="padding:10px;"><b>${actor}</b></td>
                <td style="padding:10px;">
                    <span style="background: rgba(59, 130, 246, 0.15); color: #93c5fd; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;">
                        ${action}
                    </span>
                </td>
                <td style="padding:10px; color:#cbd5e1; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; font-size: 12px; max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${details.replace(/\"/g, '&quot;')}">${details}</td>
                <td style="padding:10px; color:#94a3b8;">${ip}</td>
                <td style="padding:10px;">
                    <span style="padding:2px 8px; border-radius:999px; background:${ok ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}; color:${ok ? '#86efac' : '#fca5a5'}; font-size:0.8em; font-weight:600;">
                        ${ok ? 'SUCCESS' : 'FAILED'}
                    </span>
                </td>
            </tr>
        `;
    }).join('');
}

window.loadAuditLogs = async () => {
    const table = document.getElementById('auditLogsTable');
    if (table) {
        table.innerHTML = '<tr><td colspan="6" style="padding: 20px; text-align: center; color: #94a3b8;">Loading audit logs...</td></tr>';
    }

    try {
        const res = await adminFetch(`${API_BASE}/admin/audit-logs?limit=250`);
        const ct = (res.headers.get('content-type') || '').toLowerCase();
        let result;
        if (ct.includes('application/json')) {
            result = await res.json();
        } else {
            const text = await res.text();
            throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
        }
        if (!result.success) {
            throw new Error(result.error || `Request failed (HTTP ${res.status})`);
        }
        _auditLogsCache = Array.isArray(result.events) ? result.events : [];
        _renderAuditLogs();
    } catch (e) {
        console.error('Audit logs error', e);
        if (table) {
            const msg = (e && e.message) ? e.message : 'Failed to load audit logs';
            table.innerHTML = `<tr><td colspan="6" style="padding: 20px; text-align: center; color: #f87171;">${msg}</td></tr>`;
        }
    }
};

window.exportAuditLogs = async () => {
    try {
        const res = await adminFetch(`${API_BASE}/admin/audit-logs?limit=1000`);
        const ct = (res.headers.get('content-type') || '').toLowerCase();
        let result;
        if (ct.includes('application/json')) {
            result = await res.json();
        } else {
            const text = await res.text();
            throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
        }
        if (!result.success) {
            throw new Error(result.error || `Request failed (HTTP ${res.status})`);
        }
        const payload = {
            exported_at: new Date().toISOString(),
            total: result.total || (result.events?.length || 0),
            events: result.events || []
        };

        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `admin_audit_logs_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert(' Failed to export audit logs: ' + (e?.message || 'unknown error'));
        console.error(e);
    }
};

// Hook up filter input if present
try {
    const filterEl = document.getElementById('auditFilter');
    if (filterEl) {
        filterEl.addEventListener('input', _renderAuditLogs);
    }
} catch (_) { }

// 8. Load Login History
async function loadHistory() {
    try {
        const tbody = document.getElementById('loginHistoryTable');
        const res = await adminFetch(`${API_BASE}/admin/history?limit=50`);
        const result = await res.json();

        if (result.success && result.history && result.history.length > 0) {
            tbody.innerHTML = result.history.map(log => `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <td style="padding:10px;"><b>${log.username}</b></td>
                    <td style="padding:10px;"><span style="padding:2px 6px; border-radius:4px; background:${log.role === 'ADMIN' ? 'rgba(255,100,100,0.2)' : 'rgba(100,255,100,0.2)'}; color:${log.role === 'ADMIN' ? '#ffadad' : '#adffad'}; font-size:0.8em;">${log.role || 'N/A'}</span></td>
                    <td style="padding:10px; color:#94a3b8;">${new Date(log.timestamp).toLocaleString()}</td>
                    <td style="padding:10px;">
                        <span style="padding:2px 8px; border-radius:999px; background:${log.status === 'success' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}; color:${log.status === 'success' ? '#86efac' : '#fca5a5'}; font-size:0.8em; font-weight:600;">
                            ${log.status === 'success' ? 'SUCCESS' : 'FAILED'}
                        </span>
                    </td>
                </tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:20px; color:#94a3b8;">No login records found</td></tr>';
        }
    } catch (e) {
        console.error("History Load Error", e);
    }
}

// 9. Load Users
async function loadUsers() {
    try {
        const tbody = document.getElementById('usersTable');
        const res = await adminFetch(`${API_BASE}/admin/users`);
        const result = await res.json();

        if (result.success && result.users && result.users.length > 0) {
            tbody.innerHTML = result.users.map(u => `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <td style="padding:10px;"><b>${u.username}</b></td>
                    <td style="padding:10px;"><span class="user-badge ${u.role === 'ADMIN' ? 'badge-admin' : 'badge-user'}">${u.role}</span></td>
                    <td style="padding:10px;">
                        ${u.username !== 'admin' ? `<button onclick="deleteUser('${u.username}')" style="background:rgba(255,100,100,0.2); color:#ffadad; border:none; padding:0.5rem 1rem; border-radius:6px; cursor:pointer;"> Delete</button>` : '<span style="color:#94a3b8;">Protected</span>'}
                    </td>
                </tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align:center; padding:20px; color:#94a3b8;">No users found</td></tr>';
        }
    } catch (e) {
        console.error("Users Load Error", e);
        document.getElementById('usersTable').innerHTML = '<tr><td colspan="3" style="text-align:center; padding:20px; color:#ff6b6b;">Error loading users</td></tr>';
    }
}

// 10. Add User
window.addUser = async () => {
    const username = document.getElementById('new-username').value.trim();
    const password = document.getElementById('new-password').value.trim();
    const role = document.getElementById('new-role').value;

    if (!username || !password) {
        alert(' Please enter both username and password');
        return;
    }

    try {
        const res = await adminFetch(`${API_BASE}/admin/users`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, role })
        });
        const result = await res.json();

        if (result.success) {
            alert(' User added successfully!');
            document.getElementById('new-username').value = '';
            document.getElementById('new-password').value = '';
            loadUsers(); // Reload users table
        } else {
            alert(' ' + (result.error || 'Failed to add user'));
        }
    } catch (e) {
        alert(' Error adding user');
        console.error(e);
    }
}

// 11. Delete User
window.deleteUser = async (username) => {
    if (!confirm(`Are you sure you want to delete user "${username}"?`)) {
        return;
    }

    try {
        const res = await adminFetch(`${API_BASE}/admin/users`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username })
        });
        const result = await res.json();

        if (result.success) {
            alert(' User deleted successfully!');
            loadUsers(); // Reload users table
        } else {
            alert(' ' + (result.error || 'Failed to delete user'));
        }
    } catch (e) {
        alert(' Error deleting user');
        console.error(e);
    }
}

// 12. Load System Health
window.loadSystemHealth = async () => {
    try {
        const res = await adminFetch(`${API_BASE}/admin/system-health`);
        const raw = await res.text();
        let result = {};

        try {
            result = JSON.parse(raw);
        } catch {
            result = { success: false, error: raw || 'Non-JSON response from server' };
        }

        if (!result.success || !result.health) {
            throw new Error(result.error || 'System health data unavailable');
        }

        const h = result.health;
        const mongodb = h.mongodb || {};
        const dataFile = h.data_file || {};
        const server = h.server || {};
        const uptimeSeconds = Number(server.uptime_seconds || 0);
        const uptimeHours = Math.floor(uptimeSeconds / 3600);
        const uptimeMinutes = Math.floor((uptimeSeconds % 3600) / 60);
        const records = Number(dataFile.records || 0);

        document.getElementById('health-mongodb').innerHTML = `
            <p><b>Status:</b> <span style="color:${mongodb.status === 'Connected' ? '#adffad' : '#ffadad'}">${mongodb.status || 'Unknown'}</span></p>
            <p><b>Collection:</b> ${mongodb.collection || 'N/A'}</p>
        `;

        document.getElementById('health-datafile').innerHTML = `
            <p><b>Exists:</b> ${dataFile.exists ? 'Yes' : 'No'}</p>
            <p><b>Records:</b> ${records.toLocaleString()}</p>
            <p><b>Size:</b> ${Number(dataFile.size_mb || 0).toFixed(2)} MB</p>
            <p><b>Path:</b> <span style="color:#94a3b8;">${dataFile.path || 'N/A'}</span></p>
        `;

        document.getElementById('health-server').innerHTML = `
            <p><b>Memory:</b> ${Number(server.memory_mb || 0).toFixed(2)} MB</p>
            <p><b>CPU:</b> ${Number(server.cpu_percent || 0).toFixed(2)}%</p>
            <p><b>Uptime:</b> ${uptimeHours}h ${uptimeMinutes}m</p>
            <p><b>Metrics Source:</b> ${server.psutil_available ? 'psutil' : 'fallback'}</p>
        `;
    } catch (e) {
        console.error('System Health Error', e);
        const msg = (e && e.message) ? e.message : 'Unknown error';
        document.getElementById('health-mongodb').innerHTML = `<p style="color:#f87171;">Failed to load MongoDB health</p><p style="color:#94a3b8; font-size:0.9rem;">${msg}</p>`;
        document.getElementById('health-datafile').innerHTML = `<p style="color:#f87171;">Failed to load data file health</p><p style="color:#94a3b8; font-size:0.9rem;">${msg}</p>`;
        document.getElementById('health-server').innerHTML = `<p style="color:#f87171;">Failed to load server health</p><p style="color:#94a3b8; font-size:0.9rem;">${msg}</p>`;
    }
}
// 13. Export Logs
window.exportLogs = async () => {
    try {
        const res = await adminFetch(`${API_BASE}/admin/export-logs?limit=1000`);
        const result = await res.json();

        if (result.success) {
            // Create downloadable JSON file
            const dataStr = JSON.stringify(result.data, null, 2);
            const dataBlob = new Blob([dataStr], { type: 'application/json' });
            const url = URL.createObjectURL(dataBlob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `login_history_export_${new Date().toISOString().slice(0, 10)}.json`;
            link.click();
            URL.revokeObjectURL(url);

            alert(' Export successful!');
        } else {
            alert(' Export failed: ' + (result.error || 'Unknown error'));
        }
    } catch (e) {
        console.error("Export Error", e);
        alert(' Failed to export logs');
    }
}

// Init - Load dashboard stats on page load
loadDashboardStats();

// Start with hidden sidebar; open via menu button
{
    setSidebarState(false);
}

// ========================================
// EMAIL ALERT SETTINGS
// ========================================

// Load Alert Settings
window.loadAlertSettings = async () => {
    try {
        // Load email configuration
        const configRes = await adminFetch(`${API_BASE}/admin/alert-config`);
        const config = await configRes.json();

        if (config.success) {
            const status = config.config.enabled ? ' Enabled' : ' Disabled';
            const statusColor = config.config.enabled ? '#4ade80' : '#f87171';

            document.getElementById('emailStatus').innerHTML = `<span style="color: ${statusColor}">${status}</span>`;
            document.getElementById('fromEmail').textContent = config.config.from_email;
            document.getElementById('recipientCount').textContent = `${config.config.recipient_count} recipients`;

            // Display recipients
            const recipients = Array.isArray(config.config.recipients) ? config.config.recipients : [];
            const recipientsHtml = recipients.map((email, index) => `
                <div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px; display: flex; align-items: center; gap: 10px;">
                    <span style="color: #3b82f6; font-size: 20px;"></span>
                    <span style="flex: 1;">${email}</span>
                    <span style="background: rgba(59, 130, 246, 0.2); color: #3b82f6; padding: 4px 12px; border-radius: 12px; font-size: 12px;">Recipient ${index + 1}</span>
                </div>
            `).join('');
            document.getElementById('recipientsList').innerHTML = recipientsHtml || '<div style="color:#94a3b8;">No recipients configured</div>';
        } else {
            document.getElementById('emailStatus').innerHTML = '<span style="color: #f87171"> Error loading config</span>';
        }

        // Load alert history
        loadAlertHistory();

    } catch (e) {
        console.error('Error loading alert settings:', e);
        document.getElementById('emailStatus').innerHTML = '<span style="color: #f87171"> Error</span>';
    }
}

// Send Test Email
window.sendTestEmail = async () => {
    const btn = document.getElementById('testEmailBtn');
    const resultDiv = document.getElementById('testEmailResult');

    // Show loading state  
    btn.disabled = true;
    btn.textContent = ' Sending...';
    resultDiv.style.display = 'none';

    try {
        const res = await adminFetch(`${API_BASE}/admin/test-email`, {
            method: 'POST'
        });
        const result = await res.json();

        if (result.success) {
            resultDiv.style.display = 'block';
            resultDiv.style.background = 'rgba(74, 222, 128, 0.2)';
            resultDiv.style.border = '1px solid #4ade80';
            resultDiv.style.color = '#4ade80';
            resultDiv.innerHTML = `
                <div style="font-weight: bold; margin-bottom: 8px;"> Success!</div>
                <div>${result.message}</div>
                <div style="margin-top: 8px; font-size: 14px; color: #94a3b8;">Check your inbox within 1-2 minutes</div>
            `;
        } else {
            resultDiv.style.display = 'block';
            resultDiv.style.background = 'rgba(248, 113, 113, 0.2)';
            resultDiv.style.border = '1px solid #f87171';
            resultDiv.style.color = '#f87171';
            resultDiv.innerHTML = `
                <div style="font-weight: bold; margin-bottom: 8px;"> Failed</div>
                <div>${result.error}</div>
            `;
        }
    } catch (e) {
        resultDiv.style.display = 'block';
        resultDiv.style.background = 'rgba(248, 113, 113, 0.2)';
        resultDiv.style.border = '1px solid #f87171';
        resultDiv.style.color = '#f87171';
        resultDiv.innerHTML = `
            <div style="font-weight: bold; margin-bottom: 8px;"> Error</div>
            <div>${e.message}</div>
        `;
    } finally {
        btn.disabled = false;
        btn.textContent = ' Send Test Email';
    }
}

// Load Alert History
async function loadAlertHistory() {
    try {
        const res = await adminFetch(`${API_BASE}/admin/alert-history?limit=20`);
        const result = await res.json();

        const table = document.getElementById('alertHistoryTable');

        if (result.success && result.alerts.length > 0) {
            table.innerHTML = result.alerts.map(alert => `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.1);">
                    <td style="padding: 12px;">${new Date(alert.timestamp).toLocaleString()}</td>
                    <td style="padding: 12px;"><span style="background: rgba(168, 85, 247, 0.2); color: #a855f7; padding: 4px 12px; border-radius: 12px; font-size: 12px;">${alert.metric}</span></td>
                    <td style="padding: 12px; font-weight: bold; color: #f87171;">${alert.value}</td>
                    <td style="padding: 12px;">${alert.threshold}</td>
                </tr>
            `).join('');
        } else {
            table.innerHTML = '<tr><td colspan="4" style="padding: 20px; text-align: center; color: #94a3b8;">No alerts sent yet</td></tr>';
        }
    } catch (e) {
        console.error('Error loading alert history:', e);
        document.getElementById('alertHistoryTable').innerHTML = '<tr><td colspan="4" style="padding: 20px; text-align: center; color: #f87171;">Error loading history</td></tr>';
    }
}






