"""Session advisory lock keys shared by execution and recovery dispatch."""

from uuid import UUID


def run_lock_key(run_id: UUID) -> int:
    return int.from_bytes(run_id.bytes[:8], "big", signed=True)
