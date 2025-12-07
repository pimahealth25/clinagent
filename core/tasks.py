"""
Background task queue for incremental summarization.
Uses Celery + Redis as broker (optional; gracefully degrades).

Tasks:
  - summarize_incrementally: Chunk studies and summarize incrementally
"""

import json
from typing import List, Dict, Any

try:
    from celery import Celery, Task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    print("⚠️  Celery not installed. Async tasks disabled.")
    print("   Install via: pip install celery[redis]")


# ===== CELERY APP INITIALIZATION =====

celery_app = None

if CELERY_AVAILABLE:
    try:
        celery_app = Celery(
            "clinagent",
            broker="redis://localhost:6379/0",
            backend="redis://localhost:6379/0"
        )

        celery_app.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="UTC",
            enable_utc=True,
            task_track_started=True,
            task_time_limit=30 * 60,  # 30 min hard limit
            task_soft_time_limit=25 * 60,  # 25 min soft limit
        )
        print("✓ Celery task queue initialized (async mode)")
    except Exception as e:
        print(f"⚠️  Celery broker connection failed: {e}")
        print("   Async tasks disabled. Install Redis for async support.")
        celery_app = None


# ===== FALLBACK: SYNCHRONOUS SUMMARIZATION =====

def _summarize_sync(
    query: str,
    studies: List[Dict],
    fields: List[str],
    model: str = "gpt-3.5-turbo"
) -> Dict[str, Any]:
    """Synchronous fallback summarization (used if Celery unavailable)."""
    print(f"[Sync] Summarizing {len(studies)} studies synchronously...")

    try:
        from core.llm import summarize_studies_json
        from core.cache import set_cached_summary

        final_summary = summarize_studies_json(
            query=query,
            studies=studies,
            model=model,
            max_tokens=800
        )

        # Cache result
        set_cached_summary(query, fields, model, final_summary, ttl=1800)

        return {"status": "done", "summary": final_summary}
    except Exception as e:
        print(f"[Sync] ✗ Summarization failed: {e}")
        return {"status": "error", "error": str(e)}


# ===== CELERY TASK =====

if CELERY_AVAILABLE and celery_app:

    @celery_app.task(bind=True, name="core.tasks.summarize_incrementally")
    def summarize_incrementally(
        self,
        query: str,
        studies: List[Dict],
        fields: List[str],
        model: str = "gpt-3.5-turbo"
    ) -> Dict[str, Any]:
        """
        Summarize studies incrementally by chunking and aggregating.

        Reduces LLM token usage and allows faster feedback.

        Args:
            query: user's original query / search expression
            studies: list of study dicts (already preprocessed)
            fields: field names used (for caching)
            model: LLM model to use

        Returns:
            dict with status, summary, and chunks_processed
        """
        from core.llm import summarize_studies_json
        from core.cache import set_cached_summary

        CHUNK_SIZE = 5  # Process 5 studies per chunk

        if not studies:
            summary = "No studies matched the criteria."
            set_cached_summary(query, fields, model, summary)
            return {"status": "done", "summary": summary, "chunks_processed": 0}

        print(
            f"\n[Task {self.request.id}] Summarizing {len(studies)} studies (model={model})...")

        # ===== STAGE 1: CHUNK & SUMMARIZE CHUNKS =====
        chunks = [studies[i:i+CHUNK_SIZE]
                  for i in range(0, len(studies), CHUNK_SIZE)]
        chunk_summaries = []

        print(
            f"[Task {self.request.id}] Stage 1: Processing {len(chunks)} chunks of {CHUNK_SIZE}...")

        for idx, chunk in enumerate(chunks, 1):
            try:
                # Update task state to show progress
                self.update_state(
                    state="PROGRESS",
                    meta={"current": idx, "total": len(chunks)}
                )

                partial = summarize_studies_json(
                    query=query,
                    studies=chunk,
                    model=model,
                    max_tokens=250,
                    system_prompt=(
                        "You are a medical research assistant. "
                        "Summarize this batch of clinical trials concisely. "
                        "Output clean Markdown only."
                    )
                )
                chunk_summaries.append(partial)
                print(
                    f"[Task {self.request.id}] ✓ Chunk {idx}/{len(chunks)} summarized")

            except Exception as e:
                print(f"[Task {self.request.id}] ✗ Chunk {idx} failed: {e}")
                return {"status": "error", "error": str(e), "chunks_processed": idx - 1}

        # ===== STAGE 2: AGGREGATE CHUNK SUMMARIES =====
        print(
            f"[Task {self.request.id}] Stage 2: Aggregating {len(chunk_summaries)} summaries...")

        try:
            # Prepare aggregation input
            agg_input = [
                {"chunk_index": i+1, "summary": s}
                for i, s in enumerate(chunk_summaries)
            ]

            final_summary = summarize_studies_json(
                query=query,
                studies=agg_input,
                model=model,
                max_tokens=600,
                system_prompt=(
                    "You are a medical research assistant. "
                    "Synthesize the following chunk summaries into one cohesive Markdown summary. "
                    "Eliminate redundancy while preserving all key findings. "
                    "Output clean Markdown only."
                )
            )
            print(f"[Task {self.request.id}] ✓ Final summary generated")

        except Exception as e:
            print(f"[Task {self.request.id}] ✗ Aggregation failed: {e}")
            return {"status": "error", "error": str(e), "chunks_processed": len(chunks)}

        # ===== STAGE 3: CACHE RESULT =====
        try:
            set_cached_summary(query, fields, model, final_summary, ttl=1800)
            print(f"[Task {self.request.id}] ✓ Summary cached")
        except Exception as e:
            print(f"[Task {self.request.id}] ⚠️  Caching failed: {e}")
            # Still return success even if cache fails

        return {
            "status": "done",
            "summary": final_summary,
            "chunks_processed": len(chunks)
        }

