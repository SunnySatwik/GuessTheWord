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
                controlsPlaceholder: document.getElementById("controls-placeholder"),
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
            tile.textContent = "";
            tile.classList.remove("is-filled", "is-correct", "is-present", "is-absent", "is-revealing");
            tile.removeAttribute("data-state");
            tile.setAttribute("aria-label", `Row ${row + 1}, Letter ${col + 1}`);
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

            setTimeout(() => {
                tile.classList.add("is-revealing");
                setTimeout(() => {
                    tile.classList.remove("is-filled");
                    tile.classList.add(`is-${state}`);
                    tile.setAttribute("data-state", state);
                }, 225);

                setTimeout(() => {
                    tile.classList.remove("is-revealing");
                }, 450);
            }, delayMs);
        },

        bindEvents() {
            if (this.elements.btnStartGame) {
                this.elements.btnStartGame.addEventListener("click", (e) => {
                    e.preventDefault();
                    this.startGame();
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
                !this.isStartingGame
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
            if (this.currentInput.length === 0) return;

            const colToRemove = this.currentInput.length - 1;
            this.currentInput = this.currentInput.slice(0, -1);
            this.clearTile(this.activeRowIndex, colToRemove);
        },

        /**
         * Recognize Enter key action without submission (Phase 4B-3B hook)
         * @returns {object|null}
         */
        handleSubmitRequest() {
            if (!this.canAcceptInput()) return null;
            if (this.currentInput.length < 5) {
                return { submitted: false, reason: "Word must be 5 letters." };
            }
            return {
                submitted: false,
                guess: this.currentInput,
                reason: "Submission not implemented yet."
            };
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
         * Set the start button loading and disabled state
         * @param {boolean} isLoading
         */
        setStartButtonLoading(isLoading) {
            const btn = this.elements.btnStartGame;
            if (!btn) return;
            this.isStartingGame = !!isLoading;
            btn.disabled = !!isLoading;

            if (isLoading) {
                btn.classList.add("is-loading");
                btn.innerHTML = '<span class="btn-spinner-sm" aria-hidden="true"></span><span class="btn-text">Starting...</span>';
            } else {
                btn.classList.remove("is-loading");
                btn.innerHTML = '<span id="btn-start-game" class="btn-text">Start Game</span>';
            }
        },

        /**
         * Initiate game creation via POST /game/start
         */
        async startGame() {
            if (this.isStartingGame) return;
            this.setStartButtonLoading(true);

            try {
                const response = await fetch("/game/start", {
                    method: "POST",
                    headers: {
                        "Accept": "application/json"
                    },
                    credentials: "same-origin"
                });

                await this.handleStartGameResponse(response);
            } catch (err) {
                this.handleStartGameError(err);
            }
        },

        /**
         * Process response from POST /game/start
         * @param {Response} response
         */
        async handleStartGameResponse(response) {
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
            this.setStartButtonLoading(false);

            if (response.status === 429) {
                let limitMsg = "You have completed your 3 game sessions for today. Come back tomorrow for new words!";
                try {
                    const data = await response.json();
                    if (data && typeof data.detail === "string") {
                        limitMsg = data.detail;
                    }
                } catch (_) {}

                if (this.elements.limitMessage) {
                    this.elements.limitMessage.textContent = limitMsg;
                }
                this.showState("limit", { keepReady: true });
                this.updateStatusBadge("ready", "Limit Reached");
                return;
            }

            if (response.status === 401) {
                this.showError("Your session has expired. Please log in again to start a game.", true);
                this.updateStatusBadge("ready", "Login Required");
                return;
            }

            let errorMsg = "Unable to start game. Please try again.";
            try {
                const data = await response.json();
                if (data && typeof data.detail === "string") {
                    errorMsg = data.detail;
                }
            } catch (_) {}

            this.showError(errorMsg, true);
            this.updateStatusBadge("ready", "Error");
        },

        /**
         * Handle network or unexpected exceptions during game start
         * @param {Error} error
         */
        handleStartGameError(error) {
            this.setStartButtonLoading(false);
            this.showError("Unable to connect to the game server. Please check your network and try again.", true);
            this.updateStatusBadge("ready", "Offline");
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
                if (gameId && gameId.trim() !== "") {
                    this.loadGameState(gameId.trim());
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
            if (this.elements.completionTargetWrapper) {
                this.elements.completionTargetWrapper.classList.add("is-hidden");
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
                this.showCompletedState(gameState, true);
            } else if (status === "LOST") {
                this.updateStatusBadge("lost", "Lost");
                this.setActiveRow(-1);
                this.showCompletedState(gameState, false);
            } else {
                // IN_PROGRESS
                this.updateStatusBadge("in-progress", "In Progress");
                if (attempts < maxAttempts) {
                    this.setActiveRow(attempts);
                } else {
                    this.setActiveRow(-1);
                }
                this.showState(null); // Hide all banners, board is primary focus
            }
            this.syncCurrentInput();
        },

        /**
         * Display completed game state banner with revealed target word
         * @param {object} gameState
         * @param {boolean} isWin
         */
        showCompletedState(gameState, isWin) {
            if (this.elements.completionTitle) {
                this.elements.completionTitle.textContent = isWin ? "Splendid! Game Won" : "Game Over";
            }
            if (this.elements.completionMessage) {
                this.elements.completionMessage.textContent = gameState.message || (isWin ? "Congratulations! You guessed the word correctly!" : "You ran out of attempts.");
            }
            if (this.elements.completionTargetWrapper && this.elements.completionTarget) {
                if (gameState.target_word) {
                    this.elements.completionTarget.textContent = gameState.target_word;
                    this.elements.completionTargetWrapper.classList.remove("is-hidden");
                } else {
                    this.elements.completionTargetWrapper.classList.add("is-hidden");
                }
            }
            this.showState("completed");
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
