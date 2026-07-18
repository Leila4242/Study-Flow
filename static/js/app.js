/* ==========================================================================
   Study Planner - app.js
   Step 1 scope: responsive sidebar toggle + dark mode toggle.
   More JS features (search, filters, countdowns, etc.) are added
   alongside the pages that need them in later steps.
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    initSidebarToggle();
    initDarkMode();
    initFlashMessages();
    initPasswordToggles();
    initColorSwatchPicker();
    initDeleteConfirmations();
    initInstantSearch();
    initExamCountdowns();
    initFormValidation();
});

function initSidebarToggle() {
    const topbarNav = document.getElementById("topbarNav");
    const overlay = document.getElementById("sidebarOverlay");
    const menuToggle = document.getElementById("menuToggle");

    if (!topbarNav || !menuToggle) return;

    const openNav = () => {
        topbarNav.classList.add("open");
        if (overlay) overlay.classList.add("open");
    };

    const closeNav = () => {
        topbarNav.classList.remove("open");
        if (overlay) overlay.classList.remove("open");
    };

    menuToggle.addEventListener("click", () => {
        topbarNav.classList.contains("open") ? closeNav() : openNav();
    });

    if (overlay) {
        overlay.addEventListener("click", closeNav);
    }
}

function initDarkMode() {
    const toggleBtn = document.getElementById("darkModeToggle");
    if (!toggleBtn) return;

    const icon = toggleBtn.querySelector("i");
    const html = document.documentElement;

    const applyMode = (isDark) => {
        html.setAttribute("data-theme", isDark ? "dark" : "light");
        if (icon) {
            icon.classList.toggle("fa-moon", !isDark);
            icon.classList.toggle("fa-sun", isDark);
        }
        // Keep legacy body class for auth.css compatibility
        document.body.classList.toggle("dark-mode", isDark);
    };

    const savedMode = localStorage.getItem("studyPlannerDarkMode") === "true";
    applyMode(savedMode);

    toggleBtn.addEventListener("click", () => {
        const isDark = html.getAttribute("data-theme") !== "dark";
        applyMode(isDark);
        localStorage.setItem("studyPlannerDarkMode", isDark);
    });
}

/**
 * Flash messages: dismiss on click, and auto-close after a few seconds.
 */
function initFlashMessages() {
    const messages = document.querySelectorAll(".flash-message");

    messages.forEach((msg) => {
        const closeMsg = () => {
            msg.style.opacity = "0";
            msg.style.transform = "translateY(-8px)";
            setTimeout(() => msg.remove(), 200);
        };

        const closeBtn = msg.querySelector(".flash-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", closeMsg);
        }

        // Auto-close after 4.5s
        setTimeout(closeMsg, 4500);
    });
}

/**
 * Login/Register password visibility toggles.
 */
function initPasswordToggles() {
    const toggles = document.querySelectorAll(".toggle-password");

    toggles.forEach((toggle) => {
        toggle.addEventListener("click", () => {
            const input = toggle.parentElement.querySelector("input");
            const icon = toggle.querySelector("i");
            if (!input) return;

            const isPassword = input.type === "password";
            input.type = isPassword ? "text" : "password";

            if (icon) {
                icon.classList.toggle("fa-eye", !isPassword);
                icon.classList.toggle("fa-eye-slash", isPassword);
            }
        });
    });
}

/**
 * Add/Edit Subject color swatch picker.
 * Clicking a swatch marks it selected and updates the hidden #color input.
 */
function initColorSwatchPicker() {
    const picker = document.getElementById("colorPicker");
    const hiddenInput = document.getElementById("color");
    if (!picker || !hiddenInput) return;

    picker.querySelectorAll(".color-swatch").forEach((swatch) => {
        swatch.addEventListener("click", () => {
            picker.querySelectorAll(".color-swatch").forEach((s) => s.classList.remove("selected"));
            swatch.classList.add("selected");
            hiddenInput.value = swatch.dataset.color;
        });
    });
}

/**
 * Any form/button with a data-confirm attribute asks for confirmation
 * before submitting. Used for subject/task/exam delete actions.
 */
function initDeleteConfirmations() {
    document.querySelectorAll("[data-confirm]").forEach((trigger) => {
        trigger.addEventListener("click", (event) => {
            const message = trigger.getAttribute("data-confirm");
            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });
}

/**
 * Instant search: auto-submits the search form ~400ms after the user
 * stops typing, so results update without needing to press Enter.
 */
function initInstantSearch() {
    const form = document.getElementById("taskSearchForm");
    const input = document.getElementById("taskSearchInput");
    if (!form || !input) return;

    let debounceTimer;
    input.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => form.submit(), 400);
    });
}

