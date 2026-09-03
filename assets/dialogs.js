(function () {
    "use strict";

    function escapeHtml(str) {
        if (!str) return "";
        return String(str).replace(/[&<>"']/g, function (m) {
            return {
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;",
            }[m];
        });
    }

    function escapeAttr(str) {
        return escapeHtml(str);
    }

    /**
     * In-page action confirmation dialog replacing window.confirm().
     * @returns {Promise<boolean>} Resolves true if confirmed, false if cancelled.
     */
    window.showConfirmDialog = function ({
        title = "Confirm Action",
        message = "Are you sure you want to proceed?",
        confirmText = "Confirm",
        cancelText = "Cancel",
        danger = false,
    } = {}) {
        return new Promise((resolve) => {
            const dialog = document.createElement("dialog");
            dialog.className = "app-modal app-confirm-dialog";
            dialog.innerHTML = `
                <div class="confirm-dialog-content">
                    <div class="confirm-dialog-header">
                        ${danger ? '<span class="confirm-icon confirm-icon--danger" aria-hidden="true">⚠️</span>' : '<span class="confirm-icon" aria-hidden="true">❓</span>'}
                        <h3>${escapeHtml(title)}</h3>
                    </div>
                    <p class="confirm-dialog-msg">${escapeHtml(message)}</p>
                    <div class="modal-buttons">
                        <button type="button" class="secondary-button confirm-cancel-btn">${escapeHtml(cancelText)}</button>
                        <button type="button" class="${danger ? 'primary-button primary-button--danger' : 'primary-button'} confirm-ok-btn">${escapeHtml(confirmText)}</button>
                    </div>
                </div>
            `;
            document.body.appendChild(dialog);

            const cancelBtn = dialog.querySelector(".confirm-cancel-btn");
            const okBtn = dialog.querySelector(".confirm-ok-btn");

            function cleanup(result) {
                dialog.close();
                dialog.remove();
                resolve(result);
            }

            cancelBtn.addEventListener("click", () => cleanup(false));
            okBtn.addEventListener("click", () => cleanup(true));
            dialog.addEventListener("cancel", (e) => {
                e.preventDefault();
                cleanup(false);
            });

            dialog.showModal();
            (danger ? cancelBtn : okBtn).focus();
        });
    };

    /**
     * In-page prompt dialog replacing window.prompt().
     * @returns {Promise<string|null>} Resolves entered string or null if cancelled.
     */
    window.showPromptDialog = function ({
        title = "Input Required",
        message = "Please enter a value:",
        defaultValue = "",
        placeholder = "",
        confirmText = "Save",
        cancelText = "Cancel",
    } = {}) {
        return new Promise((resolve) => {
            const dialog = document.createElement("dialog");
            dialog.className = "app-modal app-confirm-dialog";
            dialog.innerHTML = `
                <form method="dialog" class="confirm-dialog-content">
                    <div class="confirm-dialog-header">
                        <span class="confirm-icon" aria-hidden="true">✏️</span>
                        <h3>${escapeHtml(title)}</h3>
                    </div>
                    <p class="confirm-dialog-msg">${escapeHtml(message)}</p>
                    <div class="field-row" style="margin: 6px 0 0 0;">
                        <input type="text" class="prompt-input" value="${escapeAttr(defaultValue)}" placeholder="${escapeAttr(placeholder)}" autocomplete="off" />
                    </div>
                    <div class="modal-buttons">
                        <button type="button" class="secondary-button prompt-cancel-btn">${escapeHtml(cancelText)}</button>
                        <button type="submit" class="primary-button prompt-ok-btn">${escapeHtml(confirmText)}</button>
                    </div>
                </form>
            `;
            document.body.appendChild(dialog);

            const input = dialog.querySelector(".prompt-input");
            const cancelBtn = dialog.querySelector(".prompt-cancel-btn");
            const form = dialog.querySelector("form");

            function cleanup(result) {
                dialog.close();
                dialog.remove();
                resolve(result);
            }

            cancelBtn.addEventListener("click", () => cleanup(null));
            form.addEventListener("submit", (e) => {
                e.preventDefault();
                cleanup(input.value);
            });
            dialog.addEventListener("cancel", (e) => {
                e.preventDefault();
                cleanup(null);
            });

            dialog.showModal();
            input.focus();
            input.select();
        });
    };

    /**
     * In-page alert dialog replacing window.alert().
     * @returns {Promise<void>} Resolves when dismissed.
     */
    window.showAlertDialog = function ({
        title = "Notice",
        message = "",
        confirmText = "OK",
        type = "info",
    } = {}) {
        return new Promise((resolve) => {
            const dialog = document.createElement("dialog");
            dialog.className = "app-modal app-confirm-dialog";
            const icon = type === "error" ? "⚠️" : (type === "success" ? "✅" : "ℹ️");
            dialog.innerHTML = `
                <div class="confirm-dialog-content">
                    <div class="confirm-dialog-header">
                        <span class="confirm-icon ${type === 'error' ? 'confirm-icon--danger' : ''}" aria-hidden="true">${icon}</span>
                        <h3>${escapeHtml(title)}</h3>
                    </div>
                    <p class="confirm-dialog-msg">${escapeHtml(message)}</p>
                    <div class="modal-buttons">
                        <button type="button" class="primary-button alert-ok-btn">${escapeHtml(confirmText)}</button>
                    </div>
                </div>
            `;
            document.body.appendChild(dialog);

            const okBtn = dialog.querySelector(".alert-ok-btn");
            function cleanup() {
                dialog.close();
                dialog.remove();
                resolve();
            }

            okBtn.addEventListener("click", cleanup);
            dialog.addEventListener("cancel", (e) => {
                e.preventDefault();
                cleanup();
            });

            dialog.showModal();
            okBtn.focus();
        });
    };
})();
