"""Credits: what a learning action is worth.

The problem this solves: a promise measured in hours ("Learn French, 3h/week")
registered nothing for a quiz, because a quiz is over in under a minute. Real
elapsed time is the honest number but a useless signal — a measured 52-second
quiz is 0.49% of a weekly target, which displays as 0%. Doing your daily quiz
every day for a week left the bar reading zero.

So effort is credited per **item answered**, not per second elapsed. One
question answered, or one card rated, is worth one credit-minute regardless of
how fast you were. This deliberately does not track wall-clock time:

  - It cannot be farmed by leaving a tab open.
  - Answering carefully and answering quickly are worth the same, which is what
    you want from a recall exercise.
  - It is predictable — you can see what a session is worth before starting it.

Credits are stored in their own column. `actions.time_spent_hours` keeps the
real measured duration, so the honest record of time spent survives next to the
credited value and neither has to lie about the other.

Every rate lives here. Changing the feel of the system should be a one-line
edit in this file, not a hunt through repositories.
"""

# One answered item is worth one minute of credit.
CREDIT_MINUTES_PER_QUIZ_QUESTION = 1.0
CREDIT_MINUTES_PER_FLASHCARD = 1.0

# What it takes for a day to count as done. Below this a session still earns its
# credits — they simply do not tick the day over. Five is deliberately low: the
# streak should reward turning up, and the accumulating total rewards depth.
DAILY_CHECKIN_THRESHOLD_MINUTES = 5.0


def quiz_credits(questions_answered: int) -> float:
    """Credit for a completed quiz deck."""
    return max(0, int(questions_answered)) * CREDIT_MINUTES_PER_QUIZ_QUESTION


def flashcard_credits(cards_rated: int) -> float:
    """Credit for a spaced-repetition review session."""
    return max(0, int(cards_rated)) * CREDIT_MINUTES_PER_FLASHCARD


def counts_as_checkin(credit_minutes: float) -> bool:
    """Whether a day's accumulated credit is enough to call the day done."""
    return float(credit_minutes or 0.0) >= DAILY_CHECKIN_THRESHOLD_MINUTES


def credits_to_hours(credit_minutes: float) -> float:
    """Credits are minutes, so a promise measured in hours can consume them."""
    return float(credit_minutes or 0.0) / 60.0