/**
 * Live countdown for upcoming exams. Targets midnight (local time) of
 * the exam date and ticks down every second as "Xd Xh Xm Xs". Falls
 * back gracefully - the server already rendered a static label
 * (countdown_display) that this simply takes over once JS runs.
 */
function initExamCountdowns() {
    const elements = document.querySelectorAll(".countdown-live");
    if (!elements.length) return;

    const update = () => {
        const now = new Date();

        elements.forEach((el) => {
            const target = new Date(`${el.dataset.examDate}T00:00:00`);
            const diff = target - now;

            el.classList.remove("countdown-badge-today", "countdown-badge-soon", "countdown-badge-upcoming");

            if (diff <= 0) {
                el.textContent = "Today";
                el.classList.add("countdown-badge-today");
                return;
            }

            const days = Math.floor(diff / 86400000);
            const hours = Math.floor((diff / 3600000) % 24);
            const minutes = Math.floor((diff / 60000) % 60);
            const seconds = Math.floor((diff / 1000) % 60);

            el.textContent = `${days}d ${hours}h ${minutes}m ${seconds}s`;
            el.classList.add(days === 0 ? "countdown-badge-today" : (days <= 7 ? "countdown-badge-soon" : "countdown-badge-upcoming"));
        });
    };

    update();
    setInterval(update, 1000);
}

/**
 * Client-side form validation. Every form rendered with the `novalidate`
 * attribute opts in to this (novalidate just silences the browser's
 * native bubble tooltips - the constraint-validation API underneath
 * still works, so we use it to show inline messages instead).
 * Handles required fields, email format, minlength, and - when both
 * fields are present - password/confirm-password matching.
 */
function initFormValidation() {
    const forms = document.querySelectorAll("form[novalidate]");
    if (!forms.length) return;

    forms.forEach((form) => {
        const fields = form.querySelectorAll(
            "input[required], select[required], textarea[required], input[minlength]"
        );
        if (!fields.length) return;

        const fieldWrap = (field) => field.closest(".input-wrap") || field;

        const showError = (field, message) => {
            const wrap = fieldWrap(field);
            wrap.classList.add("is-invalid");
            let error = wrap.parentElement.querySelector(".field-error");
            if (!error) {
                error = document.createElement("span");
                error.className = "field-error";
                wrap.insertAdjacentElement("afterend", error);
            }
            error.textContent = message;
        };

        const clearError = (field) => {
            const wrap = fieldWrap(field);
            wrap.classList.remove("is-invalid");
            const error = wrap.parentElement.querySelector(".field-error");
            if (error) error.remove();
        };

        const validateField = (field) => {
            if (field.validity.valueMissing) {
                showError(field, "This field is required.");
                return false;
            }
            if (field.type === "email" && field.validity.typeMismatch) {
                showError(field, "Enter a valid email address.");
                return false;
            }
            if (field.validity.tooShort) {
                showError(field, `Must be at least ${field.minLength} characters.`);
                return false;
            }
            clearError(field);
            return true;
        };

        fields.forEach((field) => {
            field.addEventListener("blur", () => validateField(field));
            field.addEventListener("input", () => {
                if (fieldWrap(field).classList.contains("is-invalid")) {
                    validateField(field);
                }
            });
        });

        const password = form.querySelector("#password");
        const confirmPassword = form.querySelector("#confirm_password");

        const matchFields = form.querySelectorAll("[data-match]");

        const checkMatches = () => {
            let allMatch = true;
            matchFields.forEach((field) => {
                const target = form.querySelector(`#${field.dataset.match}`);
                if (!target || !field.value) {
                    clearError(field);
                    return;
                }
                if (field.value !== target.value) {
                    showError(field, "Passwords don't match.");
                    allMatch = false;
                } else {
                    clearError(field);
                }
            });
            return allMatch;
        };

        matchFields.forEach((field) => {
            const target = form.querySelector(`#${field.dataset.match}`);
            field.addEventListener("input", checkMatches);
            if (target) target.addEventListener("input", checkMatches);
        });

        form.addEventListener("submit", (event) => {
            let isValid = true;

            fields.forEach((field) => {
                if (!validateField(field)) isValid = false;
            });

            if (!checkMatches()) isValid = false;

            if (!isValid) {
                event.preventDefault();
                const firstInvalid = form.querySelector(".is-invalid");
                if (firstInvalid) {
                    const target = firstInvalid.querySelector("input, select, textarea") || firstInvalid;
                    target.focus();
                }
            }
        });
    });
}
