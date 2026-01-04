from enum import Enum


class ActionType(Enum):
    LOG_TIME = "log_time"
    CHECKIN = "checkin"
    SKIP = "skip"
    DELETE = "delete"
    REMIND_NEXT_WEEK = "remind_next_week"
    REPORT = "report"


class SessionStatus(Enum):
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    ABORTED = "aborted"


class Weekday(Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6
