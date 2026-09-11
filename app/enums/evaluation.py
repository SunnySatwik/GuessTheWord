import enum


class LetterEvaluation(str, enum.Enum):
    """Wordle-style letter evaluation state."""

    CORRECT = "CORRECT"  # Correct letter and position
    PRESENT = "PRESENT"  # Correct letter, wrong position
    ABSENT = "ABSENT"    # Letter does not occur in remaining target
