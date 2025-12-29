from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime, timezone
import os
import json
from core.clinicaltrials import run_full_studies, run_study_fields
from core.preprocessor import resolve_field_set, shrink_trials, normalize_field_names, load_studies_from_csv
from core.tasks import orchestrate_task, CELERY_AVAILABLE
from core.cache import (_make_key, get_cached_summary, get_cached_raw, set_cached_raw,
                        set_cached_summary, clear_all_caches, get_job_status, get_final_summary, set_job_status, get_chunk_summary)
from core.llm import summarize_studies_json
from core.utils import calculate_chunk_progress_percentage

clear_all_caches()

load_dotenv()
_CHUNK_SUMMARIZER_OPENAI_MODEL = os.getenv(
    "CHUNK_SUMMARIZER_MODEL") or "gpt-3.5-turbo"
_GENERAL_OPENAI_MODEL = os.getenv("FINAL_SUMMARIZER_MODEL") or "gpt-4.1-mini"
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY")
client = OpenAI(api_key=_OPENAI_API_KEY) if _OPENAI_API_KEY else None
_CHUNK_SIZE = int(os.getenv("CHUNK_SIZE")) or 5
_NO_CHUNK_AI_PROMPT = _CHUNK_MODEL_PROMPT = ("""
You are a clinical research  summarizer.

You are given a clinical trial records.

──────────────── OUTPUT RULES ────────────────
• Format: Markdown only
• Facts only — never infer or hallucinate
• Omit missing or empty fields

──────────────── TRIAL FORMAT ────────────────
Include a trial ONLY if at least one meaningful field exists.

For each trial, include ONLY available fields:
• **NCTId**  
  Format: NCTId (link format: [NCTxxxxx](https://clinicaltrials.gov/study/NCTxxxxx))\n"
• **Title**
• **Condition(s)**
• **Phase**
• **Study Type**
• **Interventions**
• **Overall Status**
• **Start Date**

──────────────── FORMATTING ────────────────
• Use bullet points
• Max 4–6 lines per trial
• Bold Phase, Status, Interventions
• No emojis, no commentary

──────────────── EDGE CASES ────────────────
• Empty content → return: “No studies in this page.”

──────────────── INPUT ────────────────
Below is the content of trial data to summarize.

""")


# clear_all_caches()

app = Flask(__name__, static_url_path="", static_folder="static")


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_full_studies",
            "description": "Retrieve complete detailed studies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_expr": {"type": "string"},
                    "max_studies": {"type": "number", "default": 10, "maximum": 50},
                },
                "required": ["search_expr"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_study_fields",
            "description": "Retrieve specific fields for studies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_expr": {"type": "string"},
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "max_studies": {"type": "number", "default": 50, "maximum": 200},
                    "fmt": {"type": "string"}
                },
                "required": ["search_expr", "fields"]
            }
        }
    }
]


@app.get("/")
def index():
    return render_template("demo.html")


