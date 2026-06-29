from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    SUCCESS = 0
    INVALID_PARAMS = 1001
    UNKNOWN_SKILL = 1002
    PROTOCOL_VERSION_MISMATCH = 1003
    UNAUTHENTICATED = 1004
    PERMISSION_DENIED = 1005
    ROBOT_OFFLINE = 2001
    ROBOT_STATE_INVALID = 2002
    TASK_INTERRUPTED = 2003
    TASK_TIMEOUT = 2004
    SDK_CALL_FAILED = 2005
    SAFETY_REJECTED = 2006
    LOW_BATTERY = 3001
    POSE_INVALID = 3002
    HIGH_PRIORITY_TASK_RUNNING = 3003
    SAFETY_LOCKED = 3004
    SKILL_NOT_ALLOWED = 3005


_DEFAULT_MESSAGES = {
    ErrorCode.SUCCESS: "success",
    ErrorCode.INVALID_PARAMS: "invalid parameters",
    ErrorCode.UNKNOWN_SKILL: "unknown skill",
    ErrorCode.PROTOCOL_VERSION_MISMATCH: "protocol version mismatch",
    ErrorCode.UNAUTHENTICATED: "unauthenticated",
    ErrorCode.PERMISSION_DENIED: "permission denied",
    ErrorCode.ROBOT_OFFLINE: "robot offline",
    ErrorCode.ROBOT_STATE_INVALID: "robot state invalid",
    ErrorCode.TASK_INTERRUPTED: "task interrupted",
    ErrorCode.TASK_TIMEOUT: "task timeout",
    ErrorCode.SDK_CALL_FAILED: "sdk call failed",
    ErrorCode.SAFETY_REJECTED: "safety rejected",
    ErrorCode.LOW_BATTERY: "low battery",
    ErrorCode.POSE_INVALID: "pose invalid",
    ErrorCode.HIGH_PRIORITY_TASK_RUNNING: "high priority task running",
    ErrorCode.SAFETY_LOCKED: "safety locked",
    ErrorCode.SKILL_NOT_ALLOWED: "skill not allowed",
}


def default_error_message(code: int | ErrorCode) -> str:
    try:
        normalized = ErrorCode(code)
    except ValueError:
        return "unknown error"
    return _DEFAULT_MESSAGES.get(normalized, "unknown error")
