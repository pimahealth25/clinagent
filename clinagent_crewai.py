import os
import json
import argparse
from typing import List, Dict, Any

import requests
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
try:
    from crewai_tools import tool as crewai_tool
except Exception:
    crewai_tool = None
try:
    from crewai_tools import BaseTool as CrewBaseTool  # preferred base type
except Exception:
    CrewBaseTool = None
try:
    # Some versions expose the decorator under crewai.tools
    from crewai.tools import tool as crewai_tool_alt
except Exception:
    crewai_tool_alt = None

load_dotenv()
# Let both names work to match your current env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY")
if not OPENAI_API_KEY:
    print("WARNING: OPENAI_API_KEY not set. Set OPENAI_API_KEY or OPEN_AI_KEY.")

API_URL = "https://clinicaltrials.gov/api/v2/studies"


def _normalize_trials(data: Dict[str, Any]) -> List[Dict[str, str]]:
    trials: List[Dict[str, str]] = []
    for study in data.get("studies", []):
        ps = study.get("protocolSection", {}) or {}
        title = (
            ps.get("identificationModule", {}).get("briefTitle")
            or study.get("BriefTitle")
            or "Untitled"
        )
        phase_list = (
            ps.get("designModule", {}).get("phases")
            or study.get("Phase")
            or []
        )
        status = (
            ps.get("statusModule", {}).get("overallStatus")
            or study.get("OverallStatus")
            or "N/A"
        )
        conditions = (
            ps.get("conditionsModule", {}).get("conditions")
            or study.get("Condition")
            or []
        )
        phase = ", ".join(phase_list) if isinstance(phase_list, list) else str(phase_list)
        condition = ", ".join(conditions) if isinstance(conditions, list) else str(conditions)
        trials.append({
            "title": title or "Untitled",
            "phase": phase or "N/A",
            "status": status or "N/A",
            "condition": condition or "N/A",
        })
    return trials


def _search_clinical_trials(term: str, page_size: int = 5) -> str:
    """Search ClinicalTrials.gov for a term. Returns a JSON string list of trials with title, phase, status, condition."""
    params = {
        "query.term": term,
        "fields": "BriefTitle,Phase,Condition,OverallStatus",
        "pageSize": page_size,
    }
    resp = requests.get(API_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json() if resp.content else {}
    trials = _normalize_trials(data)
    return json.dumps(trials, ensure_ascii=False)


def make_search_tool():
    """Return a CrewAI-compatible tool instance for searching trials.

    Tries, in order:
      1) crewai_tools.tool decorator
      2) crewai.tools.tool decorator
      3) subclassing crewai_tools.BaseTool
    """
    if crewai_tool is not None:
        @crewai_tool("search_clinical_trials")
        def wrapped(term: str, page_size: int = 5) -> str:
            """Search ClinicalTrials.gov for a term. Args: term (str), page_size (int). Returns JSON string list of trials with title, phase, status, condition."""
            return _search_clinical_trials(term, page_size)

        return wrapped

    if crewai_tool_alt is not None:
        @crewai_tool_alt("search_clinical_trials")
        def wrapped_alt(term: str, page_size: int = 5) -> str:
            """Search ClinicalTrials.gov for a term. Args: term (str), page_size (int). Returns JSON string list of trials with title, phase, status, condition."""
            return _search_clinical_trials(term, page_size)

        return wrapped_alt

    if CrewBaseTool is not None:
        class SearchClinicalTrialsTool(CrewBaseTool):
            name: str = "search_clinical_trials"
            description: str = (
                "Search ClinicalTrials.gov for a term. Returns JSON string of trials: "
                "[{title, phase, status, condition}]."
            )

            def _run(self, term: str, page_size: int = 5) -> str:  # type: ignore[override]
                return _search_clinical_trials(term, page_size)

        return SearchClinicalTrialsTool()

    # As a last resort, raise a clear error so the UI can show a helpful message
    raise ImportError(
        "No compatible CrewAI tool interface found. Please upgrade crewai and crewai-tools."
    )


def build_crew(model: str = "gpt-4o-mini") -> Crew:
    search_tool = make_search_tool()

    researcher = Agent(
        role="Clinical Trials Researcher",
        goal="Find the most relevant and up-to-date clinical trials for the user's goal.",
        backstory=(
            "You are skilled at searching ClinicalTrials.gov and extracting key fields like title, phase, "
            "recruitment status, and condition."
        ),
        tools=[search_tool],
        allow_delegation=False,
        verbose=True,
        llm=model,
    )

    writer = Agent(
        role="Medical Writer",
        goal="Summarize trials for a professional audience, focusing on patterns across phases, conditions, and statuses.",
        backstory=(
            "You write concise, clear summaries tailored to clinicians and researchers, highlighting key insights."
        ),
        allow_delegation=False,
        verbose=True,
        llm=model,
    )

    research_task = Task(
        description=(
            "Search ClinicalTrials.gov for: '{query}'. Use the tool to fetch up to {page_size} trials. "
            "Always return a compact JSON array of trials with fields: title, phase, status, condition. "
            "Prefer ongoing studies when the user implies 'ongoing' (e.g., status contains Recruiting)."
        ),
        expected_output=(
            "A JSON array of trial objects: [{\"title\":str, \"phase\":str, \"status\":str, \"condition\":str}, ...]"
        ),
        agent=researcher,
    )

    summary_task = Task(
        description=(
            "Read the JSON trials from the research task. First, output a numbered list of the trials (one per line) "
            "in the format: '<n>. <title> — Phase: <phase> | Status: <status> | Condition: <condition>'. Then provide a "
            "concise professional summary highlighting patterns in phases, conditions, and recruitment statuses."
        ),
        expected_output=(
            "1) A numbered list of the trials, 5-15 items if available, exactly one line per item as specified.\n"
            "2) A short summary paragraph followed by 3-6 bullet highlights."
        ),
        agent=writer,
        context=[research_task],
    )

    return Crew(
        agents=[researcher, writer],
        tasks=[research_task, summary_task],
        process=Process.sequential,
        verbose=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="CrewAI clinical trials agent")
    parser.add_argument("query", nargs="?", help="Search query, e.g. 'phase 3 diabetes trials'")
    parser.add_argument("--page-size", type=int, default=5, help="Number of trials to fetch (default 5)")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model to use (default gpt-4o-mini)")
    args = parser.parse_args()

    q = args.query or input("Enter your goal (e.g., 'phase 3 diabetes trials'): ")
    crew = build_crew(model=args.model)

    result = crew.kickoff(inputs={"query": q, "page_size": args.page_size})
    print("\n=== Agent Result ===\n")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
