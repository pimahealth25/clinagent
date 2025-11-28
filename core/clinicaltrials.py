from __future__ import annotations
from pytrials.client import ClinicalTrials

import re
from typing import List, Dict, Any, Tuple, Optional

import requests
import pandas as pd
from requests.exceptions import RequestException


API_URL = "https://clinicaltrials.gov/api/v2/studies"

ct = ClinicalTrials()


def run_full_studies(search_expr: str, max_studies: int = 50):
    full_studies = ct.get_full_studies(
        search_expr=search_expr, max_studies=max_studies)

    print("#######################################")
    print(f'full_studies func: {str(full_studies)[:100]}')
    print("#######################################")

    df = pd.DataFrame.from_records(full_studies[1:], columns=full_studies[0])
    df.to_csv("full_studies.csv", index=False)

    return df.to_dict(orient="records")


def run_study_fields(search_expr: str, fields: list, max_studies: int = 100, fmt: str = "csv"):
    '''
    Docstring for run_study_fields

    :param search_expr: Description
    :type search_expr: str
    :param fields: Description
    :type fields: list
    :param max_studies: Description
    :type max_studies: int
    :param fmt: Description
    :type fmt: str
    '''
    search_expr = search_expr.replace(" ", "+")

    results = ct.get_study_fields(
        search_expr=search_expr,
        fields=clean_fields(fields),
        max_studies=max_studies,
        fmt=fmt,
    )

    print("#######################################")
    print(f'results run field function: {str(results)[:100]}...')
    print("#######################################")

    studies = results.get("studies", [])

    parse_results, _ = parse_clinical_studies(studies)

    df = pd.DataFrame(parse_results)

    # Optional export
    df.to_csv("study_fields.csv", index=False)

    return df.to_dict(orient="records")


def extract_value(protocol_section, study, module_name, field_name, default=""):
    """
    Extract a field from a protocolSection module or fall back
    to the study-level field. Returns empty string instead of None.
    """
    module = protocol_section.get(module_name, {}) or {}
    value = module.get(field_name) or study.get(field_name) or default
    return default if value is None else value


def clean_fields(fields: List[str]) -> List[str]:
    """Clean and validate requested fields for study fields retrieval."""
    VALID_STUDY_FIELDS = [
        "NCTId",
        "BriefTitle",
        "Condition",
        "OverallStatus",
        "Phase",
        "StudyType",
        "StartDate",
        "CompletionDate",
        "LastUpdatePostDate",
        "BriefSummary",
        "LocationCountry",
        "LocationCity",
        "LocationState",
        "CentralContactName",
        "CentralContactPhone",
        "CentralContactEMail"
    ]
    return [f for f in fields if f in VALID_STUDY_FIELDS]


def extract_list(value, default=""):
    """
    Convert a list into a comma-separated string.
    For non-lists, convert to string. Guaranteed no None return.
    """
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value) if value not in (None, "") else default


def extract_date(module, struct_name):
    """
    Extract a date from a dateStruct (which uses 'date' field in v2 API).
    Example:
      "startDateStruct": { "date": "2010-09" }
    """
    struct = module.get(struct_name, {}) or {}
    date_raw = struct.get("date")
    return date_raw if date_raw else ""


def extract_interventions(section):
    """
    Extract and join all intervention names under armsInterventionsModule.
    """
    module = section.get("armsInterventionsModule", {}) or {}
    interventions = module.get("interventions", []) or []

    names = [i.get("name") for i in interventions if "name" in i]
    return ", ".join(names) if names else ""


def extract_countries(section):
    """
    Extract country list from contactsLocationsModule.
    """
    module = section.get("contactsLocationsModule", {}) or {}
    locations = module.get("locations", []) or []

    countries = [loc.get("country") for loc in locations if loc.get("country")]
    return ", ".join(countries) if countries else ""


def parse_clinical_studies(studies: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Fully improved ClinicalTrials.gov v2 study parser.

    Returns a list of clean, normalized study dictionaries
    with no None values and complete useful fields.
    """
    if studies is None:
        return [], []

    parsed = []

    for study in studies:
        section = study.get("protocolSection", {}) or {}
        status_module = section.get("statusModule", {}) or {}

        # --- Identification ---
        nct_id = extract_value(
            section, study, "identificationModule", "nctId", "")
        title = extract_value(
            section, study, "identificationModule", "briefTitle", "Untitled")

        # --- Conditions ---
        conditions_raw = extract_value(
            section, study, "conditionsModule", "conditions", [])
        conditions = extract_list(conditions_raw, default="N/A")

        # --- Phase ---
        phase_raw = extract_value(section, study, "designModule", "phases", [])
        phase = extract_list(phase_raw, default="N/A")

        # --- Study type ---
        study_type = extract_value(
            section, study, "designModule", "studyType", "N/A")

        # --- Status ---
        status = extract_value(
            section, study, "statusModule", "overallStatus", "N/A")

        # --- Dates ---
        start_date = extract_date(status_module, "startDateStruct")
        primary_completion_date = extract_date(
            status_module, "primaryCompletionDateStruct")
        completion_date = extract_date(status_module, "completionDateStruct")
        last_update = extract_date(status_module, "lastUpdatePostDateStruct")

        # --- Interventions ---
        interventions = extract_interventions(section)

        # --- Countries ---
        country = extract_countries(section)

        # --- Build result row ---
        parsed.append({
            "nct_id": nct_id,
            "title": title,
            "phase": phase,
            "study_type": study_type,
            "status": status,
            "condition": conditions,
            "interventions": interventions,
            "country": country,
            "start_date": start_date,
            "primary_completion_date": primary_completion_date,
            "completion_date": completion_date,
            "last_update": last_update,
        })

    return parsed, list(parsed[0].keys()) if parsed else []


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
    '''Format a list of trials into a human-readable string.'''
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
