from enum import StrEnum


class WorkItemLevel(StrEnum):
    OBJECTIVE = "OBJECTIVE"
    WORKSTREAM = "WORKSTREAM"
    ACTIVITY = "ACTIVITY"
    TASK = "TASK"
    SUB_TASK = "SUB_TASK"


class WorkItemStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
