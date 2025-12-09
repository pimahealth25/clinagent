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


def summarize_studies_json(
    query: str,
    studies: List[Dict[str, Any]],
    model: str = "gpt-4.1",
    max_tokens: int = 500,
    system_prompt: str = None
) -> str:
    """
    Summarize studies using JSON input instead of raw markdown.

    This is more efficient and allows better model reasoning.

    Args:
        query: user's original query / search expression
        studies: list of study dicts (already preprocessed)
        model: which model to use
        max_tokens: max tokens for response
        system_prompt: override default system prompt

    Returns:
        Markdown summary string
    """
    if not _client:
        return "OpenAI API key not configured. Set OPENAI_API_KEY and retry."

    if not system_prompt:
        system_prompt = (
            "You are a clinical research summarizer. Transform structured study data into clear, actionable Markdown.\n\n"
            "## OUTPUT REQUIREMENTS\n"
            "- Format: Markdown only (no code blocks, no JSON)\n"
            "- Content: Facts only—never invent or infer\n"
            "- Completeness: Omit missing/empty fields\n\n"
            "## STRUCTURE\n"
            "1. Executive Summary (1-2 sentences)\n"
            "2. Trials by Phase\n"
            "3. Trials by Study Type\n"
            "4. Key Interventions (if 3+ trials share treatments)\n\n"
            "## FOR EACH TRIAL, INCLUDE ONLY IF PRESENT\n"
            "- NCTId (link format: [NCTxxxxx](https://clinicaltrials.gov/study/NCTxxxxx))\n"
            "- Title, Condition(s), Phase, Study Type, Interventions, Status, Start Date\n\n"
            "## FORMATTING\n"
            "- Use ### Phase X or ### Study Type as headers\n"
            "- Use bullet points, 4-6 lines max per trial\n"
            "- Bold key criteria\n\n"
            "## EDGE CASES\n"
            "- Empty list: Return 'No studies matched.'\n"
            "- 20+ studies: Group by Phase, then Type\n"
        )

    try:
        completion = _client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({
                        "user query": query,
                        "num_studies": len(studies),
                        "studies": studies
                    }, indent=2)
                }
            ],
            # max_tokens=max_tokens,
            temperature=0.4,
        )
        print(f"[LLM] ✓ Summary generated using {str(completion)}")
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"Error summarizing: {str(e)}"


def llm_summarize(trials: List[Dict[str, Any]], query: str, *, model: str = "gpt-4o-mini", temperature: float = 0.4) -> str:
    """Legacy wrapper — delegates to summarize_studies_json."""
    return summarize_studies_json(
        query=query,
        studies=trials,
        model=model,
        max_tokens=800
    )


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


def ask_with_mcp(user_message: str, *, model: str = "gpt-4o-mini", temperature: float = 0.0) -> str:
    """Send a plain-English user message to the LLM and return the model reply.

    Important: for MCP/tool usage to work the model you call here must have the
    MCP/tools configured server-side (on the OpenAI/ChatGPT side). If the model
    has the clinicaltrials MCP tool available, the model will automatically
    select and call it when appropriate. No special client-side JSON tooling is
    required — just pass the user's text as-is.

    This helper is a minimal convenience wrapper to call the same chat API used
    elsewhere in this module.
    """
    if not _client:
        return "OpenAI API key not configured. Set OPENAI_API_KEY and retry."

    completion = _client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": user_message}],
        temperature=temperature,
    )
    return completion.choices[0].message.content.strip()
