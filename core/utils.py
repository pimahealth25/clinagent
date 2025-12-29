import hashlib
import time
from typing import Optional, Any, Dict
from core.tasks import get_cached_chunk_summary


def generate_job_id(query: str, timestamp: Optional[str] = None) -> str:
    """
    Generate unique, deterministic job ID.

    Uses hash of query + timestamp to avoid collisions.
    """
    if timestamp is None:
        timestamp = str(int(time.time() * 1000))

    combined = f"{query}:{timestamp}"
    job_hash = hashlib.sha256(combined.encode()).hexdigest()[:12]
    return f"job_{job_hash}_{timestamp}"


def calculate_chunk_progress_percentage(job_info: Dict[str, Any]):
    """
    Docstring for calculate chunk progress percentage
    """

    progress_pct = 0
    if job_info.get("total_chunks", 0) > 0:
        progress_pct = (len(job_info.get("completed_chunks", 0)) /
                        job_info["total_chunks"]) * 100
    return progress_pct
