"""Intent parser — keyword/pattern matching for free-form OM input."""

import re

INTENTS = {
    "create_plan": [
        r"(?:build|create|make|start|new|generate)\b.*\b(?:plan|shift)",
        r"(?:day|night)\s*(?:shift|plan)",
        r"let'?s\s+plan",
    ],
    "modify_plan": [
        r"(?:change|update|modify|adjust|set)\b.*\b(?:volume|hc|headcount|rate|uph|show\s*rate|duration)",
        r"what\s+if\b",
    ],
    "apply_override": [
        r"(?:override|set|change)\b.*\b(?:to|=)\s*\d+",
        r"(?:lock|unlock)\b",
    ],
    "ask_question": [
        r"(?:why|how|what|explain|tell\s+me)\b",
        r"(?:indirect|support)\s*(?:%|percent|budget)",
        r"(?:lp\s*rate|support\s*rate)",
    ],
    "lock_plan": [
        r"\block\b(?:\s+(?:it|plan|this))?$",
        r"finalize",
    ],
    "close_artifact": [
        r"\bclose\b",
        r"end\s*of\s*shift",
        r"\beos\b",
    ],
    "export": [
        r"\bexport\b",
        r"\b(?:pdf|csv|slack)\b",
    ],
    "help": [
        r"\bhelp\b",
        r"\bcommands?\b",
    ],
    "show_plan": [
        r"\bshow\b.*\bplan\b",
        r"\bartifact\b",
        r"\bprint\b.*\bplan\b",
    ],
    "enter_actuals": [
        r"\bactual",
        r"\boutcome",
        r"\bresult",
    ],
}


def classify_intent(text: str) -> str:
    text_lower = text.strip().lower()
    for intent, patterns in INTENTS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent
    return "ask_question"  # default to Q&A


def extract_number(text: str) -> float | None:
    m = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    return float(m.group()) if m else None


def extract_role_code(text: str) -> str | None:
    text_upper = text.upper()
    codes = [
        "CRET-RCV", "CRET-SRT", "CRET-NS-SRT", "CRET-BIN", "CRET-NS-BIN",
        "CRET-PICK", "CRET-PACK", "CRET-SHIP", "CRET-REBIN", "CRET-NS-REBIN",
        "CRET-PS", "CRET-FLOW", "CRET-WATER", "CRET-INDUCT", "CRET-QA", "CRET-LEAD",
        "WHD-RCV", "WHD-STOW", "WHD-PICK",
    ]
    for code in codes:
        if code in text_upper:
            return code
    # Fuzzy match role names
    name_map = {
        "receive": "CRET-RCV", "sort": "CRET-SRT", "binning": "CRET-BIN",
        "pick": "CRET-PICK", "pack": "CRET-PACK", "ship": "CRET-SHIP",
        "rebin": "CRET-REBIN", "problem solve": "CRET-PS", "flow": "CRET-FLOW",
        "water spider": "CRET-WATER", "induction": "CRET-INDUCT",
        "qa": "CRET-QA", "quality": "CRET-QA", "lead": "CRET-LEAD",
        "ambassador": "CRET-LEAD", "stow": "WHD-STOW",
    }
    text_lower = text.lower()
    for name, code in name_map.items():
        if name in text_lower:
            return code
    return None


def extract_shift_type(text: str) -> str | None:
    t = text.lower()
    if "night" in t:
        return "Night"
    if "day" in t:
        return "Day"
    return None
