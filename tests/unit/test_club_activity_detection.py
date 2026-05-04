from services.club_activity_detection import detect_activity_evidence


def test_detects_score_timer_completion_share():
    evidence = detect_activity_evidence("I played today's round\n00:04:26\nscore 5/6")

    assert evidence.matched is True
    assert "score" in evidence.reason


def test_detects_grid_style_result_block():
    text = "\U0001f7e8\u2b1b\U0001f7e8\u2b1b\u2b1b\n\u2b1b\u2b1b\U0001f7e9\u2b1b\U0001f7e8\n\U0001f7e9\U0001f7e9\U0001f7e9\U0001f7e9\U0001f7e9"

    evidence = detect_activity_evidence(text)

    assert evidence.matched is True
    assert "grid_result" in evidence.reason


def test_detects_first_person_completion_phrase():
    evidence = detect_activity_evidence("I finished today's workout", what_counts="workout")

    assert evidence.matched is True
    assert "completion_phrase" in evidence.reason


def test_rejects_negated_completion_claim():
    evidence = detect_activity_evidence("I didn't finish today")

    assert evidence.matched is False
    assert evidence.reason == "negated"


def test_rejects_ordinary_question():
    evidence = detect_activity_evidence("did you finish today?")

    assert evidence.matched is False
    assert evidence.reason == "question"
