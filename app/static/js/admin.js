/**
 * Guess the Word • Admin Reports Script (Phase 4C-2 & Phase 4C-3)
 *
 * Manages the Admin Daily Report dashboard and Per-User Report,
 * asynchronous API requests, and accessible state transitions.
 */

(function () {
    "use strict";

    window.GuessTheWord = window.GuessTheWord || {};

    const AdminReports = {
        elements: {},
        isLoading: false, // Daily report loading state
        isUserLoading: false, // User report loading state
        userReportRequestId: 0, // Race-condition sequence tracker
        usersList: [], // Cached users from GET /admin/reports/users

        init() {
            this.cacheElements();
            this.bindEvents();
            this.setDefaultDates();
            this.fetchInitialReport();
            this.loadUsers();
        },

        /**
         * Cache references to DOM elements
         */
        cacheElements() {
            this.elements = {
                // Daily Report Elements
                form: document.getElementById("daily-report-form"),
                dateInput: document.getElementById("report-date-input"),
                btnRun: document.getElementById("btn-run-daily-report"),
                btnText: document.getElementById("btn-run-text"),
                feedback: document.getElementById("report-feedback"),
                feedbackText: document.getElementById("feedback-text"),
                feedbackSpinner: document.getElementById("feedback-spinner"),
                contextDate: document.getElementById("context-date-display"),
                metricUsers: document.getElementById("metric-users-value"),
                metricCorrect: document.getElementById("metric-correct-value"),
                cardUsers: document.getElementById("metric-card-users"),
                cardCorrect: document.getElementById("metric-card-correct"),

                // User Report Elements (Phase 4C-3)
                userSection: document.getElementById("user-report-section"),
                userForm: document.getElementById("user-report-form"),
                userSelect: document.getElementById("user-select"),
                userDateInput: document.getElementById("user-report-date-input"),
                btnRunUser: document.getElementById("btn-run-user-report"),
                btnRunUserText: document.getElementById("btn-run-user-text"),
                userFeedback: document.getElementById("user-report-feedback"),
                userFeedbackText: document.getElementById("user-feedback-text"),
                userFeedbackSpinner: document.getElementById("user-feedback-spinner"),
                userContextBar: document.getElementById("user-context-bar"),
                userContextUsername: document.getElementById("user-context-username"),
                userContextDate: document.getElementById("user-context-date"),
                metricWordsTried: document.getElementById("metric-words-tried-value"),
                metricUserCorrect: document.getElementById("metric-user-correct-value"),
                cardWordsTried: document.getElementById("metric-card-words-tried"),
                cardUserCorrect: document.getElementById("metric-card-user-correct"),
            };
        },

        /**
         * Get today's calendar date in UTC YYYY-MM-DD format
         * @returns {string}
         */
        getTodayUTCDate() {
            const now = new Date();
            const year = now.getUTCFullYear();
            const month = String(now.getUTCMonth() + 1).padStart(2, "0");
            const day = String(now.getUTCDate()).padStart(2, "0");
            return `${year}-${month}-${day}`;
        },

        /**
         * Set default date in date inputs to today's UTC date
         */
        setDefaultDates() {
            const today = this.getTodayUTCDate();
            if (this.elements.dateInput && !this.elements.dateInput.value) {
                this.elements.dateInput.value = today;
            }
            if (this.elements.userDateInput && !this.elements.userDateInput.value) {
                this.elements.userDateInput.value = today;
            }
        },

        /**
         * Bind submit listeners to forms once
         */
        bindEvents() {
            // Daily Report Form Submit
            if (this.elements.form) {
                this.elements.form.addEventListener("submit", (e) => {
                    e.preventDefault();
                    this.handleRunReport();
                });
            }

            // User Report Form Submit
            if (this.elements.userForm) {
                this.elements.userForm.addEventListener("submit", (e) => {
                    e.preventDefault();
                    this.handleRunUserReport();
                });
            }
        },

        // ====================================================================
        // Daily Report Logic
        // ====================================================================

        /**
         * Handle Run Daily Report submission
         */
        handleRunReport() {
            if (this.isLoading) return;

            const selectedDate = this.elements.dateInput ? this.elements.dateInput.value.trim() : "";
            if (!selectedDate) {
                this.showError("Please select a valid report date.");
                return;
            }

            this.fetchDailyReport(selectedDate);
        },

        /**
         * Fetch initial daily report on page load
         */
        fetchInitialReport() {
            const initialDate = this.elements.dateInput ? this.elements.dateInput.value.trim() : this.getTodayUTCDate();
            this.fetchDailyReport(initialDate);
        },

        /**
         * Set UI loading state and indicators for Daily Report
         * @param {boolean} isLoading
         * @param {string} [targetDate=""]
         */
        setLoading(isLoading, targetDate = "") {
            this.isLoading = !!isLoading;

            if (this.elements.btnRun) {
                this.elements.btnRun.disabled = !!isLoading;
                if (isLoading) {
                    this.elements.btnRun.classList.add("is-loading");
                    this.elements.btnRun.innerHTML = '<span class="feedback-spinner" aria-hidden="true"></span><span class="btn-text">Running...</span>';
                } else {
                    this.elements.btnRun.classList.remove("is-loading");
                    this.elements.btnRun.innerHTML = '<span class="btn-text" id="btn-run-text">Run Report</span>';
                }
            }

            if (isLoading) {
                // Clear stale numbers during fetch
                if (this.elements.metricUsers) this.elements.metricUsers.textContent = "--";
                if (this.elements.metricCorrect) this.elements.metricCorrect.textContent = "--";
                if (this.elements.contextDate) this.elements.contextDate.textContent = targetDate || "--";

                this.showLoadingFeedback(`Loading report for ${targetDate || "selected date"}...`);
            } else {
                if (this.elements.feedback && this.elements.feedback.classList.contains("is-loading")) {
                    this.clearFeedback();
                }
            }
        },

        /**
         * Fetch daily report from GET /admin/reports/daily?date=YYYY-MM-DD
         * @param {string} targetDate
         */
        async fetchDailyReport(targetDate) {
            if (!targetDate) return;

            this.clearFeedback();
            this.setLoading(true, targetDate);

            try {
                const url = `/admin/reports/daily?date=${encodeURIComponent(targetDate)}`;
                const response = await fetch(url, {
                    method: "GET",
                    headers: {
                        "Accept": "application/json"
                    },
                    credentials: "same-origin"
                });

                await this.handleResponse(response, targetDate);
            } catch (err) {
                this.setLoading(false);
                this.showError("Unable to connect to the server. Please check your network connection.");
            }
        },

        /**
         * Process response from GET /admin/reports/daily
         * @param {Response} response
         * @param {string} targetDate
         */
        async handleResponse(response, targetDate) {
            this.setLoading(false);

            if (response.status === 200) {
                try {
                    const data = await response.json();
                    this.clearFeedback();
                    this.renderDailyReport(data);
                } catch (e) {
                    this.showError("Unexpected response format received from server.");
                }
                return;
            }

            if (response.status === 401) {
                this.showError("Your session has expired. Please log in again to view admin reports.");
                window.location.href = "/login";
                return;
            }

            if (response.status === 403) {
                this.showError("You do not have permission to view admin reports.");
                return;
            }

            if (response.status === 422) {
                this.showError("Invalid date format. Please select a valid date (YYYY-MM-DD).");
                return;
            }

            let errorMsg = "Unable to load daily report. Please try again.";
            try {
                const data = await response.json();
                if (data && typeof data.detail === "string" && data.detail.trim()) {
                    errorMsg = data.detail.trim();
                }
            } catch (_) {}

            this.showError(errorMsg);
        },

        /**
         * Render report data onto daily metric cards
         * @param {object} data
         */
        renderDailyReport(data) {
            if (!data) return;

            if (this.elements.contextDate) {
                this.elements.contextDate.textContent = data.date || "--";
            }

            if (this.elements.metricUsers) {
                const users = typeof data.number_of_users === "number" ? data.number_of_users : 0;
                this.elements.metricUsers.textContent = users.toLocaleString();
            }

            if (this.elements.metricCorrect) {
                const correct = typeof data.number_of_correct_guesses === "number" ? data.number_of_correct_guesses : 0;
                this.elements.metricCorrect.textContent = correct.toLocaleString();
            }
        },

        /**
         * Display daily report loading feedback
         * @param {string} message
         */
        showLoadingFeedback(message) {
            if (!this.elements.feedback) return;
            const el = this.elements.feedback;
            el.className = "report-feedback is-loading";

            if (this.elements.feedbackSpinner) {
                this.elements.feedbackSpinner.classList.remove("is-hidden");
            }
            if (this.elements.feedbackText) {
                this.elements.feedbackText.textContent = message || "Loading...";
            }
            el.classList.remove("is-hidden");
        },

        /**
         * Display daily report error banner
         * @param {string} message
         */
        showError(message) {
            if (!this.elements.feedback) return;
            const el = this.elements.feedback;
            el.className = "report-feedback is-error";

            if (this.elements.feedbackSpinner) {
                this.elements.feedbackSpinner.classList.add("is-hidden");
            }
            if (this.elements.feedbackText) {
                this.elements.feedbackText.textContent = message || "An error occurred.";
            }
            el.classList.remove("is-hidden");
        },

        /**
         * Clear daily report feedback banner
         */
        clearFeedback() {
            if (!this.elements.feedback) return;
            this.elements.feedback.classList.add("is-hidden");
            if (this.elements.feedbackText) {
                this.elements.feedbackText.textContent = "";
            }
            if (this.elements.feedbackSpinner) {
                this.elements.feedbackSpinner.classList.add("is-hidden");
            }
        },

        // ====================================================================
        // Per-User Report Logic (Phase 4C-3)
        // ====================================================================

        /**
         * Fetch users list from GET /admin/reports/users and populate selector
         */
        async loadUsers() {
            if (!this.elements.userSelect) return;

            // Initial loading state for user select
            this.elements.userSelect.disabled = true;
            if (this.elements.btnRunUser) {
                this.elements.btnRunUser.disabled = true;
            }
            this.elements.userSelect.innerHTML = '<option value="" disabled selected>Loading users...</option>';

            try {
                const response = await fetch("/admin/reports/users", {
                    method: "GET",
                    headers: {
                        "Accept": "application/json"
                    },
                    credentials: "same-origin"
                });

                if (response.status === 200) {
                    const users = await response.json();
                    this.populateUserSelect(users);
                    return;
                }

                if (response.status === 401) {
                    this.showUserReportError("Your session has expired. Please log in again.");
                    window.location.href = "/login";
                    return;
                }

                if (response.status === 403) {
                    this.showUserReportError("You do not have permission to view admin reports.");
                    this.elements.userSelect.innerHTML = '<option value="" disabled selected>Access denied</option>';
                    return;
                }

                this.showUserReportError("Failed to load user list.");
                this.elements.userSelect.innerHTML = '<option value="" disabled selected>Failed to load users</option>';
            } catch (err) {
                this.showUserReportError("Unable to load user list. Please check your network connection.");
                this.elements.userSelect.innerHTML = '<option value="" disabled selected>Error loading users</option>';
            }
        },

        /**
         * Populate the user selector and trigger default initial user report
         * @param {Array<{id: number, username: string, role: string}>} users
         */
        populateUserSelect(users) {
            this.usersList = Array.isArray(users) ? users : [];
            const selectEl = this.elements.userSelect;
            if (!selectEl) return;

            if (this.usersList.length === 0) {
                selectEl.innerHTML = '<option value="" disabled selected>No users found</option>';
                selectEl.disabled = true;
                if (this.elements.btnRunUser) {
                    this.elements.btnRunUser.disabled = true;
                }
                return;
            }

            selectEl.innerHTML = "";
            this.usersList.forEach((u) => {
                const opt = document.createElement("option");
                opt.value = String(u.id);
                opt.textContent = u.username;
                selectEl.appendChild(opt);
            });

            selectEl.disabled = false;
            selectEl.selectedIndex = 0;

            if (this.elements.btnRunUser) {
                this.elements.btnRunUser.disabled = false;
            }

            // Automatic initial fetch for the selected first user and default date
            const initialUserId = selectEl.value;
            const initialDate = this.elements.userDateInput ? this.elements.userDateInput.value.trim() : this.getTodayUTCDate();

            if (initialUserId && initialDate) {
                this.fetchUserReport(initialUserId, initialDate);
            }
        },

        /**
         * Handle Run User Report submission
         */
        handleRunUserReport() {
            if (this.isUserLoading) return;

            const selectedUserId = this.elements.userSelect ? this.elements.userSelect.value.trim() : "";
            const selectedDate = this.elements.userDateInput ? this.elements.userDateInput.value.trim() : "";

            if (!selectedUserId) {
                this.showUserReportError("Please select a user to generate the report.");
                return;
            }

            if (!selectedDate) {
                this.showUserReportError("Please select a valid report date.");
                return;
            }

            this.fetchUserReport(selectedUserId, selectedDate);
        },

        /**
         * Set UI loading state and indicators for User Report
         * @param {boolean} isLoading
         * @param {string} [targetUsername=""]
         * @param {string} [targetDate=""]
         */
        setUserReportLoading(isLoading, targetUsername = "", targetDate = "") {
            this.isUserLoading = !!isLoading;

            if (this.elements.btnRunUser) {
                this.elements.btnRunUser.disabled = !!isLoading;
                if (isLoading) {
                    this.elements.btnRunUser.classList.add("is-loading");
                    this.elements.btnRunUser.innerHTML = '<span class="feedback-spinner" aria-hidden="true"></span><span class="btn-text">Running...</span>';
                } else {
                    this.elements.btnRunUser.classList.remove("is-loading");
                    this.elements.btnRunUser.innerHTML = '<span class="btn-text" id="btn-run-user-text">Run Report</span>';
                }
            }

            if (this.elements.userSelect) {
                this.elements.userSelect.disabled = !!isLoading;
            }
            if (this.elements.userDateInput) {
                this.elements.userDateInput.disabled = !!isLoading;
            }

            if (isLoading) {
                // Clear stale metrics during fetch
                if (this.elements.metricWordsTried) this.elements.metricWordsTried.textContent = "--";
                if (this.elements.metricUserCorrect) this.elements.metricUserCorrect.textContent = "--";
                if (this.elements.userContextUsername) this.elements.userContextUsername.textContent = targetUsername || "--";
                if (this.elements.userContextDate) this.elements.userContextDate.textContent = targetDate || "--";

                this.showUserReportLoadingFeedback(
                    `Loading report for ${targetUsername || "user"} on ${targetDate || "selected date"}...`
                );
            } else {
                if (this.elements.userFeedback && this.elements.userFeedback.classList.contains("is-loading")) {
                    this.clearUserReportFeedback();
                }
            }
        },

        /**
         * Fetch user report from GET /admin/reports/user/{user_id}?date=YYYY-MM-DD
         * Includes race condition token to discard superseded asynchronous responses.
         * @param {string|number} userId
         * @param {string} targetDate
         */
        async fetchUserReport(userId, targetDate) {
            if (!userId || !targetDate) return;

            // Resolve target username for immediate display
            let targetUsername = "";
            if (this.elements.userSelect && this.elements.userSelect.selectedOptions && this.elements.userSelect.selectedOptions[0]) {
                targetUsername = this.elements.userSelect.selectedOptions[0].textContent;
            } else {
                const found = this.usersList.find((u) => String(u.id) === String(userId));
                targetUsername = found ? found.username : `User ${userId}`;
            }

            this.clearUserReportFeedback();

            // Track request ID to ignore stale responses
            const currentRequestId = ++this.userReportRequestId;
            this.setUserReportLoading(true, targetUsername, targetDate);

            try {
                const url = `/admin/reports/user/${encodeURIComponent(userId)}?date=${encodeURIComponent(targetDate)}`;
                const response = await fetch(url, {
                    method: "GET",
                    headers: {
                        "Accept": "application/json"
                    },
                    credentials: "same-origin"
                });

                await this.handleUserReportResponse(response, userId, targetDate, currentRequestId);
            } catch (err) {
                if (currentRequestId !== this.userReportRequestId) return;
                this.setUserReportLoading(false);
                this.showUserReportError("Unable to connect to the server. Please check your network connection.");
            }
        },

        /**
         * Process response from GET /admin/reports/user/{user_id}
         * @param {Response} response
         * @param {string|number} userId
         * @param {string} targetDate
         * @param {number} requestId
         */
        async handleUserReportResponse(response, userId, targetDate, requestId) {
            // Drop stale asynchronous response if a newer request was dispatched
            if (requestId !== this.userReportRequestId) return;

            this.setUserReportLoading(false);

            if (response.status === 200) {
                try {
                    const data = await response.json();
                    this.clearUserReportFeedback();
                    this.renderUserReport(data);
                } catch (e) {
                    this.showUserReportError("Unexpected response format received from server.");
                }
                return;
            }

            if (response.status === 401) {
                this.showUserReportError("Your session has expired. Please log in again to view admin reports.");
                window.location.href = "/login";
                return;
            }

            if (response.status === 403) {
                this.showUserReportError("You do not have permission to view admin reports.");
                return;
            }

            if (response.status === 404) {
                this.showUserReportError("User not found. The requested user account may have been removed.");
                return;
            }

            if (response.status === 422) {
                this.showUserReportError("Invalid date format. Please select a valid date (YYYY-MM-DD).");
                return;
            }

            let errorMsg = "Unable to load user report. Please try again.";
            try {
                const data = await response.json();
                if (data && typeof data.detail === "string" && data.detail.trim()) {
                    errorMsg = data.detail.trim();
                }
            } catch (_) {}

            this.showUserReportError(errorMsg);
        },

        /**
         * Render user report data onto metric cards
         * @param {object} data
         */
        renderUserReport(data) {
            if (!data) return;

            if (this.elements.userContextUsername) {
                this.elements.userContextUsername.textContent = data.username || "--";
            }

            if (this.elements.userContextDate) {
                this.elements.userContextDate.textContent = data.date || "--";
            }

            if (this.elements.metricWordsTried) {
                const tried = typeof data.number_of_words_tried === "number" ? data.number_of_words_tried : 0;
                this.elements.metricWordsTried.textContent = tried.toLocaleString();
            }

            if (this.elements.metricUserCorrect) {
                const correct = typeof data.number_of_correct_guesses === "number" ? data.number_of_correct_guesses : 0;
                this.elements.metricUserCorrect.textContent = correct.toLocaleString();
            }
        },

        /**
         * Display user report loading feedback
         * @param {string} message
         */
        showUserReportLoadingFeedback(message) {
            if (!this.elements.userFeedback) return;
            const el = this.elements.userFeedback;
            el.className = "report-feedback is-loading";

            if (this.elements.userFeedbackSpinner) {
                this.elements.userFeedbackSpinner.classList.remove("is-hidden");
            }
            if (this.elements.userFeedbackText) {
                this.elements.userFeedbackText.textContent = message || "Loading...";
            }
            el.classList.remove("is-hidden");
        },

        /**
         * Display user report error banner
         * @param {string} message
         */
        showUserReportError(message) {
            if (!this.elements.userFeedback) return;
            const el = this.elements.userFeedback;
            el.className = "report-feedback is-error";

            if (this.elements.userFeedbackSpinner) {
                this.elements.userFeedbackSpinner.classList.add("is-hidden");
            }
            if (this.elements.userFeedbackText) {
                this.elements.userFeedbackText.textContent = message || "An error occurred.";
            }
            el.classList.remove("is-hidden");
        },

        /**
         * Clear user report feedback banner
         */
        clearUserReportFeedback() {
            if (!this.elements.userFeedback) return;
            this.elements.userFeedback.classList.add("is-hidden");
            if (this.elements.userFeedbackText) {
                this.elements.userFeedbackText.textContent = "";
            }
            if (this.elements.userFeedbackSpinner) {
                this.elements.userFeedbackSpinner.classList.add("is-hidden");
            }
        }
    };

    window.GuessTheWord.AdminReports = AdminReports;

    // Initialize when DOM is ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => AdminReports.init());
    } else {
        AdminReports.init();
    }
})();
