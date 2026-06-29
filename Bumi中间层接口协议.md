# Bumi 中间层接口协议

## 1. 文档目标

本文档定义 Bumi 智能中间层的接口协议，覆盖：

- 云端服务对外 REST API
- 云端服务与 Robot Agent 的 WebSocket 协议
- 机器人技能调用模型
- 状态上报模型
- 错误码与执行约束

本文档默认面向第一阶段 MVP，实现目标是先稳定跑通单机器人远程智能控制链路。

## 2. 设计原则

- 所有跨网络控制均使用结构化消息，不直接传自由文本控制。
- 云端只下发高层技能，不下发关节级控制指令。
- 机器人本地拥有最终执行权和拒绝权。
- 运动类指令默认带超时和停止保护。
- 协议优先保证可观测、可恢复、可扩展。

## 3. 名词定义

- `Cloud Server`
  - 云端中间层服务。
- `Robot Agent`
  - 运行在机器人侧 Jetson 或本地计算单元上的执行代理。
- `Task`
  - 一次完整的执行请求。
- `Skill`
  - 受控能力单元，例如移动、挥手、播报。
- `Event`
  - 执行过程中的状态更新、告警、阶段变化。

## 4. 通信架构

推荐使用以下通信方式：

- 外部系统 -> 云端服务：`HTTP REST`
- 云端服务 <-> Robot Agent：`WebSocket`
- 后续内部微服务：`gRPC`

第一版只要求实现：

- REST API
- WebSocket 双向通信
- JSON 消息编码

## 5. 统一消息封装

所有 WebSocket 消息都建议使用统一外层结构。

```json
{
  "msg_id": "01JABCDE1234567890",
  "msg_type": "task_command",
  "timestamp": 1782345600000,
  "robot_id": "bumi_001",
  "trace_id": "trace_20260625_001",
  "payload": {}
}
```

字段定义：

- `msg_id`
  - 消息唯一 ID，建议使用 ULID 或 UUID。
- `msg_type`
  - 消息类型。
- `timestamp`
  - 毫秒级 Unix 时间戳。
- `robot_id`
  - 机器人唯一标识。
- `trace_id`
  - 一次任务链路的追踪 ID。
- `payload`
  - 具体业务内容。

## 6. 消息类型

建议支持以下 `msg_type`：

- `agent_hello`
- `agent_heartbeat`
- `task_command`
- `task_ack`
- `task_event`
- `task_result`
- `robot_state`
- `alert`
- `interrupt_command`
- `interrupt_result`

## 7. WebSocket 连接协议

## 7.1 Agent 首次上线

Robot Agent 建立连接后，先发送 `agent_hello`。

```json
{
  "msg_id": "01JHELLO001",
  "msg_type": "agent_hello",
  "timestamp": 1782345600000,
  "robot_id": "bumi_001",
  "trace_id": "connect_001",
  "payload": {
    "agent_version": "0.1.0",
    "sdk_version": "bumi-highcontrol-v1",
    "protocol_version": "1.0",
    "capabilities": [
      "move",
      "stop",
      "gesture",
      "play_teach",
      "speak",
      "interrupt_task"
    ]
  }
}
```

云端成功接收后返回确认消息：

```json
{
  "msg_id": "01JHELLO002",
  "msg_type": "task_ack",
  "timestamp": 1782345600100,
  "robot_id": "bumi_001",
  "trace_id": "connect_001",
  "payload": {
    "ack_type": "agent_hello",
    "accepted": true,
    "server_time": 1782345600100
  }
}
```

## 7.2 心跳

Robot Agent 每 `3` 到 `5` 秒发送一次 `agent_heartbeat`。

```json
{
  "msg_id": "01JHEART001",
  "msg_type": "agent_heartbeat",
  "timestamp": 1782345605000,
  "robot_id": "bumi_001",
  "trace_id": "heartbeat_001",
  "payload": {
    "status": "online",
    "battery_percent": 82,
    "current_task_id": "task_20260625_001",
    "safety_state": "normal"
  }
}
```

云端若连续 `15` 秒未收到心跳，应将机器人标记为 `offline_suspected`。

## 8. REST API 设计

## 8.1 认证方式

建议第一版使用：

- `Authorization: Bearer <token>`

后续可升级为：

- 设备双向证书
- 机器人单独签名密钥

## 8.2 创建任务

`POST /api/v1/robots/{robot_id}/tasks`

请求体：

