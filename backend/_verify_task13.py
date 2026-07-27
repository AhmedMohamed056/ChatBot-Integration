import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prompts import build_visitor_system_prompt

p = build_visitor_system_prompt()

supervisor_markers = [
    "تعليمات التعامل مع مشرفي الحملات",
    "هل لديكم إعلان",
    "هل أعتمد هذا الإعلان",
    "هل ترغب في اعتماد",
    "تفضل، أرسل الإعلان",
    "توثيق العملية",
    "قواعد الدمج",
    "الرسائل المتكررة",
]

found = [m for m in supervisor_markers if m in p]

visitor_markers = [
    "معين الزائرين",
    "تعليمات التعامل مع الزائر",
    "القاعدة الأولى",
    "المراجعة الذاتية",
    "كن مرشدًا لا مجرد مجيب",
]

missing_visitor = [m for m in visitor_markers if m not in p]

out = []
out.append("LENGTH=" + str(len(p)))
out.append("SUPERVISOR_FOUND=" + str(found))
out.append("VISITOR_MISSING=" + str(missing_visitor))
out.append("STARTS_WITH=" + repr(p[:60]))
out.append("RESULT=" + ("PASS" if not found and not missing_visitor else "FAIL"))

Path("_verify_task13.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))