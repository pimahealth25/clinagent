from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from core.clinicaltrials import run_full_studies, run_study_fields

load_dotenv()
client = OpenAI()

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
                    "max_studies": {"type": "number"}
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
                    "max_studies": {"type": "number"},
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
    # return app.send_static_file("demo.html")


@app.post("/ask")
def ask():
    '''
    are there any trials on breast cancer that doesn't involve chemotherapy

    sample of input: 
    ser input: {'id': '1764632899771', 'role': 'user', 
    'content': "2 trials on breast cancer that doesn't involve chemotherapy", 'is_streaming': False, 'conversation_id': 2}
    '''
    # user_message = request.json.get("message", "")
    query = request.json.get("message", "")
    user_message = query.get("content", "")

    print("#######################################")
    print(f' user input: {user_message}')
    print("#######################################")

    # ChatGPT will automatically call the MCP tool.
    response = client.chat.completions.create(
        model="gpt-5.1",
        messages=[
            {
                "role": "system",
                "content": (
                    """
                    You are a clinical trial assistant. You convert natural-language questions
                    into valid ClinicalTrials.gov v2 search expressions.

                    STRICT RULES:
                    1. NEVER generate AREA[...] syntax. It is NOT supported in API v2.
                    2. ALWAYS generate Boolean search expressions using:
                    - AND
                    - OR
                    - NOT
                    - Parentheses where needed
                    3. ALWAYS use plain field terms (Condition, Intervention, Phase, Status)
                    but DO NOT wrap them in AREA[...] blocks.
                    4. VALID EXAMPLES OF v2 QUERY SYNTAX:
                    - "Breast Cancer AND NOT Chemotherapy"
                    - "(Lung Cancer) AND (Phase 2)"
                    - "(Breast Cancer) AND (Recruiting)"
                    - "Diabetes AND Metformin AND NOT Insulin"
                    5. Date filters MUST follow API v2 syntax:
                    - StartDate:2025
                    - StartDate:[2024 TO 2026]
                    6. Select the function:
                    - If the user wants summary or basic details → call run_study_fields.
                    - If the user wants full details or comprehensive listing → call run_full_studies.
                    7. ALWAYS keep search expressions compact, free of English phrases.
                    8. NEVER include natural-language explanations in the search query.

                    MAPPING GUIDE:
                    - Condition/Disease → “Breast Cancer”, “Lung Cancer”
                    - Treatment/Intervention → “Chemotherapy”, “Metformin”
                    - Status → “Recruiting”, “Completed”, “Terminated”
                    - Phase → “Phase 1”, “Phase 2”, etc.
                    - Dates → StartDate:YYYY or StartDate:[YYYY TO YYYY]

                    EXAMPLES:
                    - "recruiting breast cancer trials" →
                    "Breast Cancer AND Recruiting"

                    - "phase 2 lung cancer studies starting in 2025" →
                    "Lung Cancer AND Phase 2 AND StartDate:2025"

                    """

                )
            },
            {"role": "user", "content": user_message}
        ],
        tools=TOOLS,
        tool_choice="auto"
    )

    msg = response.choices[0].message
    print("#######################################")
    print(f'mesg: {msg}')
    print("#######################################")

    # No tool call → Just reply normally
    if not msg.tool_calls:
        return jsonify({"response": msg.content})

    tool_call = msg.tool_calls[0]
    func_name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    print("#######################################")
    print(f"function: {func_name} arg: {args}")
    print("#######################################")

    result = ''
    # Run actual Python function locally
    if func_name == "run_full_studies":
        result = run_full_studies(**args)
    elif func_name == "run_study_fields":
        result = run_study_fields(**args)
    else:
        return jsonify({"response": f"Unknown function: {func_name}"})

    # Summarize the result
    summary = client.chat.completions.create(
        model="gpt-5.1",
        messages=[
            {"role": "system",  "content": (
                """
                You are a medical research assistant. Summarize the clinical study data provided to you.

                Guidelines:
                Output clean Markdown only.
                Do not mention external websites or sources.
                Do not instruct the user to search anywhere.
                Do not speculate about missing data.
                If the list is empty, respond:
                No studies matched the criteria.
                Group summaries using meaningful medical patterns (phase, condition, interventions).
                Do not reference tools, schemas, or the system.
                No disclaimers or meta commentary.
                """

            )},
            {"role": "user", "content": (
                f"User query: {user_message}\n\n"
                f"Study results returned from ClinicalTrials.gov:\n{json.dumps(result, indent=2)}"
            )}
        ]
    )

    print("#######################################")
    print(f'summary: {str(summary)[:100]}')
    print("#######################################")

    return jsonify({
        "response": summary.choices[0].message.content,
        "raw_data": result
    })


if __name__ == "__main__":
    app.run(debug=True)
