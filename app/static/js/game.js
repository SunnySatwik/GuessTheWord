/**
 * Guess the Word • Client-side Game Script (Phase 4B-1 Visual Foundation)
 * 
 * Sets up the game module namespace, DOM element references, and foundational
 * UI state hooks for subsequent phases without executing game/guess logic.
 */

(function () {
    "use strict";

    window.GuessTheWord = window.GuessTheWord || {};

    const GamePage = {
        elements: {},
        currentInput: "",
        activeRowIndex: -1,
        gameState: null,
        isKeyHandlerBound: false,
        isStartingGame: false,
        isSubmittingGuess: false,
        isRevealing: false,
        revealTimeouts: [],

        init() {
            this.cacheElements();
            this.bindEvents();
            this.bindKeyboardEvents();
            this.checkInitialGame();
        },

        cacheElements() {
            const btnElement = document.getElementById("action-start-game") || document.getElementById("btn-start-game");
            const resolvedBtn = btnElement && btnElement.tagName === "SPAN" ? (btnElement.closest("button") || btnElement) : btnElement;

            this.elements = {
                container: document.querySelector(".game-page-container"),
                attemptsDisplay: document.getElementById("attempts-display"),
                dailyGamesDisplay: document.getElementById("daily-games-display"),
                statusBadge: document.getElementById("game-status-badge"),
                btnStartGame: resolvedBtn,
                stateReady: document.getElementById("state-ready"),
                stateCompleted: document.getElementById("state-completed"),
                stateLimit: document.getElementById("state-limit"),
                limitMessage: document.getElementById("limit-message"),
                stateLoading: document.getElementById("state-loading"),
                stateError: document.getElementById("state-error"),
                errorText: document.getElementById("error-text"),
                completionTitle: document.getElementById("completion-title"),
                completionMessage: document.getElementById("completion-message"),
                completionTargetWrapper: document.getElementById("completion-target-wrapper"),
                completionTarget: document.getElementById("completion-target"),
                gameStage: document.getElementById("game-stage"),
                gameBoard: document.getElementById("game-board"),
                boardRows: document.querySelectorAll(".board-row"),
                boardTiles: document.querySelectorAll(".board-tile"),
                gameControls: document.getElementById("game-controls"),
                guessFeedback: document.getElementById("guess-feedback"),
                feedbackText: document.getElementById("feedback-text"),
                completionIcon: document.getElementById("completion-icon"),
                completionAttempts: document.getElementById("completion-attempts"),
                btnPlayAgain: document.getElementById("action-play-again") || document.getElementById("btn-play-again"),
                completionFeedback: document.getElementById("completion-feedback"),
                completionFeedbackText: document.getElementById("completion-feedback-text"),
                // HUD Phase 3
                attemptPips: document.querySelectorAll(".attempt-pip"),
                dailySegs: document.querySelectorAll(".daily-seg[data-seg]"),
            };
        },

        /**
         * Lookup helper to get a specific tile by row and column indices
         * @param {number} row (0-4)
         * @param {number} col (0-4)
         * @returns {HTMLElement|null}
         */
        getTile(row, col) {
            return document.querySelector(`.board-tile[data-row="${row}"][data-col="${col}"]`);
        },

        /**
         * Set the letter inside a specific tile and update filled state
         * @param {number} row (0-4)
         * @param {number} col (0-4)
         * @param {string} letter
         */
        setTileLetter(row, col, letter) {
            const tile = this.getTile(row, col);
            if (!tile) return;
            const normalized = (letter || "").toUpperCase().trim().slice(0, 1);
            tile.textContent = normalized;
            if (normalized) {
                tile.classList.add("is-filled");
                tile.setAttribute("aria-label", `Row ${row + 1}, Letter ${col + 1}: ${normalized}`);
            } else {
                tile.classList.remove("is-filled");
                tile.setAttribute("aria-label", `Row ${row + 1}, Letter ${col + 1}`);
            }
        },

        /**
         * Set evaluation or visual state for a specific tile
         * @param {number} row (0-4)
         * @param {number} col (0-4)
         * @param {"empty"|"filled"|"correct"|"present"|"absent"|"revealing"} state
         */
        setTileState(row, col, state) {
            const tile = this.getTile(row, col);
            if (!tile) return;

            // Remove all evaluation and interaction states
            tile.classList.remove("is-filled", "is-correct", "is-present", "is-absent", "is-revealing");

            if (state && state !== "empty") {
                tile.classList.add(`is-${state}`);
                tile.setAttribute("data-state", state);
                const char = tile.textContent || "";
                if (char) {
                    tile.setAttribute("aria-label", `Row ${row + 1}, Letter ${col + 1}: ${char}, ${state}`);
                }
            } else {
                tile.removeAttribute("data-state");
            }
        },

        /**
         * Clear a specific tile's letter and all state classes
         * @param {number} row (0-4)
         * @param {number} col (0-4)
         */
        clearTile(row, col) {
            const tile = this.getTile(row, col);
            if (!tile) return;

            // Brief remove animation only if tile had a letter (backspace UX)
            if (tile.textContent && tile.textContent.trim()) {
                tile.classList.add("is-removing");
                setTimeout(() => {
                    tile.classList.remove("is-removing");
                    tile.textContent = "";
                    tile.classList.remove("is-filled", "is-correct", "is-present", "is-absent", "is-revealing");
                    tile.removeAttribute("data-state");
                    tile.setAttribute("aria-label", `Row ${row + 1}, Letter ${col + 1}`);
                }, 100);
            } else {
                tile.textContent = "";
                tile.classList.remove("is-filled", "is-correct", "is-present", "is-absent", "is-revealing");
                tile.removeAttribute("data-state");
                tile.setAttribute("aria-label", `Row ${row + 1}, Letter ${col + 1}`);
            }
        },

        /**
         * Trigger a flip reveal animation on a tile and update its state midway
         * @param {number} row (0-4)
         * @param {number} col (0-4)
         * @param {"correct"|"present"|"absent"} state
         * @param {number} [delayMs=0]
         */
        revealTile(row, col, state, delayMs = 0) {
            const tile = this.getTile(row, col);
            if (!tile) return;

            const t1 = setTimeout(() => {
                tile.classList.add("is-revealing");
                const t2 = setTimeout(() => {
                    tile.classList.remove("is-filled");
                    tile.classList.add(`is-${state}`);
                    tile.setAttribute("data-state", state);
                }, 250);

                const t3 = setTimeout(() => {
                    tile.classList.remove("is-revealing");
                }, 500);

                this.revealTimeouts.push(t2, t3);
            }, delayMs);

            this.revealTimeouts.push(t1);
        },

        /**
         * Clear any pending reveal timeouts
         */
        clearRevealTimeouts() {
            if (this.revealTimeouts && this.revealTimeouts.length > 0) {
                this.revealTimeouts.forEach(t => clearTimeout(t));
                this.revealTimeouts = [];
            }
        },

        bindEvents() {
            if (this.elements.btnStartGame) {
                this.elements.btnStartGame.addEventListener("click", (e) => {
                    e.preventDefault();
                    this.startGame("start");
                });
            }
            if (this.elements.btnPlayAgain) {
                const resolvedPlayAgainBtn = this.elements.btnPlayAgain.tagName === "SPAN" 
                    ? (this.elements.btnPlayAgain.closest("button") || this.elements.btnPlayAgain) 
                    : this.elements.btnPlayAgain;
                resolvedPlayAgainBtn.addEventListener("click", (e) => {
                    e.preventDefault();
                    this.startGame("play-again");
                });
            }
        },

        /**
         * Bind global physical keyboard input listener once
         */
        bindKeyboardEvents() {
            if (this.isKeyHandlerBound) return;
            this.boundKeyDownHandler = (e) => this.handleKeyDown(e);
            document.addEventListener("keydown", this.boundKeyDownHandler);
            this.isKeyHandlerBound = true;
        },

        /**
         * Determine if the game is in an active state capable of receiving guess input
         * @returns {boolean}
         */
        canAcceptInput() {
            return (
                this.gameState != null &&
                this.gameState.status === "IN_PROGRESS" &&
                this.activeRowIndex >= 0 &&
                this.activeRowIndex < 5 &&
                (typeof this.gameState.attempts !== "number" || this.gameState.attempts < (this.gameState.max_attempts || 5)) &&
                !this.isStartingGame &&
                !this.isSubmittingGuess &&
                !this.isRevealing
            );
        },

        /**
         * Process physical keyboard keydown events
         * @param {KeyboardEvent} event
         */
        handleKeyDown(event) {
            // Do not capture if user is typing in a form control
            const targetTag = event.target && event.target.tagName;
            if (targetTag === "INPUT" || targetTag === "TEXTAREA" || targetTag === "SELECT") {
                return;
            }
            if (event.target && event.target.isContentEditable) {
                return;
            }

            // Do not interfere with browser navigation / system shortcuts
            if (event.ctrlKey || event.altKey || event.metaKey) {
                return;
            }

            // Guard against international IME composition keystrokes
            if (event.isComposing || event.keyCode === 229) {
                return;
            }

            // Only proceed if game is active and accepting input
            if (!this.canAcceptInput()) {
                return;
            }

            const key = event.key;
            const code = event.code;

            if (key === "Backspace" || code === "Backspace") {
                event.preventDefault();
                this.handleBackspace();
                return;
            }

            if (key === "Enter" || code === "Enter") {
                if (event.repeat) return;
                event.preventDefault();
                this.handleSubmitRequest();
                return;
            }

            // Single alphabetic key A-Z (handles standard char or code like KeyA)
            let letter = "";
            if (key && key.length === 1 && /^[a-zA-Z]$/.test(key)) {
                letter = key;
            } else if (code && code.startsWith("Key") && code.length === 4) {
                letter = code.slice(3);
            }

            if (letter && /^[a-zA-Z]$/.test(letter)) {
                event.preventDefault();
                this.handleLetterInput(letter);
                return;
            }
        },

        /**
         * Append an alphabetic letter to the current guess in the active row
         * @param {string} letter
         */
        handleLetterInput(letter) {
            if (!this.canAcceptInput()) return;
            if (this.currentInput.length >= 5) return;

            this.clearInputFeedback();
            const normalized = letter.toUpperCase();
            const col = this.currentInput.length;
            this.currentInput += normalized;
            this.setTileLetter(this.activeRowIndex, col, normalized);
        },

        /**
         * Remove the most recently entered letter from the active row
         */
        handleBackspace() {
            if (!this.canAcceptInput()) return;
            this.clearInputFeedback();
            if (this.currentInput.length === 0) return;

            const colToRemove = this.currentInput.length - 1;
            this.currentInput = this.currentInput.slice(0, -1);
            this.clearTile(this.activeRowIndex, colToRemove);
        },

        /**
         * Process Enter key action for guess submission (Phase 4B-3C)
         * @returns {object|null}
         */
        handleSubmitRequest() {
            if (!this.canAcceptInput()) return null;

            if (this.currentInput.length < 5) {
                this.showInputFeedback("5 letters required", "error");
                return { submitted: false, reason: "Word must be 5 letters." };
            }

            this.clearInputFeedback();
            this.submitGuess();
            return {
                submitted: true,
                guess: this.currentInput
            };
        },

        /**
         * Submit the current 5-letter guess to POST /game/{game_id}/guess
         */
        async submitGuess() {
            if (this.isSubmittingGuess || this.currentInput.length !== 5 || !this.canAcceptInput()) {
                return;
            }

            const guess = this.currentInput.toUpperCase();
            const gameId = this.gameState && this.gameState.game_id;
            if (!gameId) return;

            this.setSubmissionLoading(true);

            try {
                const response = await fetch(`/game/${encodeURIComponent(gameId)}/guess`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    credentials: "same-origin",
                    body: JSON.stringify({ guess: guess })
                });

                await this.handleGuessResponse(response);
            } catch (err) {
                this.handleGuessError(err);
            }
        },

        /**
         * Set submission loading state and UI indicators
         * @param {boolean} isLoading
         */
        setSubmissionLoading(isLoading) {
            this.isSubmittingGuess = !!isLoading;
            if (this.activeRowIndex >= 0 && this.elements.boardRows && this.elements.boardRows[this.activeRowIndex]) {
                const activeRow = this.elements.boardRows[this.activeRowIndex];
                if (isLoading) {
                    activeRow.classList.add("is-submitting");
                } else {
                    activeRow.classList.remove("is-submitting");
                }
            }

            if (isLoading) {
                this.showInputFeedback("Checking guess...", "loading");
            } else {
                if (this.elements.guessFeedback && this.elements.guessFeedback.classList.contains("is-loading")) {
                    this.clearInputFeedback();
                }
            }
        },

        /**
         * Process response from POST /game/{game_id}/guess
         * @param {Response} response
         */
        async handleGuessResponse(response) {
            this.setSubmissionLoading(false);

            if (response.status === 200) {
                try {
                    const updatedState = await response.json();
                    this.clearInputFeedback();
                    this.animateGuessReveal(updatedState);
                } catch (e) {
                    this.showInputFeedback("Unexpected response format from server.", "error");
                }
                return;
            }

            if (response.status === 400) {
                let errorMsg = "Invalid guess. Please try again.";
                try {
                    const data = await response.json();
                    if (data && typeof data.detail === "string") {
                        errorMsg = data.detail;
                    }
                } catch (_) {}
                this.showInputFeedback(errorMsg, "error");
                return;
            }

            if (response.status === 401) {
                this.showInputFeedback("Your session has expired. Please log in again.", "error");
                this.updateStatusBadge("ready", "Login Required");
                return;
            }

            if (response.status === 403) {
                let errorMsg = "You do not have permission to access this game.";
                try {
                    const data = await response.json();
                    if (data && typeof data.detail === "string") {
                        errorMsg = data.detail;
                    }
                } catch (_) {}
                this.showInputFeedback(errorMsg, "error");
                this.updateStatusBadge("ready", "Forbidden");
                return;
            }

            if (response.status === 404) {
                this.showInputFeedback("Game not found. Please check the game ID or start a new game.", "error");
                this.updateStatusBadge("ready", "Not Found");
                return;
            }

            let errorMsg = "Unable to submit guess. Please try again.";
            try {
                const data = await response.json();
                if (data && typeof data.detail === "string") {
                    errorMsg = data.detail;
                }
            } catch (_) {}
            this.showInputFeedback(errorMsg, "error");
        },

        /**
         * Handle network or client-side fetch errors during guess submission
         * @param {Error} error
         */
        handleGuessError(error) {
            this.setSubmissionLoading(false);
            this.showInputFeedback("Connection error. Please check your network and try again.", "error");
        },

        /**
         * Sequentially reveal evaluation for the submitted guess row with 3D flip animation (Phase 4B-4A)
         * @param {object} gameState
         */
        animateGuessReveal(gameState) {
            if (!gameState) return;
            this.gameState = gameState;

            const submittedRow = this.activeRowIndex;
            const guesses = gameState.guesses || [];
            const latestGuess = guesses.length > 0 ? guesses[guesses.length - 1] : null;

            if (!latestGuess || !latestGuess.evaluations || submittedRow < 0 || submittedRow >= 5) {
                this.applyGuessResult(gameState);
                return;
            }

            // Check reduced motion preference
            const prefersReducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
            if (prefersReducedMotion) {
                this.applyGuessResult(gameState);
                return;
            }

            // Lock input and block duplicate submissions for the reveal duration
            this.isRevealing = true;
            this.clearRevealTimeouts();

            const evaluations = latestGuess.evaluations;
            const tileStaggerMs = 250;
            const tileDurationMs = 500;
            const totalDurationMs = (evaluations.length - 1) * tileStaggerMs + tileDurationMs; // 4 * 250 + 500 = 1500ms

            // Sequentially trigger tile flips from left to right
            for (let c = 0; c < 5; c++) {
                const evalItem = evaluations[c];
                if (!evalItem) continue;

                const letter = evalItem.letter || (latestGuess.guess ? latestGuess.guess[c] : "");
                this.setTileLetter(submittedRow, c, letter);

                let state = "empty";
                if (evalItem.result === "CORRECT") state = "correct";
                else if (evalItem.result === "PRESENT") state = "present";
                else if (evalItem.result === "ABSENT") state = "absent";

                this.revealTile(submittedRow, c, state, c * tileStaggerMs);
            }

            // Schedule finalization callback after all 5 tiles finish revealing
            const finalizeTimeout = setTimeout(() => {
                this.isRevealing = false;

                // 1. Update attempt metadata display
                const attempts = typeof gameState.attempts === "number" ? gameState.attempts : 0;
                const maxAttempts = typeof gameState.max_attempts === "number" ? gameState.max_attempts : 5;
                if (this.elements.attemptsDisplay) {
                    this.elements.attemptsDisplay.textContent = `${attempts} / ${maxAttempts}`;
                }

                // 2. Clear current staged input for the completed row
                this.currentInput = "";

                // 3. Status handling and row advancement or completion state
                const status = (gameState.status || "IN_PROGRESS").toUpperCase();
                if (status === "WON") {
                    this.updateStatusBadge("won", "Won");
                    this.setActiveRow(-1);
                    this.updateAttemptPips(attempts, maxAttempts, "won");
                    this.showCompletedState(gameState, true);
                } else if (status === "LOST") {
                    this.updateStatusBadge("lost", "Lost");
                    this.setActiveRow(-1);
                    this.updateAttemptPips(attempts, maxAttempts, "lost");
                    this.showCompletedState(gameState, false);
                } else {
                    // IN_PROGRESS: activate next row and re-enable typing
                    this.updateStatusBadge("in-progress", "In Progress");
                    this.updateAttemptPips(attempts, maxAttempts, "in-progress");
                    if (attempts < maxAttempts) {
                        this.setActiveRow(attempts);
                    } else {
                        this.setActiveRow(-1);
                    }
                }
            }, totalDurationMs);

            this.revealTimeouts.push(finalizeTimeout);
        },

        /**
         * Apply successful guess result directly from backend response
         * Maps CORRECT -> correct, PRESENT -> present, ABSENT -> absent
         * @param {object} gameState
         */
        applyGuessResult(gameState) {
            if (!gameState) return;
            this.gameState = gameState;

            // 1. Render evaluations directly onto the row that was just submitted
            const submittedRow = this.activeRowIndex;
            const guesses = gameState.guesses || [];
            const latestGuess = guesses.length > 0 ? guesses[guesses.length - 1] : null;

            if (latestGuess && latestGuess.evaluations && submittedRow >= 0 && submittedRow < 5) {
                for (let c = 0; c < 5; c++) {
                    const evalItem = latestGuess.evaluations[c];
                    if (!evalItem) continue;

                    const letter = evalItem.letter || (latestGuess.guess ? latestGuess.guess[c] : "");
                    this.setTileLetter(submittedRow, c, letter);

                    let state = "empty";
                    if (evalItem.result === "CORRECT") state = "correct";
                    else if (evalItem.result === "PRESENT") state = "present";
                    else if (evalItem.result === "ABSENT") state = "absent";

                    this.setTileState(submittedRow, c, state);
                }
            }

            // 2. Update attempt metadata display
            const attempts = typeof gameState.attempts === "number" ? gameState.attempts : 0;
            const maxAttempts = typeof gameState.max_attempts === "number" ? gameState.max_attempts : 5;
            if (this.elements.attemptsDisplay) {
                this.elements.attemptsDisplay.textContent = `${attempts} / ${maxAttempts}`;
            }

            // 3. Clear current staged input for the completed row
            this.currentInput = "";

            // 4. Update status and handle active row advancement or completion
            const status = (gameState.status || "IN_PROGRESS").toUpperCase();
            if (status === "WON") {
                this.updateStatusBadge("won", "Won");
                this.setActiveRow(-1);
                this.updateAttemptPips(attempts, maxAttempts, "won");
                this.showCompletedState(gameState, true);
            } else if (status === "LOST") {
                this.updateStatusBadge("lost", "Lost");
                this.setActiveRow(-1);
                this.updateAttemptPips(attempts, maxAttempts, "lost");
                this.showCompletedState(gameState, false);
            } else {
                // IN_PROGRESS
                this.updateStatusBadge("in-progress", "In Progress");
                this.updateAttemptPips(attempts, maxAttempts, "in-progress");
                if (attempts < maxAttempts) {
                    this.setActiveRow(attempts);
                } else {
                    this.setActiveRow(-1);
                }
            }
        },

        /**
         * Show subtle inline feedback or error below the game board
         * @param {string} message
         * @param {"info"|"error"|"loading"} [type="info"]
         */
        showInputFeedback(message, type = "info") {
            if (!this.elements.guessFeedback) return;
            const el = this.elements.guessFeedback;
            el.className = "guess-feedback";
            if (type === "error") {
                el.classList.add("is-error");
            } else if (type === "loading") {
                el.classList.add("is-loading");
            } else if (type === "success") {
                el.classList.add("is-success");
            } else {
                el.classList.add("is-info");
            }

            if (type === "loading") {
                el.innerHTML = '<span class="feedback-spinner" aria-hidden="true"></span><span class="feedback-text" id="feedback-text">' + (message || "Checking guess...") + '</span>';
            } else {
                el.innerHTML = '<span class="feedback-icon" aria-hidden="true"></span><span class="feedback-text" id="feedback-text">' + (message || "") + '</span>';
            }
            this.elements.feedbackText = document.getElementById("feedback-text");
            el.classList.remove("is-hidden");
        },

        /**
         * Clear subtle inline feedback if visible
         */
        clearInputFeedback() {
            if (!this.elements.guessFeedback) return;
            this.elements.guessFeedback.classList.add("is-hidden");
            this.elements.guessFeedback.textContent = "";
        },

        /**
         * Clear staged letters for the active row and reset input string
         */
        clearCurrentInput() {
            if (this.activeRowIndex >= 0 && this.activeRowIndex < 5 && this.currentInput) {
                for (let c = 0; c < this.currentInput.length; c++) {
                    this.clearTile(this.activeRowIndex, c);
                }
            }
            this.currentInput = "";
        },

        /**
         * Ensure currentInput is empty/consistent for the current active input row
         */
        syncCurrentInput() {
            this.currentInput = "";
        },


        /**
         * Show inline feedback within the completion panel (daily limit, session expired, or errors)
         * @param {string} message
         * @param {"limit"|"error"} [type="error"]
         */
        showCompletionFeedback(message, type = "error") {
            if (!this.elements.completionFeedback) return;
            const el = this.elements.completionFeedback;
            el.className = "completion-feedback";
            if (type === "limit") {
                el.classList.add("is-limit");
            } else {
                el.classList.add("is-error");
            }
            if (this.elements.completionFeedbackText) {
                this.elements.completionFeedbackText.textContent = message || "";
            } else {
                el.textContent = message || "";
            }
            el.classList.remove("is-hidden");
        },

        /**
         * Clear completion panel inline feedback if visible
         */
        clearCompletionFeedback() {
            if (!this.elements.completionFeedback) return;
            this.elements.completionFeedback.classList.add("is-hidden");
            if (this.elements.completionFeedbackText) {
                this.elements.completionFeedbackText.textContent = "";
            }
        },

        /**
         * Set the start or play-again button loading and disabled state
         * @param {boolean} isLoading
         * @param {"start"|"play-again"} [triggerSource="start"]
         */
        setStartButtonLoading(isLoading, triggerSource = "start") {
            this.isStartingGame = !!isLoading;

            const startBtn = this.elements.btnStartGame;
            if (startBtn) {
                startBtn.disabled = !!isLoading;
                if (isLoading && triggerSource === "start") {
                    startBtn.classList.add("is-loading");
                    startBtn.innerHTML = '<span class="btn-spinner-sm" aria-hidden="true"></span><span class="btn-text">Starting...</span>';
                } else {
                    startBtn.classList.remove("is-loading");
                    startBtn.innerHTML = '<span id="btn-start-game" class="btn-text">Start Game</span>';
                }
            }

            const playAgainBtn = this.elements.btnPlayAgain 
                ? (this.elements.btnPlayAgain.tagName === "SPAN" ? (this.elements.btnPlayAgain.closest("button") || this.elements.btnPlayAgain) : this.elements.btnPlayAgain) 
                : null;
            if (playAgainBtn) {
                playAgainBtn.disabled = !!isLoading;
                if (isLoading && triggerSource === "play-again") {
                    playAgainBtn.classList.add("is-loading");
                    playAgainBtn.innerHTML = '<span class="btn-spinner-sm" aria-hidden="true"></span><span class="btn-text">Starting...</span>';
                } else if (!isLoading) {
                    playAgainBtn.classList.remove("is-loading");
                    playAgainBtn.innerHTML = '<span id="btn-play-again" class="btn-text">Play Again</span>';
                }
            }
        },

        /**
         * Initiate game creation via POST /game/start
         * @param {"start"|"play-again"} [triggerSource="start"]
         */
        async startGame(triggerSource = "start") {
            if (this.isStartingGame) return;
            if (this.elements.stateError) {
                this.elements.stateError.classList.add("is-hidden");
            }
            this.clearCompletionFeedback();
            this.setStartButtonLoading(true, triggerSource);

            try {
                const response = await fetch("/game/start", {
                    method: "POST",
                    headers: {
                        "Accept": "application/json"
                    },
                    credentials: "same-origin"
                });

                await this.handleStartGameResponse(response, triggerSource);
            } catch (err) {
                this.handleStartGameError(err, triggerSource);
            }
        },

        /**
         * Process response from POST /game/start
         * @param {Response} response
         * @param {"start"|"play-again"} [triggerSource="start"]
         */
        async handleStartGameResponse(response, triggerSource = "start") {
            if (response.status === 201) {
                try {
                    const data = await response.json();
                    const newGameId = data.game_id || data.id;
                    if (newGameId != null) {
                        window.location.assign(`/game?game_id=${encodeURIComponent(newGameId)}`);
                        return;
                    }
                } catch (_) {}
                window.location.reload();
                return;
            }

            // Non-201 response: re-enable button and handle states
            this.setStartButtonLoading(false, triggerSource);

            if (response.status === 429) {
                let limitMsg = "You have completed your 3 game sessions for today. Come back tomorrow for new words!";
                try {
                    const data = await response.json();
                    if (data && typeof data.detail === "string" && data.detail.trim()) {
                        limitMsg = data.detail.trim();
                    }
                } catch (_) {}

                if (this.elements.dailyGamesDisplay) {
                    this.elements.dailyGamesDisplay.textContent = "3 / 3";
                }

                if (triggerSource === "play-again") {
                    // Keep completed game state intact and visible
                    this.showCompletionFeedback(limitMsg, "limit");
                    const playAgainBtn = this.elements.btnPlayAgain 
                        ? (this.elements.btnPlayAgain.tagName === "SPAN" ? (this.elements.btnPlayAgain.closest("button") || this.elements.btnPlayAgain) : this.elements.btnPlayAgain) 
                        : null;
                    if (playAgainBtn) {
                        playAgainBtn.disabled = true;
                        playAgainBtn.innerHTML = '<span id="btn-play-again" class="btn-text">Daily Limit Reached</span>';
                    }
                } else {
                    if (this.elements.limitMessage) {
                        this.elements.limitMessage.textContent = limitMsg;
                    }
                    this.showState("limit", { keepReady: true });
                    this.updateStatusBadge("ready", "Limit Reached");
                }
                return;
            }

            if (response.status === 401) {
                if (triggerSource === "play-again") {
                    this.showCompletionFeedback("Your session has expired. Please log in again to start a game.", "error");
                    this.updateStatusBadge("ready", "Login Required");
                } else {
                    this.showError("Your session has expired. Please log in again to start a game.", true);
                    this.updateStatusBadge("ready", "Login Required");
                }
                return;
            }

            let errorMsg = "Unable to start game. Please try again.";
            try {
                const data = await response.json();
                if (data && typeof data.detail === "string" && data.detail.trim()) {
                    errorMsg = data.detail.trim();
                }
            } catch (_) {}

            if (triggerSource === "play-again") {
                this.showCompletionFeedback(errorMsg, "error");
            } else {
                this.showError(errorMsg, true);
                this.updateStatusBadge("ready", "Error");
            }
        },

        /**
         * Handle network or unexpected exceptions during game start
         * @param {Error} error
         * @param {"start"|"play-again"} [triggerSource="start"]
         */
        handleStartGameError(error, triggerSource = "start") {
            this.setStartButtonLoading(false, triggerSource);
            const msg = "Unable to connect to the game server. Please check your network and try again.";
            if (triggerSource === "play-again") {
                this.showCompletionFeedback(msg, "error");
            } else {
                this.showError(msg, true);
                this.updateStatusBadge("ready", "Offline");
            }
        },

        /**
         * Page initialization: check for demo param or game_id
         */
        checkInitialGame() {
            try {
                const urlParams = new URLSearchParams(window.location.search);
                if (urlParams.get("demo") === "1") {
                    this.runDemo();
                    return;
                }

                const gameId = urlParams.get("game_id") || (this.elements.container ? this.elements.container.dataset.gameId : null);
                const isDailyLimitReached = this.elements.container && this.elements.container.dataset.dailyLimitReached === "true";

                if (gameId && gameId.trim() !== "") {
                    // Always load the active/requested game session first
                    this.loadGameState(gameId.trim());
                } else if (isDailyLimitReached) {
                    // No game_id and daily limit reached: display limit state cleanly
                    this.gameState = null;
                    this.resetBoard();
                    this.showState("limit", { keepReady: true });
                    this.updateStatusBadge("ready", "Limit Reached");
                    if (this.elements.btnStartGame) {
                        this.elements.btnStartGame.disabled = true;
                        this.elements.btnStartGame.innerHTML = '<span id="btn-start-game" class="btn-text">Daily Limit Reached</span>';
                    }
                } else {
                    // No game_id: remain in ready state, empty board, make zero API requests
                    this.gameState = null;
                    this.resetBoard();
                    this.showState("ready");
                    this.updateStatusBadge("ready", "Ready");
                }
            } catch (e) {
                this.showState("ready");
            }
        },

        /**
         * Fetch persisted game state from GET /game/{game_id}
         * @param {string|number} gameId
         */
        async loadGameState(gameId) {
            this.resetBoard();
            this.showState("loading");
            try {
                const response = await fetch(`/game/${encodeURIComponent(gameId)}`, {
                    headers: { "Accept": "application/json" }
                });

                if (!response.ok) {
                    let errorMsg = "An error occurred while loading your game session.";
                    if (response.status === 404) {
                        errorMsg = "Game not found. Please check the game ID or start a new game.";
                    } else if (response.status === 403) {
                        errorMsg = "You do not have permission to access this game session.";
                    } else if (response.status === 401) {
                        errorMsg = "Your session has expired. Please log in again.";
                    }
                    try {
                        const data = await response.json();
                        if (data && typeof data.detail === "string") {
                            errorMsg = data.detail;
                        }
                    } catch (_) {}

                    this.showError(errorMsg);
                    this.updateStatusBadge("ready", "Error");
                    return;
                }

                const gameState = await response.json();
                this.renderGameState(gameState);
            } catch (err) {
                this.showError("Unable to load game state. Please check your network connection.");
                this.updateStatusBadge("ready", "Offline");
            }
        },

        /**
         * Display an error message inside the state-error banner
         * @param {string} message
         * @param {boolean} [keepReady=false]
         */
        showError(message, keepReady = false) {
            if (this.elements.errorText) {
                this.elements.errorText.textContent = message || "An error occurred. Please try again.";
            }
            this.showState("error", { keepReady });
        },

        /**
         * Reset all board tiles and clear active row indicators
         */
        resetBoard() {
            this.clearCurrentInput();
            this.clearInputFeedback();
            this.clearCompletionFeedback();
            this.clearRevealTimeouts();
            this.isRevealing = false;
            this.activeRowIndex = -1;
            for (let r = 0; r < 5; r++) {
                for (let c = 0; c < 5; c++) {
                    this.clearTile(r, c);
                }
            }
            if (this.elements.boardRows) {
                this.elements.boardRows.forEach(row => {
                    row.classList.remove("is-active");
                    row.removeAttribute("aria-current");
                });
            }
            // Clear board game-state classes
            if (this.elements.gameBoard) {
                this.elements.gameBoard.classList.remove("board-won", "board-lost");
            }
            if (this.elements.gameStage) {
                this.elements.gameStage.classList.remove("board-won");
            }
            if (this.elements.completionTargetWrapper) {
                this.elements.completionTargetWrapper.classList.add("is-hidden");
            }
            if (this.elements.stateCompleted) {
                this.elements.stateCompleted.classList.remove("is-won", "is-lost");
            }
        },

        /**
         * Mark the current attempt row as active
         * @param {number} rowIndex (0-4, or negative to clear)
         */
        setActiveRow(rowIndex) {
            this.activeRowIndex = rowIndex;
            if (rowIndex < 0 || rowIndex >= 5) {
                this.clearCurrentInput();
            }
            if (!this.elements.boardRows) return;
            this.elements.boardRows.forEach((row, idx) => {
                if (idx === rowIndex) {
                    row.classList.add("is-active");
                    row.setAttribute("aria-current", "step");
                } else {
                    row.classList.remove("is-active");
                    row.removeAttribute("aria-current");
                }
            });
        },

        /**
         * Render a single persisted guess onto the 5x5 board
         * @param {object} guess
         */
        renderGuess(guess) {
            if (!guess || typeof guess.attempt_number !== "number") return;
            const row = guess.attempt_number - 1;
            if (row < 0 || row >= 5) return;

            const evaluations = guess.evaluations || [];
            for (let c = 0; c < 5; c++) {
                const evalItem = evaluations[c];
                if (!evalItem) continue;

                const letter = evalItem.letter || (guess.guess ? guess.guess[c] : "");
                this.setTileLetter(row, c, letter);

                let state = "empty";
                if (evalItem.result === "CORRECT") state = "correct";
                else if (evalItem.result === "PRESENT") state = "present";
                else if (evalItem.result === "ABSENT") state = "absent";

                this.setTileState(row, c, state);
            }
        },

        /**
         * Render complete persisted game state onto the UI
         * @param {object} gameState
         */
        renderGameState(gameState) {
            if (!gameState) return;
            this.gameState = gameState;
            this.resetBoard();

            // 1. Update attempt metadata
            const attempts = typeof gameState.attempts === "number" ? gameState.attempts : 0;
            const maxAttempts = typeof gameState.max_attempts === "number" ? gameState.max_attempts : 5;
            if (this.elements.attemptsDisplay) {
                this.elements.attemptsDisplay.textContent = `${attempts} / ${maxAttempts}`;
            }

            // 2. Render all persisted guesses in order
            const guesses = gameState.guesses || [];
            guesses.forEach(g => this.renderGuess(g));

            // 3. Status handling and active row assignment
            const status = (gameState.status || "IN_PROGRESS").toUpperCase();

            if (status === "WON") {
                this.updateStatusBadge("won", "Won");
                this.setActiveRow(-1);
                this.updateAttemptPips(attempts, maxAttempts, "won");
                this.showCompletedState(gameState, true);
            } else if (status === "LOST") {
                this.updateStatusBadge("lost", "Lost");
                this.setActiveRow(-1);
                this.updateAttemptPips(attempts, maxAttempts, "lost");
                this.showCompletedState(gameState, false);
            } else {
                // IN_PROGRESS
                this.updateStatusBadge("in-progress", "In Progress");
                if (attempts < maxAttempts) {
                    this.setActiveRow(attempts);
                } else {
                    this.setActiveRow(-1);
                }
                this.updateAttemptPips(attempts, maxAttempts, "in-progress");
                // Board entrance animation for fresh active game
                if (this.elements.gameStage && guesses.length === 0) {
                    this.elements.gameStage.classList.add("is-entering");
                    setTimeout(() => { if (this.elements.gameStage) this.elements.gameStage.classList.remove("is-entering"); }, 700);
                }
                this.showState(null); // Hide all banners, board is primary focus
            }
            this.syncCurrentInput();
        },

        /**
         * Display completed game state banner with revealed target word (Phase 4B-4B)
         * @param {object} gameState
         * @param {boolean} isWin
         */
        showCompletedState(gameState, isWin) {
            const panel = this.elements.stateCompleted;
            if (panel) {
                panel.classList.remove("is-won", "is-lost");
                panel.classList.add(isWin ? "is-won" : "is-lost");
            }


            if (this.elements.completionIcon) {
                // WON: clean emerald check (&#10003;), LOST: clean subtle marker (&#10005;)
                this.elements.completionIcon.innerHTML = isWin ? "&#10003;" : "&#10005;";
                this.elements.completionIcon.setAttribute("aria-label", isWin ? "Victory" : "Game Over");
            }

            const attempts = typeof gameState.attempts === "number" ? gameState.attempts : (isWin ? 1 : 5);
            const maxAttempts = typeof gameState.max_attempts === "number" ? gameState.max_attempts : 5;

            if (this.elements.completionTitle) {
                this.elements.completionTitle.textContent = isWin ? "Splendid! Game Won" : "Game Over";
            }

            if (this.elements.completionMessage) {
                if (gameState.message) {
                    this.elements.completionMessage.textContent = gameState.message;
                } else if (isWin) {
                    const winPhrases = {
                        1: "Genius! Solved on the very first try!",
                        2: "Magnificent! Outstanding deduction!",
                        3: "Impressive! Excellent word mastery!",
                        4: "Splendid! Well played!",
                        5: "Phew! Solved in the nick of time!"
                    };
                    this.elements.completionMessage.textContent = winPhrases[attempts] || "Congratulations! You guessed the word correctly!";
                } else {
                    this.elements.completionMessage.textContent = "Better luck next time! The daily word challenge resets every day.";
                }
            }

            if (this.elements.completionAttempts) {
                this.elements.completionAttempts.textContent = `${attempts} / ${maxAttempts}`;
            }

            if (this.elements.completionTargetWrapper && this.elements.completionTarget) {
                if (gameState.target_word) {
                    this.elements.completionTarget.textContent = gameState.target_word;
                    this.elements.completionTargetWrapper.classList.remove("is-hidden");
                } else {
                    this.elements.completionTargetWrapper.classList.add("is-hidden");
                }
            }

            this.clearInputFeedback();
            this.clearCompletionFeedback();

            // Re-enable Play Again button if not currently starting a game
            const playAgainBtn = this.elements.btnPlayAgain 
                ? (this.elements.btnPlayAgain.tagName === "SPAN" ? (this.elements.btnPlayAgain.closest("button") || this.elements.btnPlayAgain) : this.elements.btnPlayAgain) 
                : null;
            if (playAgainBtn && !this.isStartingGame) {
                playAgainBtn.disabled = false;
                playAgainBtn.classList.remove("is-loading");
                playAgainBtn.innerHTML = '<span id="btn-play-again" class="btn-text">Play Again</span>';
            }

            this.showState("completed");

            // Board ambient glow treatment (win = emerald, loss = cool dim)
            if (this.elements.gameBoard) {
                this.elements.gameBoard.classList.remove("board-won", "board-lost");
                this.elements.gameBoard.classList.add(isWin ? "board-won" : "board-lost");
            }
            if (this.elements.gameStage) {
                this.elements.gameStage.classList.remove("board-won");
                if (isWin) { this.elements.gameStage.classList.add("board-won"); }
            }

            // Keyboard accessibility: focus Play Again button if enabled, or fallback to completion panel
            if (playAgainBtn && !playAgainBtn.disabled && typeof playAgainBtn.focus === "function") {
                try {
                    playAgainBtn.focus({ preventScroll: true });
                } catch (_) {}
            } else if (this.elements.stateCompleted && typeof this.elements.stateCompleted.focus === "function") {
                try {
                    this.elements.stateCompleted.focus({ preventScroll: true });
                } catch (_) {}
            }
        },

        /**
         * Safe demonstration helper showing all states when ?demo=1 is present
         */
        runDemo() {
            // Row 0: Filled typed state (unsubmitted)
            ['C', 'R', 'A', 'N', 'E'].forEach((ch, c) => {
                this.setTileLetter(0, c, ch);
            });

            // Row 1: Correct evaluation state (emerald green)
            ['P', 'L', 'A', 'N', 'T'].forEach((ch, c) => {
                this.setTileLetter(1, c, ch);
                this.setTileState(1, c, 'correct');
            });

            // Row 2: Present evaluation state (warm amber)
            ['W', 'A', 'T', 'E', 'R'].forEach((ch, c) => {
                this.setTileLetter(2, c, ch);
                this.setTileState(2, c, 'present');
            });

            // Row 3: Absent evaluation state (muted slate)
            ['G', 'H', 'O', 'S', 'T'].forEach((ch, c) => {
                this.setTileLetter(3, c, ch);
                this.setTileState(3, c, 'absent');
            });

            // Row 4: Mixed Wordle evaluation row
            const mixed = [
                { ch: 'B', st: 'correct' },
                { ch: 'E', st: 'present' },
                { ch: 'A', st: 'absent' },
                { ch: 'C', st: 'correct' },
                { ch: 'H', st: 'absent' },
            ];
            mixed.forEach((item, c) => {
                this.setTileLetter(4, c, item.ch);
                this.setTileState(4, c, item.st);
            });
        },

        /**
         * Foundational UI state helper for toggling state panels
         * @param {"ready"|"completed"|"limit"|"loading"|"error"|null} stateName 
         * @param {object} [options={}]
         */
        showState(stateName, options = {}) {
            const panels = [
                this.elements.stateReady,
                this.elements.stateCompleted,
                this.elements.stateLimit,
                this.elements.stateLoading,
                this.elements.stateError
            ];

            panels.forEach(panel => {
                if (panel) {
                    panel.classList.add("is-hidden");
                }
            });

            switch (stateName) {
                case "ready":
                    if (this.elements.stateReady) this.elements.stateReady.classList.remove("is-hidden");
                    break;
                case "completed":
                    if (this.elements.stateCompleted) this.elements.stateCompleted.classList.remove("is-hidden");
                    break;
                case "limit":
                    if (this.elements.stateLimit) this.elements.stateLimit.classList.remove("is-hidden");
                    if (options.keepReady !== false && this.elements.stateReady) {
                        this.elements.stateReady.classList.remove("is-hidden");
                    }
                    break;
                case "loading":
                    if (this.elements.stateLoading) this.elements.stateLoading.classList.remove("is-hidden");
                    break;
                case "error":
                    if (this.elements.stateError) this.elements.stateError.classList.remove("is-hidden");
                    if (options.keepReady && this.elements.stateReady) {
                        this.elements.stateReady.classList.remove("is-hidden");
                    }
                    break;
            }
        },

        /**
         * Update status badge text and styling
         * @param {"ready"|"in-progress"|"won"|"lost"} status 
         * @param {string} [label] 
         */
        updateStatusBadge(status, label) {
            if (!this.elements.statusBadge) return;
            const badge = this.elements.statusBadge;
            badge.className = "status-badge";
            if (status === "in-progress") {
                badge.classList.add("in-progress");
                badge.textContent = label || "In Progress";
            } else if (status === "won") {
                badge.classList.add("won");
                badge.textContent = label || "Won";
            } else if (status === "lost") {
                badge.classList.add("lost");
                badge.textContent = label || "Lost";
            } else {
                badge.textContent = label || "Ready";
            }
        },

        /**
         * Update the 5 attempt pip indicators in the HUD
         * @param {number} attempts — guesses used so far
         * @param {number} maxAttempts — always 5
         * @param {"in-progress"|"won"|"lost"|"ready"} status
         */
        updateAttemptPips(attempts, maxAttempts, status = "in-progress") {
            const pips = this.elements.attemptPips;
            if (!pips || pips.length === 0) {
                // Re-query if not cached yet (e.g., late call)
                this.elements.attemptPips = document.querySelectorAll(".attempt-pip");
            }
            const pipEls = this.elements.attemptPips;
            if (!pipEls) return;
            pipEls.forEach((pip, idx) => {
                const pipNum = idx + 1; // pips are 1-indexed via data-pip
                pip.classList.remove("is-done", "is-active", "is-won", "is-lost");
                if (status === "won") {
                    if (pipNum <= attempts) pip.classList.add("is-won");
                } else if (status === "lost") {
                    if (pipNum <= attempts) pip.classList.add("is-lost");
                } else {
                    // in-progress or ready
                    if (pipNum < attempts + 1) pip.classList.add("is-done");
                    else if (pipNum === attempts + 1) pip.classList.add("is-active");
                }
            });
        },

        /**
         * Update the daily segmented meter in the HUD
         * @param {number} gamesUsed — number of games played today
         */
        updateDailySegs(gamesUsed) {
            const segs = document.querySelectorAll(".daily-seg[data-seg]");
            segs.forEach(seg => {
                const segNum = parseInt(seg.dataset.seg, 10);
                if (segNum <= gamesUsed) {
                    seg.classList.add("is-used");
                } else {
                    seg.classList.remove("is-used");
                }
            });
        }
    };

    window.GuessTheWord.GamePage = GamePage;

    // Initialize when DOM is ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => GamePage.init());
    } else {
        GamePage.init();
    }
})();
