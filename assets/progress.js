(function () {
    "use strict";

    const config = window.furiganalyseJob;
    if (!config) return;
    const pollingInterval = 1000;

    function byId(id) { return document.getElementById(id); }
    function formatNumber(value) { return Number(value || 0).toLocaleString(); }
    function formatDuration(seconds) {
        if (seconds === null || seconds === undefined) return "calculating…";
        const minutes = Math.floor(seconds / 60);
        const remainder = Math.round(seconds % 60);
        return minutes ? minutes + "m " + remainder + "s" : remainder + "s";
    }
    function formatBytes(bytes) {
        if (bytes === null || bytes === undefined) return "pending";
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / 1048576).toFixed(1) + " MB";
    }
    function stageLabel(stage) {
        return ({queued: "Queued", preparing: "Preparing files", extracting: "Extracting ebook", "canonical-analysis": "Mapping canonical chapters", tokenizing: "Tokenizing Japanese text", "dictionary-lookup": "Looking up JMdict vocabulary", "expression-lookup": "Looking up JMdict expressions", "name-lookup": "Looking up JMnedict names", "study-selection": "Selecting study items", "linked-rendering": "Building notes and backlinks", "assistance-selection": "Applying assistance states", "density-planning": "Scheduling assistance density", "adaptive-rendering": "Rendering adaptive assistance", processing: "Annotating Japanese text", packaging: "Packaging output", complete: "Complete", error: "Stopped"})[stage] || "Working";
    }
    function updateStages(stage) {
        const groups = [
            ["queued", "preparing", "extracting"],
            ["canonical-analysis", "tokenizing", "processing"],
            ["dictionary-lookup", "expression-lookup", "name-lookup"],
            ["study-selection", "linked-rendering"],
            ["assistance-selection", "density-planning", "adaptive-rendering"],
            ["packaging", "complete"]
        ];
        const current = groups.findIndex(group => group.includes(stage));
        document.querySelectorAll(".stage-strip span").forEach(function (element, index) {
            element.classList.toggle("is-active", index === current);
            element.classList.toggle("is-complete", current > index || stage === "complete");
        });
    }
    function updateProgress(progress) {
        if (!progress) return;
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
        const dictionaryPhase = progress.pipeline_mode === "study" ||
            (["combined", "guided"].includes(progress.pipeline_mode) && progress.combined_phase !== "furigana");
        byId("progress-remaining").textContent = dictionaryPhase ?
            formatNumber(progress.words_remaining) + " word candidates · " + formatNumber(progress.names_total - progress.names_processed) + " names left" :
            formatNumber(progress.sections_remaining) + " sections · " + formatNumber(progress.characters_remaining) + " characters left";
        byId("progress-elapsed").textContent = formatDuration(progress.elapsed_seconds);
        byId("progress-eta").textContent = progress.eta_seconds === null ? "ETA calculating…" : "ETA " + formatDuration(progress.eta_seconds);
        byId("progress-rate").textContent = formatNumber(progress.characters_per_second) + " chars/s";
        byId("progress-size").textContent = formatBytes(progress.input_bytes) + " → " + formatBytes(progress.output_bytes);
        byId("progress-status-note").textContent = progress.stage === "processing" ?
            "Adding furigana in canonical section order" : combinedPrefix + stageLabel(progress.stage);
        updateStages(progress.stage);
    }
    function showComplete() {
        byId("job-title").textContent = "Conversion complete";
        byId("job-description").textContent = "Your converted ebook is ready to download.";
        byId("header-status-text").textContent = "Ready";
        document.querySelector(".header-status .status-dot").classList.remove("status-dot--pulse");
        byId("result").hidden = false;
    }
    function showError() {
        byId("job-title").textContent = "Conversion stopped";
        byId("job-description").textContent = "No partially converted file will be offered.";
        byId("header-status-text").textContent = "Needs attention";
        document.querySelector(".header-status .status-dot").classList.remove("status-dot--pulse");
        byId("error").hidden = false;
    }
    async function poll() {
        try {
            const response = await fetch(config.statusUrl, {headers: {"Accept": "application/json"}, cache: "no-store"});
            if (!response.ok) throw new Error("status unavailable");
            const data = await response.json();
            updateProgress(data.progress);
            if (data.status === "complete") return showComplete();
            if (data.status === "error") return showError();
            window.setTimeout(poll, pollingInterval);
        } catch (error) {
            showError();
        }
    }
    window.setTimeout(poll, 250);
}());
