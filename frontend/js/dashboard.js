
// Check Auth
const userStr = localStorage.getItem('user');
if (!userStr) {
    window.location.href = '/';
}
const user = JSON.parse(userStr);
document.getElementById('usernameDisplay').textContent = user.username + (user.role === 'ADMIN' ? ' (Admin)' : '');

// Sidebar Toggle Function
window.toggleSidebar = () => {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('mainContent');
    const menuToggle = document.getElementById('menuToggle');

    sidebar.classList.toggle('collapsed');
    mainContent.classList.toggle('expanded');
    menuToggle.classList.toggle('active');
}



// Constants
const API_BASE = '/api';
function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatAiResponse(text) {
    if (!text) return '';

    const lines = String(text).replace(/\r\n/g, '\n').split('\n');
    const out = [];
    let inCodeFence = false;
    let inCommandSection = false;
    let commandBuffer = [];

    const flushCommandBox = () => {
        if (!commandBuffer.length) return;
        const body = commandBuffer
            .join('\n')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        out.push('<pre style="background: rgba(0,0,0,0.4); border: 1px solid rgba(168,85,247,0.4); padding: 12px; border-radius: 10px; overflow:auto; margin: 8px 0;"><code>' + body + '</code></pre>');
        commandBuffer = [];
    };

    const isHeading = (line) => /^#{1,3}\s+/.test(line.trim());
    const isCommandLike = (line) => {
        const t = line.trim();
        if (!t) return false;
        if (/^(bash|sh|shell)$/i.test(t)) return true;
        return /^(\$|sudo\s+|ps\s+|top\b|kill\b|free\b|journalctl\b|systemctl\b|cat\b|tail\b|grep\b|kubectl\b|docker\b)/i.test(t);
    };

    for (let i = 0; i < lines.length; i++) {
        const raw = lines[i];
        const line = raw || '';
        const trimmed = line.trim();

        if (trimmed.startsWith('```')) {
            if (!inCodeFence) {
                inCodeFence = true;
                commandBuffer = [];
            } else {
                inCodeFence = false;
                flushCommandBox();
            }
            continue;
        }

        if (inCodeFence) {
            commandBuffer.push(line);
            continue;
        }

        if (/specific commands/i.test(trimmed)) {
            flushCommandBox();
            inCommandSection = true;
        }

        if (inCommandSection && isHeading(line) && !/specific commands/i.test(trimmed)) {
            flushCommandBox();
            inCommandSection = false;
        }

        if (inCommandSection && isCommandLike(line)) {
            commandBuffer.push(line);
            continue;
        }

        if (inCommandSection && commandBuffer.length && !trimmed) {
            commandBuffer.push('');
            continue;
        }

        if (inCommandSection && commandBuffer.length && !isCommandLike(line)) {
            flushCommandBox();
        }

        let html = line
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        html = html.replace(/`([^`]+)`/g, '<code style="background: rgba(0,0,0,0.35); padding: 2px 6px; border-radius: 6px;">$1</code>');
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/^###\s+(.*)$/g, '<div style="font-size: 18px; font-weight: 700; margin: 14px 0 8px; color: #c4b5fd;">$1</div>');
        html = html.replace(/^##\s+(.*)$/g, '<div style="font-size: 20px; font-weight: 700; margin: 14px 0 8px; color: #ddd6fe;">$1</div>');
        html = html.replace(/^#\s+(.*)$/g, '<div style="font-size: 22px; font-weight: 700; margin: 14px 0 8px; color: #ede9fe;">$1</div>');
        html = html.replace(/^\s*[-*]\s+(.*)$/g, '<div style="margin: 4px 0 4px 16px;">- $1</div>');
        html = html.replace(/^\s*(\d+)\.\s+(.*)$/g, '<div style="margin: 4px 0;">$1. $2</div>');

        out.push(html);
    }

    flushCommandBox();

    return out.join('<br>');
}

// Util: Show Section
window.showSection = (id) => {
    document.querySelectorAll('.section').forEach(el => el.classList.remove('active'));
    document.getElementById(id).classList.add('active');

    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    // Find nav item (hacky simplified way)
    const navs = document.querySelectorAll('.nav-item');
    if (id === 'monitoring') navs[0].classList.add('active');
    if (id === 'command') navs[1].classList.add('active');
    if (id === 'forecast') navs[2].classList.add('active');
    if (id === 'logs') navs[3].classList.add('active');


    // Trigger render if needed
    if (id === 'monitoring') loadDashboardData();
    if (id === 'forecast') runForecast();
    if (id === 'logs') loadLogs();
}

window.logout = () => {
    localStorage.removeItem('user');
    window.location.href = '/';
}

// Data Loading
async function loadDashboardData() {
    // Get Window Size
    const winSize = document.getElementById('windowSize').value || 100;

    // Get Status Filter
    const statusFilter = document.getElementById('statusFilter').value; // ALL or ALERT
    // Map UI value "ALERT" to Backend value "ALERT" or adjust if needed.
    // Backend expects 'alert_status' param.

    try {
        const res = await fetch(`${API_BASE}/data?window=${winSize}&alert_status=${statusFilter}`);
        const result = await res.json();

        if (!result.success) return;

        const data = result.data;
        const latest = result.latest;

        // Update KPIs
        updateKPI('cpu', latest.cpu_usage, '%', 80);
        updateKPI('mem', latest.memory_usage, ' GB', 8);
        updateKPI('lat', latest.response_time, ' ms', 1000);
        updateKPI('anom', latest.anomaly_label === 1 ? 'YES' : 'NO', '', 0.5, true);

        // Render Chart
        renderMainChart(data);
        renderPieCharts(result.statistics); // Add Pie Charts

    } catch (err) {
        console.error("Error loading dashboard data:", err);
    }
}

function updateKPI(id, val, unit, thresh, isBool = false) {
    document.getElementById(`kpi-${id}`).innerText = val + unit;
    const badge = document.getElementById(`badge-${id}`);

    let status = 'normal';
    // Simplified logic
    if (isBool) {
        status = val === 'YES' ? 'critical' : 'normal';
        // Show feedback buttons if anomaly
        if (id === 'anom') {
            document.getElementById('feedback-btns').style.display = (val === 'YES') ? 'flex' : 'none';
        }
    } else {
        if (val > thresh) status = 'critical';
        else if (val > thresh * 0.75) status = 'warning';
    }

    badge.className = `status-badge status-${status}`;
    badge.innerText = status.toUpperCase();
}



window.submitFeedback = (type) => {
    // In a real app, this would send to an API
    console.log("Feedback submitted:", type);
    alert(`Feedback Recorded: ${type === 'true_positive' ? 'Confirmed Issue' : 'False Alarm'}`);
    document.getElementById('feedback-btns').style.display = 'none';
}

function renderMainChart(data) {
    // Parse timestamps to Date objects to ensure Plotly treats them as dates
    const timestamps = data.map(d => new Date(d.timestamp));
    const cpu = data.map(d => d.cpu_usage);
    const mem = data.map(d => d.memory_usage);
    const lat = data.map(d => d.response_time);

    // Common Layout
    const commonLayout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#94a3b8' },
        xaxis: {
            type: 'date',  // Force Date Axis
            gridcolor: 'rgba(255,255,255,0.1)',
            tickformat: '%b %d<br>%H:%M:%S', // <br> for newline in HTML/SVG
            nticks: 8,
            automargin: true
        },
        yaxis: { gridcolor: 'rgba(255,255,255,0.1)' },
        showlegend: false,
        margin: { t: 40, r: 20, l: 40, b: 60 }
    };

    // CPU Chart
    Plotly.newPlot('cpuChart', [{
        x: timestamps, y: cpu, type: 'scatter', mode: 'lines', name: 'CPU',
        line: { color: '#3b82f6', width: 2 }, fill: 'tozeroy'
    }], { ...commonLayout, title: 'CPU Load (%)' });

    // Memory Chart
    Plotly.newPlot('memoryChart', [{
        x: timestamps, y: mem, type: 'scatter', mode: 'lines', name: 'Memory',
        line: { color: '#a855f7', width: 2 }, fill: 'tozeroy'
    }], { ...commonLayout, title: 'Memory Usage (GB)' });

    // Latency Chart
    Plotly.newPlot('latencyChart', [{
        x: timestamps, y: lat, type: 'scatter', mode: 'lines', name: 'Latency',
        line: { color: '#06b6d4', width: 2 }, fill: 'tozeroy'
    }], { ...commonLayout, title: 'Network Latency (ms)' });

    // Refresh visibility based on current toggle state
    // (In case window resize or re-render messes things up)
    const activeBtn = document.querySelector('.metric-btn.active');
    if (activeBtn) {
        toggleMetric(activeBtn.id.replace('btn-', ''));
    }
}

// Feature: Metric Toggle
window.toggleMetric = (metric) => {
    // Buttons
    document.querySelectorAll('.metric-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`btn-${metric}`).classList.add('active');

    // Charts
    const row = document.getElementById('chart-container-row');
    const cCPU = document.getElementById('card-cpu');
    const cMem = document.getElementById('card-mem');
    const cLat = document.getElementById('card-lat');

    // Reset styles
    row.style.display = 'grid';
    row.style.gridTemplateColumns = '1fr 1fr';
    cCPU.style.display = 'block';
    cMem.style.display = 'block';
    cLat.style.display = 'block';

    if (metric === 'all') {
        // Default View
    } else if (metric === 'cpu') {
        row.style.display = 'block'; // Block to stack
        cMem.style.display = 'none';
        cLat.style.display = 'none';
    } else if (metric === 'mem') {
        row.style.display = 'block';
        cCPU.style.display = 'none';
        cLat.style.display = 'none';
    } else if (metric === 'lat') {
        row.style.display = 'none'; // Hide top row entirely
        cLat.style.display = 'block';
    }

    // Trigger Resize for Plotly to fit new container size
    setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
    }, 100);
}

// Feature: Report Generation
window.downloadReport = async () => {
    try {
        const btn = document.querySelector('button[onclick="downloadReport()"]');
        const originalText = btn.innerText;
        btn.innerText = " Generating...";
        btn.disabled = true;

        const res = await fetch(`${API_BASE}/report`);

        if (!res.ok) {
            const errJson = await res.json();
            throw new Error(errJson.error || "Report generation failed");
        }

        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `AIOps_Report_${new Date().toISOString().slice(0, 10)}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);

        btn.innerText = originalText;
        btn.disabled = false;
        alert(" Report Downloaded Successfully!");

    } catch (err) {
        console.error("Report Error:", err);
        alert(` Failed to generate report: ${err.message}`);
        const btn = document.querySelector('button[onclick="downloadReport()"]');
        if (btn) {
            btn.innerText = " Generate Report";
            btn.disabled = false;
        }
    }
}

