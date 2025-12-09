"""
Data preprocessing module for clinical trials.

Extracts and filters essential fields to reduce LLM processing overhead.
Supports configurable field sets: essential, extended, full.

start docker and run on another terminal > docker run -p 6379:6379 --name redis-clinagent -d redis:7

"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import pandas as pd


# ===== FIELD SETS FOR FIELD-LIMITED RETRIEVAL =====

FIELD_SETS = {
    "essential": [
        "NCTId",
        "BriefTitle",
        "OverallStatus",
        "Condition",
        "Interventions",
        "Phase",
        "StudyType",
        "StartDate",
    ],
    "extended": [
        "NCTId",
        "BriefTitle",
        "OverallStatus",
        "Condition",
        "Interventions",
        "Phase",
        "StudyType",
        "StartDate",
        "PrimaryCompletionDate",
        "LocationCountry",
        "Enrollment",
    ],
    "full": None  # None = fetch all available fields
}


def resolve_field_set(fields_arg: Any) -> List[str]:
    """
    Resolve `fields_arg` to a list of field names.

    Supports:
    - None or 'essential': use essential field set (default)
    - 'extended': use extended field set
    - 'full': use all fields (None means no filtering)
    - list: use explicit field list

    Args:
        fields_arg: str (named set) or list (explicit) or None (use essential)

    Returns:
        list of field names, or None for 'full' set
    """
    essential_field = FIELD_SETS["essential"]
    if fields_arg is None:
        return essential_field

    if isinstance(fields_arg, str):
        if fields_arg in FIELD_SETS:
            resolved = FIELD_SETS[fields_arg]
            return resolved if resolved is not None else []
        # Treat unknown strings as 'essential'
        return essential_field

    if isinstance(fields_arg, list):
        return [field for field in fields_arg if field not in essential_field] + essential_field

    # Default fallback
    return essential_field


def normalize_field_names(trial: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize field names between different formats.
    - PascalCase (API): NCTId, BriefTitle, StartDate
    - snake_case (CSV): nct_id, title, start_date

    Args:
        trial: Single trial dict with inconsistent field names
        source_format: "auto" (detect), "pascal" (API), "snake" (CSV)

    Returns:
        Trial dict with normalized PascalCase field names
    """
    # Mapping from snake_case to PascalCase
    FIELD_MAPPING = {
        "nct_id": "NCTId",
        "title": "BriefTitle",
        "phase": "Phase",
        "study_type": "StudyType",
        "status": "OverallStatus",
        "condition": "Condition",
        "interventions": "Interventions",
        "country": "LocationCountry",
        "start_date": "StartDate",
        "primary_completion_date": "PrimaryCompletionDate",
        "completion_date": "CompletionDate",
        "last_update": "LastUpdate",
        "locations": "Locations"
    }

    normalized = {}
    for key, value in trial.items():
        # If key is lowercase/snake_case, map it to PascalCase
        if key in FIELD_MAPPING:
            normalized[FIELD_MAPPING[key]] = value
        else:
            # Keep existing PascalCase keys as-is
            normalized[key] = value

    return normalized


def shrink_trials(
    trials: List[Dict[str, Any]],
    field_names: List[str],
    normalize: bool = True
) -> List[Dict[str, Any]]:
    """
    Reduce trial records to only specified fields.
    Optionally normalizes field names from snake_case to PascalCase.

    Args:
        trials: list of study dicts (can be mixed format)
        field_names: list of field names to keep (PascalCase)
        normalize: if True, normalize snake_case fields to PascalCase (default: True)

    Returns:
        list of shrunken dicts with PascalCase field names
    """
    print(f"[PREPROCESS] ⏳ Shrinking to {len(field_names)} fields...")
    if not field_names:
        return trials

    shrinked = []
    for trial in trials:
        # Normalize field names if enabled
        if normalize:
            trial = normalize_field_names(trial)

        # Keep only requested fields
        filtered = {k: v for k, v in trial.items() if k in field_names}
        # print(f"[DEBUG] Requested fields: {field_names}")
        # print(f"[DEBUG] Available fields in trial: {list(trial.keys())}")
        # print(f"[DEBUG] Trial before shrink: {str(trial)[:50]}...")
        # print(f"[DEBUG] Trial after shrink: {str(filtered)[:50]}...")

        # Only add if we got some fields (avoid empty dicts)
        if filtered:
            shrinked.append(filtered)

    # Log results
    if shrinked:
        df = pd.DataFrame(shrinked)
        print(
            f"[PREPROCESS] ✓ Shrunk {len(shrinked)} studies to {len(df.columns)} fields.")
        df.to_csv("guides/shrink_fields.csv", index=False)
    else:
        print(f"[PREPROCESS] ✗ No fields matched after shrinking!")

    return shrinked


def load_studies_from_csv(
    filepath: str = "study_fields.csv",
    filter_condition: Optional[str] = None,
    max_records: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Load studies from CSV file and optionally filter.

    Args:
        filepath: Path to CSV file
        filter_condition: Optional search term to filter by condition
        max_records: Limit number of records returned

    Returns:
        List of study dicts
    """
    df = pd.read_csv(filepath)

    if filter_condition:
        # Filter by condition if provided
        df = df[df['condition'].str.contains(
            filter_condition, case=False, na=False)]

    records = df.to_dict('records')

    if max_records:
        records = records[:max_records]

    print(f"[CSV] Loaded {len(records)} studies from {filepath}")
    return records


def normalize_full_study_fields(fields: list[str]) -> list[str, Any]:
    """
    fields: ['NCT Number', 'Study Title', 'Study URL', 'Acronym', 'Study Status', 'Age', 'Phases', 'Enrollment', 'Locations', 'Study Documents']
    Normalize full study field names into your study_fields format.
    Converts names like 'Study Title' -> 'BriefTitle',
    'NCT Number' -> 'NCTId', 'Phases' -> 'Phase', etc.
    """
    # print(f"[PREPROCESS]: Normalizing {fields}...")

    # Mapping from full studies → study_fields
    FIELD_MAP = {
        "NCT Number": "NCTId",
        "Study Title": "BriefTitle",
        "Study Status": "OverallStatus",
        "Conditions": "Condition",
        "Interventions": "Interventions",
        "Phases": "Phase",
        "Study Type": "StudyType",
        "Start Date": "StartDate",
        "Completion Date": "CompletionDate",
        "Last Update Posted": "LastUpdatePostDate",
        "Brief Summary": "BriefSummary",

        # OPTIONAL EXTRA MAPPINGS for future use
        "Locations": "LocationList",
        "Age": "Age",
        "Sex": "Sex",
        "Sponsor": "Sponsor",
    }

    normalized = []

    for field in fields:

        # If key exists in mapping, convert it
        if field in FIELD_MAP:
            new_field = FIELD_MAP[field]
        else:
            # Fallback → convert to PascalCase
            new_field = ''.join(word.capitalize()
                                for word in field.replace("_", " ").split())
        normalized.append(new_field)

    return normalized