```json
{
  "skill": "speak",
  "params": {
    "text": "你好，我是 Bumi。"
  },
  "policy": {
    "interruptible": true,
    "timeout_ms": 5000,
    "priority": 50,
    "need_ack": true
  },
  "source": {
    "type": "agent",
    "name": "cloud_brain"
  }
}
```

返回体：

```json
{
  "code": 0,
  "message": "accepted",
  "data": {
    "task_id": "task_20260625_001",
    "robot_id": "bumi_001",
    "status": "queued"
  }
}
```

## 8.3 获取机器人状态

`GET /api/v1/robots/{robot_id}/state`

返回体：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "robot_id": "bumi_001",
    "online": true,
    "workmode": 2,
    "battery_percent": 82,
    "motion_state": "idle",
    "speech_state": "idle",
    "safety_state": "normal",
    "current_task_id": null,
    "updated_at": 1782345605000
  }
}
```

## 8.4 获取任务详情

`GET /api/v1/tasks/{task_id}`

返回体：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": "task_20260625_001",
    "robot_id": "bumi_001",
    "skill": "speak",
    "status": "success",
    "result_code": 0,
    "result_message": "speech finished",
    "created_at": 1782345600000,
    "finished_at": 1782345603000
  }
}
```

## 8.5 中断任务

`POST /api/v1/robots/{robot_id}/interrupt`

请求体：

```json
{
  "reason": "manual_override",
  "scope": "current_task"
}
```

返回体：

```json
{
  "code": 0,
  "message": "interrupt_sent",
  "data": {
    "robot_id": "bumi_001"
  }
}
```

## 8.6 获取机器人能力

`GET /api/v1/robots/{robot_id}/capabilities`

