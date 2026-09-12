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

        init() {
            this.cacheElements();
            this.bindEvents();
            this.checkDemoParam();
        },

        cacheElements() {
            this.elements = {
                container: document.querySelector(".game-page-container"),
                attemptsDisplay: document.getElementById("attempts-display"),
                dailyGamesDisplay: document.getElementById("daily-games-display"),
                statusBadge: document.getElementById("game-status-badge"),
                btnStartGame: document.getElementById("btn-start-game"),
                stateReady: document.getElementById("state-ready"),
                stateCompleted: document.getElementById("state-completed"),
                stateLimit: document.getElementById("state-limit"),
                stateLoading: document.getElementById("state-loading"),
                stateError: document.getElementById("state-error"),
                errorText: document.getElementById("error-text"),
                completionTitle: document.getElementById("completion-title"),
                completionMessage: document.getElementById("completion-message"),
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
            // Placeholder interaction bindings for Phase 4B-1 foundation
            // Full game lifecycle and board rendering will attach here in Phase 4B-2
        },

        /**
         * Check for safe verification/demo query parameter (?demo=1)
         */
        checkDemoParam() {
            try {
                const urlParams = new URLSearchParams(window.location.search);
                if (urlParams.get("demo") === "1") {
                    this.runDemo();
                }
            } catch (e) {
                // Ignore query param errors in non-browser environments
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
         * @param {"ready"|"completed"|"limit"|"loading"|"error"} stateName 
         */
        showState(stateName) {
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
                    break;
                case "loading":
                    if (this.elements.stateLoading) this.elements.stateLoading.classList.remove("is-hidden");
                    break;
                case "error":
                    if (this.elements.stateError) this.elements.stateError.classList.remove("is-hidden");
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
