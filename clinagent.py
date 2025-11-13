import os
import re
import sys
import argparse
from typing import List, Dict, Any, Optional

import requests
from requests.exceptions import RequestException
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
from flask import Flask, request, jsonify, render_template_string

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
        print(f"{i}. {t['title']}\n   Phase: {t['phase']} | Status: {t['status']} | Condition: {t['condition']}\n")
    if limit and len(trials) > limit:
        print(f"... and {len(trials) - limit} more.")


def agent_mode(initial_query: str, page_size: int = 5) -> None:
    query = initial_query.strip()
    phase = status = condition = ""
    cur_page = page_size

    print("🤖 Agent mode. Commands: more | filter | refine | clear | summarize | exit\n")

    while True:
        print(f"🔍 Fetching: '{query}' | pageSize={cur_page} | filters={{'phase': '{phase}', 'status': '{status}', 'condition': '{condition}'}}");
        trials = fetch_trials(query, page_size=cur_page)
        trials = apply_filters(trials, phase=phase, status=status, condition=condition)

        if not trials:
            print("No studies found with current filters.")
        else:
            print_trials(trials, limit=min(10, len(trials)))
            print("\n🧾 Summary:\n")
            print(llm_summarize(trials, query))

        raw = input("\nNext [more|filter|refine|clear|summarize|exit or type a sentence]: ").strip()
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
        return render_template_string(
            """
<!doctype html>
<html lang=\"en\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>Clinical Trials Chat</title>
        <style>
            body { font-family: -apple-system, system-ui, Segoe UI, Roboto, sans-serif; margin: 0; padding: 0; background: #f7f7f8; }
            .container { max-width: 960px; margin: 0 auto; padding: 16px; }
            h1 { font-size: 20px; margin: 12px 0 16px; }
            #chat { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; height: 72vh; overflow-y: auto; white-space: pre-wrap; font-size: 14px; line-height: 1.6; word-break: break-word; }
            .msg { margin: 12px 0; display: flex; gap: 10px; align-items: flex-start; }
            .msg.user { color: #111827; }
            .msg.bot { color: #374151; }
            .msg .label { font-weight: 600; padding: 2px 6px; border-radius: 999px; font-size: 12px; flex: 0 0 auto; }
            .msg .content { white-space: pre-wrap; display: block; margin-top: 2px; }
            .user .label { background: #eef2ff; color: #1e3a8a; border: 1px solid #e0e7ff; }
            .bot .label { background: #ecfeff; color: #0c4a6e; border: 1px solid #cffafe; }
            .user .content { background: #f8fafc; border: 1px solid #e5e7eb; padding: 8px 10px; border-radius: 8px; }
            .bot .content { background: #f9fafb; border: 1px solid #e5e7eb; padding: 8px 10px; border-radius: 8px; }
            .row { display: flex; gap: 8px; margin-top: 10px; }
            textarea { flex: 1; resize: vertical; min-height: 56px; padding: 10px; border: 1px solid #e5e7eb; border-radius: 6px; }
            button { background: #111827; color: #fff; border: 0; border-radius: 6px; padding: 10px 14px; cursor: pointer; }
            button.secondary { background: #4b5563; }
            .help { font-size: 12px; color: #6b7280; margin-top: 8px; }
        </style>
    </head>
    <body>
        <div class=\"container\">
            <h1>Clinical Trials Chat</h1>
            <div id=\"chat\"></div>
            <div id=\"status\" class=\"help\"></div>
            <div class=\"row\">
                <textarea id=\"input\" placeholder=\"Type a query (e.g., phase 3 diabetes) or 'help'\"></textarea>
            </div>
            <div class=\"row\" style=\"align-items:center; flex-wrap:wrap;\">
                <button id=\"send\">Send</button>
                <button class=\"secondary\" id=\"show\">Show</button>
                <button class=\"secondary\" id=\"clear\">Clear Filters</button>
                <label style=\"display:flex; align-items:center; gap:6px; font-size:12px; color:#374151;\">
                    <input type=\"checkbox\" id=\"agent\" /> Use Agents
                </label>
            </div>
            <div class=\"help\">Commands: help • refine &lt;query&gt; • filter phase=&lt;v&gt; | status=&lt;v&gt; | condition=&lt;v&gt; • more • clear • show</div>
        </div>

        <script>
            const chat = document.getElementById('chat');
            const input = document.getElementById('input');
            const btnSend = document.getElementById('send');
            const btnShow = document.getElementById('show');
            const btnClear = document.getElementById('clear');
            const chkAgent = document.getElementById('agent');
            const statusDiv = document.getElementById('status');

            let state = { query: '', page_size: 5, filters: {}, agent: false };

            function append(role, text) {
                const div = document.createElement('div');
                div.className = 'msg ' + (role === 'user' ? 'user' : 'bot');
                const label = document.createElement('span');
                label.className = 'label';
                label.textContent = role === 'user' ? 'You' : 'Agent';
                const content = document.createElement('span');
                content.className = 'content';
                content.textContent = ' ' + text;
                div.appendChild(label);
                div.appendChild(content);
                chat.appendChild(div);
                chat.scrollTop = chat.scrollHeight;
            }

            function setStatus(s) {
                const filters = s?.filters || {};
                const pieces = [];
                if (s?.query) pieces.push(`query: "${s.query}"`);
                const phase = filters.phase ? `phase=${filters.phase}` : '';
                const st = filters.status ? `status=${filters.status}` : '';
                const cond = filters.condition ? `condition=${filters.condition}` : '';
                const sort = filters.sort ? `sort=${filters.sort}` : '';
                const limit = filters.limit ? `limit=${filters.limit}` : '';
                const fs = [phase, st, cond, sort, limit].filter(Boolean).join(' · ');
                if (fs) pieces.push(fs);
                if (s?.page_size) pieces.push(`pageSize=${s.page_size}`);
                if (s?.refiner) pieces.push('refiner=on');
                if (s?.agent) pieces.push('agent=on');
                statusDiv.textContent = pieces.length ? `State: ${pieces.join(' | ')}` : '';
            }

            function updateShowLabel() {
                const hasText = !!input.value.trim();
                const hasQuery = !!(state?.query && state.query.trim());
                // If there's new text or no current query, it's a fresh fetch => Show
                // If no new text but a current query exists, act as More
                btnShow.textContent = (hasText || !hasQuery) ? 'Show' : 'More';
            }

            // Initialize agent toggle
            chkAgent.checked = !!state.agent;
            chkAgent.addEventListener('change', () => {
                state.agent = chkAgent.checked;
                setStatus(state);
            });

            async function sendMessage(message) {
                append('user', message);
                input.value = '';
                try {
                    const res = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message, state }),
                    });
                    const data = await res.json();
                    state = data.state || state;
                    setStatus(state);
                    updateShowLabel();
                    append('bot', data.reply || '');
                } catch (e) {
                    append('bot', 'Error contacting server.');
                }
            }

            // Send a command silently (no 'You: ...' echo)
            async function sendCommand(message) {
                try {
                    const res = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message, state }),
                    });
                    const data = await res.json();
                    state = data.state || state;
                    setStatus(state);
                    updateShowLabel();
                    append('bot', data.reply || '');
                } catch (e) {
                    append('bot', 'Error contacting server.');
                }
            }

            // Show for a typed query: display the query as the user's message, but send 'show <query>'
            async function sendShowForQuery(q) {
                append('user', q);
                input.value = '';
                state.filters = { ...(state.filters || {}), limit: '10' };
                await sendCommand('show ' + q);
            }

            btnSend.addEventListener('click', () => {
                const text = input.value.trim();
                if (text) sendMessage(text);
            });
            input.addEventListener('input', updateShowLabel);
            btnShow.addEventListener('click', () => {
                const text = input.value.trim();
                if (text) {
                    // One-click: user sees their query, not the 'show' command
                    sendShowForQuery(text);
                    updateShowLabel();
                } else {
                    // No new text: reveal more by bumping the view limit by 10 (max 100)
                    const f = state.filters || {};
                    const current = parseInt((f.limit || '10'), 10);
                    const next = Math.min((isNaN(current) ? 10 : current + 10), 100);
                    state.filters = { ...f, limit: String(next) };
                    // Also increase page_size to ensure the backend fetches enough to show
                    const ps = parseInt(String(state.page_size || '5'), 10);
                    state.page_size = Math.min(Math.max(isNaN(ps) ? 5 : ps, next), 100);
                    // Send silently so the chat doesn't show 'You: show'
                    sendCommand('show');
                }
            });
            btnClear.addEventListener('click', () => sendMessage('clear'));

            // Enter to send (Shift+Enter for newline)
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    const text = input.value.trim();
                    if (text) sendMessage(text);
                }
            });

            // Greet
            append('bot', "Hi! Try 'phase 3 diabetes', '5 most recent lung cancer', or type 'help'.");
            updateShowLabel();
        </script>
    </body>
    </html>
            """
        )

    @app.post("/chat")
    def chat_api():
        try:
            payload = request.get_json(force=True) or {}
        except Exception:
            payload = {}

        message = (payload.get("message") or "").strip()
        state = payload.get("state") or {"query": "", "page_size": 5, "filters": {}}

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
            return jsonify({"reply": f"Query set to: {state['query']}. Click Show.", "state": state})

        if message.lower().startswith("filter "):
            kv = message[7:].strip()
            m = re.match(r"(phase|status|condition)\s*=\s*(.+)", kv, re.I)
            if m:
                k, v = m.group(1).lower(), m.group(2).strip()
                state.setdefault("filters", {})[k] = v
                return jsonify({"reply": f"Filter set: {k}={v}. Click Show.", "state": state})
            return jsonify({"reply": "Use: filter phase=<v>|status=<v>|condition=<v>", "state": state})

        # Toggle refiner
        if message.lower() in {"refiner on", "refiner off"}:
            state["refiner"] = message.lower().endswith("on")
            return jsonify({"reply": f"Refiner set to: {'on' if state['refiner'] else 'off'}.", "state": state})

        # Toggle debug
        if message.lower() in {"debug on", "debug off"}:
            state["debug"] = message.lower().endswith("on")
            return jsonify({"reply": f"Debug set to: {'on' if state.get('debug') else 'off'}.", "state": state})

        # Support "show <query>" as a command to both set and fetch
        if message.lower().startswith("show "):
            state["query"] = message[5:].strip()
            state["filters"] = {}
            message = "show"

        if message.lower() == "more":
            state["page_size"] = min(int(state.get("page_size", 5)) + 10, 100)
            return jsonify({"reply": f"Page size: {state['page_size']}. Click Show.", "state": state})

        if message.lower() == "clear":
            state["filters"] = {}
            return jsonify({"reply": "Filters cleared. Click Show.", "state": state})

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
            result = crew.kickoff(inputs={"query": q, "page_size": int(state.get("page_size", 5))})
            # best effort stringify
            reply = f"{result}"
            return jsonify({"reply": reply, "state": state})

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
                    result = crew.kickoff(inputs={"query": q, "page_size": int(state.get("page_size", 5))})
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
                    use_refiner = (os.getenv("CLINAGENT_REFINE", "0").lower() in {"1", "true", "yes", "on"})

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
                        trials = fetch_trials(alt_q, page_size=max(page_size, limit or 0, 20))
                        trials = apply_filters(
                            trials,
                            phase=str(fdict.get("phase", "")),
                            status=str(fdict.get("status", "")),
                            condition=str(fdict.get("condition", "")),
                        )

                # Sort if requested (e.g., 'recent')
                sort_hint = str(fdict.get("sort", "")).lower()
                if sort_hint in {"recent", "latest", "newest", "last_update"}:
                    trials = sort_trials(trials, key="last_update", descending=True)
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
    parser = argparse.ArgumentParser(description="Clinical trials tool (one-shot or agent mode)")
    parser.add_argument("query", nargs="?", help="Search query (e.g., 'phase 3 diabetes')")
    parser.add_argument("--page-size", type=int, default=5, help="Trials per fetch (default 5)")
    parser.add_argument("--agent", action="store_true", help="Run interactive agent mode")
    parser.add_argument("--web", action="store_true", help="Run minimal web UI on http://127.0.0.1:5000")
    parser.add_argument("--host", default="127.0.0.1", help="Web host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Web port (default 5000)")
    args = parser.parse_args(argv)

    if args.web:
        app = build_web_app()
        app.run(host=args.host, port=args.port, debug=False)
        return 0

    if args.agent:
        q = args.query or input("Enter your goal (e.g., 'phase 3 diabetes trials'): ")
        agent_mode(q, page_size=args.page_size)
        return 0

    # one-shot mode
    q = args.query or input("Enter your question (e.g., 'new phase 3 diabetes trials'): ")
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