function renderPieCharts(stats) {
    // Root Cause Pie
    const rootCauses = stats.root_causes || {};
    const labels1 = Object.keys(rootCauses);
    const values1 = Object.values(rootCauses);

    if (labels1.length > 0) {
        const data1 = [{
            values: values1,
            labels: labels1,
            type: 'pie',
            hole: 0.4,
            marker: { colors: ['#3b82f6', '#ef4444', '#a855f7'] }
        }];
        const layout1 = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#cbd5e1' },
            margin: { t: 0, b: 0, l: 0, r: 0 },
            showlegend: true
        };
        Plotly.newPlot('pieChart', data1, layout1);
    }

    // Alert Distribution Pie
    const okCount = stats.ok_count || 0;
    const alertCount = stats.alerts_count || 0;

    const data2 = [{
        values: [okCount, alertCount],
        labels: ['Normal', 'Alerts'],
        type: 'pie',
        hole: 0.4,
        marker: { colors: ['#22c55e', '#ef4444'] }
    }];
    const layout2 = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#cbd5e1' },
        margin: { t: 0, b: 0, l: 0, r: 0 },
        showlegend: true
    };
    Plotly.newPlot('pieChart2', data2, layout2);
}

// Feature: Forecast
window.runForecast = async () => {
    const metric = document.getElementById('forecastMetric').value;
    const forecastBtn = document.querySelector('button[onclick="runForecast()"]');

    try {
        // Show loading state
        forecastBtn.innerText = ' Analyzing...';
        forecastBtn.disabled = true;

        const res = await fetch(`${API_BASE}/forecast`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ metric: metric, horizon: 30 })
        });
        const result = await res.json();

        if (result.success) {
            // Fetch recent historical data for context (match forecast length for balance)
            const histRes = await fetch(`${API_BASE}/data?window=30`);
            const histResult = await histRes.json();

            let historicalDates = [];
            let historicalValues = [];

            if (histResult.success && histResult.data) {
                historicalDates = histResult.data.map(d => new Date(d.timestamp));
                historicalValues = histResult.data.map(d => d[metric]);
            }

            // Calculate confidence intervals (simple estimation)
            const stdDev = result.predictions.reduce((sum, val, i, arr) => {
                const mean = arr.reduce((a, b) => a + b) / arr.length;
                return sum + Math.pow(val - mean, 2);
            }, 0) / result.predictions.length;

            const confidenceMultiplier = 1.96; // 95% confidence
            const upperBound = result.predictions.map(p => p + Math.sqrt(stdDev) * confidenceMultiplier);
            const lowerBound = result.predictions.map(p => Math.max(0, p - Math.sqrt(stdDev) * confidenceMultiplier));

            // Determine trend
            const firstPred = result.predictions[0];
            const lastPred = result.predictions[result.predictions.length - 1];
            const trend = lastPred > firstPred ? ' Increasing' : lastPred < firstPred ? ' Decreasing' : ' Stable';
            const trendColor = lastPred > firstPred ? '#f87171' : lastPred < firstPred ? '#4ade80' : '#94a3b8';

            // Convert forecast dates to Date objects
            const forecastDates = result.dates.map(d => new Date(d));

            // Prepare traces
            const traces = [];

            // Historical data (if available)
            if (historicalDates.length > 0) {
                // Add the last historical point to forecast to connect them
                const lastHistDate = historicalDates[historicalDates.length - 1];
                const lastHistValue = historicalValues[historicalValues.length - 1];

                traces.push({
                    x: historicalDates,
                    y: historicalValues,
                    mode: 'lines',
                    name: 'Historical',
                    line: {
                        color: '#3b82f6',
                        width: 3
                    },
                    fill: 'tozeroy',
                    fillcolor: 'rgba(59, 130, 246, 0.1)'
                });

                // Add connection point (bridge between historical and forecast)
                traces.push({
                    x: [lastHistDate, forecastDates[0]],
                    y: [lastHistValue, result.predictions[0]],
                    mode: 'lines',
                    name: 'Connection',
                    line: {
                        color: '#a855f7',
                        width: 2,
                        dash: 'dot'
                    },
                    showlegend: false,
                    hoverinfo: 'skip'
                });
            }

            // Forecast line
            traces.push({
                x: forecastDates,
                y: result.predictions,
                mode: 'lines',
                name: 'Forecast',
                line: {
                    dash: 'dot',
                    color: '#a855f7',
                    width: 4
                }
            });

            // Upper confidence bound
            traces.push({
                x: forecastDates,
                y: upperBound,
                mode: 'lines',
                name: 'Upper Bound',
                line: {
                    width: 0
                },
                showlegend: false,
                hoverinfo: 'skip'
            });

            // Lower confidence bound (with fill)
            traces.push({
                x: forecastDates,
                y: lowerBound,
                mode: 'lines',
                name: '95% Confidence',
                fill: 'tonexty',
                fillcolor: 'rgba(168, 85, 247, 0.2)',
                line: {
                    width: 0
                },
                showlegend: true
            });

            const layout = {
                title: {
                    text: `AI Forecast: ${metric.replace('_', ' ').toUpperCase()}<br><sub style="color:${trendColor}">Trend: ${trend} | Avg: ${result.avg_predicted.toFixed(2)} | Range: ${result.min_predicted.toFixed(2)} - ${result.max_predicted.toFixed(2)}</sub>`,
                    font: { size: 18, color: '#cbd5e1' }
                },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#cbd5e1' },
                xaxis: {
                    type: 'date',
                    gridcolor: 'rgba(255,255,255,0.1)',
                    title: 'Time'
                },
                yaxis: {
                    gridcolor: 'rgba(255,255,255,0.1)',
                    title: metric.replace('_', ' ').toUpperCase()
                },
                showlegend: true,
                legend: {
                    orientation: 'h',
                    x: 0.5,
                    y: -0.25,
                    xanchor: 'center',
                    yanchor: 'top',
                    bgcolor: 'rgba(15, 23, 42, 0.95)',
                    bordercolor: 'rgba(255,255,255,0.3)',
                    borderwidth: 1,
                    font: { size: 11 }
                },
                margin: { t: 80, r: 40, l: 60, b: 120 },
                hovermode: 'x unified'
            };

            Plotly.newPlot('forecastChart', traces, layout, { responsive: true });

            forecastBtn.innerText = 'Run Forecast';
            forecastBtn.disabled = false;
        } else {
            alert(` Forecast failed: ${result.error}`);
            forecastBtn.innerText = 'Run Forecast';
            forecastBtn.disabled = false;
        }
    } catch (err) {
        console.error(err);
        alert(' Error running forecast');
        forecastBtn.innerText = 'Run Forecast';
        forecastBtn.disabled = false;
    }
}

