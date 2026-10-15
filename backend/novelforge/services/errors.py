class NotFound(Exception):
    def __init__(self, entity: str, entity_id: object):
        super().__init__(f"{entity} {entity_id} not found")
        self.entity = entity


class Conflict(Exception):
    """Optimistic-locking or uniqueness conflict. `current_version` is set for stale writes."""

    def __init__(self, message: str, current_version: int | None = None):
        super().__init__(message)
        self.current_version = current_version
