(function () {
    "use strict";

    const config = window.furiganalyseJob;
    if (!config) return;

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
        latestProgressData = progress;
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

            // Render Discovered Context Panel
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
        const consoleEl = byId("backend-console-logs");
        if (consoleEl && progress.log_lines && progress.log_lines.length > 0) {
            consoleEl.innerHTML = progress.log_lines.map(line => {
                const isHighlight = line.includes("ready") || line.includes("Ready") || line.includes("Complete") || line.includes("packaged");
                const isPass = line.includes("Pass 1") || line.includes("Pass 2") || line.includes("Translating") || line.includes("Ollama") || line.includes("Hetzner") || line.includes("Series") || line.includes("Module 2");
                const cls = isHighlight ? "console-log-line--highlight" : (isPass ? "console-log-line--pass" : "console-log-line--normal");
                return `<div class="console-log-line ${cls}">${escapeHtml(line)}</div>`;
            }).join("");
            consoleEl.scrollTop = consoleEl.scrollHeight;
        }

        updateStages(progress.stage);
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

    async function poll() {
        try {
            const response = await fetch(config.statusUrl, {headers: {"Accept": "application/json"}, cache: "no-store"});
            if (!response.ok) throw new Error("status unavailable");
            const data = await response.json();
            updateProgress(data.progress);
            if (data.status === "complete") return showComplete(data.progress);
            if (data.status === "cancelled" || (data.progress && data.progress.stage === "cancelled")) return showCancelled();
            if (data.status === "error") return showError();
            window.setTimeout(poll, DEFAULT_POLL_INTERVAL_MS);
        } catch (error) {
            showError();
        }
    }

    const cancelBtn = byId("cancel-button");
    if (cancelBtn) {
        cancelBtn.addEventListener("click", async function () {
            if (confirm("Are you sure you want to cancel this conversion?")) {
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
                alert("Context data is still generating. Please wait a moment.");
                return;
            }
            const defaultName = prompt("Enter a Series Name to save this Cast & Glossary for next volumes:", "My Light Novel Series");
            if (!defaultName) return;

            const casts = (latestProgressData.cast_summary || []).reduce((acc, c) => {
                acc[c.name] = { kanji: c.name, romanized: c.romanized || c.name, role: c.role || "Character" };
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
                        title: defaultName,
                        characters: casts,
                        glossary: glossary
                    })
                });
                if (resp.ok) {
                    alert("Series Memory profile saved! You can now select '" + defaultName + "' when converting Volume 2, 3, etc.");
                    saveSeriesBtn.textContent = "✓ Saved to Series";
                } else {
                    alert("Failed to save series profile.");
                    saveSeriesBtn.disabled = false;
                    saveSeriesBtn.textContent = "💾 Save to Series Memory";
                }
            } catch (e) {
                alert("Error saving series: " + e.message);
                saveSeriesBtn.disabled = false;
                saveSeriesBtn.textContent = "💾 Save to Series Memory";
            }
        });
    }

    window.setTimeout(poll, INITIAL_POLL_DELAY_MS);
}());
