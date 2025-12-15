"""
Background task queue for incremental summarization.
Uses Celery + Redis as broker (optional; gracefully degrades).
celery -A your_module_name worker --loglevel=info
Tasks:
  - summarize_chunk: Chunk studies and summarize incrementally
    - aggregate_chunks: Combine chunk summaries into final summary
    - orchestrate_task: Orchestrate chunking, summarization, aggregation

"""

import json
import os
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv
from core.llm import summarize_studies_json
from core.pipeline import (chunk_studies, validate_chunk_config)
from core.cache import get_cached_summary, set_cached_summary, get_cached_chunk_summary, set_cached_chunk_summary, set_job_status
load_dotenv()

logger = logging.getLogger("celery.task")

try:
    from celery import Celery, group, chain, chord
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

    @celery_app.task(bind=True, name="core.tasks.summarize_chunk")
    def summarize_chunk(
        self, job_id: str, chunk_index: int, chunk_data: List[Dict[str, Any]],
        query: str, total_chunks: int, model: str = "gpt-4.1-mini"
    ) -> Dict[str, Any]:

        logger.info(
            f"[TASK] Summarizing chunk {chunk_index} of job {job_id}...")

        try:
            summary = summarize_studies_json(
                query=query, studies=chunk_data, model=model,
            )
            logger.info(f"[TASK] Chunk {chunk_index} summary generated")
            set_cached_chunk_summary(job_id, chunk_index=chunk_index, chunk_summary=summary)
            set_job_status(
                job_id=job_id,
                status="processing",
                chunk_completed=chunk_index+1,
                total_chunks=total_chunks,
                summary=summary
            )

            logger.info(
                f"[TASK] ✓ Chunk {chunk_index} / {total_chunks} of job {job_id} completed and cached")

            return {
                "job_id":job_id,
                "status": "done",
                "chunk_index": chunk_index,
                "summary": summary[:100]
            }

        except Exception as e:
            logger.error(
                f"[TASK] ✗ chunk {chunk_index} / {total_chunks} of job {job_id} failed: {e}")

            return {
                "job_id":job_id,
                "status": "error",
                "chunk_index": chunk_index,
                "error": str(e)
            }

    @celery_app.task(name="core.tasks.aggregate_chunks")
    def aggregate_chunks(results, *,job_id: str, total_chunks: int, query: str, model: str = "gpt-4.1-mini") -> Dict[str, Any]:
        """
         Aggregate all chunk summaries into a final summary.

         Args:
             job_id: The pipeline job ID
             total_chunks: Total number of chunks
             query: Original search query
             model: Fast model for aggregation

         Returns:
             Final aggregated summary

         Behavior:
             - Retrieves all chunk summaries from cache
             - Combines them with fast model
             - Stores final result in cache
             - Returns to user via job polling
         """
        logger.info(
            f"[TASK] Aggregating {total_chunks} chunks for job {job_id}...")
        try:
            chunk_summaries = []
            for i in range(total_chunks):
                data = get_cached_chunk_summary(job_id, chunk_index=i)
                if not data:
                    raise ValueError(
                        f"Missing chunk summary for chunk {i} in job {job_id}")
                chunk_summaries.append(data)

            if not chunk_summaries:
                raise ValueError("No chunk summaries was found to aggregate")

            final_sys_prompt = """
            You are summarizing clinical trial search results.

            Below are summaries of trial chunks. Combine them into a single,
            coherent markdown summary that:
            1. Eliminates redundancy
            2. Preserves key findings from all chunks
            3. Organizes by trial status/phase
            4. Includes practical insights for the user
            5. Keeps format professional and scannable

            CHUNK SUMMARIES TO COMBINE

            OUTPUT: Single cohesive markdown summary
            """

            final_summary = summarize_studies_json(
                query=query, studies=chunk_summaries, model=model, system_prompt=final_sys_prompt)

            set_cached_summary(job_id, summary=final_summary)
            set_job_status(
                job_id=job_id,
                status="done",
                chunk_completed=total_chunks,
                total_chunks=total_chunks,
                summary=final_summary,
            )
            logger.info(f"[TASK] ✓ Aggregation complete for job {job_id}")
            print(f"[TASK] Final Summary: {final_summary[:200]}...")

            return {
                "status": "done",
                "job_id": job_id,
                "summary": final_summary
            }

        except Exception as e:
            logger.error(f"[TASK] ✗ Aggregation failed: {e}")

            set_job_status(
                job_id=job_id,
                status="error",
                chunk_completed=total_chunks,
                total_chunks=total_chunks,
                summary=final_summary,
            )

            return {
                "status": "error",
                "job_id": job_id,
                "error": str(e)
            }

    @celery_app.task(name="core.task.orchestrate_task")
    def orchestrate_task(
        job_id: str,
        query: str,
        studies: List[Dict[str, Any]],
        chunk_size: int = 5,
        model_chunk: str = "gpt-4.1-min",
        model_aggregate: str = "gpt-4.1-mini"
    ) -> str:
        """
        Orchestrate the entire pipeline: chunk → summarize → aggregate.

        Args:
            job_id: Unique job identifier
            query: Search query
            studies: All studies to process
            chunk_size: Studies per chunk
            model_summarize: Model for chunk summaries
            model_aggregate: Model for final aggregation

        Returns:
            Job ID for user to poll

        Behavior:
            1. Chunk the studies
            2. Enqueue chunk summarization tasks (parallel)
            3. Enqueue aggregation task (after all chunks)
            4. Return job_id to user immediately
        """

        logger.info(f"[ORCHESTRATOR] Starting pipeline for job {job_id}...")

        # chunk the studies
        chunks = chunk_studies(studies=studies, chunk_size=chunk_size)
        config = validate_chunk_config(len(studies), chunk_size)

        # create chunk summarization tasks
        chunk_tasks = [
            summarize_chunk.s(job_id=job_id, chunk_index=i, chunk_data=chunk, query=query,
                               model=model_chunk, total_chunks=len(chunks)) for i, chunk in enumerate(chunks)]

        # create workflow for running all chunk summarizer and aggregate summarizer
        # group() runs tasks in parallel
        # chord() runs callback after group completes
        workflow = chord(
            group(*chunk_tasks),
            aggregate_chunks.s(job_id=job_id, total_chunks=len(chunks), query=query,
                                 model=model_aggregate)
        )

        result = workflow.apply_async()

        logger.info(
            f"[ORCHESTRATION] pipeline enqueued with task ID {result.id}")
        logger.info(
            f"[ORCHESTRATION] Expected to complete in {config['estimated_time_parallel']}")

        return job_id

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
