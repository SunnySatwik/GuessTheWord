"""Domain exceptions for the Guess the Word application."""


class GameError(Exception):
    """Base domain exception for game operations."""

    def __init__(self, message: str = "A game error occurred."):
        self.message = message
        super().__init__(self.message)


class DailyLimitReachedError(GameError):
    """Raised when a player exceeds their daily game limit (3 games per calendar day)."""

    def __init__(self, message: str = "Daily limit reached. You can only play 3 games per calendar day."):
        super().__init__(message)


class GameNotFoundError(GameError):
    """Raised when the requested game does not exist."""

    def __init__(self, message: str = "Game not found."):
        super().__init__(message)


class UnauthorizedGameAccessError(GameError):
    """Raised when a player attempts to access another player's game."""

    def __init__(self, message: str = "You do not have access to this game."):
        super().__init__(message)


class GameFinishedError(GameError):
    """Raised when an action is performed on an already completed game or maximum attempts reached."""

    def __init__(self, message: str = "This game is already finished."):
        super().__init__(message)


class InvalidGuessError(GameError):
    """Raised when an invalid guess is submitted (e.g. not 5 letters, non-alphabetic)."""

    def __init__(self, message: str = "Guess must be exactly 5 alphabetic letters."):
        super().__init__(message)
