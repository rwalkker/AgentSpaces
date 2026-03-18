"""CRET and AR/WHD role definitions with baseline UPH and quarterly adjustments."""

from dataclasses import dataclass
from enum import Enum


class Quarter(Enum):
    Q1 = 1
    Q2 = 2
    Q3 = 3
    Q4 = 4


QUARTERLY_WEIGHTS = {Quarter.Q1: 26.9, Quarter.Q2: 21.0, Quarter.Q3: 30.1, Quarter.Q4: 22.0}


def quarterly_adjustment_factor(q: Quarter) -> float:
    """(Quarter Weight% - 25%) / 100"""
    return (QUARTERLY_WEIGHTS[q] - 25.0) / 100.0


def adjusted_uph(base_uph: float, q: Quarter) -> float:
    return base_uph * (1 + quarterly_adjustment_factor(q))


@dataclass
class RoleDef:
    code: str
    name: str
    baseline_uph: float
    is_direct: bool
    volume_pct: float = 0.0  # only for direct roles
    is_ns: bool = False


# --- CRET Direct (10 roles) ---
CRET_DIRECT = [
    RoleDef("CRET-RCV", "Receive", 180, True, 0.12),
    RoleDef("CRET-SRT", "Sort", 220, True, 0.22),
    RoleDef("CRET-NS-SRT", "NS Sort", 210, True, 0.08, is_ns=True),
    RoleDef("CRET-BIN", "Binning", 195, True, 0.14),
    RoleDef("CRET-NS-BIN", "NS Binning", 190, True, 0.06, is_ns=True),
    RoleDef("CRET-PICK", "Pick", 210, True, 0.14),
    RoleDef("CRET-PACK", "Pack", 175, True, 0.10),
    RoleDef("CRET-SHIP", "Ship", 160, True, 0.06),
    RoleDef("CRET-REBIN", "Rebin", 200, True, 0.05),
    RoleDef("CRET-NS-REBIN", "NS Rebin", 195, True, 0.03, is_ns=True),
]

# --- CRET Support (6 roles) ---
CRET_SUPPORT = [
    RoleDef("CRET-PS", "Problem Solve", 0, False),
    RoleDef("CRET-FLOW", "Flow Control", 0, False),
    RoleDef("CRET-WATER", "Water Spider", 0, False),
    RoleDef("CRET-INDUCT", "Induction", 0, False),
    RoleDef("CRET-QA", "Quality Assurance", 0, False),
    RoleDef("CRET-LEAD", "Process Lead", 0, False),
]

CRET_ALL = CRET_DIRECT + CRET_SUPPORT

# --- AR/WHD Direct (3 roles) ---
WHD_DIRECT = [
    RoleDef("WHD-RCV", "Receive", 145, True),
    RoleDef("WHD-STOW", "Stow", 130, True),
    RoleDef("WHD-PICK", "Pick", 155, True),
]

# AR/WHD volume split: equal thirds by default
WHD_VOLUME_SPLIT = {"WHD-RCV": 1 / 3, "WHD-STOW": 1 / 3, "WHD-PICK": 1 / 3}

# v1.3 indirect staffing ratios (policy targets)
INDIRECT_RATIOS = {
    "CRAUDIT": ("Audit", 0.0085),  # 0.85% of total CR hours
    "CRDSCAN": ("Dock Scan", 1 / 57),
    "REBTRN3": ("Problem Solve", 1 / 22),
    "CRADD": ("Add-Ins", 1 / 70),
    "CRETREF": ("Exceptions/Refurb", 1 / 57),
    "PRGCRET_FC": ("Process Guide Full Case", 1 / 21),
    "PRGCRET_TM": ("Process Guide Team/Mech", 1 / 29),
    "CRUNLD_FC": ("Unloader Full Case", 1 / 14),
    "CRUNLD_TM": ("Unloader Team/Mech", 1 / 8),
    "CRAMB": ("Ambassador", 1 / 10),  # conditional — new hires only
    "CREOL": ("End of Line", 1 / 19),
    "CRTCON": ("Consolidation", 1 / 38),
    "CRSDCNTF_FC": ("Water Spider Full Case", 1 / 21),
    "CRSDCNTF_TM": ("Water Spider Team/Mech", 1 / 14),
}

# Disposition routing outcomes (v1.2)
DISPOSITIONS = [
    "Sellable", "Amazon Resale (AR)", "AR Tech", "External Repairs",
    "Unsellable/STOW", "Liquidation", "Refurb", "Donation", "Recycle",
    "Advanced Detection",
]

# CALM codes (v1.2)
CALM_CODES = {
    "CRUNLD": "Unload", "CREOL": "End of Line", "CRSDCNTF": "Water Spider",
    "REBTTRN3": "Problem Solve", "CRADD": "Add Ins", "CRAUDIT": "Audit",
    "SCRFB10": "IOL", "CRAMB": "Ambassador", "CRSS": "5S", "CRETREF": "Refurbish",
}
