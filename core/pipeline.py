"""
Pipeline utilities for chunked, incremental summarization.

Handles:
- Splitting large result sets into manageable chunks
- Tracking chunk processing state
- Coordinating chunk → aggregation workflow
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import json
import hashlib
from datetime import datetime


def chunk_studies(studies: List[Dict[str, Any]], chunk_size: int = 5) -> List[List[Dict[str, Any]]]:
    """
      Split studies into fixed-size chunks.

      Args:
          studies: List of study dicts
          chunk_size: Number of studies per chunk (default: 5)

      Returns:
          List of chunks (each chunk is a list of studies)

      Example:
          >>> studies = [{"id": i} for i in range(12)]
          >>> chunks = chunk_studies(studies, chunk_size=5)
          >>> len(chunks)
          3  # [5 studies, 5 studies, 2 studies]
      """
    chunks = [studies[i:i+chunk_size]
              for i in range(0, len(studies), chunk_size)]
    print(
        f"[PIPELINE] Split {len(studies)} studies into {len(chunks)} chunks (size={chunk_size})")
    return chunks


# == == = VALIDATION & LOGGING == == =
def validate_chunk_config(total_studies: int,
                          chunk_size: int = 5, max_parallel: int = 10) -> Dict[str, Any]:
    """
    Validate chunking configuration and show expected metrics.

    Args:
        total_studies: Total number of studies to process
        chunk_size: Studies per chunk
        max_parallel: Max parallel tasks

    Returns:
        Config dict with calculated metrics
    """
    num_chunks = (total_studies + chunk_size - 1) // chunk_size

    config = {
        "total_studies": total_studies,
        "chunk_size": chunk_size,
        "num_chunks": num_chunks,
        "max_parallel": max_parallel,
        "batches_needed": (num_chunks + max_parallel - 1) // max_parallel,
        "estimated_time_per_chunk": "3-5 seconds",
        "estimated_total_time": f"{num_chunks * 4} seconds (sequential)",
        "estimated_time_parallel": f"{((num_chunks + max_parallel - 1) // max_parallel) * 4} seconds",
    }

    print(f"[PIPELINE] Configuration:")
    print(f"  Total studies: {config['total_studies']}")
    print(f"  Chunk size: {config['chunk_size']} studies/chunk")
    print(f"  Total chunks: {config['num_chunks']}")
    print(f"  Max parallel tasks: {config['max_parallel']}")
    print(f"  Expected time: {config['estimated_time_parallel']}")

    return config
