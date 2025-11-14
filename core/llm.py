from __future__ import annotations

import os
from typing import List, Dict, Any
import json

from dotenv import load_dotenv
from openai import OpenAI

# Load .env if present
load_dotenv()

# Prefer OPENAI_API_KEY; fallback to OPEN_AI_KEY
_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY")
_client = OpenAI(api_key=_API_KEY) if _API_KEY else None


def llm_summarize(trials: List[Dict[str, Any]], query: str, *, model: str = "gpt-4o-mini", temperature: float = 0.4) -> str:
    if not _client:
        return "OpenAI API key not configured. Set OPENAI_API_KEY and retry."
    if not trials:
        return "No studies found."

    trial_text = "\n".join([
        f"- {t['title']} (Phase: {t['phase']}, Status: {t['status']}, Condition: {t['condition']})"
        for t in trials
    ])
    prompt = f"""
    You are a biomedical research assistant.
    Summarize these clinical trials for a professional audience.
    Focus on key patterns (e.g., phases, conditions, and statuses).

    User query: {query}

    Trials:
    {trial_text}
    """

    completion = _client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return completion.choices[0].message.content.strip()


def refine_query(user_query: str, *, model: str = "gpt-4o-mini", temperature: float = 0.0) -> Dict[str, Any]:
    """Use the LLM to rewrite the user's query into a better API search term and optional filters.

    Returns dict: {"refined_query": str, "filters": {"phase": str, "status": str, "condition": str}}
    Falls back to simple heuristics if API key is not set.
    """
    # Fallback if no client
    if not _client:
        try:
            # Lazy import to avoid circulars at import time
            from .clinicaltrials import extract_from_sentence  # type: ignore
        except Exception:
            return {"refined_query": user_query, "filters": {}}

        filters = extract_from_sentence(user_query)
        # refined query: remove phase/status words and keep core condition keywords
        refined = user_query
        return {"refined_query": refined, "filters": filters}

    system = (
        "You rewrite end-user requests into effective search queries for ClinicalTrials.gov API. "
        "Focus the refined_query on concise condition/disease terms and key keywords. "
        "Do NOT include phrases like 'phase 3' or recruitment statuses in refined_query; those belong in filters. "
        "Return STRICT JSON with keys refined_query (string) and filters (object with optional keys phase, status, condition)."
    )
    user = f"""
    User request: {user_query}

    Instructions:
    - refined_query: short string optimized for ClinicalTrials.gov 'query.term'
    - filters: object with optional keys: phase (e.g., "Phase 3"), status (e.g., "Recruiting"), condition (e.g., "diabetes mellitus")
    - Only return JSON.
    """

    completion = _client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )

    content = completion.choices[0].message.content.strip()
    try:
        data = json.loads(content)
        refined = str(data.get("refined_query") or user_query).strip()
        filters = data.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}
        return {"refined_query": refined, "filters": filters}
    except Exception:
        return {"refined_query": user_query, "filters": {}}
