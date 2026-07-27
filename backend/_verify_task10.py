"""Verification script for Task 10 - Visitor Question Logging.

Runs the migration, exercises the service, and checks the repository.
Writes results to _verify_task10_out.txt.
"""

import sys
import traceback
from pathlib import Path

out = Path(__file__).resolve().parent / "_verify_task10_out.txt"
buf = []


def log(msg=""):
    print(msg)
    buf.append(str(msg))


try:
    # 1) Syntax check main.py
    import ast

    ast.parse(Path("main.py").read_text(encoding="utf-8"))
    log("[OK] main.py syntax valid")

    # 2) Run the DB migration
    from db import init_db, get_schema_version
    from db.base import get_session

    init_db()
    log(f"[OK] init_db() done. schema_version={get_schema_version()}")

    # 3) Verify the visitor_questions table schema
    from sqlalchemy import inspect
    from db.base import engine

    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("visitor_questions")}
    expected = {
        "id",
        "phone_number",
        "visitor_name",
        "campaign_name",
        "question",
        "detected_language",
        "message_timestamp",
        "created_at",
    }
    log(f"[INFO] visitor_questions columns: {sorted(cols)}")
    assert cols == expected, f"Schema mismatch. extra={cols-expected} missing={expected-cols}"
    log("[OK] visitor_questions schema matches Task 10 spec exactly")

    indexes = {idx["name"] for idx in inspector.get_indexes("visitor_questions")}
    log(f"[INFO] indexes: {sorted(indexes)}")

    # 4) Test the service
    from visitor_question_service import log_visitor_question, detect_language

    # Language detection
    assert detect_language("امتى حملة الشباب؟") == "ar"
    assert detect_language("When is the campaign?") == "en"
    assert detect_language("12345 ???") == "unknown"
    log("[OK] detect_language heuristic works (ar/en/unknown)")

    # Log an Arabic question with a phone
    r1 = log_visitor_question("01012345678", "امتى حملة الشباب؟")
    assert r1["ok"] is True
    log(f"[OK] logged arabic question id={r1['id']}")

    # Log an English question without phone
    r2 = log_visitor_question(None, "When does the campaign start?")
    assert r2["ok"] is True
    log(f"[OK] logged english question (no phone) id={r2['id']}")

    # Empty question must raise
    try:
        log_visitor_question("01012345678", "   ")
        log("[FAIL] empty question did NOT raise")
    except ValueError:
        log("[OK] empty question raised ValueError")

    # 5) Test the repository list/count
    from db.repositories.visitor_question_repository import VisitorQuestionRepository

    with get_session() as session:
        repo = VisitorQuestionRepository(session)
        total = repo.count_questions()
        latest = repo.list_questions(limit=10)
        log(f"[OK] count_questions={total}, list_questions returned {len(latest)}")
        first = repo.to_dict(latest[0])
        log(f"[INFO] latest question dict keys: {sorted(first.keys())}")

    # 6) Confirm endpoints exist in main.py
    main_src = Path("main.py").read_text(encoding="utf-8")
    assert '"/admin/questions/log"' in main_src, "POST endpoint missing"
    assert '"/admin/questions"' in main_src, "GET endpoint missing"
    assert "VisitorQuestionLogRequest" in main_src, "request model missing"
    log("[OK] both API endpoints present in main.py")

    log("")
    log("=== ALL VERIFICATIONS PASSED ===")
except Exception as e:
    log("")
    log("=== VERIFICATION FAILED ===")
    log(traceback.format_exc())

out.write_text("\n".join(buf), encoding="utf-8")