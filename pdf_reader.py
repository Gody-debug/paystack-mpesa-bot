"""Extract and normalise Kenyan mobile numbers from a PDF."""
import re
import fitz  # PyMuPDF

# Matches 07xx / 01xx / +2547xx / 2541xx, allowing spaces or dashes inside.
PHONE_RE = re.compile(r"(?<!\d)(?:\+?254|0)[\s\-]?[17](?:[\s\-]?\d){8}(?!\d)")


def normalise(raw: str) -> str | None:
    """Return +254XXXXXXXXX or None if invalid."""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("254"):
        national = digits[3:]
    elif digits.startswith("0"):
        national = digits[1:]
    else:
        return None
    if len(national) != 9 or national[0] not in "17":
        return None
    return "+254" + national


def extract_numbers(pdf_bytes: bytes) -> list[str]:
    """Return unique, valid numbers in the order they first appear."""
    seen: dict[str, None] = {}
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            for line in page.get_text().splitlines():
                for match in PHONE_RE.finditer(line):
                    num = normalise(match.group())
                    if num:
                        seen.setdefault(num, None)
    return list(seen)
