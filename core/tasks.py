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

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

try:
    from celery import Celery, group, chord
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
            broker=_REDIS_URL,
            backend=_REDIS_URL
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

            if summary is None:
                logger.warning("Received empty summary from LLM")
                return {
                    "job_id": job_id,
                    "status": "empty",
                    "chunk_index": chunk_index,
                    "message": "Empty summary from LLM"
                }

            logger.info(f"[TASK] Chunk {chunk_index} summary generated")

            set_cached_chunk_summary(
                job_id, chunk_index=chunk_index, chunk_summary=summary)

            set_job_status(
                job_id=job_id,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
            )

            logger.info(
                f"[TASK] ✓ Chunk {chunk_index} / {total_chunks} of job {job_id} completed and cached content {summary[:50]}")

            return {
                "job_id": job_id,
                "status": "processing",
                "chunk_index": chunk_index,
                "summary": summary[:100]
            }

        except Exception as e:
            logger.error(
                f"[TASK] ✗ chunk {chunk_index} / {total_chunks} of job {job_id} failed: {e}")

            return {
                "job_id": job_id,
                "status": "error",
                "chunk_index": chunk_index,
                "total_chunks": total_chunks,
            }

    @celery_app.task(name="core.tasks.aggregate_chunks")
    def aggregate_chunks(results, *, job_id: str, total_chunks: int, query: str, model: str = "gpt-4.1-mini") -> Dict[str, Any]:
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
            for i in range(1, total_chunks+1):
                data = get_cached_chunk_summary(job_id, chunk_index=i)
                if not data:
                    logger.error(
                        f"[TASK] ✗ Missing chunk summary for chunk {i} in job {job_id}")

                chunk_summaries.append(data)

            if not chunk_summaries:
                logger.error(
                    f"[TASK] ✗ No chunk summaries found for aggregation in job {job_id}")
                # raise ValueError("No chunk summaries was found to aggregate")

            final_sys_prompt = """
           You are a clinical research summary aggregator.

            You are given multiple CHUNK SUMMARIES derived from clinical trial data.
            Each chunk may overlap in content.

            Your task is to merge them into ONE cohesive, accurate Markdown summary.

            ──────────────── CRITICAL RULES ────────────────
            • Use ONLY facts present in the input
            • Deduplicate trials using NCTId as the primary key
            • If fields differ, keep the most complete version
            • Do NOT invent missing data
            • Remove all redundancy

            ──────────────── OUTPUT FORMAT ────────────────
            Markdown only. No code blocks. No JSON.

            ──────────────── STRUCTURE ────────────────
            1. Executive Summary (1–2 sentences)
            2. Trials by Phase
            3. Trials by Study Type
            4. Key Interventions
            (Include only if ≥3 trials share an intervention)

            ──────────────── TRIAL DISPLAY RULES ────────────────
            Include a trial ONLY if at least one field is present.

            Fields to include ONLY if available:
            •  NCTId (link format: [NCTxxxxx](https://clinicaltrials.gov/study/NCTxxxxx))"
            • **Title**
            • **Condition(s)**
            • **Phase**
            • **Study Type**
            • **Interventions**
            • **Overall Status**
            • **Start Date**

            ──────────────── ORGANIZATION LOGIC ────────────────
            • Phase order: Phase 3 → Phase 2 → Phase 1 → NA
            • Status priority: Recruiting → Active → Completed → Unknown
            • Sort within sections by Start Date (newest first)

            ──────────────── FORMATTING ────────────────
            • Section headers (### Phase X, ### Observational)
            • Bullet points
            • Max 4–6 lines per trial
            • Bold Phase, Status, Interventions

            ──────────────── EDGE CASES ────────────────
            • No valid trials → “No studies matched your criteria.”
            • ≥20 trials → strictly group by Phase, then Study Type
            • Highly diverse interventions → omit “Key Interventions”

            ──────────────── INPUT ────────────────
            Below are the chunk summaries to combine.


            """

            final_summary = summarize_studies_json(
                query=query, studies=chunk_summaries, model=model, system_prompt=final_sys_prompt)

            set_cached_summary(job_id, summary=final_summary)

            # set_cached_chunk_summary(
            #     job_id, chunk_index=total_chunks, chunk_summary=final_summary)

            # the last summary is the aggregated one
            set_job_status(
                job_id=job_id,
                status="done",
                chunk_index=total_chunks,  # it won't be used because status is done
                total_chunks=total_chunks,
            )
            logger.info(
                f"[TASK] ✓ Aggregation complete for job {job_id} the total chunks {total_chunks}   ")
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
                chunk_index=total_chunks,
                total_chunks=total_chunks,
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
                              model=model_chunk, total_chunks=len(chunks)) for i, chunk in enumerate(chunks, 1)]

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
    def orchestrate_task(*args, **kwargs):
        raise RuntimeError(
            "Celery is not available. Async tasks are disabled.")
