from __future__ import annotations

import re
from typing import List, Dict, Any, Tuple, Optional

import requests
from requests.exceptions import RequestException

API_URL = "https://clinicaltrials.gov/api/v2/studies"


def _coerce_date(value: Optional[str]) -> str:
    """Return YYYY-MM-DD or empty string."""
    if not value:
        return ""
    # Already ISO?
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
    if m:
        return value
    # Try YYYY Mon DD or Mon YYYY variants (lightweight)
    try:
        import datetime as _dt
        for fmt in ("%b %Y", "%B %Y", "%Y %b", "%Y %B", "%m/%d/%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
            try:
                d = _dt.datetime.strptime(value, fmt)
                return d.strftime("%Y-%m-%d")
            except Exception:
                pass
    except Exception:
        pass
    # As a last resort, return original (may be empty downstream)
    return value


def simplify_term(term: str) -> str:
    """Make a looser search term by removing phase/status words and generic fillers."""
    low = term
    low = re.sub(r"\bphase\s*[1-4]\b", " ", low, flags=re.I)
    low = re.sub(r"\b(trial|trials|study|studies|patients|with)\b",
                 " ", low, flags=re.I)

    # remove common statuses
    low = re.sub(r"\b(not yet recruiting|active,? not recruiting|recruiting|completed|terminated|suspended|enrolling by invitation)\b", " ", low, flags=re.I)

    # collapse whitespace
    low = re.sub(r"\s+", " ", low).strip()
    return low or term


def _expand_drug_synonyms(term: str) -> str:
    """Append common brand/generic synonyms to improve recall (e.g., 'keytruda' -> also 'pembrolizumab')."""
    synonyms = {
        "keytruda": "pembrolizumab",
        "opdivo": "nivolumab",
        "imfinzi": "durvalumab",
        "tecentriq": "atezolizumab",
        "yervoy": "ipilimumab",
        "herceptin": "trastuzumab",
        "avastin": "bevacizumab",
        "libtayo": "cemiplimab",
        "jemperli": "dostarlimab",
    }
    low = term.lower()
    extras: List[str] = []
    for brand, generic in synonyms.items():
        if brand in low and generic not in low:
            extras.append(generic)
        if generic in low and brand not in low:
            extras.append(brand)
    if extras:
        return term + " " + " ".join(sorted(set(extras)))
    return term


def _attempt_fetch(term: str, page_size: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    params = {
        "query.term": term,
        "fields": "BriefTitle,Phase,Condition,OverallStatus",
        "pageSize": page_size,
    }

    try:
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
    except RequestException as e:
        raise RuntimeError(f"ClinicalTrials.gov request failed: {e}") from e

    data = resp.json() if getattr(resp, "content", None) else {}

    trials: List[Dict[str, Any]] = []

    for study in data.get("studies", []):
        ps = study.get("protocolSection", {}) or {}
        title = (
            ps.get("identificationModule", {}).get("briefTitle")
            or study.get("BriefTitle")
            or "Untitled"
        )
        phase_list = (
            ps.get("designModule", {}).get("phases")
            or study.get("Phase")
            or []
        )
        status = (
            ps.get("statusModule", {}).get("overallStatus")
            or study.get("OverallStatus")
            or "N/A"
        )
        conditions = (
            ps.get("conditionsModule", {}).get("conditions")
            or study.get("Condition")
            or []
        )

        phase = ", ".join(phase_list) if isinstance(
            phase_list, list) else str(phase_list or "N/A")

        condition = ", ".join(conditions) if isinstance(
            conditions, list) else str(conditions or "N/A")

        # Dates (prefer v2 structs; fallback to legacy fields if present)
        sm = ps.get("statusModule", {}) if isinstance(ps, dict) else {}
        start_dt = _coerce_date(
            (sm.get("startDateStruct") or {}).get("startDate"))
        prim_dt = _coerce_date(
            (sm.get("primaryCompletionDateStruct") or {}).get("primaryCompletionDate"))
        comp_dt = _coerce_date(
            (sm.get("completionDateStruct") or {}).get("completionDate"))
        last_upd = _coerce_date(
            (sm.get("lastUpdatePostDateStruct") or {}).get("lastUpdatePostDate"))

        trials.append({
            "title": title,
            "phase": phase or "N/A",
            "status": status or "N/A",
            "condition": condition or "N/A",
            "start_date": start_dt,
            "primary_completion_date": prim_dt,
            "completion_date": comp_dt,
            "last_update": last_upd,
        })
    return trials, data


def fetch_trials(term: str, page_size: int = 5) -> List[Dict[str, Any]]:
    """Fetch trials and normalize fields.

    Strategy: try the user term once; if zero results, retry with a simplified
    term that removes phase/status words and increases page size for recall.
    """
    term = _expand_drug_synonyms(term)
    trials, _ = _attempt_fetch(term, page_size)
    if trials:
        return trials

    simplified = simplify_term(term)
    if simplified != term:
        simplified = _expand_drug_synonyms(simplified)
        trials2, _ = _attempt_fetch(simplified, max(page_size, 20))
        return trials2
    return trials


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("_", " ").replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def apply_filters(trials: List[Dict[str, Any]], *, phase: str = "", status: str = "", condition: str = "") -> List[Dict[str, Any]]:
    res = trials
    if phase:
        # match by phase number if present (e.g., "Phase 3" vs "PHASE3")
        pnum = _digits(phase)
        if pnum:
            res = [t for t in res if _digits(t.get("phase", "")) == pnum]
        else:
            p = _norm(phase)
            res = [t for t in res if p in _norm(t.get("phase", ""))]
    if status:
        # Use exact match on normalized status to avoid 'recruiting' matching 'active not recruiting'
        def norm_status(x: str) -> str:
            x = _norm(x)
            # standardize a few common variants
            replacements = {
                "active, not recruiting": "active not recruiting",
                "n/a": "na",
            }
            return replacements.get(x, x)

        want = norm_status(status)
        res = [t for t in res if norm_status(t.get("status", "")) == want]
    if condition:
        c = _norm(condition)
        res = [t for t in res if c in _norm(t.get("condition", ""))]
    return res


def sort_trials(trials: List[Dict[str, Any]], *, key: str = "last_update", descending: bool = True) -> List[Dict[str, Any]]:
    def _key(t: Dict[str, Any]) -> str:
        v = str(t.get(key) or "")
        # Empty dates should sort last when descending
        return v or ("0000-00-00" if not descending else "")

    return sorted(trials, key=_key, reverse=descending)


def apply_filters_dict(trials: List[Dict[str, Any]], filters: Dict[str, str]) -> List[Dict[str, Any]]:
    phase = (filters or {}).get("phase", "")
    status = (filters or {}).get("status", "")
    condition = (filters or {}).get("condition", "")
    return apply_filters(trials, phase=phase, status=status, condition=condition)


def format_trials(trials: List[Dict[str, Any]], limit: int = 10) -> str:
    lines = []
    for i, t in enumerate(trials[:limit], 1):
        lines.append(
            f"{i}. {t['title']}\n   Phase: {t['phase']} | Status: {t['status']} | Condition: {t['condition']}")
    if len(trials) > limit:
        lines.append(f"... and {len(trials) - limit} more.")
    return "\n".join(lines) or "No studies found."


def extract_from_sentence(text: str) -> Dict[str, str]:
    """Extract simple filters from a natural-language sentence.
    Returns keys possibly among: phase, status, condition.
    """
    filters: Dict[str, str] = {}
    low = text.lower()

    m = re.search(r"\bphase\s*([1-4])\b", low)
    if m:
        filters["phase"] = f"Phase {m.group(1)}"

    statuses = [
        "not yet recruiting",
        "active, not recruiting",
        "recruiting",
        "completed",
        "terminated",
        "suspended",
        "enrolling by invitation",
    ]
    # Simple synonym mapping
    synonyms = {
        "enrolling": "recruiting",
        "open": "recruiting",
        "actively enrolling": "recruiting",
    }
    for k, v in synonyms.items():
        if k in low:
            filters["status"] = v
            break
    for s in statuses:
        if s in low:
            filters["status"] = s
            break

    cond = None
    for kw in ["for", "in"]:  # exclude 'on' to avoid capturing 'on <drug>' as condition
        m = re.search(rf"\b{kw}\s+([^.,;:!?]+)", low)
        if m:
            cond = m.group(1).strip()
            break
    if cond:
        cond = re.sub(
            r"\b(trial|trials|study|studies|patients|with|about|on)\b", "", cond).strip()
        cond = re.sub(r"\bphase\s*[1-4]\b", "", cond).strip()
        # only set condition if disease-like terms are present
        if re.search(r"\b(cancer|carcinoma|tumou?r|diabetes|disease|syndrome|melanoma|lymphoma|myeloma|leukemia)\b", cond):
            filters.setdefault("condition", cond)

    # Look for recency intent and simple limit (e.g., '5 most recent')
    if re.search(r"\b(recent|latest|newest|most\s+recent)\b", low):
        filters["sort"] = "recent"
    mnum = re.search(
        r"\b(\d{1,3})\b\s+(most\s+)?(recent|latest|newest|studies|trials)", low)
    if mnum:
        filters["limit"] = mnum.group(1)

    return filters
