"""
LLM function-calling schemas for Bumi robot skills.

Each skill is defined as an OpenAI-compatible function definition.
The same definitions can be adapted for Anthropic tool-use format.
"""

from __future__ import annotations

from typing import Any

# ---------- System Prompt ----------

SYSTEM_PROMPT = """You are Bumi, a humanoid robot assistant. You control a real humanoid robot.

Available capabilities:
- move: walk or turn (small steps only, x limit ±0.2m, yaw limit ±0.3rad)
- gesture: perform a gesture (wave_hand, shake_hand, cheer, tear)
- play_teach: replay a pre-recorded motion (teach index 1~N)
- speak: say something with TTS
- stop: immediately stop all motion
- interrupt: interrupt the current task and safe-stop

Rules:
1. When the user asks you to do something physical, call the matching function.
2. Never call multiple motion functions at once — do them one at a time.
3. If the user asks you to stop or emergency, call stop or interrupt IMMEDIATELY.
4. For casual conversation, just reply naturally without calling any function.
5. Keep replies in Chinese when the user speaks Chinese.

Current robot state will be provided in the context when available.
"""

# ---------- Individual Skill Schemas ----------

MOVE_SCHEMA: dict[str, Any] = {
    "name": "move",
    "description": "让机器人行走或转向。x 为前后移动（正=前进，负=后退），yaw 为左右转向（正=左转，负=右转）。移动完成后自动停止。",
    "parameters": {
        "type": "object",
        "properties": {
            "x": {
                "type": "number",
                "description": "前后移动距离，单位米。范围 [-0.2, 0.2]，正值为前进",
                "minimum": -0.2,
                "maximum": 0.2,
            },
            "yaw": {
                "type": "number",
                "description": "左右转向角度，单位弧度。范围 [-0.3, 0.3]，正值为左转",
                "minimum": -0.3,
                "maximum": 0.3,
            },
            "duration_ms": {
                "type": "integer",
                "description": "移动持续时间，单位毫秒。默认 2000",
                "default": 2000,
                "minimum": 100,
                "maximum": 10000,
            },
        },
        "required": [],
    },
}

STOP_SCHEMA: dict[str, Any] = {
    "name": "stop",
    "description": "立即停止机器人所有运动，进入安全停止状态。用于紧急情况或用户要求停下。",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

GESTURE_SCHEMA: dict[str, Any] = {
    "name": "gesture",
    "description": "让机器人执行一个手势动作。支持挥手、握手、欢呼、擦眼泪。",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "手势名称",
                "enum": ["wave_hand", "shake_hand", "cheer", "tear"],
            },
        },
        "required": ["name"],
    },
}

PLAY_TEACH_SCHEMA: dict[str, Any] = {
    "name": "play_teach",
    "description": "播放预先录制好的示教动作。index 为示教动作编号。",
    "parameters": {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "示教动作编号，从 1 开始",
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": ["index"],
    },
}

SPEAK_SCHEMA: dict[str, Any] = {
    "name": "speak",
    "description": "让机器人用语音说出指定文本。用于打招呼、回答问题、播报信息等。",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "要说出的文本内容",
                "maxLength": 500,
            },
            "voice": {
                "type": "string",
                "description": "语音风格，默认 default",
                "enum": ["default"],
            },
        },
        "required": ["text"],
    },
}

INTERRUPT_SCHEMA: dict[str, Any] = {
    "name": "interrupt",
    "description": "中断当前正在执行的任务，强制安全停止。用于紧急情况或需要立即切换任务时。",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

# ---------- Collection ----------

SKILL_SCHEMAS: list[dict[str, Any]] = [
    MOVE_SCHEMA,
    STOP_SCHEMA,
    GESTURE_SCHEMA,
    PLAY_TEACH_SCHEMA,
    SPEAK_SCHEMA,
    INTERRUPT_SCHEMA,
]

SKILL_SCHEMA_MAP: dict[str, dict[str, Any]] = {
    s["name"]: s for s in SKILL_SCHEMAS
}


def build_function_list() -> list[dict[str, Any]]:
    """Return the function list in OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s["description"],
                "parameters": s["parameters"],
            },
        }
        for s in SKILL_SCHEMAS
    ]
