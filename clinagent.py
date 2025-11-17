import os
import re
import sys
import argparse
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from core.clinicaltrials import (
    fetch_trials as core_fetch_trials,
    apply_filters as core_apply_filters,
    extract_from_sentence as core_extract_from_sentence,
    simplify_term,
    sort_trials,
    format_trials as core_format_trials,
)
from core.llm import llm_summarize as core_llm_summarize, refine_query
from flask import Flask, request, jsonify, render_template

# Load environment if present
load_dotenv()

# Allow OPENAI_API_KEY (preferred) or OPEN_AI_KEY (fallback)
# Core module handles OpenAI client; we just ensure env is loaded.


def fetch_trials(term: str, page_size: int = 5) -> List[Dict[str, Any]]:
    """Wrapper delegating to core implementation."""
    return core_fetch_trials(term, page_size)


def llm_summarize(trials: List[Dict[str, Any]], query: str) -> str:
    """Wrapper delegating to core LLM summarizer."""
    return core_llm_summarize(trials, query)


def apply_filters(trials: List[Dict[str, Any]], phase: str = "", status: str = "", condition: str = "") -> List[Dict[str, Any]]:
    """Wrapper delegating to core filters."""
    return core_apply_filters(trials, phase=phase, status=status, condition=condition)


def extract_from_sentence(text: str) -> Dict[str, str]:
    """Wrapper delegating to core NLP heuristics."""
    return core_extract_from_sentence(text)


def print_trials(trials: List[Dict[str, Any]], limit: Optional[int] = None) -> None:
    shown = trials if limit is None else trials[:limit]
    for i, t in enumerate(shown, 1):
        print(
            f"{i}. {t['title']}\n   Phase: {t['phase']} | Status: {t['status']} | Condition: {t['condition']}\n")
    if limit and len(trials) > limit:
        print(f"... and {len(trials) - limit} more.")


def agent_mode(initial_query: str, page_size: int = 5) -> None:
    query = initial_query.strip()
    phase = status = condition = ""
    cur_page = page_size

    print("🤖 Agent mode. Commands: more | filter | refine | clear | summarize | exit\n")

    while True:
        print(
            f"🔍 Fetching: '{query}' | pageSize={cur_page} | filters={{'phase': '{phase}', 'status': '{status}', 'condition': '{condition}'}}")

        trials = fetch_trials(query, page_size=cur_page)
        trials = apply_filters(trials, phase=phase,
                               status=status, condition=condition)

        if not trials:
            print("No studies found with current filters.")

        else:
            print_trials(trials, limit=min(10, len(trials)))
            print("\n🧾 Summary:\n")
            print(llm_summarize(trials, query))

        raw = input(
            "\nNext [more|filter|refine|clear|summarize|exit or type a sentence]: ").strip()
        cmd = raw.lower()

        if cmd == "exit":
            print("Goodbye.")
            return

        if cmd == "more":
            cur_page = min(cur_page + 10, 100)
            continue

        if cmd == "filter":
            k = input("Key [phase|status|condition]: ").strip().lower()
            v = input("Value: ").strip()

            if k == "phase":
                phase = v
            elif k == "status":
                status = v
            elif k == "condition":
                condition = v
            else:
                print("Unknown filter key.")
            continue

        if cmd == "refine":
            query = input("New query: ").strip()
            continue

        if cmd == "clear":
            phase = status = condition = ""
            print("Filters cleared.")
            continue

        if cmd == "summarize":
            print("\n🧾 Summary:\n")
            print(llm_summarize(trials, query))
            continue

        # Treat as natural sentence: extract filters and set query
        guessed = extract_from_sentence(raw)
        if guessed:
            # Update filters if present
            phase = guessed.get("phase", phase)
            status = guessed.get("status", status)
            condition = guessed.get("condition", condition)
        # Update main query to the sentence itself

        if raw:
            query = raw
            print(f"Query set to: {query}")
            if guessed:
                print(f"Parsed filters: {guessed}")
        else:
            print("Unknown command.")


