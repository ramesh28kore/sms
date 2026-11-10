"""
SMS segment estimator.
Estimates GSM-7 and Unicode multipart segment counts.
Labeled as estimates; actual carrier segmentation may vary.
Handles GSM extension characters correctly.

References:
- GSM 03.38: 7-bit encoding, 160 chars per segment, 153 per multipart
- Unicode/UCS-2: 70 chars per single segment, 67 per multipart
- GSM extension characters count as 2 GSM-7 units
"""

# GSM 7-bit basic character set
GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./"
    "0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "ÄÖÑܧ¿abcdefghijklmnopqrstuvwxyz"
    "äöñüà"
)

# GSM 7-bit extension characters (each costs 2 GSM-7 units)
GSM7_EXTENDED = set("^{}\\[~]|€")


def estimate_segments(text: str, is_unicode_device: bool = True) -> dict:
    """
    Estimate SMS segments for a message.

    Returns:
        {
            "encoding": "gsm7" | "unicode",
            "char_units": int,       # Characters in the encoding
            "segments": int,         # Estimated segment count
            "is_estimate": True,     # Always True; actual may vary
            "note": str,             # Explanation of limitations
        }
    """
    if not text:
        return {
            "encoding": "gsm7",
            "char_units": 0,
            "segments": 0,
            "is_estimate": True,
            "note": "Empty message.",
        }

    # Determine encoding
    gsm7_units = 0
    can_use_gsm7 = True

    for char in text:
        if char in GSM7_BASIC:
            gsm7_units += 1
        elif char in GSM7_EXTENDED:
            gsm7_units += 2  # Extension: escape + char
        else:
            can_use_gsm7 = False
            break

    if can_use_gsm7:
        # GSM-7
        if gsm7_units <= 160:
            segments = 1
        else:
            # Multipart: 153 GSM-7 units per segment
            segments = -(-gsm7_units // 153)  # Ceiling division
        return {
            "encoding": "gsm7",
            "char_units": gsm7_units,
            "segments": segments,
            "is_estimate": True,
            "note": (
                "GSM-7 encoding estimated. Extension characters count as 2 units. "
                "Actual segmentation depends on carrier and device implementation."
            ),
        }
    else:
        # Unicode (UCS-2 / UTF-16)
        char_count = len(text)
        if char_count <= 70:
            segments = 1
        else:
            # Multipart: 67 Unicode characters per segment
            segments = -(-char_count // 67)
        return {
            "encoding": "unicode",
            "char_units": char_count,
            "segments": segments,
            "is_estimate": True,
            "note": (
                "Unicode encoding required. Telugu and other non-GSM-7 characters use Unicode. "
                "Confirm modem/device Unicode support before live use. "
                "Actual segments depend on carrier and device."
            ),
        }

