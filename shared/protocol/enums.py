from __future__ import annotations

from enum import Enum


class MessageType(str, Enum):
    AGENT_HELLO = "agent_hello"
    AGENT_HEARTBEAT = "agent_heartbeat"
    TASK_COMMAND = "task_command"
    TASK_ACK = "task_ack"
    TASK_EVENT = "task_event"
    TASK_RESULT = "task_result"
    ROBOT_STATE = "robot_state"
    ALERT = "alert"
    INTERRUPT_COMMAND = "interrupt_command"
    INTERRUPT_RESULT = "interrupt_result"


class SkillName(str, Enum):
    MOVE = "move"
    STOP = "stop"
    GESTURE = "gesture"
    PLAY_TEACH = "play_teach"
    SPEAK = "speak"
    INTERRUPT_TASK = "interrupt_task"
    COMPOUND_TASK = "compound_task"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    ACKED = "acked"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class TaskStage(str, Enum):
    QUEUED = "queued"
    STARTED = "started"
    EXECUTING = "executing"
    MOTION_STARTED = "motion_started"
    SPEECH_STARTED = "speech_started"
    STEP_FINISHED = "step_finished"
    INTERRUPTED = "interrupted"
    SAFE_STOP = "safe_stop"
    FAILED = "failed"
    COMPLETED = "completed"


class MotionState(str, Enum):
    IDLE = "idle"
    WALKING = "walking"
    TURNING = "turning"
    GESTURE_RUNNING = "gesture_running"
    TEACH_PLAYING = "teach_playing"
    STOPPING = "stopping"
    ERROR = "error"


class SpeechState(str, Enum):
    IDLE = "idle"
    QUEUED = "queued"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"


class SafetyState(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    RESTRICTED = "restricted"
    SAFE_STOP = "safe_stop"
    FAULT = "fault"


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
