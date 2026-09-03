(function () {
    let currentSeriesId = "";
    let currentProfile = null;

    function byId(id) {
        return document.getElementById(id);
    }

    // Initialize
    document.addEventListener("DOMContentLoaded", () => {
        initSidebarClickHandlers();
        initTabs();
        initModals();
        initSearchFilters();

        const firstItem = document.querySelector(".series-list-item");
        if (firstItem) {
            const id = firstItem.getAttribute("data-id");
            loadSeriesProfile(id);
        }
    });

    function initSidebarClickHandlers() {
        const list = byId("series-list");
        if (!list) return;

        list.addEventListener("click", (e) => {
            const item = e.target.closest(".series-list-item");
            if (!item) return;

            document.querySelectorAll(".series-list-item").forEach(el => el.classList.remove("active"));
            item.classList.add("active");

            const id = item.getAttribute("data-id");
            loadSeriesProfile(id);
        });

        const createBtn = byId("btn-create-series");
        if (createBtn) {
            createBtn.addEventListener("click", () => {
                byId("create-title").value = "";
                byId("create-id").value = "";
                byId("modal-create").showModal();
            });
        }

        const emptyCreateBtn = byId("btn-create-series-empty");
        if (emptyCreateBtn) {
            emptyCreateBtn.addEventListener("click", () => {
                byId("create-title").value = "";
                byId("create-id").value = "";
                byId("modal-create").showModal();
            });
        }
    }

    function initTabs() {
        const strip = byId("series-tab-strip");
        if (!strip) return;

        strip.addEventListener("click", (e) => {
            const btn = e.target.closest(".tab-btn");
            if (!btn) return;

            strip.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            const targetTab = btn.getAttribute("data-tab");
            document.querySelectorAll(".tab-pane").forEach(pane => {
                if (pane.id === `pane-${targetTab}`) {
                    pane.classList.add("active");
                    pane.hidden = false;
                } else {
                    pane.classList.remove("active");
                    pane.hidden = true;
                }
            });
        });
    }

    async function loadSeriesProfile(seriesId) {
        if (!seriesId) return;
        currentSeriesId = seriesId;

        const spinner = byId("series-loading-spinner");
        const content = byId("series-content-area");
        const emptyWorkspace = byId("series-empty-workspace");
        if (emptyWorkspace) emptyWorkspace.hidden = true;
        if (spinner) spinner.hidden = false;
        if (content) content.hidden = true;

        try {
            const resp = await fetch(`/api/series/${encodeURIComponent(seriesId)}`);
            if (!resp.ok) throw new Error("Failed to load profile");
            currentProfile = await resp.json();
            renderCurrentProfile();
        } catch (e) {
            console.error("Error loading series profile:", e);
            await window.showAlertDialog({
                title: "Series Profile Error",
                message: "Could not load series profile: " + e.message,
                type: "error",
            });
        } finally {
            if (spinner) spinner.hidden = true;
            if (content) content.hidden = false;
        }
    }

    function renderCurrentProfile() {
        if (!currentProfile) return;

        // Header info
        byId("series-slug-kicker").textContent = `Series ID: ${currentProfile.series_id}`;
        byId("series-title-display").textContent = currentProfile.title || currentProfile.series_id;

        // Counters
        const chars = currentProfile.characters || {};
        const gloss = currentProfile.glossary || {};
        const ruby = currentProfile.ruby_overrides || {};

        byId("tab-char-count").textContent = Object.keys(chars).length;
        byId("tab-gloss-count").textContent = Object.keys(gloss).length;
        byId("tab-ruby-count").textContent = Object.keys(ruby).length;

        renderCharactersTable(chars);
        renderGlossaryTable(gloss);
        renderRubyTable(ruby);
        renderLoreForm();
    }

    function renderCharactersTable(chars) {
        const tbody = byId("tbody-characters");
        if (!tbody) return;

        const keys = Object.keys(chars);
        if (keys.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No characters saved in this profile yet. Click "+ Add Character" to create one.</td></tr>`;
            return;
        }

        tbody.innerHTML = keys.map(k => {
            const c = chars[k] || {};
            const reading = typeof c === "object" ? (c.reading || c.hiragana || "") : "";
            const romanized = typeof c === "object" ? (c.romanized || "") : "";
            const role = typeof c === "object" ? (c.role || "") : "";
            const gender = typeof c === "object" ? (c.gender || "") : "";
            const tone = typeof c === "object" ? (c.speaking_tone || "") : "";
            const rel = typeof c === "object" ? (
                typeof c.relationships === "object" && c.relationships !== null ?
                    Object.entries(c.relationships).map(([target, desc]) => desc ? `${target} (${desc})` : target).join(", ") :
                    (c.relationships || "")
            ) : "";
            const aliases = typeof c === "object" ? (
                Array.isArray(c.aliases) ? c.aliases.join(", ") : (c.aliases || "")
            ) : "";

            const genderBadge = gender === "male" ? '<span class="gender-tag gender-tag--male">♂ Male</span>' :
                (gender === "female" ? '<span class="gender-tag gender-tag--female">♀ Female</span>' :
                (gender && gender !== "unknown" ? `<span class="gender-tag">${escapeHtml(gender)}</span>` : '<span class="text-muted">—</span>'));

            return `
                <tr data-kanji="${escapeHtml(k)}">
                    <td><strong>${escapeHtml(k)}</strong></td>
                    <td>${escapeHtml(reading || "—")}</td>
                    <td>${escapeHtml(romanized || "—")}</td>
                    <td><span class="badge-role">${escapeHtml(role || "Character")}</span></td>
                    <td>${genderBadge}</td>
                    <td>${rel ? `<small class="relation-text">🔗 ${escapeHtml(rel)}</small>` : '<span class="text-muted">—</span>'}</td>
                    <td>${aliases ? `<small class="alias-text">🏷️ ${escapeHtml(aliases)}</small>` : '<span class="text-muted">—</span>'}</td>
                    <td><small class="text-muted">${escapeHtml(tone || "—")}</small></td>
                    <td>
                        <div class="row-actions">
                            <button type="button" class="btn-icon edit-char-btn" title="Edit character">✏️</button>
                            <button type="button" class="btn-icon del-char-btn" title="Delete character">🗑️</button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
    }

    function renderGlossaryTable(gloss) {
        const tbody = byId("tbody-glossary");
        if (!tbody) return;

        const keys = Object.keys(gloss);
        if (keys.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">No glossary items saved in this profile yet. Click "+ Add Term" to create one.</td></tr>`;
            return;
        }

        tbody.innerHTML = keys.map(k => {
            const g = gloss[k] || {};
            const reading = typeof g === "object" ? (g.reading || "") : "";
            const ruby = typeof g === "object" ? (g.author_ruby_override || "") : "";
            const trans = typeof g === "object" ? (g.preferred_translation || g.translation || "") : (typeof g === "string" ? g : "");
            const defn = typeof g === "object" ? (g.definition || "") : "";
            const cat = typeof g === "object" ? (g.category || "general") : "general";

            return `
                <tr data-term="${escapeHtml(k)}">
                    <td><strong>${escapeHtml(k)}</strong></td>
                    <td>${escapeHtml(reading)}</td>
                    <td><span class="badge-ruby">${escapeHtml(ruby || "—")}</span></td>
                    <td>${escapeHtml(trans)}</td>
                    <td><small class="lore-text">${escapeHtml(defn || "—")}</small></td>
                    <td><span class="badge-cat">${escapeHtml(cat)}</span></td>
                    <td>
                        <div class="row-actions">
                            <button type="button" class="btn-icon edit-gloss-btn" title="Edit term">✏️</button>
                            <button type="button" class="btn-icon del-gloss-btn" title="Delete term">🗑️</button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
    }

    function renderRubyTable(ruby) {
        const tbody = byId("tbody-ruby");
        if (!tbody) return;

        const keys = Object.keys(ruby);
        if (keys.length === 0) {
            tbody.innerHTML = `<tr><td colspan="3" class="text-center text-muted">No author ruby overrides saved. Click "+ Add Ruby Override" to force a custom reading for kanji.</td></tr>`;
            return;
        }

        tbody.innerHTML = keys.map(k => {
            const val = ruby[k] || "";
            return `
                <tr data-kanji="${escapeHtml(k)}">
                    <td><strong>${escapeHtml(k)}</strong></td>
                    <td><span class="badge-ruby-highlight">${escapeHtml(val)}</span></td>
                    <td>
                        <div class="row-actions">
                            <button type="button" class="btn-icon edit-ruby-btn" title="Edit ruby override">✏️</button>
                            <button type="button" class="btn-icon del-ruby-btn" title="Delete ruby override">🗑️</button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
    }

    function renderLoreForm() {
        if (!currentProfile) return;
        byId("lore-title").value = currentProfile.title || "";
        byId("lore-synopsis").value = currentProfile.synopsis || "";
        byId("lore-world").value = currentProfile.world_setting || "";

        const volChips = byId("lore-volumes-chips");
        if (volChips) {
            const vols = currentProfile.volumes_processed || [];
            if (vols.length > 0) {
                volChips.innerHTML = vols.map(v => `<span class="context-chip">📚 ${escapeHtml(v)}</span>`).join("");
            } else {
                volChips.innerHTML = `<span class="text-muted">No specific volumes tagged yet.</span>`;
            }
        }
    }

    function initSearchFilters() {
        const charInput = byId("filter-chars");
        if (charInput) {
            charInput.addEventListener("input", (e) => {
                const q = e.target.value.toLowerCase();
                document.querySelectorAll("#tbody-characters tr").forEach(tr => {
                    tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
                });
            });
        }

        const glossInput = byId("filter-glossary");
        if (glossInput) {
            glossInput.addEventListener("input", (e) => {
                const q = e.target.value.toLowerCase();
                document.querySelectorAll("#tbody-glossary tr").forEach(tr => {
                    tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
                });
            });
        }

        const rubyInput = byId("filter-ruby");
        if (rubyInput) {
            rubyInput.addEventListener("input", (e) => {
                const q = e.target.value.toLowerCase();
                document.querySelectorAll("#tbody-ruby tr").forEach(tr => {
                    tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
                });
            });
        }
    }

    function initModals() {
        // Create Profile Modal
        const createModal = byId("modal-create");
        const createForm = byId("form-modal-create");
        const autoSuggestBtn = byId("btn-auto-suggest-series");
        const rawSampleInput = byId("create-raw-sample");
        const createTitleInput = byId("create-title");
        const createIdInput = byId("create-id");

        async function triggerAutoSuggest(rawText) {
            if (!rawText) return;
            try {
                const resp = await fetch("/api/series/suggest?query=" + encodeURIComponent(rawText));
                if (resp.ok) {
                    const data = await resp.json();
                    if (data.title) createTitleInput.value = data.title;
                    if (data.series_id) createIdInput.value = data.series_id;
                }
            } catch (err) {
                console.warn("Auto suggest error:", err);
            }
        }

        autoSuggestBtn?.addEventListener("click", () => {
            triggerAutoSuggest(rawSampleInput?.value.trim());
        });

        rawSampleInput?.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                triggerAutoSuggest(rawSampleInput.value.trim());
            }
        });

        createTitleInput?.addEventListener("input", (e) => {
            const val = e.target.value.trim();
            if (val && (!createIdInput.value || !createIdInput.dataset.manualEdited)) {
                createIdInput.value = val
                    .toLowerCase()
                    .replace(/[^\w\s\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF-]/g, "")
                    .replace(/[\s_-]+/g, "-")
                    .replace(/^-+|-+$/g, "");
            }
        });

        createIdInput?.addEventListener("input", () => {
            createIdInput.dataset.manualEdited = "true";
        });

        byId("btn-cancel-create")?.addEventListener("click", () => createModal.close());
        createForm?.addEventListener("submit", async (e) => {
            e.preventDefault();
            const title = createTitleInput.value.trim();
            const seriesId = createIdInput.value.trim();
            if (!title) return;

            try {
                const resp = await fetch("/api/series", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({title, series_id: seriesId}),
                });
                if (!resp.ok) throw new Error("Failed to create series profile");
                createModal.close();
                window.location.reload();
            } catch (err) {
                await window.showAlertDialog({
                    title: "Creation Failed",
                    message: "Error creating profile: " + err.message,
                    type: "error",
                });
            }
        });

        // Add / Edit Character Modal
        const charModal = byId("modal-char");
        const charForm = byId("form-modal-char");
        byId("btn-cancel-char")?.addEventListener("click", () => charModal.close());
        byId("btn-add-character")?.addEventListener("click", () => {
            byId("modal-char-title").textContent = "Add New Character";
            byId("char-kanji").value = "";
            byId("char-kanji").readOnly = false;
            byId("char-reading").value = "";
            byId("char-romanized").value = "";
            byId("char-role").value = "";
            if (byId("char-gender")) byId("char-gender").value = "unknown";
            if (byId("char-relations")) byId("char-relations").value = "";
            if (byId("char-aliases")) byId("char-aliases").value = "";
            byId("char-tone").value = "";
            charModal.showModal();
        });

        byId("tbody-characters")?.addEventListener("click", async (e) => {
            const editBtn = e.target.closest(".edit-char-btn");
            const delBtn = e.target.closest(".del-char-btn");
            const tr = e.target.closest("tr");
            if (!tr) return;
            const kanji = tr.getAttribute("data-kanji");
            if (!kanji || !currentProfile) return;

            if (editBtn) {
                const c = currentProfile.characters[kanji] || {};
                byId("modal-char-title").textContent = `Edit Character: ${kanji}`;
                byId("char-kanji").value = kanji;
                byId("char-kanji").readOnly = true;
                byId("char-reading").value = c.reading || c.hiragana || "";
                byId("char-romanized").value = c.romanized || "";
                byId("char-role").value = c.role || "";
                if (byId("char-gender")) byId("char-gender").value = c.gender || "unknown";
                byId("char-tone").value = c.speaking_tone || "";
                const relVal = typeof c.relationships === "object" && c.relationships !== null ?
                    Object.entries(c.relationships).map(([target, desc]) => desc ? `${target}: ${desc}` : target).join(", ") :
                    (c.relationships || "");
                if (byId("char-relations")) byId("char-relations").value = relVal;
                if (byId("char-aliases")) {
                    byId("char-aliases").value = Array.isArray(c.aliases) ? c.aliases.join(", ") : (c.aliases || "");
                }
                charModal.showModal();
            } else if (delBtn) {
                const confirmed = await window.showConfirmDialog({
                    title: "Remove Character",
                    message: `Remove character "${kanji}" from series memory?`,
                    confirmText: "Remove",
                    cancelText: "Keep",
                    danger: true,
                });
                if (confirmed) {
                    delete currentProfile.characters[kanji];
                    saveCurrentProfile();
                }
            }
        });

        charForm?.addEventListener("submit", (e) => {
            e.preventDefault();
            if (!currentProfile) return;
            const kanji = byId("char-kanji").value.trim();
            if (!kanji) return;

            if (!currentProfile.characters) currentProfile.characters = {};
            const relVal = byId("char-relations") ? byId("char-relations").value.trim() : "";
            const aliasesStr = byId("char-aliases") ? byId("char-aliases").value.trim() : "";
            const aliasesList = aliasesStr ? aliasesStr.split(",").map(a => a.trim()).filter(Boolean) : [];

            currentProfile.characters[kanji] = {
                kanji,
                reading: byId("char-reading").value.trim(),
                romanized: byId("char-romanized").value.trim(),
                role: byId("char-role").value.trim() || "Character",
                gender: byId("char-gender") ? byId("char-gender").value : "unknown",
                relationships: relVal,
                aliases: aliasesList,
                speaking_tone: byId("char-tone").value.trim(),
            };

            charModal.close();
            saveCurrentProfile();
        });

        // Add / Edit Glossary Modal
        const glossModal = byId("modal-glossary");
        const glossForm = byId("form-modal-glossary");
        byId("btn-cancel-glossary")?.addEventListener("click", () => glossModal.close());
        byId("btn-add-glossary")?.addEventListener("click", () => {
            byId("modal-glossary-title").textContent = "Add Glossary Term";
            byId("gloss-term").value = "";
            byId("gloss-term").readOnly = false;
            byId("gloss-reading").value = "";
            byId("gloss-ruby").value = "";
            byId("gloss-trans").value = "";
            byId("gloss-defn").value = "";
            byId("gloss-cat").value = "general";
            glossModal.showModal();
        });

        byId("tbody-glossary")?.addEventListener("click", async (e) => {
            const editBtn = e.target.closest(".edit-gloss-btn");
            const delBtn = e.target.closest(".del-gloss-btn");
            const tr = e.target.closest("tr");
            if (!tr) return;
            const term = tr.getAttribute("data-term");
            if (!term || !currentProfile) return;

            if (editBtn) {
                const g = currentProfile.glossary[term] || {};
                byId("modal-glossary-title").textContent = `Edit Term: ${term}`;
                byId("gloss-term").value = term;
                byId("gloss-term").readOnly = true;
                byId("gloss-reading").value = g.reading || "";
                byId("gloss-ruby").value = g.author_ruby_override || "";
                byId("gloss-trans").value = g.preferred_translation || g.translation || "";
                byId("gloss-defn").value = g.definition || "";
                byId("gloss-cat").value = g.category || "general";
                glossModal.showModal();
            } else if (delBtn) {
                const confirmed = await window.showConfirmDialog({
                    title: "Remove Glossary Term",
                    message: `Remove term "${term}" from series glossary?`,
                    confirmText: "Remove",
                    cancelText: "Keep",
                    danger: true,
                });
                if (confirmed) {
                    delete currentProfile.glossary[term];
                    saveCurrentProfile();
                }
            }
        });

        glossForm?.addEventListener("submit", (e) => {
            e.preventDefault();
            if (!currentProfile) return;
            const term = byId("gloss-term").value.trim();
            if (!term) return;

            if (!currentProfile.glossary) currentProfile.glossary = {};
            currentProfile.glossary[term] = {
                japanese: term,
                reading: byId("gloss-reading").value.trim(),
                author_ruby_override: byId("gloss-ruby").value.trim(),
                preferred_translation: byId("gloss-trans").value.trim(),
                definition: byId("gloss-defn").value.trim(),
                category: byId("gloss-cat").value,
            };

            glossModal.close();
            saveCurrentProfile();
        });

        // Add / Edit Ruby Modal
        const rubyModal = byId("modal-ruby");
        const rubyForm = byId("form-modal-ruby");
        byId("btn-cancel-ruby")?.addEventListener("click", () => rubyModal.close());
        byId("btn-add-ruby")?.addEventListener("click", () => {
            byId("modal-ruby-title").textContent = "Add Ruby Override";
            byId("ruby-kanji").value = "";
            byId("ruby-kanji").readOnly = false;
            byId("ruby-reading").value = "";
            rubyModal.showModal();
        });

        byId("tbody-ruby")?.addEventListener("click", async (e) => {
            const editBtn = e.target.closest(".edit-ruby-btn");
            const delBtn = e.target.closest(".del-ruby-btn");
            const tr = e.target.closest("tr");
            if (!tr) return;
            const kanji = tr.getAttribute("data-kanji");
            if (!kanji || !currentProfile) return;

            if (editBtn) {
                const val = currentProfile.ruby_overrides[kanji] || "";
                byId("modal-ruby-title").textContent = `Edit Ruby Override: ${kanji}`;
                byId("ruby-kanji").value = kanji;
                byId("ruby-kanji").readOnly = true;
                byId("ruby-reading").value = val;
                rubyModal.showModal();
            } else if (delBtn) {
                const confirmed = await window.showConfirmDialog({
                    title: "Remove Ruby Override",
                    message: `Remove ruby override for "${kanji}"?`,
                    confirmText: "Remove",
                    cancelText: "Keep",
                    danger: true,
                });
                if (confirmed) {
                    delete currentProfile.ruby_overrides[kanji];
                    saveCurrentProfile();
                }
            }
        });

        rubyForm?.addEventListener("submit", (e) => {
            e.preventDefault();
            if (!currentProfile) return;
            const kanji = byId("ruby-kanji").value.trim();
            const reading = byId("ruby-reading").value.trim();
            if (!kanji || !reading) return;

            if (!currentProfile.ruby_overrides) currentProfile.ruby_overrides = {};
            currentProfile.ruby_overrides[kanji] = reading;

            rubyModal.close();
            saveCurrentProfile();
        });

        // Save Lore Form
        byId("form-lore")?.addEventListener("submit", (e) => {
            e.preventDefault();
            if (!currentProfile) return;
            currentProfile.title = byId("lore-title").value.trim();
            currentProfile.synopsis = byId("lore-synopsis").value.trim();
            currentProfile.world_setting = byId("lore-world").value.trim();
            saveCurrentProfile();
        });

        // Export JSON
        byId("btn-export-json")?.addEventListener("click", () => {
            if (!currentProfile) return;
            const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(currentProfile, null, 2));
            const downloadAnchor = document.createElement("a");
            downloadAnchor.setAttribute("href", dataStr);
            downloadAnchor.setAttribute("download", `${currentProfile.series_id || "series"}_profile.json`);
            document.body.appendChild(downloadAnchor);
            downloadAnchor.click();
            downloadAnchor.remove();
        });

        // Delete Series
        byId("btn-delete-series")?.addEventListener("click", async () => {
            if (!currentProfile) return;
            const confirmed = await window.showConfirmDialog({
                title: "Delete Series Profile",
                message: `Are you sure you want to permanently delete series profile "${currentProfile.title}" (${currentProfile.series_id})? All saved character readings and glossaries for this series will be lost.`,
                confirmText: "Delete Profile",
                cancelText: "Cancel",
                danger: true,
            });
            if (confirmed) {
                try {
                    const resp = await fetch(`/api/series/${encodeURIComponent(currentProfile.series_id)}`, {method: "DELETE"});
                    if (!resp.ok) throw new Error("Failed to delete");
                    window.location.reload();
                } catch (err) {
                    await window.showAlertDialog({
                        title: "Delete Failed",
                        message: "Error deleting series: " + err.message,
                        type: "error",
                    });
                }
            }
        });
    }

    async function saveCurrentProfile() {
        if (!currentProfile) return;
        try {
            const resp = await fetch("/api/series", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(currentProfile),
            });
            if (!resp.ok) throw new Error("Failed to save changes");
            currentProfile = await resp.json();
            renderCurrentProfile();
        } catch (err) {
            console.error("Save error:", err);
            await window.showAlertDialog({
                title: "Save Failed",
                message: "Error saving profile: " + err.message,
                type: "error",
            });
        }
    }

    function escapeHtml(str) {
        return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }
})();
