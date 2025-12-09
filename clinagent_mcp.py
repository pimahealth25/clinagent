from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from core.clinicaltrials import run_full_studies, run_study_fields
from core.preprocessor import resolve_field_set, shrink_trials, load_studies_from_csv
from core.preprocessor import normalize_field_names
from core.tasks import summarize_incrementally
from core.cache import get_cached_summary, get_cached_raw, set_cached_raw, set_cached_summary, clear_all_caches, redis_client
from core.llm import summarize_studies_json

load_dotenv()
_CHUNK_SUMMARIZER_OPENAI_MODEL = os.getenv(
    "CHUNK_SUMMARIZER_MODEL") or "gpt-3.5-turbo"
_GENERAL_OPENAI_MODEL = os.getenv("FINAL_SUMMARIZER_MODEL") or "gpt-4.1-mini"
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY")
client = OpenAI(api_key=_OPENAI_API_KEY) if _OPENAI_API_KEY else None

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
    job_mode = args.get("job_mode", "inline")
    max_studies = args.get("max_studies", 10)

    print(f"[ASK] Function: {func_name}")
    print(f"[ASK] Search expr: {search_expr}")

    # ===== STAGE 2: RESOLVE FIELD SET =====
    field_names = resolve_field_set(args.get("fields", "essential"))

    # ===== STAGE 3: CHECK CACHE FOR SUMMARY =====
    cached_summary = get_cached_summary(
        search_expr, field_names or [], _GENERAL_OPENAI_MODEL)

    if cached_summary:
        print("[ASK] ✓ CACHE HIT: summary found")
        return jsonify({
            "response": cached_summary,
            "from_cache": True,
            "cache_type": "summary"
        })

    # ===== STAGE 4: CHECK CACHE FOR RAW RESULTS =====
    cached_raw = get_cached_raw(search_expr, max_studies, field_names or [])

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

            # Cache the raw results
            set_cached_raw(search_expr, max_studies,
                           field_names or [], result, ttl=600)
            print(f"[ASK] ✓ Fetched {len(result)} studies and cached")
        except Exception as e:
            print(f"[ASK] ✗ Fetch failed: {e}")
            return jsonify({"error": f"Failed to fetch studies: {str(e)}"}), 500

    print(f"[ASK] ✓ Fetched result {str(result)[:80]} ")

    if not result:
        return jsonify({
            "response": "No studies matched the criteria.",
            "raw_data": []
        })

    '''
    # [test] parse the csv record from study_fields.csv file
    result = load_studies_from_csv(
        "study_fields.csv", filter_condition="Breast Cancer", max_records=10)

    field_names = ['NCTId', 'BriefTitle', 'OverallStatus',
                   'Condition', 'Phase', 'StudyType', 'StartDate']
    job_mode = "inline"
    search_expr = "Breast Cancer AND NOT Chemotherapy"
    '''

    # ===== STAGE 6: PREPROCESS WITH FIELD NORMALIZATION =====
    # Normalize field names from CSV (snake_case) to API format (PascalCase)
    result_normalized = [normalize_field_names(trial) for trial in result]
    result_shrunken = shrink_trials(
        result_normalized, field_names, normalize=False)
    print(
        f"[ASK] ✓ Normalized {len(result)} studies, shrunk to {len(result_shrunken)} with requested fields")

    # ===== STAGE 7: DECIDE INLINE VS BACKGROUND =====
    if job_mode == "background" or len(result) > 20:
        # Enqueue background job and return job_id
        print(f"[ASK] Enqueueing background summarization job...")
        try:
            job = summarize_incrementally.delay(
                query=search_expr,
                studies=result_shrunken,
                fields=field_names or [],
                model=_GENERAL_OPENAI_MODEL
            )

            print(f"[ASK] ✓ Job enqueued: {job.id}")
            return jsonify({
                "status": "processing",
                "job_id": str(job.id),
                "num_studies": len(result),
                "message": f"Summarizing {len(result)} studies in background..."
            })
        except Exception as e:
            print(
                f"[ASK] ✗ Failed to enqueue job: {e}. Falling back to inline.")
            job_mode = "inline"

    # ===== STAGE 8: INLINE SUMMARIZATION (if mode = "inline") =====
    if job_mode == "inline":
        print(f"[ASK] Inline summarization...")
        try:
            summary = summarize_studies_json(
                query=search_expr,
                studies=result_shrunken,
                model=_GENERAL_OPENAI_MODEL,
            )

            set_cached_summary(search_expr, field_names or [],
                               _GENERAL_OPENAI_MODEL, summary)
            print(
                f"[ASK] ✓ Summary generated and cached {str(summary)[:100]}...")
        except Exception as e:
            print(f"[ASK] ✗ Summarization failed: {e}")
            summary = f"Could not summarize: {str(e)}"

        return jsonify({
            "response": summary,
            "raw_data": result,
            "num_studies": len(result)
        })

    print("#######################################")
    print(f'summary: {str(summary)[:100]}')
    print("#######################################")

    return jsonify({
        "response": summary,
        "raw_data": result
    })


@app.get("/status")
def status():
    return jsonify({"status": "active!!!"})


# @app.get("/all_job_status")
# def all_jobs_status():
#     """
#     Poll for background job status.

#     GET /status?job_id=<job_id>

#     Returns:
#         {
#             "status": "processing" | "done" | "error",
#             "result": <summary_string>,  # only if done
#             "error": <error_message>,    # only if error
#             "chunks_processed": <int>    # only if done
#         }
#     """
#     from core.tasks import summarize_incrementally

#     job_id = request.args.get("job_id")
#     if not job_id:
#         return jsonify({"error": "Missing job_id parameter"}), 400

#     try:
#         result = summarize_incrementally.AsyncResult(job_id)

#         if result.state == "PENDING":
#             return jsonify({"status": "processing"})
#         elif result.state == "SUCCESS":
#             return jsonify({
#                 "status": "done",
#                 "result": result.result
#             })
#         elif result.state == "FAILURE":
#             return jsonify({
#                 "status": "error",
#                 "error": str(result.info)
#             })
#         else:
#             return jsonify({"status": result.state})
#     except Exception as e:
#         return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/job/<job_id>/status")
def job_status(job_id):
    '''{
    "job_id": "029c71f5-0f6e-4b09-8e68-3f0b9584cdde",
    "message": "Summarizing 50 studies in background...",
    "num_studies": 50,
    "status": "processing"
}
'''
    meta = redis_client.hgetall(f"job:{job_id}:meta")
    return jsonify(meta)


@app.get("/cache_inspect")
def cache_inspect():
    from core.cache import cache_stats
    stats = cache_stats()
    return jsonify(stats)


if __name__ == "__main__":
    app.run(debug=True)