// Feature: Logs
window.loadLogs = async () => {
    try {
        const res = await fetch(`${API_BASE}/logs?window=50`);
        const result = await res.json();

        if (result.success) {
            const tbody = document.getElementById('logBody');
            tbody.innerHTML = '';

            result.logs.forEach(log => {
                const tr = document.createElement('tr');
                let color = '#ccc';
                if (log.level === 'ERROR') color = '#f87171';
                if (log.level === 'WARNING') color = '#facc15';

                tr.innerHTML = `
                    <td style="padding:0.8rem; border-bottom:1px solid rgba(255,255,255,0.05); color:#94a3b8;">${log.timestamp.split('T')[1].split('.')[0]}</td>
                    <td style="padding:0.8rem; border-bottom:1px solid rgba(255,255,255,0.05); color:${color}; font-weight:bold;">${log.level}</td>
                    <td style="padding:0.8rem; border-bottom:1px solid rgba(255,255,255,0.05);">${log.message}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (e) {
        console.error('Error getting logs:', e);
    }
}

// ========================================
// GROQ AI CHAT FUNCTIONALITY
// ========================================

let chatHistory = [];

window.sendChatMessage = async () => {
    const input = document.getElementById('chatInput');
    const chatBox = document.getElementById('chatBox');
    const message = input.value.trim();

    if (!message) return;

    // Clear placeholder if first message
    if (chatHistory.length === 0) {
        chatBox.innerHTML = '';
    }

    // Add user message to chat
    const userDiv = document.createElement('div');
    userDiv.style.cssText = 'background: rgba(99, 102, 241, 0.2); padding: 12px; border-radius: 12px; margin-left: auto; max-width: 70%; border-left: 3px solid #6366f1;';
    userDiv.innerHTML = `
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 4px;">You</div>
        <div style="color: white;">${message}</div>
    `;
    chatBox.appendChild(userDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    // Clear input
    input.value = '';

    // Show loading
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'ai-loading';
    loadingDiv.style.cssText = 'background: rgba(168, 85, 247, 0.2); padding: 12px; border-radius: 12px; max-width: 70%; border-left: 3px solid #a855f7;';
    loadingDiv.innerHTML = `
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 4px;"> AI Assistant</div>
        <div style="color: white;">Thinking...</div>
    `;
    chatBox.appendChild(loadingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        // Call API
        const res = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                history: chatHistory
            })
        });

        const result = await res.json();

        // Remove loading
        loadingDiv.remove();

        if (result.success) {
            // Add AI response
            const aiDiv = document.createElement('div');
            aiDiv.style.cssText = 'background: rgba(168, 85, 247, 0.2); padding: 12px; border-radius: 12px; max-width: 70%; border-left: 3px solid #a855f7;';
            aiDiv.innerHTML = `
                <div style="font-size: 12px; color: #94a3b8; margin-bottom: 4px;"> AI Assistant</div>
                <div style="color: white; ">${result.response}</div>
            `;
            chatBox.appendChild(aiDiv);

            // Update history
            chatHistory.push(
                { role: 'user', content: message },
                { role: 'assistant', content: result.response }
            );
        } else {
            // Show error
            const errorDiv = document.createElement('div');
            errorDiv.style.cssText = 'background: rgba(248, 113, 113, 0.2); padding: 12px; border-radius: 12px; max-width: 70%; border-left: 3px solid #f87171;';
            errorDiv.innerHTML = `
                <div style="font-size: 12px; color: #94a3b8; margin-bottom: 4px;"> Error</div>
                <div style="color: white;">${result.error}</div>
            `;
            chatBox.appendChild(errorDiv);
        }

    } catch (e) {
        loadingDiv.remove();
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = 'background: rgba(248, 113, 113, 0.2); padding: 12px; border-radius: 12px; max-width: 70%;';
        errorDiv.innerHTML = `<div style="color: white;"> Error: ${e.message}</div>`;
        chatBox.appendChild(errorDiv);
    }

    chatBox.scrollTop = chatBox.scrollHeight;
}

// ========================================
// AUTO-ANALYZE SYSTEM FEATURE
// ========================================

window.autoAnalyzeSystem = async () => {
    const btn = document.getElementById('analyzeBtn');
    const resultsDiv = document.getElementById('analysisResults');

    // Show loading state
    btn.disabled = true;
    btn.textContent = ' Analyzing your dashboard...';

    resultsDiv.innerHTML = `
        <div style="text-align: center; color: #94a3b8;">
            <div style="font-size: 48px; margin-bottom: 1rem;"></div>
            <div style="font-size: 18px; margin-bottom: 0.5rem;">Analyzing System State...</div>
            <div>Fetching metrics, checking anomalies, reviewing logs...</div>
        </div>
    `;

    try {
        // Step 1: Fetch current dashboard data
        const dataResponse = await fetch(`${API_BASE}/data?window=10`);
        const dashboardData = await dataResponse.json();

        if (!dashboardData.success) {
            throw new Error('Failed to fetch dashboard data');
        }

        // Step 2: Analyze the data to find issues
        const latestData = dashboardData.data[dashboardData.data.length - 1];
        const issues = [];
        const metrics = [];

        // Check CPU
        if (latestData.cpu_usage > 80) {
            issues.push(`High CPU Usage: ${latestData.cpu_usage.toFixed(1)}% (threshold: 80%)`);
            metrics.push(`CPU: ${latestData.cpu_usage.toFixed(1)}%`);
        }

        // Check Memory
        if (latestData.memory_usage > 8) {
            issues.push(`High Memory Usage: ${latestData.memory_usage.toFixed(2)} GB (threshold: 8 GB)`);
            metrics.push(`Memory: ${latestData.memory_usage.toFixed(2)} GB`);
        }

        // Check Response Time
        if (latestData.response_time > 1000) {
            issues.push(`High Latency: ${latestData.response_time.toFixed(0)} ms (threshold: 1000 ms)`);
            metrics.push(`Latency: ${latestData.response_time} ms`);
        }

        // Check for anomalies
        if (latestData.anomaly_label === 1) {
            issues.push('Anomaly detected in system behavior');
        }

        // Step 3: Build analysis request
        let analysisPrompt;
        if (issues.length === 0) {
            // No issues - just provide general health summary
            analysisPrompt = `System Health Check - All metrics are within normal ranges:
- CPU: ${latestData.cpu_usage.toFixed(1)}%
- Memory: ${latestData.memory_usage.toFixed(2)} GB
- Latency: ${latestData.response_time} ms
- Anomalies: None detected

Please provide:
1. A brief "All Clear" message
2. General best practices for maintaining system health
3. What to monitor proactively`;
        } else {
            // Issues found - request detailed analysis
            analysisPrompt = `AIOps Analysis - System Issues Detected:

CURRENT METRICS:
${metrics.join('\n')}

ISSUES FOUND:
${issues.map((issue, i) => `${i + 1}. ${issue}`).join('\n')}

Please provide:
1. Root Cause Analysis (why these issues are happening)
2. Immediate Actions (what to do right now)
3. Specific Commands (exact shell commands to run)
4. Preventive Measures (how to avoid this in future)

Be specific and actionable.`;
        }

        // Step 4: Call AI for analysis
        const aiResponse = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: analysisPrompt,
                history: []
            })
        });

        const aiResult = await aiResponse.json();

        if (!aiResult.success) {
            throw new Error(aiResult.error || 'AI analysis failed');
        }

        // Step 5: Display results
        const statusColor = issues.length === 0 ? '#4ade80' : '#f87171';
        const statusIcon = issues.length === 0 ? '' : '';
        const statusText = issues.length === 0 ? 'System Healthy' : `${issues.length} Issue${issues.length > 1 ? 's' : ''} Found`;

        resultsDiv.innerHTML = `
            <!-- Status Header -->
            <div style="background: linear-gradient(135deg, rgba(102, 126, 234, 0.2) 0%, rgba(118, 75, 162, 0.2) 100%); padding: 20px; border-radius: 12px; border-left: 4px solid ${statusColor};">
                <div style="font-size: 24px; font-weight: bold; color: white; margin-bottom: 8px;">
                    ${statusIcon} ${statusText}
                </div>
                <div style="color: #94a3b8; font-size: 14px;">
                    Analysis completed at ${new Date().toLocaleTimeString()}
                </div>
            </div>
            
            <!-- Current Metrics -->
            <div style="background: rgba(255,255,255,0.05); padding: 16px; border-radius: 12px;">
                <div style="font-weight: bold; color: #a855f7; margin-bottom: 12px;"> Current Metrics:</div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
                    <div style="background: rgba(0,0,0,0.3); padding: 12px; border-radius: 8px; text-align: center;">
                        <div style="color: #94a3b8; font-size: 12px;">CPU</div>
                        <div style="font-size: 20px; font-weight: bold; color: ${latestData.cpu_usage > 80 ? '#f87171' : '#4ade80'};">
                            ${latestData.cpu_usage.toFixed(1)}%
                        </div>
                    </div>
                    <div style="background: rgba(0,0,0,0.3); padding: 12px; border-radius: 8px; text-align: center;">
                        <div style="color: #94a3b8; font-size: 12px;">Memory</div>
                        <div style="font-size: 20px; font-weight: bold; color: ${latestData.memory_usage > 8 ? '#f87171' : '#4ade80'};">
                            ${latestData.memory_usage.toFixed(2)} GB
                        </div>
                    </div>
                    <div style="background: rgba(0,0,0,0.3); padding: 12px; border-radius: 8px; text-align: center;">
                        <div style="color: #94a3b8; font-size: 12px;">Latency</div>
                        <div style="font-size: 20px; font-weight: bold; color: ${latestData.response_time > 1000 ? '#f87171' : '#4ade80'};">
                            ${latestData.response_time} ms
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- AI Recommendations -->
            <div style="background: rgba(168, 85, 247, 0.1); padding: 20px; border-radius: 12px; border: 1px solid rgba(168, 85, 247, 0.3);">
                <div style="font-weight: bold; color: #a855f7; margin-bottom: 12px; font-size: 16px;">
                     AI Analysis & Recommendations:
                </div>
                <div style="color: white; line-height: 1.6;">
                    ${formatAiResponse(aiResult.response)}
                </div>
            </div>
        `;

    } catch (e) {
        console.error('Analysis error:', e);
        resultsDiv.innerHTML = `
            <div style="background: rgba(248, 113, 113, 0.2); padding: 20px; border-radius: 12px; border-left: 4px solid #f87171;">
                <div style="font-weight: bold; color: #f87171; margin-bottom: 8px;"> Analysis Failed</div>
                <div style="color: white;">${e.message}</div>
                <div style="color: #94a3b8; margin-top: 12px; font-size: 14px;">
                    Make sure the backend server is running and Groq API is configured.
                </div>
            </div>
        `;
    } finally {
        btn.disabled = false;
        btn.textContent = ' Analyze Dashboard & Get AI Recommendations';
    }
}

// Feature: Hotfix
window.deployHotfix = async () => {
    // Current config
    const res = await fetch(`${API_BASE}/config`);
    const result = await res.json();
    if (result.success) {
        const config = result.config;
        config.hotfix_until = Date.now() / 1000 + 30; // 30s from now

        await fetch(`${API_BASE}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        alert(" Hotfix Deployed! System stabilization initiated.");
        loadDashboardData();
    }
}

// Init
setInterval(() => {
    const now = new Date();
    document.getElementById('clock').innerText = now.toLocaleTimeString();
}, 1000);

// Auto Refresh Monitor every 2s
setInterval(() => {
    if (document.getElementById('monitoring').classList.contains('active')) {
        loadDashboardData();
    }
}, 2000);

loadDashboardData();






