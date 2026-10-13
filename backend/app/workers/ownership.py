"""Session advisory lock keys shared by execution and recovery dispatch."""

from uuid import UUID


class OwnershipLost(RuntimeError):
    """The execution connection no longer owns its session advisory lock."""


def run_lock_key(run_id: UUID) -> int:
    return int.from_bytes(run_id.bytes[:8], "big", signed=True)
