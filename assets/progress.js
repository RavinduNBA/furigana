(function () {
    "use strict";

    const config = window.furiganalyseJob;
    if (!config) return;

    let latestProgressData = null;

    const DEFAULT_POLL_INTERVAL_MS = 1000;
    const INITIAL_POLL_DELAY_MS = 250;
    const BYTES_PER_KB = 1024;
    const BYTES_PER_MB = 1048576;
    const SECONDS_PER_MINUTE = 60;

    function byId(id) { return document.getElementById(id); }
    function formatNumber(value) { return Number(value || 0).toLocaleString(); }
    function formatDuration(seconds) {
        if (seconds === null || seconds === undefined) return "calculating…";
        const minutes = Math.floor(seconds / SECONDS_PER_MINUTE);
        const remainder = Math.round(seconds % SECONDS_PER_MINUTE);
        return minutes ? minutes + "m " + remainder + "s" : remainder + "s";
    }
    function formatBytes(bytes) {
        if (bytes === null || bytes === undefined) return "pending";
        if (bytes < BYTES_PER_KB) return bytes + " B";
        if (bytes < BYTES_PER_MB) return (bytes / BYTES_PER_KB).toFixed(1) + " KB";
        return (bytes / BYTES_PER_MB).toFixed(1) + " MB";
    }
    function stageLabel(stage) {
        return ({
            queued: "Queued",
            preparing: "Preparing files",
            extracting: "Extracting ebook",
            "canonical-analysis": "Mapping canonical chapters",
            tokenizing: "Tokenizing Japanese text",
            "dictionary-lookup": "Looking up JMdict vocabulary",
            "expression-lookup": "Looking up JMdict expressions",
            "name-lookup": "Looking up JMnedict names",
            "study-selection": "Selecting study items",
            "linked-rendering": "Building notes and backlinks",
            "assistance-selection": "Applying assistance states",
            "density-planning": "Scheduling assistance density",
            "adaptive-rendering": "Rendering adaptive assistance",
            "bilingual-translation": "Translating companion chapters",
            processing: "Annotating Japanese text",
            packaging: "Packaging output",
            complete: "Complete",
            cancelled: "Cancelled",
            error: "Stopped"
        })[stage] || "Working";
    }

    function getPipelineActionSummary(progress) {
        if (!progress) return "Waiting for the worker…";
        const stage = progress.stage;
        const comp = formatNumber(progress.sections_completed || 0);
        const total = formatNumber(progress.sections_total || 0);
        const chars = formatNumber(progress.characters_processed || 0);
        const charsTotal = formatNumber(progress.characters_total || 0);
        const words = formatNumber(progress.words_processed || 0);
        const wordsTotal = formatNumber(progress.words_total || 0);

        switch (stage) {
            case "queued":
                return "Job is queued and waiting for worker process allocation…";
            case "preparing":
                return "Validating and staging EPUB archive files…";
            case "extracting":
                return "Extracting XHTML book chapters and stylesheet manifests (" + comp + " / " + total + " sections)…";
            case "canonical-analysis":
                return "Analyzing reading order, ruby structure, and book metadata…";
            case "tokenizing":
                return "Tokenizing Japanese text & morphological decomposition (" + chars + " / " + charsTotal + " characters scanned)…";
            case "dictionary-lookup":
                return "Looking up vocabulary in JMdict (" + words + " / " + wordsTotal + " candidates matched)…";
            case "expression-lookup":
                return "Matching multi-word idioms and expressions in JMdict…";
            case "name-lookup":
                return "Identifying proper nouns, character names, and places in JMnedict…";
            case "study-selection":
                return "Filtering target vocabulary by JLPT level and learner profile…";
            case "linked-rendering":
                return "Generating bidirectional chapter study notes and glosses…";
            case "assistance-selection":
                return "Assigning inline dictionary definitions and assistance levels…";
            case "density-planning":
                return "Balancing furigana and gloss density across book sections…";
            case "adaptive-rendering":
                return "Injecting adaptive assistance into XHTML chapter documents…";
            case "bilingual-translation": {
                const pComp = formatNumber(progress.translation_paragraphs_completed || 0);
                const pTotal = formatNumber(progress.translation_paragraphs_total || 0);
                const chComp = formatNumber(progress.translation_chapters_completed || 0);
                const chTotal = formatNumber(progress.translation_chapters_total || 0);
                return "Translating companion chapters with LLM: " + pComp + " / " + pTotal + " paragraphs (" + chComp + " / " + chTotal + " chapters)…";
            }
            case "processing":
                return "Annotating Japanese text with furigana readings (" + comp + " / " + total + " sections)…";
            case "packaging":
                return "Reassembling and compressing final EPUB container with deterministic structure…";
            case "complete":
                return "All processing stages completed successfully!";
            case "cancelled":
                return "Conversion cancelled by user.";
            case "error":
                return "Conversion encountered an issue and stopped safely.";
            default:
                return "Processing ebook…";
        }
    }

    function getRemainingWorkSummary(progress) {
        if (!progress) return "Calculating remaining work…";
        if (progress.stage === "complete") return "0 tasks remaining · 100% complete";
        if (progress.stage === "bilingual-translation") {
            const pLeft = (progress.translation_paragraphs_total || 0) - (progress.translation_paragraphs_completed || 0);
            const chLeft = (progress.translation_chapters_total || 0) - (progress.translation_chapters_completed || 0);
            return Math.max(0, pLeft) + " paragraphs (" + Math.max(0, chLeft) + " chapters) remaining to translate";
        }
        if (progress.pipeline_mode === "study" || (["combined", "guided"].includes(progress.pipeline_mode) && progress.combined_phase !== "furigana")) {
            const wLeft = progress.words_remaining || 0;
            const sLeft = progress.sections_remaining || 0;
            return formatNumber(wLeft) + " words · " + formatNumber(sLeft) + " sections left";
        }
        const sLeft = progress.sections_remaining !== undefined ? progress.sections_remaining : Math.max(0, (progress.sections_total || 0) - (progress.sections_completed || 0));
        const cLeft = progress.characters_remaining !== undefined ? progress.characters_remaining : Math.max(0, (progress.characters_total || 0) - (progress.characters_processed || 0));
        return formatNumber(sLeft) + " sections (" + formatNumber(cLeft) + " chars) left";
    }

    function updateStages(stage) {
        const groups = [
            ["queued", "preparing", "extracting"],
            ["canonical-analysis", "tokenizing", "processing"],
            ["dictionary-lookup", "expression-lookup", "name-lookup"],
            ["study-selection", "linked-rendering"],
            ["assistance-selection", "density-planning", "adaptive-rendering"],
            ["bilingual-translation", "packaging", "complete"]
        ];
        const current = groups.findIndex(group => group.includes(stage));
        document.querySelectorAll(".stage-strip span").forEach(function (element, index) {
            element.classList.toggle("is-active", index === current);
            element.classList.toggle("is-complete", current > index || stage === "complete");
        });
    }

    function updateProgress(progress) {
        if (!progress) return;
        latestProgressData = Object.assign({}, latestProgressData, progress);
        if (progress.cast_summary) latestProgressData.cast_summary = progress.cast_summary;
        if (progress.glossary_summary) latestProgressData.glossary_summary = progress.glossary_summary;
        const percent = progress.percent || 0;
        byId("conversion-progress").value = percent;
        byId("conversion-progress").textContent = percent + "%";
        byId("progress-percent").textContent = percent + "%";
        const combinedPrefix = ["combined", "guided"].includes(progress.pipeline_mode) ?
            (progress.combined_phase === "furigana" ? "Furigana · " : "Dictionary · ") : "";
        byId("progress-stage").textContent = combinedPrefix + stageLabel(progress.stage);
        byId("progress-sections").textContent = formatNumber(progress.sections_completed) + " / " + formatNumber(progress.sections_total);
        byId("progress-characters").textContent = formatNumber(progress.characters_processed) + " / " + formatNumber(progress.characters_total);
        byId("progress-words").textContent = formatNumber(progress.words_processed) + " / " + formatNumber(progress.words_total);
        byId("words-caption").textContent = formatNumber(progress.words_remaining) + " candidates left";
        byId("progress-matches").textContent = formatNumber(progress.dictionary_matches) + " words · " + formatNumber(progress.expression_matches) + " expressions · " + formatNumber(progress.name_matches) + " names";
        byId("matches-caption").textContent = progress.study_items ? formatNumber(progress.study_items) + " selected study items" : "Local dictionary only";
        byId("progress-remaining").textContent = getRemainingWorkSummary(progress);
        byId("progress-elapsed").textContent = formatDuration(progress.elapsed_seconds);
        byId("progress-eta").textContent = progress.eta_seconds === null ? "ETA calculating…" : "ETA " + formatDuration(progress.eta_seconds);
        byId("progress-rate").textContent = formatNumber(progress.characters_per_second) + " chars/s";
        byId("progress-size").textContent = formatBytes(progress.input_bytes) + " → " + formatBytes(progress.output_bytes);
        byId("progress-status-note").textContent = getPipelineActionSummary(progress);

        const transPanel = byId("bilingual-progress-panel");
        if (transPanel && (progress.translation_backend || progress.stage === "bilingual-translation")) {
            transPanel.hidden = false;
            const modelEl = byId("progress-trans-model");
            const backendEl = byId("progress-trans-backend");
            const paraEl = byId("progress-trans-paragraphs");
            const cacheEl = byId("progress-trans-cache");
            const badgeEl = byId("bilingual-status-badge");

            if (modelEl && progress.translation_backend) modelEl.textContent = progress.translation_backend;
            if (backendEl) {
                backendEl.textContent = progress.stage === "bilingual-translation" ?
                    "Translating scene batches on local CPU…" :
                    (progress.stage === "complete" ? "Companion translation ready" : "Self-hosted local inference");
            }
            if (paraEl && progress.translation_paragraphs_total !== undefined) {
                paraEl.textContent = formatNumber(progress.translation_paragraphs_completed || 0) + " / " + formatNumber(progress.translation_paragraphs_total) + " paragraphs";
            }
            if (cacheEl && progress.translation_cache_hits !== undefined) {
                cacheEl.textContent = formatNumber(progress.translation_cache_hits) + " disk cache hits · " + formatNumber(progress.translation_chapters_completed || 0) + " / " + formatNumber(progress.translation_chapters_total || 0) + " chapters";
            }
            if (badgeEl) {
                const isActive = progress.stage === "bilingual-translation";
                badgeEl.textContent = isActive ? "Translating" : (progress.stage === "complete" ? "Ready" : "Active");
                badgeEl.classList.toggle("status-badge--active", isActive);
            }

            const streamCh = byId("stream-chapter-tag");
            const streamJa = byId("stream-japanese-text");
            const streamEn = byId("stream-english-text");

            if (streamCh && progress.translation_current_chapter) {
                streamCh.textContent = progress.translation_current_chapter;
            }
            if (streamJa && progress.translation_latest_japanese) {
                streamJa.textContent = progress.translation_latest_japanese;
            }
            if (streamEn && progress.translation_latest_english) {
                streamEn.textContent = progress.translation_latest_english;
            }
        }

        // Render Discovered Context Panel (Cast & Glossary) whenever available
        const contextPanel = byId("discovered-context-panel");
        const castRow = byId("cast-chips-row");
        const glossRow = byId("glossary-chips-row");
        const countEl = byId("context-item-count");

        if (contextPanel && (progress.cast_summary || progress.glossary_summary)) {
            contextPanel.hidden = false;
            const casts = progress.cast_summary || [];
            const gloss = progress.glossary_summary || [];
            if (countEl) countEl.textContent = (casts.length + gloss.length) + " items discovered";

            if (castRow && casts.length > 0) {
                castRow.innerHTML = casts.map(c => `
                    <div class="context-chip context-chip--cast">
                        <strong>${c.name}</strong>
                        <span>${c.romanized || c.name}</span>
                        <small>${c.role || "Character"}</small>
                    </div>
                `).join("");
            }

            if (glossRow && gloss.length > 0) {
                glossRow.innerHTML = gloss.map(g => `
                    <div class="context-chip context-chip--glossary">
                        <strong>${g.japanese}</strong>
                        <span>${g.translation || g.definition || ""}</span>
                    </div>
                `).join("");
            }
        }

        // Show early main download if main Japanese file is ready
        if (progress.main_file_ready) {
            const mainCard = byId("main-download-card");
            if (mainCard) mainCard.hidden = false;
        }
        if (progress.bilingual_file_ready) {
            const biCard = byId("bilingual-download-card");
            if (biCard) biCard.hidden = false;
        }

        // Render Live Backend Console Logs
        if (progress.log_lines && progress.log_lines.length > 0) {
            allLogLines = progress.log_lines;
            renderConsoleLogs();
        }

        updateStages(progress.stage);
    }

    let allLogLines = [];
    let activeFilterCategory = "all";
    let activeSearchQuery = "";
    let autoScrollEnabled = true;

    function getLineClass(line) {
        if (line.includes("[ERROR]") || line.includes("failed") || line.includes("Failed") || line.includes("Exception") || line.includes("Error:")) {
            return "console-log-line--error";
        }
        if (line.includes("[WARN]") || line.includes("Warning") || line.includes("skipped")) {
            return "console-log-line--warn";
        }
        if (line.includes("[SUCCESS]") || line.includes("100% complete") || line.includes("ready") || line.includes("Ready") || line.includes("Complete") || line.includes("packaged")) {
            return "console-log-line--highlight";
        }
        if (line.includes("Module 2") || line.includes("Module 3") || line.includes("Module 4") || line.includes("Pass 1") || line.includes("Pass 2") || line.includes("Series Memory") || line.includes("LLM") || line.includes("Ollama") || line.includes("Hetzner") || line.includes("Translating")) {
            return "console-log-line--module";
        }
        if (line.includes("Phase 1") || line.includes("Phase 2") || line.includes("Furigana Pass") || line.includes("Furigana Engine") || line.includes("Tokenized") || line.includes("Dictionary") || line.includes("JMdict") || line.includes("JMnedict") || line.includes("Annotation Plan") || line.includes("Sanitizing") || line.includes("Starting conversion")) {
            return "console-log-line--phase";
        }
        if (line.includes("Initializing")) {
            return "console-log-line--dim";
        }
        return "console-log-line--normal";
    }

    function renderConsoleLogs() {
        const consoleEl = byId("backend-console-logs");
        if (!consoleEl) return;

        let filtered = allLogLines;

        if (activeFilterCategory === "phases") {
            filtered = filtered.filter(l => l.includes("Phase") || l.includes("Furigana Pass") || l.includes("Furigana Engine") || l.includes("Tokenized") || l.includes("Dictionary") || l.includes("JMdict") || l.includes("JMnedict") || l.includes("Annotation Plan") || l.includes("Sanitizing") || l.includes("Packaging") || l.includes("Starting conversion") || l.includes("Extracted EPUB"));
        } else if (activeFilterCategory === "modules") {
            filtered = filtered.filter(l => l.includes("Module") || l.includes("Pass 1") || l.includes("Pass 2") || l.includes("Series Memory") || l.includes("LLM") || l.includes("Ollama") || l.includes("Hetzner") || l.includes("Cast") || l.includes("Glossary") || l.includes("Translating") || l.includes("enriched"));
        } else if (activeFilterCategory === "errors") {
            filtered = filtered.filter(l => l.includes("[ERROR]") || l.includes("[WARN]") || l.includes("failed") || l.includes("Failed") || l.includes("Exception") || l.includes("Error:") || l.includes("Warning"));
        }

        if (activeSearchQuery) {
            const q = activeSearchQuery.toLowerCase();
            filtered = filtered.filter(l => l.toLowerCase().includes(q));
        }

        const countBadge = byId("console-log-count");
        if (countBadge) {
            if (filtered.length === allLogLines.length) {
                countBadge.textContent = `${allLogLines.length} ${allLogLines.length === 1 ? "entry" : "entries"}`;
            } else {
                countBadge.textContent = `${filtered.length} / ${allLogLines.length} shown`;
            }
        }

        if (filtered.length === 0) {
            consoleEl.innerHTML = `<div class="console-log-line console-log-line--dim">No logs match the current filter.</div>`;
        } else {
            consoleEl.innerHTML = filtered.map(line => {
                const cls = getLineClass(line);
                return `<div class="console-log-line ${cls}">${escapeHtml(line)}</div>`;
            }).join("");
        }

        if (autoScrollEnabled) {
            consoleEl.scrollTop = consoleEl.scrollHeight;
        }
    }

    function escapeHtml(str) {
        return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function showComplete(progress) {
        byId("conversion-progress").value = 100;
        byId("conversion-progress").textContent = "100%";
        byId("progress-percent").textContent = "100%";
        byId("job-title").textContent = "Conversion complete";
        byId("job-description").textContent = "Your converted ebook is ready to download.";
        byId("header-status-text").textContent = "Ready";
        document.querySelector(".header-status .status-dot").classList.remove("status-dot--pulse");
        if (progress && (progress.main_file_ready || progress.bilingual_file_ready)) {
            if (progress.main_file_ready) byId("main-download-card").hidden = false;
            if (progress.bilingual_file_ready) byId("bilingual-download-card").hidden = false;
        } else {
            byId("result").hidden = false;
        }
        const cancelBtn = byId("cancel-button");
        if (cancelBtn) cancelBtn.hidden = true;
        updateStages("complete");
    }

    function showCancelled() {
        byId("job-title").textContent = "Conversion cancelled";
        byId("job-description").textContent = "Conversion was stopped by user. No partial files were saved.";
        byId("header-status-text").textContent = "Cancelled";
        document.querySelector(".header-status .status-dot").classList.remove("status-dot--pulse");
        byId("cancelled").hidden = false;
        const cancelBtn = byId("cancel-button");
        if (cancelBtn) cancelBtn.hidden = true;
    }

    function showError() {
        byId("job-title").textContent = "Conversion failed";
        byId("job-description").textContent = "No partially converted file will be offered.";
        byId("header-status-text").textContent = "Needs attention";
        document.querySelector(".header-status .status-dot").classList.remove("status-dot--pulse");
        byId("error").hidden = false;
        const cancelBtn = byId("cancel-button");
        if (cancelBtn) cancelBtn.hidden = true;
    }

    let consecutiveErrors = 0;
    const MAX_CONSECUTIVE_ERRORS = 6;

    async function poll() {
        try {
            const response = await fetch(config.statusUrl, {headers: {"Accept": "application/json"}, cache: "no-store"});
            if (!response.ok) {
                consecutiveErrors++;
                if (consecutiveErrors <= MAX_CONSECUTIVE_ERRORS) {
                    return window.setTimeout(poll, DEFAULT_POLL_INTERVAL_MS);
                }
                throw new Error("status unavailable");
            }
            const data = await response.json();
            consecutiveErrors = 0;
            updateProgress(data.progress);
            if (data.status === "complete") return showComplete(data.progress);
            if (data.status === "cancelled" || (data.progress && data.progress.stage === "cancelled")) return showCancelled();
            if (data.status === "error") return showError();
            window.setTimeout(poll, DEFAULT_POLL_INTERVAL_MS);
        } catch (error) {
            consecutiveErrors++;
            if (consecutiveErrors <= MAX_CONSECUTIVE_ERRORS) {
                window.setTimeout(poll, DEFAULT_POLL_INTERVAL_MS);
            } else {
                showError();
            }
        }
    }

    const cancelBtn = byId("cancel-button");
    if (cancelBtn) {
        cancelBtn.addEventListener("click", async function () {
            const confirmed = await window.showConfirmDialog({
                title: "Cancel Conversion",
                message: "Are you sure you want to cancel this active conversion process?",
                confirmText: "Cancel Conversion",
                cancelText: "Continue Process",
                danger: true,
            });
            if (confirmed) {
                cancelBtn.disabled = true;
                cancelBtn.textContent = "Cancelling…";
                try {
                    const cancelUrl = config.statusUrl.replace(/\/status$/, "/cancel");
                    await fetch(cancelUrl, {method: "POST"});
                    showCancelled();
                } catch (e) {
                    console.error("Cancel failed:", e);
                }
            }
        });
    }

    const saveSeriesBtn = byId("save-series-btn");
    if (saveSeriesBtn) {
        saveSeriesBtn.addEventListener("click", async function () {
            if (!latestProgressData) {
                await window.showAlertDialog({
                    title: "Context Generating",
                    message: "Context data is still generating. Please wait a moment.",
                    type: "info",
                });
                return;
            }

            // Extract book filename/title from download card or log lines for auto-suggestion
            let rawBookName = "";
            const downloadNameEl = byId("download-name");
            if (downloadNameEl && downloadNameEl.textContent) {
                rawBookName = downloadNameEl.textContent.trim();
            }
            if (!rawBookName && latestProgressData.log_lines && latestProgressData.log_lines.length) {
                for (const line of latestProgressData.log_lines) {
                    const match = line.match(/Starting conversion:\s*'([^']+)'/);
                    if (match && match[1]) {
                        rawBookName = match[1];
                        break;
                    }
                }
            }

            // Fetch auto-suggested series title and slug
            let suggestedTitle = "My Light Novel Series";
            let suggestedId = "";
            let detectedVolume = "";
            if (rawBookName) {
                try {
                    const sResp = await fetch("/api/series/suggest?query=" + encodeURIComponent(rawBookName));
                    if (sResp.ok) {
                        const sData = await sResp.json();
                        if (sData.title) suggestedTitle = sData.title;
                        if (sData.series_id) suggestedId = sData.series_id;
                        if (sData.volume_name) detectedVolume = sData.volume_name;
                    }
                } catch (e) {
                    console.warn("Series suggestion fetch failed:", e);
                }
            }

            const promptMsg = detectedVolume ?
                `Enter Series Name for ${detectedVolume} (auto-suggested from book title):` :
                "Enter a Series Name to save this Cast & Glossary for next volumes:";

            const chosenName = await window.showPromptDialog({
                title: "Save to Series Memory",
                message: promptMsg,
                defaultValue: suggestedTitle,
                placeholder: "e.g. 魔法科高校の劣等生",
                confirmText: "Save Series",
                cancelText: "Cancel",
            });
            if (!chosenName || !chosenName.trim()) return;

            const casts = (latestProgressData.cast_summary || []).reduce((acc, c) => {
                const relVal = typeof c.relationships === "object" && c.relationships !== null ?
                    Object.entries(c.relationships).map(([target, desc]) => desc ? `${target}: ${desc}` : target).join(", ") :
                    (c.relationships || "");
                acc[c.name] = {
                    kanji: c.name,
                    reading: c.reading || c.romanized || "",
                    romanized: c.romanized || c.name,
                    role: c.role || "Character",
                    gender: c.gender || "unknown",
                    relationships: relVal,
                    aliases: Array.isArray(c.aliases) ? c.aliases : (c.aliases ? [c.aliases] : []),
                    speaking_tone: c.speaking_tone || "",
                };
                return acc;
            }, {});
            const glossary = (latestProgressData.glossary_summary || []).reduce((acc, g) => {
                acc[g.japanese] = { japanese: g.japanese, preferred_translation: g.translation || g.definition || "" };
                return acc;
            }, {});

            try {
                saveSeriesBtn.disabled = true;
                saveSeriesBtn.textContent = "Saving…";
                const resp = await fetch("/api/series", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        series_id: (chosenName.trim() === suggestedTitle.trim() && suggestedId) ? suggestedId : chosenName.trim(),
                        title: chosenName.trim(),
                        volume_name: detectedVolume,
                        characters: casts,
                        glossary: glossary
                    })
                });
                if (resp.ok) {
                    await window.showAlertDialog({
                        title: "Series Memory Saved",
                        message: `Series Memory profile saved! You can now select '${chosenName.trim()}' when converting subsequent volumes.`,
                        type: "success",
                    });
                    saveSeriesBtn.textContent = "✓ Saved to Series";
                } else {
                    await window.showAlertDialog({
                        title: "Save Failed",
                        message: "Failed to save series profile to server.",
                        type: "error",
                    });
                    saveSeriesBtn.disabled = false;
                    saveSeriesBtn.textContent = "💾 Save to Series Memory";
                }
            } catch (e) {
                await window.showAlertDialog({
                    title: "Error",
                    message: "Error saving series: " + e.message,
                    type: "error",
                });
                saveSeriesBtn.disabled = false;
                saveSeriesBtn.textContent = "💾 Save to Series Memory";
            }
        });
    }

    // Console Interactive Toolbar Actions
    const filterToggleBtn = byId("console-filter-btn");
    const filterBar = byId("console-filter-bar");
    if (filterToggleBtn && filterBar) {
        filterToggleBtn.addEventListener("click", function () {
            const isHidden = filterBar.hidden;
            filterBar.hidden = !isHidden;
            filterToggleBtn.classList.toggle("active", isHidden);
            if (isHidden) {
                const input = byId("console-search-input");
                if (input) input.focus();
            }
        });
    }

    const searchInput = byId("console-search-input");
    if (searchInput) {
        searchInput.addEventListener("input", function () {
            activeSearchQuery = searchInput.value.trim();
            renderConsoleLogs();
        });
    }

    const filterChips = document.querySelectorAll(".console-filter-chips .filter-chip");
    filterChips.forEach(chip => {
        chip.addEventListener("click", function () {
            filterChips.forEach(c => c.classList.remove("active"));
            chip.classList.add("active");
            activeFilterCategory = chip.getAttribute("data-filter") || "all";
            renderConsoleLogs();
        });
    });

    const autoscrollBtn = byId("console-autoscroll-btn");
    if (autoscrollBtn) {
        autoscrollBtn.addEventListener("click", function () {
            autoScrollEnabled = !autoScrollEnabled;
            autoscrollBtn.classList.toggle("active", autoScrollEnabled);
            autoscrollBtn.textContent = autoScrollEnabled ? "⬇ Auto-scroll: ON" : "⏸ Auto-scroll: OFF";
            if (autoScrollEnabled) {
                const consoleEl = byId("backend-console-logs");
                if (consoleEl) consoleEl.scrollTop = consoleEl.scrollHeight;
            }
        });
    }

    const expandBtn = byId("console-expand-btn");
    const consoleCard = byId("backend-console-card");
    if (expandBtn && consoleCard) {
        expandBtn.addEventListener("click", function () {
            const isExpanded = consoleCard.classList.toggle("is-expanded");
            expandBtn.textContent = isExpanded ? "⤡ Collapse" : "⤢ Expand";
            expandBtn.classList.toggle("active", isExpanded);
        });
    }

    const copyBtn = byId("console-copy-btn");
    if (copyBtn) {
        copyBtn.addEventListener("click", async function () {
            if (allLogLines.length === 0) {
                await window.showAlertDialog({
                    title: "No Logs Available",
                    message: "No console logs available to copy yet.",
                    type: "info",
                });
                return;
            }
            try {
                await navigator.clipboard.writeText(allLogLines.join("\n"));
                const origText = copyBtn.textContent;
                copyBtn.textContent = "✓ Copied!";
                copyBtn.style.color = "#4ade80";
                setTimeout(() => {
                    copyBtn.textContent = origText;
                    copyBtn.style.color = "";
                }, 2000);
            } catch (err) {
                // Fallback for older browsers
                const ta = document.createElement("textarea");
                ta.value = allLogLines.join("\n");
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                const origText = copyBtn.textContent;
                copyBtn.textContent = "✓ Copied!";
                setTimeout(() => { copyBtn.textContent = origText; }, 2000);
            }
        });
    }

    function initRecentConversionsControls() {
        const clearBtn = byId("clear-recent-btn");
        if (clearBtn) {
            clearBtn.addEventListener("click", async function () {
                const confirmed = await window.showConfirmDialog({
                    title: "Clear Conversion History",
                    message: "Are you sure you want to clear all recent conversions? Saved files will no longer be stored for re-downloading.",
                    confirmText: "Clear all",
                    cancelText: "Keep history",
                    danger: true,
                });
                if (!confirmed) return;
                try {
                    clearBtn.disabled = true;
                    clearBtn.textContent = "Clearing…";
                    const resp = await fetch("/api/recent_conversions", { method: "DELETE" });
                    if (resp.ok) {
                        const list = document.querySelector(".recent-list");
                        if (list) {
                            list.innerHTML = '<p class="recent-empty-note">Your last 10 conversions will appear here for fast re-downloading.</p>';
                        }
                        const badge = byId("recent-count-badge");
                        if (badge) badge.textContent = "0 saved";
                        clearBtn.remove();
                    } else {
                        await window.showAlertDialog({
                            title: "Error",
                            message: "Failed to clear recent conversions.",
                            type: "error",
                        });
                        clearBtn.disabled = false;
                        clearBtn.textContent = "Clear all";
                    }
                } catch (e) {
                    await window.showAlertDialog({
                        title: "Error",
                        message: "Error: " + e.message,
                        type: "error",
                    });
                    clearBtn.disabled = false;
                    clearBtn.textContent = "Clear all";
                }
            });
        }

        document.querySelectorAll(".recent-del-item-btn").forEach(btn => {
            btn.addEventListener("click", async function (e) {
                e.preventDefault();
                e.stopPropagation();
                const uid = this.dataset.uid;
                if (!uid) return;
                const confirmed = await window.showConfirmDialog({
                    title: "Remove Conversion",
                    message: "Remove this conversion from history?",
                    confirmText: "Remove",
                    cancelText: "Keep",
                    danger: true,
                });
                if (!confirmed) return;
                try {
                    const resp = await fetch("/api/recent_conversions/" + uid, { method: "DELETE" });
                    if (resp.ok) {
                        const itemEl = this.closest(".recent-item");
                        if (itemEl) itemEl.remove();
                        const remaining = document.querySelectorAll(".recent-item").length;
                        const badge = byId("recent-count-badge");
                        if (badge) badge.textContent = remaining + " saved";
                        if (remaining === 0) {
                            const list = document.querySelector(".recent-list");
                            if (list) {
                                list.innerHTML = '<p class="recent-empty-note">Your last 10 conversions will appear here for fast re-downloading.</p>';
                            }
                            const clearBtnEl = byId("clear-recent-btn");
                            if (clearBtnEl) clearBtnEl.remove();
                        }
                    }
                } catch (e) {}
            });
        });
    }

    initRecentConversionsControls();
    window.setTimeout(poll, INITIAL_POLL_DELAY_MS);
}());