else:
    # Celery not available; create a dummy task
    def summarize_incrementally(
        query: str,
        studies: List[Dict],
        fields: List[str],
        model: str = "gpt-3.5-turbo"
    ) -> Dict[str, Any]:
        """Synchronous fallback (Celery not available)."""
        return _summarize_sync(query, studies, fields, model)

    class DummyAsyncResult:
        """Simulate Celery AsyncResult when Celery unavailable."""

        def __init__(self, job_id):
            self.job_id = job_id
            self.state = "FAILURE"
            self.info = "Celery not configured"

    # Mock the task.delay() method
    summarize_incrementally.delay = lambda *args, **kwargs: DummyAsyncResult(
        None)
    summarize_incrementally.AsyncResult = lambda job_id: DummyAsyncResult(
        job_id)


# ===== UTILITY FUNCTIONS =====

def submit_summarization_job(
    query: str,
    studies: List[Dict],
    fields: List[str],
    model: str = "gpt-3.5-turbo"
) -> Dict[str, Any]:
    """
    Submit a summarization job (async if Celery available, sync otherwise).

    Args:
        query: search expression
        studies: list of study dicts
        fields: field names
        model: LLM model

    Returns:
        dict with job_id (async) or status (sync)
    """

    if CELERY_AVAILABLE and celery_app:
        try:
            job = summarize_incrementally.delay(
                query=query,
                studies=studies,
                fields=fields,
                model=model
            )
            return {
                "status": "submitted",
                "job_id": str(job.id),
                "mode": "async"
            }
        except Exception as e:
            print(
                f"[Submit] ✗ Failed to submit async job: {e}. Falling back to sync.")

    # Fallback to synchronous
    print(f"[Submit] Using synchronous summarization (Celery unavailable)...")
    result = _summarize_sync(query, studies, fields, model)
    return {
        "status": result.get("status"),
        "summary": result.get("summary"),
        "mode": "sync",
        "error": result.get("error")
    }


def get_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get status of a submitted job.

    Args:
        job_id: job ID returned from submit_summarization_job

    Returns:
        dict with status ("processing", "done", "error") and result
    """
    if not CELERY_AVAILABLE or not celery_app:
        return {"status": "error", "error": "Celery not available"}

    try:
        from celery.result import AsyncResult
        result = AsyncResult(job_id, app=celery_app)

        if result.state == "PENDING":
            return {"status": "processing"}
        elif result.state == "SUCCESS":
            return {
                "status": "done",
                "result": result.result
            }
        elif result.state == "FAILURE":
            return {
                "status": "error",
                "error": str(result.info)
            }
        elif result.state == "PROGRESS":
            return {
                "status": "processing",
                "progress": result.info
            }
        else:
            return {"status": result.state}
    except Exception as e:
        return {"status": "error", "error": str(e)}
