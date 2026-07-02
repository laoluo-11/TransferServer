"""
LLM function-calling schemas for Bumi robot skills.

Each skill is defined as an OpenAI-compatible function definition.
The same definitions can be adapted for Anthropic tool-use format.
"""

from __future__ import annotations

from typing import Any

# ---------- System Prompt ----------

SYSTEM_PROMPT = """You are Bumi, a humanoid robot assistant. You control a real humanoid robot.

Available capabilities (based on Bumi delivery manual):
- move: walk or turn using normalized speed coefficients (-1.0 to 1.0).
  SAFE RANGE: x \u00b10.2 (forward/backward), yaw \u00b10.3 (turning).
  x>0 = forward, x<0 = backward. yaw>0 = turn left, yaw<0 = turn right.
- gesture: perform a gesture (wave_hand, shake_hand, cheer, tear)
- play_teach: replay a pre-recorded motion (teach index 1~N)
- speak: say something with TTS
- stop: immediately stop all motion (sends DEFAULT action)
- interrupt: interrupt the current task and safe-stop

CRITICAL SAFETY RULES (from Bumi delivery manual):
1. Motion actions (WALK/SWING/SHAKE/CHEER/TEAR/PLAYTEACH) are edge-triggered:
   send the action ONCE, then send DEFAULT (stop) afterwards.
2. To stop movement, send x=0 AND yaw=0 — both must be zero.
3. Never call multiple motion functions simultaneously — do them sequentially.
4. If the user says stop/emergency, call stop or interrupt IMMEDIATELY.
5. Keep x within \u00b10.2 and yaw within \u00b10.3 unless user explicitly asks for faster.
6. For casual conversation, reply naturally without calling any function.
7. Keep replies in Chinese when the user speaks Chinese.

Current robot state will be provided in the context when available.
"""

# ---------- Individual Skill Schemas ----------

MOVE_SCHEMA: dict[str, Any] = {
    "name": "move",
    "description": "让机器人行走或转向。x 为前后速度系数（归一化 -1.0~1.0，正=前进，负=后退），yaw 为转向速度系数（归一化 -1.0~1.0，正=左转，负=右转）。安全范围：x \u00b10.2，yaw \u00b10.3。移动完成后会自动发送 DEFAULT 停止。单位：归一化速度系数，非物理米/弧度。",
    "parameters": {
        "type": "object",
        "properties": {
            "x": {
                "type": "number",
                "description": "前后速度系数（归一化 -1.0~1.0），正值为前进。安全建议：[-0.2, 0.2]，真机测试时请从小值开始",
                "minimum": -0.2,
                "maximum": 0.2,
            },
            "yaw": {
                "type": "number",
                "description": "转向速度系数（归一化 -1.0~1.0），正值为左转。安全建议：[-0.3, 0.3]，真机测试时请从小值开始",
                "minimum": -0.3,
                "maximum": 0.3,
            },
            "duration_ms": {
                "type": "integer",
                "description": "移动持续时间，单位毫秒。默认 2000，建议首次真机测试用 500-1000ms",
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
    "description": "立即发送 DEFAULT 命令停止所有运动（符合 Bumi 交付手册：发送 x=0, yaw=0, action=DEFAULT）。用于紧急情况或用户要求停下。",
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
    "description": "中断当前任务并强制安全停止（发送 DEFAULT 命令）。用于紧急情况或需要立即切换任务时。优先级最高。",
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