@app.post("/ask")
def ask():
    '''
    are there any trials on breast cancer that doesn't involve chemotherapy

    sample of input:
    ser input: {'id': '1764632899771', 'role': 'user',
    'content': "2 trials on breast cancer that doesn't involve chemotherapy", 'is_streaming': False, 'conversation_id': 2}
    '''
    query = request.json.get("message", "")
    user_message = query.get("content", "") if isinstance(
        query, dict) else str(query)

    print(f"[ASK] User input: {user_message[:80]}...")

    # ===== STAGE 1: GENERATE SEARCH EXPRESSION =====
    try:
        response = client.chat.completions.create(
            model=_GENERAL_OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content":
                    ("""
                   You are a clinical trial assistant. You convert natural-language questions
                    into valid ClinicalTrials.gov API v2 Boolean search expressions.

                    STRICT RULES:
                    1. NEVER generate AREA[...] syntax. It is NOT supported.
                    2. NEVER generate field-prefixed filters like Status:Recruiting, Condition:Breast Cancer, Phase:2, etc.
                    3. The ONLY allowed field-prefixed syntax is date ranges:
                    - StartDate:YYYY
                    - StartDate:[YYYY TO YYYY]
                    4. ALL OTHER TERMS must be plain text combined with Boolean logic:
                    - AND
                    - OR
                    - NOT
                    - Parentheses when needed
                    5. VALID QUERY EXAMPLES:
                    - "Breast Cancer AND NOT Chemotherapy"
                    - "Melanoma AND Stage 3 AND Recruiting"
                    - "(Lung Cancer) AND (Phase 2)"
                    - "Diabetes AND Metformin AND NOT Insulin"
                    - "Breast Cancer AND Recruiting AND StartDate:[2023 TO 2025]"
                    6. Select the function:
                    - If user wants summary/basic details → call run_study_fields
                    - If user wants full details/full listing → call run_full_studies
                    7. Output ONLY the compact Boolean search expression. No explanations.

                    MAPPING:
                    - Diseases → plain (e.g., “Breast Cancer")
                    - Interventions → plain (e.g., “Chemotherapy", “Metformin")
                    - Status → plain (e.g., “Recruiting”, “Completed”)
                    - Phases → plain (e.g., “Phase 1”, “Phase 2”)

                    EXAMPLES:
                    User: "recruiting breast cancer trials"
                    → "Breast Cancer AND Recruiting"
                    """
                     )
                },
                {"role": "user", "content": user_message}
            ],
            tools=TOOLS,
            tool_choice="required"
        )

        msg = response.choices[0].message
        print("#######################################")
        print(f'mesg: {msg}')
        print("#######################################")

    except Exception as e:
        return jsonify({"error": f"Failed to generate search expression: {str(e)}"}), 500

    # No tool call → Just reply normally
    if not msg.tool_calls:
        return jsonify({"response": msg.content})

    tool_call = msg.tool_calls[0]
    func_name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    search_expr = args.get("search_expr", "")
    max_studies = args.get("max_studies", 10)

    print(f"[ASK] Function: {func_name}")
    print(f"[ASK] Search expr: {search_expr}")

    # ===== STAGE 2: RESOLVE FIELD SET =====
    field_names = resolve_field_set(args.get("fields", "essential"))

    # ===== STAGE 3: CHECK CACHE FOR SUMMARY =====
    job_id = _make_key("query", search_expr, json.dumps(
        sorted(field_names)) or [], _GENERAL_OPENAI_MODEL)
    print(f"[ASK] Generated job_id: {job_id}")

    cached_summary = get_cached_summary(job_id=job_id)

    if cached_summary:
        print("[ASK] ✓ CACHE HIT: summary found")
        return jsonify({
            "job_id": job_id,
            "status": "done",
            "summary": cached_summary,
            "from_cache": True,
            "cache_type": "summary",
            "message": "Summarization completed.",
            "updated_at": str(datetime.now(timezone.utc))
        })

    # ===== STAGE 4: CHECK CACHE FOR RAW RESULTS =====
    cached_raw = get_cached_raw(job_id, max_studies)

    if cached_raw:
        print(
            f"[ASK] ✓ CACHE HIT: raw results found ({len(cached_raw)} studies)")
        result = cached_raw
    else:
        # ===== STAGE 5: FETCH FROM API =====
        print("[ASK] CACHE MISS: fetching from API...")
        try:
            if func_name == "run_full_studies":
                result = run_full_studies(search_expr, max_studies=max_studies)
            elif func_name == "run_study_fields":
                # Pass resolved field names
                result = run_study_fields(
                    search_expr=search_expr,
                    fields=field_names or [],
                    max_studies=max_studies
                )
            else:
                return jsonify({"error": f"Unknown function: {func_name}"}), 400

            # Cache the raw results and return the hashed key
            set_cached_raw(job_id, max_studies, result)
            print(f"[ASK] ✓ Fetched {len(result)} studies and cached")
        except Exception as e:
            print(f"[ASK] ✗ Fetch failed: {e}")
            return jsonify({"error": f"Failed to fetch studies: {str(e)}"}), 500

    print(f"[ASK] ✓ Fetched result {str(result)[:80]} ")

    if not result:
        return jsonify({
            "response": "No studies matched the criteria.",
            "raw_data": [],
            "status": "done"
        })

    # ===== STAGE 6: PREPROCESS WITH FIELD NORMALIZATION =====
    # Normalize field names from CSV (snake_case) to API format (PascalCase)
    result_normalized = [normalize_field_names(trial) for trial in result]
    result_shrunken = shrink_trials(
        result_normalized, field_names, normalize=False)
    pages = (len(result_shrunken) + _CHUNK_SIZE - 1) // _CHUNK_SIZE
    print(
        f"[ASK] ✓ Normalized {len(result)} studies, shrunk to {len(result_shrunken)} with requested fields, total pages: {pages}")

    # ===== STAGE 7: DECIDE INLINE VS BACKGROUND =====
    if len(result) > 5 and CELERY_AVAILABLE:

        # Enqueue background job and return job_id
        print(f"[ASK] Enqueueing chunked pipeline job...")
        try:
            job = orchestrate_task(
                job_id=job_id,
                query=search_expr,
                studies=result_shrunken,
                chunk_size=_CHUNK_SIZE,
                model_chunk=_CHUNK_SUMMARIZER_OPENAI_MODEL,
                model_aggregate=_GENERAL_OPENAI_MODEL
            )

            set_job_status(
                job_id=job_id,
                status="created",
                total_chunks=pages
            )

            print(f"[ASK] ✓ Job  {job_id} enqueued: an status initialized...")
            return jsonify({
                "job_id": job_id,
                "status": "created",
                "chunk_index": 1,  # 1-based index for frontend
                "total_chunks": pages,
                "message": f"Summarizing {len(result)} studies in background ..."
            })
        except Exception as e:
            print(
                f"[ASK] ✗ Failed to enqueue job: {e}. Falling back to inline.")

    # ===== STAGE 8: INLINE SUMMARIZATION =====
    print(f"[ASK]  Inline summarization (small dataset)...")
    try:
        summary = summarize_studies_json(
            query=search_expr,
            studies=result_shrunken,
            model=_GENERAL_OPENAI_MODEL,
            system_prompt=_NO_CHUNK_AI_PROMPT
        )

        set_cached_summary(job_id, summary)
        set_job_status(
            job_id=job_id,
            status="done",
            chunk_index=pages,
            total_chunks=pages,
        )

        print(
            f"[ASK] ✓ Summary generated and cached {str(summary)[:100]}...")

        return jsonify({
            "job_id": job_id,
            "status": "done",
            "summary": summary,
            "chunk_index": pages,
            "total_chunks": pages,
            "message": "Summarization completed.",
            "updated_at": str(datetime.now(timezone.utc))
        })

    except Exception as e:
        print(f"[ASK] ✗ Summarization failed: {e}")
        summary = f"Could not summarize: {str(e)}"
        return jsonify({
            "job_id": job_id,
            "status": "error",
            "message": f"Summarization failed: {str(e)}"}), 500


