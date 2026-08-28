(function () {
    "use strict";

    const OLLAMA_STATUS_ENDPOINT = "/api/ollama/status";
    const OLLAMA_MODEL_ENDPOINT = "/api/ollama/model";
    const OLLAMA_PULL_ENDPOINT = "/api/ollama/pull";
    const OLLAMA_STREAM_TEST_ENDPOINT = "/api/ollama/stream_test";
    const TELEMETRY_REFRESH_INTERVAL_MS = 10000;
    const BYTES_PER_KB = 1024;
    const BYTES_PER_MB = 1048576;
    const BYTES_PER_GB = 1073741824;

    function byId(id) { return document.getElementById(id); }

    function formatBytes(bytes) {
        if (!bytes) return "0 B";
        if (bytes < BYTES_PER_KB) return bytes + " B";
        if (bytes < BYTES_PER_MB) return (bytes / BYTES_PER_KB).toFixed(1) + " KB";
        if (bytes < BYTES_PER_GB) return (bytes / BYTES_PER_MB).toFixed(1) + " MB";
        return (bytes / BYTES_PER_GB).toFixed(2) + " GB";
    }

    async function fetchDashboardData() {
        try {
            const resp = await fetch(OLLAMA_STATUS_ENDPOINT);
            if (!resp.ok) throw new Error("Dashboard status unavailable");
            const data = await resp.json();
            updateUI(data);
        } catch (err) {
            console.error("Dashboard fetch error:", err);
            byId("ollama-online-badge").textContent = "Offline";
            byId("ollama-online-badge").className = "status-badge status-badge--error";
        }
    }

    function updateUI(data) {
        // 1. Service Status
        const onlineBadge = byId("ollama-online-badge");
        if (data.online) {
            onlineBadge.textContent = "Online · v" + data.version;
            onlineBadge.className = "status-badge status-badge--active";
            byId("ollama-version-display").textContent = "Ollama v" + data.version;
            byId("ollama-latency-display").textContent = data.latency_ms + " ms";
        } else {
            onlineBadge.textContent = "Offline";
            onlineBadge.className = "status-badge status-badge--error";
            byId("ollama-version-display").textContent = "Offline";
            byId("ollama-latency-display").textContent = "—";
        }

        // 2. Hardware Telemetry
        const tel = data.telemetry || {};
        if (tel.mem_total_bytes) {
            byId("ram-percent-badge").textContent = tel.mem_percent + "%";
            byId("ram-used-display").textContent = formatBytes(tel.mem_used_bytes);
            byId("ram-total-display").textContent = "of " + formatBytes(tel.mem_total_bytes) + " total RAM";
            byId("ram-avail-display").textContent = formatBytes(tel.mem_available_bytes);
        }
        if (tel.disk_total_bytes) {
            byId("disk-percent-badge").textContent = tel.disk_percent + "%";
            byId("disk-free-display").textContent = formatBytes(tel.disk_free_bytes);
            byId("disk-used-display").textContent = formatBytes(tel.disk_used_bytes);
        }

        // 3. Models Table
        const tbody = byId("models-table-body");
        const select = byId("sandbox-model");
        const runningNames = (data.loaded_models || []).map(m => m.name || m.model);

        if (!data.installed_models || data.installed_models.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="table-empty-cell">No models found in local storage. Pull one below.</td></tr>';
            select.innerHTML = '<option value="">No models installed</option>';
            return;
        }

        let rowsHtml = "";
        let selectHtml = "";

        data.installed_models.forEach(function (m) {
            const isLoaded = runningNames.includes(m.name) || runningNames.includes(m.model);
            const statusBadge = isLoaded ?
                '<span class="status-badge status-badge--active">Loaded in RAM</span>' :
                '<span class="status-badge">On Disk</span>';

            const family = (m.details && m.details.family) ? m.details.family : (m.name.split(":")[0]);
            const quant = (m.details && m.details.quantization_level) ? m.details.quantization_level : "Q4_K_M";

            rowsHtml += `
                <tr>
                    <td><strong>${m.name}</strong></td>
                    <td>${formatBytes(m.size)}</td>
                    <td><span class="mode-pill">${family} · ${quant}</span></td>
                    <td>${statusBadge}</td>
                    <td>
                        <button class="small-btn test-model-btn" data-model="${m.name}" type="button">Test</button>
                        <button class="small-btn small-btn--danger delete-model-btn" data-model="${m.name}" type="button">Delete</button>
                    </td>
                </tr>
            `;

            selectHtml += `<option value="${m.name}">${m.name} (${formatBytes(m.size)})</option>`;
        });

        tbody.innerHTML = rowsHtml;
        select.innerHTML = selectHtml;

        // Bind delete & test buttons
        document.querySelectorAll(".delete-model-btn").forEach(function (btn) {
            btn.addEventListener("click", async function () {
                const modelName = btn.dataset.model;
                if (confirm("Are you sure you want to delete model '" + modelName + "'?")) {
                    btn.disabled = true;
                    btn.textContent = "Deleting…";
                    try {
                        const r = await fetch(OLLAMA_MODEL_ENDPOINT + "?name=" + encodeURIComponent(modelName), {method: "DELETE"});
                        if (r.ok) {
                            fetchDashboardData();
                        } else {
                            alert("Failed to delete model.");
                        }
                    } catch (e) {
                        alert("Error: " + e.message);
                    }
                }
            });
        });

        document.querySelectorAll(".test-model-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                select.value = btn.dataset.model;
                byId("sandbox-japanese").scrollIntoView({behavior: "smooth"});
            });
        });
    }

    // Model Pull Handler
    const pullBtn = byId("pull-model-btn");
    const pullInput = byId("pull-model-input");
    const pullStatusBox = byId("pull-status-box");
    const pullStatusText = byId("pull-status-text");

    if (pullBtn) {
        pullBtn.addEventListener("click", async function () {
            const model = pullInput.value.trim();
            if (!model) return;

            pullBtn.disabled = true;
            pullStatusBox.hidden = false;
            pullStatusText.textContent = "Pulling model '" + model + "' in background… (this may take a minute)";

            try {
                const res = await fetch(OLLAMA_PULL_ENDPOINT, {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({model: model})
                });
                const data = await res.json();
                if (res.ok) {
                    pullStatusText.textContent = "Successfully downloaded '" + model + "'!";
                    pullInput.value = "";
                    fetchDashboardData();
                } else {
                    pullStatusText.textContent = "Failed: " + (data.error || "Unknown error");
                }
            } catch (err) {
                pullStatusText.textContent = "Error pulling model: " + err.message;
            } finally {
                pullBtn.disabled = false;
            }
        });
    }

    document.querySelectorAll(".tag-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
            pullInput.value = btn.dataset.model;
        });
    });

    // Context Toggle Handler
    const useContextCb = byId("sandbox-use-context");
    const contextPanel = byId("sandbox-context-panel");
    if (useContextCb && contextPanel) {
        useContextCb.addEventListener("change", function () {
            contextPanel.hidden = !useContextCb.checked;
        });
    }

    // Translation Sandbox Live Streaming Handler
    const sandboxBtn = byId("sandbox-submit-btn");
    if (sandboxBtn) {
        sandboxBtn.addEventListener("click", async function () {
            const model = byId("sandbox-model").value;
            const text = byId("sandbox-japanese").value.trim();
            if (!text || !model) return;

            const useContext = useContextCb ? useContextCb.checked : false;
            const contextText = useContext && byId("sandbox-context") ? byId("sandbox-context").value.trim() : "";

            sandboxBtn.disabled = true;
            sandboxBtn.querySelector("span").textContent = "Streaming…";
            const resultBox = byId("sandbox-result");
            const metaBox = byId("sandbox-meta");

            resultBox.innerHTML = '<span class="sandbox-placeholder">Connecting to ' + model + ' stream…</span>';
            metaBox.hidden = false;
            byId("sandbox-time").textContent = "0.00s";
            byId("sandbox-tokens").textContent = "0 tokens";
            byId("sandbox-speed").textContent = "0.0 tok/s";

            try {
                const res = await fetch(OLLAMA_STREAM_TEST_ENDPOINT, {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({model: model, text: text, context: contextText})
                });

                if (!res.ok) throw new Error("Stream connection failed (" + res.status + ")");

                resultBox.textContent = "";
                const reader = res.body.getReader();
                const decoder = new TextDecoder("utf-8");
                let buffer = "";
                let accumulated = "";
                let tokenCount = 0;
                const startTime = performance.now();

                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, {stream: true});
                    const lines = buffer.split("\n");
                    buffer = lines.pop(); // retain partial line
                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (trimmed.startsWith("data:")) {
                            const jsonStr = trimmed.slice(5).trim();
                            if (!jsonStr) continue;
                            try {
                                const chunk = JSON.parse(jsonStr);
                                const piece = (chunk.message && chunk.message.content) || "";
                                accumulated += piece;
                                resultBox.textContent = accumulated;
                                if (piece) tokenCount++;
                                const elapsedSec = (performance.now() - startTime) / 1000;
                                byId("sandbox-time").textContent = elapsedSec.toFixed(2) + "s";
                                byId("sandbox-tokens").textContent = tokenCount + " tokens";
                                byId("sandbox-speed").textContent = (tokenCount / Math.max(0.1, elapsedSec)).toFixed(1) + " tok/s";
                            } catch (e) {}
                        }
                    }
                }

                if (!accumulated) {
                    resultBox.innerHTML = '<span class="sandbox-placeholder">No output generated by model.</span>';
                }
            } catch (err) {
                resultBox.textContent = "Streaming error: " + err.message;
            } finally {
                sandboxBtn.disabled = false;
                sandboxBtn.querySelector("span").textContent = "Translate Japanese (Live Stream)";
            }
        });
    }

    const refreshBtn = byId("refresh-models-btn");
    if (refreshBtn) refreshBtn.addEventListener("click", fetchDashboardData);

    fetchDashboardData();
    setInterval(fetchDashboardData, TELEMETRY_REFRESH_INTERVAL_MS);
}());
