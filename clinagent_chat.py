import os
import re
from typing import Dict, Any, List, Tuple

import gradio as gr
from dotenv import load_dotenv

from core.clinicaltrials import fetch_trials, apply_filters_dict as apply_filters, format_trials, simplify_term, sort_trials
from core.llm import llm_summarize, refine_query

# Load environment variables from .env if present
load_dotenv()


"""
Frontend (Gradio) that uses shared core functions:
- fetch_trials: ClinicalTrials.gov fetch + normalization
- apply_filters: dict-based filtering wrapper
- format_trials: pretty listing for chat
- llm_summarize: OpenAI summary
"""


# Chatbot state per session
# state = {"query": str, "page_size": int, "filters": {phase/status/condition}}

def handle_message(message: str, history: List[Tuple[str, str]], state: Dict[str, Any]):
    if state is None or not isinstance(state, dict):
        state = {"query": "", "page_size": 5, "filters": {}}

    # Commands
    text = message.strip()
    if text.lower() in {"help", "/help"}:
        help_msg = (
            "Commands:\n"
            "  refine <query>          - change topic/search query\n"
            "  filter phase=<v>        - set phase filter (e.g., phase=Phase 3)\n"
            "  filter status=<v>       - set status filter (e.g., status=Recruiting)\n"
            "  filter condition=<v>    - set condition filter (e.g., condition=diabetes)\n"
            "  more                    - increase results page size (max 100)\n"
            "  clear                   - clear all filters\n"
            "  show                    - fetch and show results\n"
        )
        return help_msg, state

    # refine command
    if text.lower().startswith("refine "):
        state["query"] = text[7:].strip()
        return f"Query set to: {state['query']}. Type 'show' to fetch.", state

    # filter commands
    if text.lower().startswith("filter "):
        kv = text[7:].strip()
        m = re.match(r"(phase|status|condition)\s*=\s*(.+)", kv, re.I)
        if m:
            k, v = m.group(1).lower(), m.group(2).strip()
            state.setdefault("filters", {})[k] = v
            return f"Filter set: {k}={v}. Type 'show' to fetch.", state
        return "Use format: filter phase=<v>|status=<v>|condition=<v>", state

    # support 'show <query>' to set and fetch immediately
    if text.lower().startswith("show "):
        state["query"] = text[5:].strip()
        # reset filters when user changes topic directly via 'show <query>'
        state["filters"] = {}
        text = "show"

    # more command
    if text.lower() == "more":
        state["page_size"] = min(int(state.get("page_size", 5)) + 10, 100)
        return f"Page size: {state['page_size']}. Type 'show' to fetch.", state

    # clear filters
    if text.lower() == "clear":
        state["filters"] = {}
        return "Filters cleared. Type 'show' to fetch.", state

    # If the user typed a bare query (no command), set as query
    if not text.lower() in {"show"} and not text.lower().startswith(("refine ", "filter ", "more", "clear")):
        # new free-form topic: clear filters to avoid stale constraints
        state["filters"] = {}
        state["query"] = text

    # show/fetch
    if text.lower() == "show" or state.get("query"):
        query = state.get("query", "").strip()
        if not query:
            return "Please provide a query, e.g. 'phase 3 diabetes' or use 'refine <query>'.", state
        try:
            # Use LLM to refine the query and possibly add filters
            rq = refine_query(query)
            refined_query = rq.get("refined_query", query) or query
            predicted_filters = rq.get("filters", {}) or {}
            # merge predicted filters into state
            if predicted_filters:
                sf = state.setdefault("filters", {})
                for k, v in predicted_filters.items():
                    if v and not sf.get(k):
                        sf[k] = v

            page_size = int(state.get("page_size", 5))
            trials = fetch_trials(refined_query, page_size=page_size)
            filters = state.get("filters", {})
            trials = apply_filters(trials, filters)

            # Sort if requested
            sort_hint = str(filters.get("sort", "")).lower()
            if sort_hint in {"recent", "latest", "newest", "last_update"}:
                trials = sort_trials(trials, key="last_update", descending=True)

            # Fallback: if nothing after filtering, try a simplified/condition-only query
            if not trials:
                cond = str(filters.get("condition", "")).strip()
                base_q = cond or refined_query or query
                alt_q = simplify_term(base_q)
                if alt_q and alt_q != refined_query:
                    trials = fetch_trials(alt_q, page_size=max(page_size, 20))
                    trials = apply_filters(trials, filters)
                    if sort_hint in {"recent", "latest", "newest", "last_update"}:
                        trials = sort_trials(trials, key="last_update", descending=True)
        except Exception as e:
            return f"Error: {e}", state

        # Respect limit if provided
        try:
            limit = int(str(state.get("filters", {}).get("limit", "")).strip() or "0")
        except Exception:
            limit = 0
        listing = format_trials(trials, limit=limit or 10)
        summary = llm_summarize(trials, query)
        reply = f"{listing}\n\nSummary:\n{summary}"
        return reply, state

    return "Type 'help' for commands, or enter a query like 'phase 3 diabetes'.", state


def build_ui():
    with gr.Blocks(title="Clinical Trials Chatbot") as demo:
        gr.Markdown("# Clinical Trials Chatbot\nAsk about trials (e.g., 'phase 3 diabetes'). Type 'help' for commands.")
        chat = gr.ChatInterface(
            fn=handle_message,
            additional_inputs=[gr.State({"query": "", "page_size": 5, "filters": {}})],
            type="messages",
        )
    return demo


if __name__ == "__main__":
    has_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY"))
    if not has_key:
        print("WARNING: OPENAI_API_KEY not set. Export OPENAI_API_KEY or OPEN_AI_KEY before running.")
    ui = build_ui()
    ui.launch(server_name="127.0.0.1", server_port=7860)
