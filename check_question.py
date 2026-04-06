#!/usr/bin/env python3
"""check_question.py — Determine whether a Signal message is a question.

Usage::

    python check_question.py "Is this a question?"

Exits with code 0 and prints ``true`` or ``false`` to stdout.
"""

import logging
import re
import sys

logger = logging.getLogger(__name__)

# Words that typically begin an interrogative sentence
_QUESTION_WORDS = frozenset({
    "who", "what", "where", "when", "why", "how",
    "which", "whose", "whom",
    "can", "could", "would", "should", "will", "shall",
    "is", "are", "was", "were",
    "do", "does", "did",
    "has", "have", "had",
    "am",
})


def is_question_heuristic(text: str) -> bool:
    """Return True if *text* appears to be a question.

    Detection strategy (in order):
    1. Contains a literal ``?`` character.
    2. Starts with a recognised interrogative or auxiliary word.

    Args:
        text: The raw message string to evaluate.

    Returns:
        ``True`` when the text is identified as a question, ``False`` otherwise.
    """
    text = text.strip()
    if not text:
        logger.debug("Empty text — not a question")
        return False

    if "?" in text:
        logger.debug("Question mark found — classified as question")
        return True

    first_word = re.split(r"\s+", text.lower(), maxsplit=1)[0].rstrip(",:;")
    if first_word in _QUESTION_WORDS:
        logger.debug("Question word '%s' found at start — classified as question", first_word)
        return True

    logger.debug("No question indicators found — not a question")
    return False


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if len(sys.argv) < 2:
        logger.error("Usage: check_question.py <message>")
        sys.exit(1)

    text = sys.argv[1]
    result = is_question_heuristic(text)
    print("true" if result else "false")


if __name__ == "__main__":
    main()