返回体：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "skills": [
      "move",
      "stop",
      "gesture",
      "play_teach",
      "speak",
      "interrupt_task"
    ]
  }
}
```

## 9. 任务指令协议

云端通过 WebSocket 下发 `task_command`。

```json
{
  "msg_id": "01JTASK001",
  "msg_type": "task_command",
  "timestamp": 1782345600000,
  "robot_id": "bumi_001",
  "trace_id": "trace_20260625_001",
  "payload": {
    "task_id": "task_20260625_001",
    "skill": "move",
    "params": {
      "x": 0.15,
      "yaw": 0.10,
      "duration_ms": 1200
    },
    "policy": {
      "interruptible": true,
      "timeout_ms": 3000,
      "priority": 50,
      "need_ack": true
    },
    "source": {
      "type": "agent",
      "name": "cloud_brain"
    }
  }
}
```

## 10. 任务确认协议

Robot Agent 收到任务后，先返回 `task_ack`，表示消息已收到并完成基本校验。

```json
{
  "msg_id": "01JTASKACK001",
  "msg_type": "task_ack",
  "timestamp": 1782345600100,
  "robot_id": "bumi_001",
  "trace_id": "trace_20260625_001",
  "payload": {
    "task_id": "task_20260625_001",
    "accepted": true,
    "reason": ""
  }
}
```

如果消息合法但当前不可执行，也应返回 `accepted: false`。

示例：

```json
{
  "msg_id": "01JTASKACK002",
  "msg_type": "task_ack",
  "timestamp": 1782345600100,
  "robot_id": "bumi_001",
  "trace_id": "trace_20260625_001",
  "payload": {
    "task_id": "task_20260625_001",
    "accepted": false,
    "reason": "LOW_BATTERY"
  }
}
```

## 11. 任务事件协议

任务执行过程中，Robot Agent 应持续上报 `task_event`。

建议事件阶段：

- `queued`
- `started`
- `planning`
- `executing`
- `speech_started`
- `motion_started`
- `step_finished`
- `interrupted`
- `safe_stop`
- `failed`
- `completed`

示例：

```json
{
  "msg_id": "01JEVENT001",
  "msg_type": "task_event",
  "timestamp": 1782345601000,
  "robot_id": "bumi_001",
  "trace_id": "trace_20260625_001",
  "payload": {
    "task_id": "task_20260625_001",
    "stage": "executing",
    "detail": "motion executor running"
  }
}
```

## 12. 任务结果协议

任务完成后必须发送 `task_result`。

```json
{
  "msg_id": "01JRESULT001",
  "msg_type": "task_result",
  "timestamp": 1782345602000,
  "robot_id": "bumi_001",
  "trace_id": "trace_20260625_001",
  "payload": {
    "task_id": "task_20260625_001",
    "status": "success",
    "result_code": 0,
    "result_message": "move finished",
    "metrics": {
      "duration_ms": 1180
    }
  }
}
```

`status` 建议取值：

- `success`
- `failed`
- `interrupted`
- `rejected`
- `timeout`

## 13. 中断协议

云端可通过 `interrupt_command` 发送中断指令。

```json
{
  "msg_id": "01JINT001",
  "msg_type": "interrupt_command",
  "timestamp": 1782345601500,
  "robot_id": "bumi_001",
  "trace_id": "trace_20260625_001",
  "payload": {
    "task_id": "task_20260625_001",
    "reason": "manual_override",
    "scope": "current_task"
  }
}
```

Robot Agent 返回：

```json
{
  "msg_id": "01JINT002",
  "msg_type": "interrupt_result",
  "timestamp": 1782345601600,
  "robot_id": "bumi_001",
  "trace_id": "trace_20260625_001",
  "payload": {
    "task_id": "task_20260625_001",
    "status": "success",
    "message": "task interrupted and safe stop applied"
  }
}
```

## 14. 技能协议定义

第一版建议支持以下技能：

- `move`
- `stop`
- `gesture`
- `play_teach`
- `speak`
- `interrupt_task`

## 14.1 move

用途：

- 前进、后退、转向。

参数定义：

```json
{
  "x": 0.15,
  "yaw": 0.10,
  "duration_ms": 1200
}
```

字段说明：

- `x`
  - 前后速度控制量。
- `yaw`
  - 转向控制量。
- `duration_ms`
  - 持续时间。

建议约束：

- `x` 取值范围建议先限制为 `-0.20` 到 `0.20`
- `yaw` 取值范围建议先限制为 `-0.30` 到 `0.30`
- `duration_ms` 建议范围为 `100` 到 `3000`

执行规则：

- 执行前检查 `battery_percent` 和 `safety_state`
- 执行中如果超时，自动进入 `safe_stop`
- 执行结束必须自动发送 `x = 0` 和 `yaw = 0`

## 14.2 stop

用途：

- 立即停止运动。

参数定义：

```json
{}
```

执行规则：

- 立即清空当前运动控制意图
- 发送一次安全停止命令
- 优先级应高于普通任务

## 14.3 gesture

用途：

- 执行预定义动作。

参数定义：

```json
{
  "name": "wave_hand"
}
```

建议映射：

- `wave_hand` -> `SWING`
- `shake_hand` -> `SHAKE`
- `cheer` -> `CHEER`

执行规则：

- 只允许调用白名单动作名
- 动作期间禁止叠加高风险移动任务

## 14.4 play_teach

用途：

- 播放示教动作。

参数定义：

```json
{
  "index": 1
}
```

执行规则：

- `PLAYTEACH` 只发一次
- 后续控制循环发送 `DEFAULT`
- 执行期间不可重复触发同一个示教命令

## 14.5 speak

用途：

- 文本播报。

参数定义：

```json
{
  "text": "欢迎来到展厅。",
  "voice": "default",
  "priority": 50,
  "interruptible": true
}
```

字段说明：

- `text`
  - 播报文本。
- `voice`
  - 音色标识。
- `priority`
  - 用于调度。
- `interruptible`
  - 是否可被高优先级任务打断。

## 14.6 interrupt_task

用途：

- 中断当前任务。

参数定义：

```json
{
  "reason": "manual_override"
}
```

## 15. 复合任务协议

如果要支持一个任务包含多个步骤，建议使用 `compound_task`。

```json
{
  "task_id": "task_20260625_002",
  "skill": "compound_task",
  "params": {
    "steps": [
      {
        "skill": "gesture",
        "params": {
          "name": "wave_hand"
        }
      },
      {
        "skill": "speak",
        "params": {
          "text": "你好，我是 Bumi。"
        }
      }
    ]
  }
}
```

执行要求：

- 每一步都要发 `task_event`
- 任一步失败后是否继续，建议由 `policy.on_error` 控制

建议策略字段：

```json
{
  "on_error": "abort"
}
```

可选值：

- `abort`
- `continue`

## 16. 状态模型

Robot Agent 应维护本地状态并向云端上报。

## 16.1 机器人状态

```json
{
  "online": true,
  "workmode": 2,
  "battery_percent": 82,
  "motion_state": "walking",
  "speech_state": "idle",
  "safety_state": "normal",
  "current_task_id": "task_20260625_001"
}
```

字段说明：

- `online`
  - 是否在线。
- `workmode`
  - Bumi 当前模式值。
- `battery_percent`
  - 电量百分比。
- `motion_state`
  - 当前运动状态。
- `speech_state`
  - 当前语音状态。
- `safety_state`
  - 当前安全状态。
- `current_task_id`
  - 当前活动任务。

## 16.2 motion_state 枚举

- `idle`
- `walking`
- `turning`
- `gesture_running`
- `teach_playing`
- `stopping`
- `error`

## 16.3 speech_state 枚举

- `idle`
- `queued`
- `speaking`
- `interrupted`
- `error`

## 16.4 safety_state 枚举

- `normal`
- `warning`
- `restricted`
- `safe_stop`
- `fault`

## 17. 告警协议

Robot Agent 应在异常时发送 `alert`。

```json
{
  "msg_id": "01JALERT001",
  "msg_type": "alert",
  "timestamp": 1782345602200,
  "robot_id": "bumi_001",
  "trace_id": "trace_20260625_001",
  "payload": {
    "level": "warning",
    "code": "LOW_BATTERY",
    "message": "battery too low for move",
    "detail": {
      "battery_percent": 12
    }
  }
}
```

`level` 建议取值：

- `info`
- `warning`
- `error`
- `critical`

## 18. 错误码设计

建议统一使用整型错误码。

### 18.1 通用错误码

- `0`
  - 成功
- `1001`
  - 参数非法
- `1002`
  - 未知技能
- `1003`
  - 协议版本不兼容
- `1004`
  - 未认证
- `1005`
  - 权限不足

### 18.2 机器人执行错误码

- `2001`
  - 机器人离线
- `2002`
  - 当前状态不允许执行
- `2003`
  - 任务被中断
- `2004`
  - 任务执行超时
- `2005`
  - SDK 调用失败
- `2006`
  - 安全层拒绝执行

### 18.3 业务安全错误码

- `3001`
  - 低电量禁止运动
- `3002`
  - 姿态异常禁止运动
- `3003`
  - 当前已有高优先级任务
- `3004`
  - 机器人处于安全锁定状态
- `3005`
  - 技能超出白名单

## 19. 幂等与重试

为避免重复执行，建议：

- 以 `task_id` 作为任务幂等键
- Robot Agent 对最近一段时间已完成任务做缓存
- 相同 `task_id` 重复下发时，不重复执行

建议行为：

- 若任务已执行成功，直接返回上次结果
- 若任务正在执行，返回当前状态
- 若任务执行失败，由上层决定是否重试

## 20. 超时与取消规则

建议默认超时规则：

- `move`
  - 默认 `3000ms`
- `gesture`
  - 默认 `5000ms`
- `play_teach`
  - 默认 `15000ms`
- `speak`
  - 默认 `10000ms`

超时处理：

- 运动类任务超时后必须执行 `safe_stop`
- 语音类任务超时后可直接中断
- 复合任务超时后默认整体失败

## 21. 安全校验要求

Robot Agent 在执行运动任务前至少校验：

- 是否在线
- 是否处于允许执行的模式
- 是否有低电量风险
- 是否处于安全锁定状态
- 是否有更高优先级任务正在执行

校验失败时：

- 不执行任务
- 发送 `task_ack accepted=false`
- 同时可附带 `alert`

## 22. 日志与审计字段

建议所有任务记录至少保存以下字段：

- `task_id`
- `robot_id`
- `trace_id`
- `skill`
- `params`
- `source`
- `status`
- `result_code`
- `result_message`
- `created_at`
- `started_at`
- `finished_at`

## 23. 协议版本管理

建议协议消息中保留版本号：

```json
{
  "protocol_version": "1.0"
}
```

规则建议：

- 小版本兼容新增字段
- 大版本变更字段语义或结构
- Robot Agent 上线时主动上报自身协议版本

## 24. MVP 范围建议

第一版必须实现：

- Agent 上线注册
- 心跳
- 单技能任务下发
- 任务确认
- 任务事件
- 任务结果
- 状态上报
- 中断任务
- 错误码

第一版可以暂缓：

- 复合任务嵌套
- 多机器人广播任务
- 视频流控制协议
- 文件上传协议

## 25. 实施建议

建议按下面顺序实现：

1. 先定义共享 JSON Schema 或 Pydantic 模型
2. 先跑通 `agent_hello`、`heartbeat`、`robot_state`
3. 再跑通 `move` 和 `stop`
4. 再补 `speak`、`gesture`、`play_teach`
5. 最后补 `interrupt`、错误码、幂等和审计

这样可以最快形成一条可演示、可调试、可扩展的智能控制链路。
