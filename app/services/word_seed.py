from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.word import Word

# Exactly 20 five-letter English words in uppercase as specified
INITIAL_WORDS: list[str] = [
    "APPLE", "BEACH", "BRAIN", "BREAD", "CHAIR",
    "CLOUD", "CRANE", "DANCE", "EARTH", "FLAME",
    "FRUIT", "GHOST", "GRAPE", "HEART", "HOUSE",
    "LIGHT", "MUSIC", "OCEAN", "PLANT", "WATER",
]


def seed_words(db: Session) -> list[Word]:
    """Seed the database with the initial 20 five-letter English words.

    Idempotent: Only inserts words that do not already exist in the database.
    Returns the list of all seeded/existing Word instances.
    """
    # Fetch existing words
    existing_words = set(db.execute(select(Word.word)).scalars().all())

    new_words: list[Word] = []
    for word_str in INITIAL_WORDS:
        clean_word = word_str.strip().upper()
        if clean_word not in existing_words:
            word_obj = Word(word=clean_word)
            db.add(word_obj)
            new_words.append(word_obj)
            existing_words.add(clean_word)

    if new_words:
        db.commit()
        for w in new_words:
            db.refresh(w)

    return list(db.execute(select(Word).order_by(Word.id)).scalars().all())


if __name__ == "__main__":
    db = SessionLocal()
    try:
        words = seed_words(db)
        print(f"Successfully seeded/verified {len(words)} words in database:")
        for idx, w in enumerate(words, start=1):
            print(f"  {idx:2d}. {w.word}")
    finally:
        db.close()
