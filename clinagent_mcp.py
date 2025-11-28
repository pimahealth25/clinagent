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
    '''
    user_message = request.json.get("message", "")

    # ChatGPT will automatically call the MCP tool.
    response = client.chat.completions.create(
        model="gpt-5.1",
        messages=[
            {
                "role": "system",
                "content": ("""You are a clinical trial assistant. You convert natural-language queries
                            into valid ClinicalTrials.gov search expressions.

                            Rules:
                            1. ALWAYS construct valid ClinicalTrials.gov AREA[...] expressions.
                            2. NEVER pass plain English text directly as a search term.
                            3. Map user intent:
                            - Condition -> AREA[Condition]
                            - Disease -> AREA[Condition]
                            - Status -> AREA[OverallStatus]
                            - Phase -> AREA[Phase]
                            - Start year or date -> AREA[StartDate]
                            4. For years, use RANGE:
                            - Example: 2025 -> AREA[StartDate]RANGE[2025, 2025]
                            - “2024–2026” -> AREA[StartDate]RANGE[2024, 2026]
                            5. If user wants detailed study info → call run_full_studies
                            6. If user wants summary → call run_study_fields
                            7. Always use AND between conditions.

                            Examples:
                            - "recruiting breast cancer trials" ->
                            AREA[Condition]Breast Cancer AND AREA[OverallStatus]Recruiting

                            - "phase 2 lung cancer studies starting in 2025" →
                            AREA[Condition]Lung Cancer AND AREA[Phase]Phase 2
                            AND AREA[StartDate]RANGE[2025, 2025]"""
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
                You are an internal medical research assistant. Summarize clinical study data already retrieved.

                Rules:
                1. Do NOT mention sources or websites.
                2. Do NOT instruct the user to search externally.
                3. Do NOT speculate on missing data.
                4. If no studies match, return: "No studies matched the criteria."
                5. Summarize studies grouped by patterns (phase, condition, intervention type).
                6. Do NOT reference the system, tools, or schemas.
                7. Avoid disclaimers or meta commentary.

                OUTPUT FORMAT (MANDATORY):
                - Return only valid JSON with a root "blocks" array.
                - Allowed block types: "heading", "paragraph", "bullet_list", "card", "section".
                - Nest blocks using "blocks" arrays inside sections or cards.
                - Headings may have optional "level" (1-6); cards may have optional "subtitle".
                - Bullet lists use "bullets" arrays of strings only.
                - Convert label/value pairs into paragraph blocks inside the parent card.
                - Unknown or novel sections must still be blocks.
                - Never use markdown or text outside JSON.
                - Output must be self-contained, fully following the block schema recursively.

                Efficiency guidance:
                - Include only actual values; omit empty fields.
                - Focus on essential details: study id, title, phase, status, condition, interventions, start/completion dates, primary focus.
                - Use concise paragraph text.
                - Bullet lists summarize patterns or key highlights across multiple studies only.
                - Avoid repetitive placeholders like "Not specified" unless necessary for clarity.
                - Preserve all meaningful study information while minimizing token usage.
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


"""

"""
