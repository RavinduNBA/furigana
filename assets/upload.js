(function () {
    "use strict";

    const OLLAMA_STATUS_ENDPOINT = "/api/ollama/status";
    const BYTES_PER_KB = 1024;
    const BYTES_PER_MB = 1048576;
    const BYTES_PER_GB = 1073741824;

    const form = document.getElementById("form");
    if (!form) return;

    const bookFile = document.getElementById("book-file");
    const fileDrop = document.getElementById("file-drop");
    const fileTitle = document.getElementById("file-title");
    const fileDetail = document.getElementById("file-detail");
    const submitButton = document.getElementById("upload");
    const knownWords = document.getElementById("known_words_list");
    const knownWordsRow = document.getElementById("known-words-row");
    const customContainer = document.getElementById("custom_word_list_container");
    const customFile = document.getElementById("custom_word_list");
    const sliderContainer = document.getElementById("custom_word_list_slider_container");
    const slider = document.getElementById("custom_word_list_limit");
    const sliderLabel = document.getElementById("custom_word_list_limit_label");
    const pipelineStudy = document.getElementById("pipeline-study");
    const pipelineCombined = document.getElementById("pipeline-combined");
    const pipelineGuided = document.getElementById("pipeline-guided");
    const furiganaOptions = document.getElementById("furigana-options");
    const studyOptions = document.getElementById("study-options");
    const layoutOptions = document.getElementById("layout-options");
    const outputFormat = document.getElementById("of");
    const experimental = document.getElementById("experimental_adaptive");
    const experimentalOptions = document.getElementById("experimental-options");
    const studyLimit = document.getElementById("per_chapter_item_limit");

    function formatBytes(bytes) {
        if (bytes < BYTES_PER_KB) return bytes + " B";
        if (bytes < BYTES_PER_MB) return (bytes / BYTES_PER_KB).toFixed(1) + " KB";
        return (bytes / BYTES_PER_MB).toFixed(1) + " MB";
    }

    function updateBookFile() {
        const file = bookFile.files && bookFile.files[0];
        submitButton.disabled = !file;
        fileDrop.classList.toggle("file-drop--selected", Boolean(file));
        if (file) {
            fileTitle.textContent = file.name;
            fileDetail.textContent = formatBytes(file.size) + " · ready to convert";
        } else {
            fileTitle.textContent = "Drop your ebook here";
            fileDetail.textContent = "or click to browse · your original file is never modified";
        }
    }

    function resetSlider() {
        slider.value = 0;
        slider.max = 0;
        sliderLabel.textContent = "No file selected";
        slider.style.setProperty("--range-progress", "0%");
    }

    function updateSliderLabel() {
        const value = Number(slider.value);
        const maximum = Number(slider.max);
        sliderLabel.textContent = maximum === 0 ? "No file selected" :
            value === maximum ? "All " + maximum.toLocaleString() + " words" :
            value === 0 ? "No exclusions" : "First " + value.toLocaleString() + " words";
        slider.style.setProperty("--range-progress", maximum ? (value / maximum * 100) + "%" : "0%");
    }

    function updateCustomVisibility() {
        const custom = knownWords.value === "__custom__";
        customContainer.hidden = !custom;
        if (!custom) {
            customFile.value = "";
            sliderContainer.hidden = true;
            resetSlider();
        }
    }

    function updateMode() {
        const remove = document.getElementById("fm_remove").checked;
        knownWords.disabled = remove;
        knownWordsRow.classList.toggle("field-row--disabled", remove);
        if (remove) {
            knownWords.value = "";
            customContainer.hidden = true;
            customFile.value = "";
            sliderContainer.hidden = true;
            resetSlider();
        } else {
            updateCustomVisibility();
        }
    }

    function updatePipeline() {
        const study = pipelineStudy && pipelineStudy.checked;
        const combined = pipelineCombined && pipelineCombined.checked;
        const guided = pipelineGuided && pipelineGuided.checked;
        const dictionary = study || combined || guided;
        const replaceMode = document.getElementById("fm_replace");
        const removeMode = document.getElementById("fm_remove");
        replaceMode.disabled = false;
        removeMode.disabled = false;
        furiganaOptions.hidden = study;
        studyOptions.hidden = !dictionary;
        layoutOptions.hidden = study;
        if (guided) studyLimit.value = "0";
        if (dictionary) outputFormat.value = "epub";
        Array.from(outputFormat.options).forEach(option => {
            option.disabled = dictionary && option.value !== "epub";
        });
        bookFile.accept = dictionary ? ".epub,application/epub+zip" : bookFile.dataset.allAccept;
        experimental.disabled = guided;
        experimentalOptions.hidden = !dictionary || !experimental.checked || guided;
        submitButton.querySelector("span").textContent = dictionary ?
            (guided ? "Build Guided Reading EPUB" :
                (combined ? "Build Combined EPUB" : "Build Study EPUB")) : "Convert ebook";
        updateMode();
    }

    function updateCustomFile() {
        const file = customFile.files && customFile.files[0];
        if (!file) {
            sliderContainer.hidden = true;
            resetSlider();
            return;
        }
        const reader = new FileReader();
        reader.onload = function (event) {
            const count = String(event.target.result).split(/\r?\n/).filter(line => line.trim()).length;
            slider.max = count;
            slider.value = count;
            sliderContainer.hidden = false;
            updateSliderLabel();
        };
        reader.readAsText(file);
    }

    ["fm_add", "fm_replace", "fm_remove"].forEach(id => document.getElementById(id).addEventListener("change", updateMode));
    ["pipeline-furigana", "pipeline-study", "pipeline-combined", "pipeline-guided"].forEach(id => {
        const element = document.getElementById(id);
        if (element) element.addEventListener("change", updatePipeline);
    });
    experimental.addEventListener("change", updatePipeline);
    bookFile.addEventListener("change", updateBookFile);
    knownWords.addEventListener("change", updateCustomVisibility);
    customFile.addEventListener("change", updateCustomFile);
    slider.addEventListener("input", updateSliderLabel);
    ["dragenter", "dragover"].forEach(type => fileDrop.addEventListener(type, function (event) {
        event.preventDefault();
        fileDrop.classList.add("file-drop--active");
    }));
    fileDrop.addEventListener("dragleave", () => fileDrop.classList.remove("file-drop--active"));
    fileDrop.addEventListener("drop", function (event) {
        event.preventDefault();
        fileDrop.classList.remove("file-drop--active");
        if (event.dataTransfer.files.length) {
            bookFile.files = event.dataTransfer.files;
            updateBookFile();
        }
    });
    const bilingualModelInput = document.getElementById("bilingual_model");
    const bilingualKeyInput = document.getElementById("bilingual_api_key");
    const bilingualUrlInput = document.getElementById("bilingual_base_url");

    function applyProviderPlaceholders(prov, modelInput, keyInput, urlInput) {
        if (!modelInput || !keyInput || !urlInput) return;
        if (prov === "hetzner") {
            modelInput.placeholder = "e.g. Qwen/Qwen3.6-35B-A3B-FP8 (default)";
            keyInput.placeholder = "Pre-configured / Custom Hetzner Token";
            urlInput.placeholder = "inference.hetzner.com/api/v1 (default)";
        } else if (prov === "google") {
            modelInput.placeholder = "e.g. gemini-flash-latest (default), gemini-pro-latest";
            keyInput.placeholder = "Pre-configured / Google AI Studio Key";
            urlInput.placeholder = "generativelanguage.googleapis.com/v1beta/openai (default)";
        } else if (prov === "openrouter") {
            modelInput.placeholder = "e.g. nvidia/nemotron-3.5-lightning:free (default), deepseek/deepseek-chat";
            keyInput.placeholder = "Pre-configured / OpenRouter Key (sk-or-v1-...)";
            urlInput.placeholder = "openrouter.ai/api/v1 (default)";
        } else if (prov === "deepseek") {
            modelInput.placeholder = "e.g. deepseek-chat (default), deepseek-reasoner";
            keyInput.placeholder = "sk-...";
            urlInput.placeholder = "api.deepseek.com/v1 (default)";
        } else if (prov === "openai") {
            modelInput.placeholder = "e.g. gpt-4o-mini (default), gpt-4o";
            keyInput.placeholder = "sk-...";
            urlInput.placeholder = "api.openai.com/v1 (default)";
        } else if (prov === "ollama") {
            modelInput.placeholder = "e.g. qwen2.5:3b, qwen2.5:7b";
            keyInput.placeholder = "Not required for local Ollama";
            urlInput.placeholder = "localhost:11434/v1 (default)";
        }
    }

    function updateBilingual() {
        if (!bilingualSettings) return;
        if (bilingualProvider) {
            const prov = bilingualProvider.value;
            if (bilingualKeyRow) bilingualKeyRow.hidden = (prov === "none" || prov === "ollama");
            if (bilingualUrlRow) bilingualUrlRow.hidden = (prov === "none");
            applyProviderPlaceholders(prov, bilingualModelInput, bilingualKeyInput, bilingualUrlInput);
        }
    }

    if (bilingualCompanion) bilingualCompanion.addEventListener("change", updateBilingual);
    if (bilingualProvider) bilingualProvider.addEventListener("change", updateBilingual);

    // LLM enrichment panel toggle
    const llmEnrichNouns = document.getElementById("llm_enrich_nouns");
    const llmEnrichGlosses = document.getElementById("llm_enrich_glosses");
    const llmEnrichSettings = document.getElementById("llm-enrich-settings");
    const llmProvider = document.getElementById("llm_provider");
    const llmEnrichKeyRow = document.getElementById("llm-enrich-key-row");
    const llmEnrichUrlRow = document.getElementById("llm-enrich-url-row");
    const llmModelInput = document.getElementById("llm_model");
    const llmKeyInput = document.getElementById("llm_api_key");
    const llmUrlInput = document.getElementById("llm_base_url");

    function updateLLMEnrich() {
        if (!llmEnrichSettings) return;
        if (llmProvider) {
            const prov = llmProvider.value;
            if (llmEnrichKeyRow) llmEnrichKeyRow.hidden = (prov === "none" || prov === "ollama");
            if (llmEnrichUrlRow) llmEnrichUrlRow.hidden = (prov === "none");
            applyProviderPlaceholders(prov, llmModelInput, llmKeyInput, llmUrlInput);
        }
    }

    if (llmEnrichNouns) llmEnrichNouns.addEventListener("change", updateLLMEnrich);
    if (llmEnrichGlosses) llmEnrichGlosses.addEventListener("change", updateLLMEnrich);
    if (llmProvider) llmProvider.addEventListener("change", updateLLMEnrich);

    form.addEventListener("submit", function () {
        submitButton.disabled = true;
        submitButton.querySelector("span").textContent = "Uploading…";
    });

    async function loadInstalledOllamaModels() {
        const modelInput = document.getElementById("bilingual_model");
        const llmModelInput = document.getElementById("llm_model");
        const modelInputs = [modelInput, llmModelInput].filter(Boolean);
        if (!modelInputs.length) return;

        try {
            const resp = await fetch(OLLAMA_STATUS_ENDPOINT);
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.installed_models && data.installed_models.length > 0) {
                let datalist = document.getElementById("ollama-models-list");
                if (!datalist) {
                    datalist = document.createElement("datalist");
                    datalist.id = "ollama-models-list";
                    document.body.appendChild(datalist);
                }
                datalist.innerHTML = data.installed_models.map(m => {
                    const sz = m.size ? ` (${(m.size / BYTES_PER_GB).toFixed(1)} GB)` : "";
                    return `<option value="${m.name}">${m.name}${sz}</option>`;
                }).join("");
                modelInputs.forEach(input => {
                    input.setAttribute("list", "ollama-models-list");
                    if (!input.value && data.installed_models[0]) {
                        input.placeholder = "e.g. " + data.installed_models[0].name;
                    }
                });
            }
        } catch (e) {}
    }

    async function loadSeriesProfiles() {
        const seriesSelect = document.getElementById("series_profile_id");
        if (!seriesSelect) return;
        try {
            const resp = await fetch("/api/series");
            if (!resp.ok) return;
            const profiles = await resp.json();
            if (profiles && profiles.length > 0) {
                seriesSelect.innerHTML = '<option value="">No series profile (standalone book)</option>' +
                    profiles.map(p => {
                        const stats = `${p.character_count} chars, ${p.glossary_count} terms`;
                        return `<option value="${p.series_id}">${p.title} (${stats})</option>`;
                    }).join("");
            }
        } catch (e) {}
    }

    function initRecentConversionsControls() {
        const clearBtn = document.getElementById("clear-recent-btn");
        if (clearBtn) {
            clearBtn.addEventListener("click", async function () {
                if (!confirm("Are you sure you want to clear all recent conversions?")) return;
                try {
                    clearBtn.disabled = true;
                    clearBtn.textContent = "Clearing…";
                    const resp = await fetch("/api/recent_conversions", { method: "DELETE" });
                    if (resp.ok) {
                        const list = document.querySelector(".recent-list");
                        if (list) {
                            list.innerHTML = '<p class="recent-empty-note">Your last 10 conversions will appear here for fast re-downloading.</p>';
                        }
                        const badge = document.getElementById("recent-count-badge");
                        if (badge) badge.textContent = "0 saved";
                        clearBtn.remove();
                    } else {
                        alert("Failed to clear recent conversions.");
                        clearBtn.disabled = false;
                        clearBtn.textContent = "Clear all";
                    }
                } catch (e) {
                    alert("Error: " + e.message);
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
                if (!confirm("Remove this conversion from history?")) return;
                try {
                    const resp = await fetch("/api/recent_conversions/" + uid, { method: "DELETE" });
                    if (resp.ok) {
                        const itemEl = this.closest(".recent-item");
                        if (itemEl) itemEl.remove();
                        const remaining = document.querySelectorAll(".recent-item").length;
                        const badge = document.getElementById("recent-count-badge");
                        if (badge) badge.textContent = remaining + " saved";
                        if (remaining === 0) {
                            const list = document.querySelector(".recent-list");
                            if (list) {
                                list.innerHTML = '<p class="recent-empty-note">Your last 10 conversions will appear here for fast re-downloading.</p>';
                            }
                            const clearBtnEl = document.getElementById("clear-recent-btn");
                            if (clearBtnEl) clearBtnEl.remove();
                        }
                    }
                } catch (e) {}
            });
        });
    }

    bookFile.dataset.allAccept = bookFile.accept;
    updateMode();
    updatePipeline();
    updateBilingual();
    updateLLMEnrich();
    loadInstalledOllamaModels();
    loadSeriesProfiles();
    initRecentConversionsControls();
    updateBookFile();
}());
