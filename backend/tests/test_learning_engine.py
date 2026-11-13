from datetime import date

from learning_engine import (
    build_daily_plan, generate_flashcards, generate_quiz, next_flashcard_review, parse_term_definition_notes,
)


def test_term_definition_parser_ignores_blank_and_duplicate_lines():
    pairs = parse_term_definition_notes("\nPhotosynthesis: Plants convert light into chemical energy.\nphotosynthesis: duplicate item\nMitosis: Cell division that makes two daughter cells.\n")
    assert len(pairs) == 2
    assert pairs[0]["front"] == "Photosynthesis"


def test_offline_quiz_generator_uses_supplied_notes_only(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    questions, source = generate_quiz(
        "Biology",
        "Osmosis: Water moves across a selectively permeable membrane.\n"
        "Mitosis: One cell divides into two genetically identical cells.\n"
        "Chloroplast: Organelle where photosynthesis occurs.",
        3, "standard",
    )
    assert len(questions) == 3
    assert all(len(item["options"]) == 4 and item["answer_index"] in range(4) for item in questions)
    assert "AURA notes parser" in source


def test_offline_flashcards_require_explicit_term_definition_pairs(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cards, _ = generate_flashcards("Physics", "Velocity: Rate of change of displacement.", 10)
    assert cards == [{"front": "Velocity", "back": "Rate of change of displacement."}]


def test_spaced_repetition_intervals_change_by_rating():
    class Card:
        repetitions = 0
        interval_days = 1

    reps, interval, due = next_flashcard_review(Card(), "good", date(2026, 11, 12))
    assert (reps, interval, due.isoformat()) == (1, 1, "2026-11-13")

    class MatureCard:
        repetitions = 2
        interval_days = 3

    reps, interval, _ = next_flashcard_review(MatureCard(), "easy", date(2026, 11, 12))
    assert reps == 3 and interval == 8


def test_daily_plan_avoids_existing_calendar_events():
    target = date(2026, 11, 20)
    plan = build_daily_plan(
        [{"id": 1, "name": "Databases", "exam_date": "2026-11-25", "difficulty": 4, "target_hours": 12, "completed_hours": 2}],
        [{"start_time": "2026-11-20T09:00", "end_time": "2026-11-20T10:00"}],
        2.0, "09:00-13:00", target, [],
    )
    assert plan["items"]
    assert plan["items"][0]["start_time"] == "2026-11-20T10:00"



def test_daily_plan_can_prioritize_project_tasks_with_approaching_due_dates():
    target = date(2026, 11, 20)
    plan = build_daily_plan(
        [{"id": 1, "name": "Biology", "exam_date": "2027-02-01", "difficulty": 2, "target_hours": 2, "completed_hours": 0}],
        [], 1.0, "09:00-12:00", target, [],
        [{"id": 8, "project_id": 3, "title": "Submit literature review", "project_title": "Thesis", "due_date": "2026-11-20"}],
    )
    assert plan["items"]
    assert plan["items"][0]["project_id"] == 3
    assert plan["items"][0]["subject_id"] is None
