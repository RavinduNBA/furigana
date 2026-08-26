(function () {
    "use strict";

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
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / 1048576).toFixed(1) + " MB";
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
        const assistedFurigana = combined || guided;
        const addMode = document.getElementById("fm_add");
        const replaceMode = document.getElementById("fm_replace");
        const removeMode = document.getElementById("fm_remove");
        if (assistedFurigana) addMode.checked = true;
        replaceMode.disabled = assistedFurigana;
        removeMode.disabled = assistedFurigana;
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
    form.addEventListener("submit", function () {
        submitButton.disabled = true;
        submitButton.querySelector("span").textContent = "Uploading…";
    });
    bookFile.dataset.allAccept = bookFile.accept;
    updateMode();
    updatePipeline();
    updateBookFile();
}());