@app.get("/app_status")
def status():
    return jsonify({"status": "active!!!"})


@app.get("/job_status")
def job_status():
    '''{"completed_chunks":[2,3,4],"job_id":"query:9d1024c333276f46","progress_pct":75,"status":"processing","total_chunks":4,"updated_at":"2025-12-29 14:04:40.612075+00:00"}
    '''
    job_id = request.args.get("job_id").strip()
    if not job_id:
        return jsonify({"error": "Missing Job_id parameter"}), 400

    job_info = get_job_status(job_id)
    print(f"[job status]: {str(job_info)[:200]}")

    if not job_info:
        return jsonify({"status": "not_found", "job_id": job_id}), 404

    progress_pct = calculate_chunk_progress_percentage(job_info)

    response = {
        "job_id": job_id,
        "status": job_info.get("status"),
        "completed_chunks": job_info.get("completed_chunks", []),
        "total_chunks": job_info.get("total_chunks", 0),
        "progress_pct": round(progress_pct, 1),
        "updated_at": job_info.get("updated_at")
    }

    return jsonify(response)


@app.get("/chunk_page/<job_id>")
def chunk_page(job_id: str):
    """
    Retrieve a specific chunk summary.
    job_id: str - The job identifier.
    page: int - The chunk page number ( 1-based).
    """
    page = request.args.get("page", 1, type=int)
    chunk = get_chunk_summary(job_id, page=page)

    if chunk is None:
        return jsonify({"job_id": job_id, "status": "error", "message": "Job not found"}), 404

    return jsonify({"job_id": job_id, "status": "done", "chunk_summary": chunk, "page": page})


@app.get("/final_summary")
def final_summary():

    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "Missing job_id"}), 400

    summary = get_final_summary(job_id)

    if not summary:
        return jsonify({"error": "Summary not found"}), 404

    return jsonify(summary)


@app.get("/cache_inspect")
def cache_inspect():
    from core.cache import cache_stats
    stats = cache_stats()
    return jsonify(stats)


if __name__ == "__main__":
    app.run(debug=True)