def build_web_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/chat")
    def chat_api():
        try:
            payload = request.get_json(force=True) or {}
        except Exception:
            payload = {}

        message = (payload.get("message") or "").strip()
        state = payload.get("state") or {
            "query": "", "page_size": 5, "filters": {}}

        if message.lower() in {"help", "/help"}:
            help_msg = (
                "You can ask naturally, e.g.:\n"
                "  • '5 most recent lung cancer studies'\n"
                "  • 'phase 3 diabetes recruiting'\n"
                "Commands:\n"
                "  refine <query> — change topic\n"
                "  filter phase=<v>|status=<v>|condition=<v> — set a filter\n"
                "  more — increase results page size (max 100)\n"
                "  clear — clear filters\n"
                "  show — fetch; click again to reveal 10 more (or 'show <query>')\n"
                "  refiner on|off — toggle LLM query refinement\n"
                "  agent on|off — use CrewAI agents to research & summarize\n"
                "  agent run <query> — one-shot CrewAI run\n"
                "  debug on|off — toggle extra details in responses\n"
            )
            return jsonify({"reply": help_msg, "state": state})

        if message.lower().startswith("refine "):
            state["query"] = message[7:].strip()
            # call show function so it shows the results after refining
            return jsonify({"reply": f"Query set to: {state['query']}. Click Show.", "state": state})

        if message.lower().startswith("filter "):
            kv = message[7:].strip()
            m = re.match(r"(phase|status|condition)\s*=\s*(.+)", kv, re.I)
            if m:
                k, v = m.group(1).lower(), m.group(2).strip()
                state.setdefault("filters", {})[k] = v
                # call show function so it shows the results after setting filter
                return jsonify({"reply": f"Filter set: {k}={v}. Click Show.", "state": state})
            return jsonify({"reply": "Use: filter phase=<v>|status=<v>|condition=<v>", "state": state})

        if message.lower() == "more":
            state["page_size"] = min(int(state.get("page_size", 5)) + 10, 100)
            return jsonify({"reply": f"Page size: {state['page_size']}. Click Show.", "state": state})

        if message.lower() == "clear":
            state["filters"] = {}
            return jsonify({"reply": "Filters cleared. Click Show.", "state": state})

        # Toggle refiner
        if message.lower() in {"refiner on", "refiner off"}:
            state["refiner"] = message.lower().endswith("on")
            return jsonify({"reply": f"Refiner set to: {'on' if state['refiner'] else 'off'}.", "state": state})

        # Toggle debug
        if message.lower() in {"debug on", "debug off"}:
            state["debug"] = message.lower().endswith("on")
            return jsonify({"reply": f"Debug set to: {'on' if state.get('debug') else 'off'}.", "state": state})

        # Free-form sentence: auto-extract filters and set query
        # Toggle agent mode
        if message.lower() in {"agent on", "agent off"}:
            state["agent"] = message.lower().endswith("on")
            return jsonify({"reply": f"Agent mode: {'on' if state.get('agent') else 'off'}.", "state": state})

        # One-shot agent run
        if message.lower().startswith("agent run "):
            q = message[10:].strip() or state.get("query", "")
            if not q:
                return jsonify({"reply": "Provide a topic, e.g. 'agent run keytruda in nsclc'.", "state": state})

            try:
                from clinagent_crewai import build_crew  # lazy import to avoid hard dependency
            except Exception as e:
                return jsonify({
                    "reply": f"Agent pipeline not available: {e.__class__.__name__}: {e}\n\nInstall deps:\n  pip install -r requirements.txt\nOr uncheck 'Use Agents' and try again.",
                    "state": state,
                })

            crew = build_crew()
            result = crew.kickoff(
                inputs={"query": q, "page_size": int(state.get("page_size", 5))})
            # best effort stringify
            reply = f"{result}"
            return jsonify({"reply": reply, "state": state})

        # Support "show <query>" as a command to both set and fetch
        if message.lower().startswith("show "):
            state["query"] = message[5:].strip()
            state["filters"] = {}
            message = "show"

        if message and message.lower() not in {"show"} and not message.lower().startswith(("refine ", "filter ", "more", "clear")):
            guessed = extract_from_sentence(message)
            if guessed:
                fs = state.setdefault("filters", {})
                for k, v in guessed.items():
                    fs[k] = v
            else:
                # new topic with no heuristic filters -> clear old filters
                state["filters"] = {}
            state["query"] = message

        if message.lower() == "show" or state.get("query"):
            q = state.get("query", "").strip()
            print(f"the current state {state}")
            if not q:
                return jsonify({"reply": "Provide a query, e.g. 'phase 3 diabetes', or use 'refine <query>'.", "state": state})
            try:
                # Agent mode: delegate to CrewAI pipeline
                if state.get("agent"):
                    try:
                        from clinagent_crewai import build_crew  # lazy import to avoid hard dependency
                    except Exception as e:
                        return jsonify({
                            "reply": f"Agent pipeline not available: {e.__class__.__name__}: {e}\n\nInstall deps:\n  pip install -r requirements.txt\nOr uncheck 'Use Agents' and try again.",
                            "state": state,
                        })

                    crew = build_crew()
                    result = crew.kickoff(
                        inputs={"query": q, "page_size": int(state.get("page_size", 5))})
                    # Robust stringify; fallback to regular path if empty
                    text = ""
                    try:
                        text = str(result) if result is not None else ""
                    except Exception:
                        text = ""

                    if text and text.strip():
                        return jsonify({"reply": text, "state": state})
                    # Fallback to regular flow if agent returned nothing useful

                # Optionally refine query via LLM
                refined_q = q
                use_refiner = state.get("refiner")
                if use_refiner is None:
                    # default from env (off unless explicitly enabled)
                    use_refiner = (os.getenv("CLINAGENT_REFINE", "0").lower() in {
                                   "1", "true", "yes", "on"})

                if use_refiner:
                    rq = refine_query(q)
                    refined_q = rq.get("refined_query", q) or q
                    predicted_filters = rq.get("filters", {}) or {}
                    if predicted_filters:
                        fs = state.setdefault("filters", {})
                        for k, v in predicted_filters.items():
                            if v and not fs.get(k):
                                fs[k] = v

                fdict = state.get("filters", {}) or {}
                # Respect limit when fetching: fetch at least as many as we plan to display
                try:
                    limit = int(str(fdict.get("limit", "")).strip() or "0")
                except Exception:
                    limit = 0
                page_size = max(int(state.get("page_size", 5)), limit or 0)
                trials = fetch_trials(refined_q, page_size=page_size)
                trials = apply_filters(
                    trials,
                    phase=str(fdict.get("phase", "")),
                    status=str(fdict.get("status", "")),
                    condition=str(fdict.get("condition", "")),
                )

                # Fallback: if no trials after filtering, try with simplified query from condition only
                if not trials:
                    cond = str(fdict.get("condition", "")).strip()
                    base_q = cond or refined_q or q
                    alt_q = simplify_term(base_q)
                    if alt_q and alt_q != refined_q:
                        trials = fetch_trials(
                            alt_q, page_size=max(page_size, limit or 0, 20))
                        trials = apply_filters(
                            trials,
                            phase=str(fdict.get("phase", "")),
                            status=str(fdict.get("status", "")),
                            condition=str(fdict.get("condition", "")),
                        )

                # Sort if requested (e.g., 'recent')
                sort_hint = str(fdict.get("sort", "")).lower()
                if sort_hint in {"recent", "latest", "newest", "last_update"}:
                    trials = sort_trials(
                        trials, key="last_update", descending=True)
                # 'limit' already parsed above
            except Exception as e:
                return jsonify({"reply": f"Error: {e}", "state": state})

            # Format listing with optional limit
            listing = core_format_trials(trials, limit=limit or 10)

            summary = llm_summarize(trials, q)
            debug_info = ""
            if state.get("debug"):
                debug_info = f"\n\n[debug] refined_query={refined_q} filters={fdict} python={sys.executable}"
            reply = f"{listing}\n\nSummary\n{summary}{debug_info}"
            return jsonify({"reply": reply, "state": state})

        return jsonify({"reply": "Type 'help' for commands, or enter a query.", "state": state})

    return app


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clinical trials tool (one-shot or agent mode)")
    parser.add_argument("query", nargs="?",
                        help="Search query (e.g., 'phase 3 diabetes')")
    parser.add_argument("--page-size", type=int, default=5,
                        help="Trials per fetch (default 5)")
    parser.add_argument("--agent", action="store_true",
                        help="Run interactive agent mode")
    parser.add_argument("--web", action="store_true",
                        help="Run minimal web UI on http://127.0.0.1:5000")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Web host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000,
                        help="Web port (default 5000)")
    args = parser.parse_args(argv)

    if args.web:
        app = build_web_app()
        app.run(host=args.host, port=args.port, debug=False)
        return 0

    if args.agent:
        q = args.query or input(
            "Enter your goal (e.g., 'phase 3 diabetes trials'): ")
        agent_mode(q, page_size=args.page_size)
        return 0

    # one-shot mode
    q = args.query or input(
        "Enter your question (e.g., 'new phase 3 diabetes trials'): ")
    print(f"🔍 Searching trials for: {q}")
    trials = fetch_trials(q, page_size=args.page_size)
    if not trials:
        print("No studies found.")
        return 0
    print("\n🧾 Summary:\n")
    print(llm_summarize(trials, q))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
