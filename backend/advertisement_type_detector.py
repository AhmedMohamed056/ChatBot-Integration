"""Advertisement Type Detector.

This module provides a completely standalone, keyword-based detector for
advertisement types. It has NO dependencies on:

- Databases
- AI / Gemini
- Prompt Builder
- Conversation State Manager
- Supervisor Flow

It exposes:

- `AdvertisementType`: an enum with the values NEW, UPDATE, ADD, CANCEL,
  UNKNOWN.
- `detect_advertisement_type(text)`: returns ONLY the detected
  `AdvertisementType` enum value. It never returns replies or changes
  any state.

Detection is purely keyword based. The first matching category (in a
fixed priority order) wins. If no keyword matches, `UNKNOWN` is
returned.
"""

from enum import Enum


class AdvertisementType(Enum):
    """Possible advertisement types detected from text."""

    NEW = "NEW"
    UPDATE = "UPDATE"
    ADD = "ADD"
    CANCEL = "CANCEL"
    UNKNOWN = "UNKNOWN"


# ----------------------------------------------------------------------
# Keyword tables
#
# Order matters: the detector checks categories in the order listed
# below and returns the first match. CANCEL is checked before ADD/NEW
# so that phrases like "تم إلغاء إضافة..." are classified as CANCEL.
# ----------------------------------------------------------------------
_KEYWORDS = (
    (AdvertisementType.CANCEL, (
        "إلغاء",
        "ألغ",
        "الغ",      # matches "الغاء" / "الغي" without the hamza variants
        "حذف",
        "تم إلغاء",
        "لم يعد",
    )),
    (AdvertisementType.UPDATE, (
        "تعديل",
        "تم تعديل",
        "تغيير",
        "تحديث",
    )),
    # ADD is checked before NEW so that phrases like "إضافة نشاط جديد"
    # are classified as ADD (the primary action) rather than NEW.
    (AdvertisementType.ADD, (
        "إضافة",
        "أضف",
        "اضف",
        "كذلك",
        "أيضا",
        "أيضاً",
        "ايضا",
        "بالإضافة",
        "بالاضافة",
    )),
    (AdvertisementType.NEW, (
        "إعلان جديد",
        "إعلان",
        "البرنامج الجديد",
        "جديد",
        "تم اعتماد برنامج جديد",
    )),
)


def detect_advertisement_type(text):
    """Detect the advertisement type from the given text.

    Performs simple, case-insensitive (Arabic-normalized) keyword
    matching. Returns ONLY an `AdvertisementType` enum value.

    Args:
        text: The input text (str). If None or empty, returns UNKNOWN.

    Returns:
        AdvertisementType: one of NEW, UPDATE, ADD, CANCEL, UNKNOWN.
    """
    if not text:
        return AdvertisementType.UNKNOWN

    raw = str(text)

    # Normalize common Arabic variants so keyword matching is robust:
    #  - strip diacritics (tashkeel)
    #  - unify alef variants
    #  - unify ya/alef-maqsura
    #  - unify ta-marbuta
    #  - collapse spaces
    normalized = _normalize_arabic(raw)

    for adv_type, keywords in _KEYWORDS:
        for kw in keywords:
            if _normalize_arabic(kw) in normalized:
                return adv_type

    return AdvertisementType.UNKNOWN


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------
_ARABIC_DIACRITICS = set(
    "\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u0653\u0654\u0655"
)


def _normalize_arabic(text):
    """Normalize an Arabic string for keyword matching.

    - Removes diacritics (tashkeel).
    - Unifies alef variants (أ إ آ ٱ -> ا).
    - Unifies ya and alef-maqsura (ى -> ي).
    - Unifies ta-marbuta (ة -> ه).
    - Lowercases Latin characters.
    - Collapses whitespace.
    """
    out = []
    for ch in text:
        if ch in _ARABIC_DIACRITICS:
            continue
        if ch in ("\u0623", "\u0625", "\u0622", "\u0671"):  # alef variants
            out.append("\u0627")
        elif ch == "\u0649":  # alef maqsura -> ya
            out.append("\u064A")
        elif ch == "\u0629":  # ta marbuta -> ha
            out.append("\u0647")
        else:
            out.append(ch)

    result = "".join(out)
    result = result.lower()

    # Collapse whitespace runs into single spaces and trim.
    result = " ".join(result.split())
    return result


# ----------------------------------------------------------------------
# Standalone demo / smoke test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    samples = [
        ("إعلان جديد عن الرحلة", AdvertisementType.NEW),
        ("إعلان هام", AdvertisementType.NEW),
        ("البرنامج الجديد", AdvertisementType.NEW),
        ("تم اعتماد برنامج جديد", AdvertisementType.NEW),
        ("تم تعديل موعد التجمع", AdvertisementType.UPDATE),
        ("تعديل الوقت", AdvertisementType.UPDATE),
        ("تغيير المكان", AdvertisementType.UPDATE),
        ("تحديث الجدول", AdvertisementType.UPDATE),
        ("إضافة نشاط جديد", AdvertisementType.ADD),
        ("أضف هذا", AdvertisementType.ADD),
        ("كذلك تم", AdvertisementType.ADD),
        ("أيضاً", AdvertisementType.ADD),
        ("بالإضافة إلى ذلك", AdvertisementType.ADD),
        ("إلغاء الرحلة", AdvertisementType.CANCEL),
        ("ألغ الموعد", AdvertisementType.CANCEL),
        ("حذف الإعلان", AdvertisementType.CANCEL),
        ("تم إلغاء الاجتماع", AdvertisementType.CANCEL),
        ("لم يعد متاحا", AdvertisementType.CANCEL),
        ("مرحبا كيف حالك", AdvertisementType.UNKNOWN),
        ("", AdvertisementType.UNKNOWN),
    ]

    all_ok = True
    for text, expected in samples:
        got = detect_advertisement_type(text)
        ok = got == expected
        all_ok = all_ok and ok
        print(
            ("OK  " if ok else "FAIL"),
            repr(text),
            "->",
            got.value,
            "(expected",
            expected.value + ")",
        )

    print("\nALL PASSED" if all_ok else "\nSOME FAILED")