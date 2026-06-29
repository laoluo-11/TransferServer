# Bumi 智能中间层方案

## 1. 目标定义

本文档给出一套适用于 Bumi 机器人的切实可行的智能中间层方案。目标不是让云端大模型直接控制机器人底层关节，而是构建一个位于机器人与云端智能体之间的中间层，统一负责：

- 机器人运动控制
- 语音播报与语音交互
- 状态采集与任务编排
- 云端大模型与智能体接入
- 安全控制与降级处理

该方案基于 Bumi 交付文档中的 DDS SDK 和 `Highcontrol` 控制模式设计，优先保证稳定性、安全性和可落地性。

## 2. 建议总体架构

推荐采用边云协同架构：

```text
用户/运营后台/网页控制台
            |
            v
      云端智能体服务
            |
            v
      中间层云服务
            |
            v
  机器人侧执行代理 Robot Agent
            |
            v
     Bumi DDS SDK Highcontrol
            |
            v
           Bumi
```

核心原则：
- 云端负责理解、推理、规划、知识调用。
- 机器人本地负责执行、限速、动作翻译、状态监测、安全兜底。
- 实时控制链路不走公网，不把 500Hz 控制闭环放到云端。
- 第一阶段只接 `Highcontrol`，不建议直接使用 `Lowcontrol` 做运动控制。

## 3. 为什么这样设计

根据交付文档，Bumi 的控制 SDK 基于 DDS，控制频率最高可达 `500Hz`。这类控制链路对实时性和稳定性要求很高，因此：

- 云端不适合直接参与运动实时闭环。
- 大模型不适合直接生成关节级控制指令。
- 最稳妥的方式是让大模型输出高层意图，由中间层翻译为机器人技能。

换句话说：

- 云端大脑负责“想做什么”
- 中间层负责“能不能做、怎么安全地做”
- 机器人 SDK 负责“具体执行”

## 4. 中间层总体职责

中间层建议拆成两部分：

- 云端中间层服务
- 机器人侧执行代理

### 4.1 云端中间层服务职责

- 接入大模型或智能体平台
- 处理多轮对话与任务规划
- 管理会话上下文与知识库
- 维护设备连接状态
- 下发结构化技能指令
- 保存日志、告警、任务记录
- 提供远程管理后台 API

### 4.2 机器人侧执行代理职责

- 对接 Bumi SDK
- 封装动作控制 API
- 执行语音播放
- 接收和上报机器人状态
- 执行本地安全规则
- 在网络异常时降级运行
- 实现任务打断、停止、恢复

## 5. 推荐模块划分

机器人侧执行代理建议包含以下模块。

### 5.1 Agent Gateway

职责：

- 与云端中间层保持长连接
- 接收结构化任务指令
- 上报执行结果和状态事件

建议协议：

- `WebSocket` 作为第一版首选
- 如果后期追求更强约束和性能，可切换为 `gRPC`

### 5.2 Skill Router

职责：

- 将云端智能体输出映射为固定技能
- 拒绝未经定义的自由控制命令
- 根据任务类型选择执行器

这是整个系统里最关键的一层。大模型不能直接控制机器人，只能调用白名单技能。

### 5.3 Motion Executor

职责：

- 把技能翻译成 Bumi `Highcontrol` 控制命令
- 管理走路、转向、示教动作、预设动作等
- 执行动作前检查状态
- 动作完成后安全收尾

重点注意：

- `PLAYTEACH` 这类一次性动作只能触发一次，后续发送 `DEFAULT`
- `WALK` 这类移动动作结束后必须补发 `x = 0` 和 `yaw = 0`
- 所有动作都需要超时保护

### 5.4 Speech Executor

职责：

- 负责语音播报和音频播放
- 管理语音队列和打断逻辑
- 与运动任务协调，避免动作和播报互相冲突

建议能力：

- `speak(text)`
- `interrupt_speech()`
- `play_audio(file_url)`
- `set_volume(level)`

### 5.5 State Collector

职责：

- 持续收集机器人运行状态
- 维护本地状态缓存
- 向上游输出标准化状态事件

建议采集内容：

- 当前 `workmode`
- 电池电量
- 连接状态
- IMU 状态
- 当前动作执行状态
- 是否处于可执行状态

### 5.6 Safety Guard

职责：

- 对所有指令进行准入校验
- 阻止危险动作
- 提供急停与保护逻辑

建议规则：

- 电量低于阈值时禁止执行高风险动作
- 当前不在允许模式时拒绝动作切换
- 机器人异常姿态时禁止移动
- 网络断开时停止接收远程控制命令
- 长时间未收到续控信号时自动停车

### 5.7 Task Manager

职责：

- 管理机器人当前任务生命周期
- 协调动作、语音、感知、对话任务
- 实现中断、恢复、超时、取消

推荐任务状态机：

```text
idle -> listening -> planning -> executing -> done
idle -> executing -> interrupted -> idle
executing -> timeout -> safe_stop -> idle
executing -> error -> safe_stop -> idle
```

## 6. 建议的控制边界

这是方案能否稳定的关键。

### 6.1 云端允许做的事

- 理解用户意图
- 拆解任务步骤
- 选择技能
- 生成播报内容
- 调用知识库
- 决定是否请求视觉感知

### 6.2 云端不应该直接做的事

- 直接生成 21 个关节控制量
- 直接控制 DDS 高频循环
- 直接决定每个控制周期的速度输出
- 跳过本地安全层执行指令

### 6.3 机器人本地必须掌握的权力

- 是否允许执行当前动作
- 是否应该急停
- 是否应该停止移动
- 是否应拒绝云端命令
- 是否进入降级模式

## 7. 推荐技能模型

第一版建议把机器人能力抽象成有限的技能集合，而不是开放式控制。

### 7.1 第一版建议技能

- `move`
- `stop`
- `gesture`
- `play_teach`
- `speak`
- `interrupt_task`
- `get_robot_state`
- `get_battery`
- `get_current_task`

### 7.2 技能说明

#### move

用于控制机器人移动或转向。

参数：

- `x`：前后移动速度，范围建议限制在安全阈值内
- `yaw`：转向速度，范围建议限制在安全阈值内
- `duration_ms`：动作持续时间

说明：

- 只允许中间层在安全模式下调用
- 动作结束后必须自动发送停止命令

#### stop

立即停止运动。

说明：

- 应具备最高执行优先级
- 执行时必须发送 `x = 0`、`yaw = 0`

#### gesture

执行预定义动作，例如挥手、握手、欢呼。

参数：

- `name`

建议映射：

- `wave_hand` -> `SWING`
- `shake_hand` -> `SHAKE`
- `cheer` -> `CHEER`

#### play_teach

播放示教动作。

参数：

- `index`

说明：

- 只能发送一次性触发命令
- 后续循环必须恢复为 `DEFAULT`

#### speak

用于机器人语音播报。

参数：

- `text`
- `voice`
- `priority`

#### interrupt_task

中断当前动作和语音任务，进入安全停止状态。

## 8. 建议的消息协议

建议所有跨进程、跨网络控制都使用结构化 JSON。第一版这样做开发效率最高。

### 8.1 云端下发任务消息

```json
{
  "msg_type": "task_command",
  "task_id": "task_20260625_001",
  "robot_id": "bumi_001",
  "timestamp": 1782345600000,
  "command": {
    "skill": "move",
    "params": {
      "x": 0.15,
      "yaw": 0.10,
      "duration_ms": 1200
    }
  },
  "policy": {
    "interruptible": true,
    "timeout_ms": 3000,
    "need_ack": true
  }
}
```

### 8.2 云端下发复合任务

```json
{
  "msg_type": "task_command",
  "task_id": "task_20260625_002",
  "robot_id": "bumi_001",
  "timestamp": 1782345601000,
  "command": {
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
            "text": "欢迎来到展厅，我来为你介绍。"
          }
        }
      ]
    }
  }
}
```

### 8.3 机器人状态上报

```json
{
  "msg_type": "robot_state",
  "robot_id": "bumi_001",
  "timestamp": 1782345602000,
  "state": {
    "online": true,
    "workmode": 2,
    "battery_percent": 76,
    "motion_state": "walking",
    "speech_state": "idle",
    "current_task_id": "task_20260625_001",
    "safety_state": "normal"
  }
}
```

### 8.4 任务执行结果上报

```json
{
  "msg_type": "task_result",
  "task_id": "task_20260625_001",
  "robot_id": "bumi_001",
  "timestamp": 1782345603500,
  "result": {
    "status": "success",
    "code": 0,
    "message": "move finished"
  }
}
```

### 8.5 异常告警上报

```json
{
  "msg_type": "alert",
  "robot_id": "bumi_001",
  "timestamp": 1782345603600,
  "alert": {
    "level": "warning",
    "code": "LOW_BATTERY",
    "message": "battery too low for motion task"
  }
}
```

## 9. 智能体调用模式建议

建议使用“工具调用”模式，而不是让大模型输出自由文本控制。

### 9.1 推荐方式

大模型只负责：

- 理解用户意图
- 判断该调用哪个工具
- 生成工具参数
- 根据执行结果继续下一步

例如：

- 用户说：“向我打个招呼，然后介绍一下自己”
- 智能体输出：
  - `gesture(name="wave_hand")`
  - `speak(text="你好，我是 Bumi，很高兴见到你。")`

### 9.2 不推荐方式

不建议让模型输出类似下面这种不可控文本：

```text
让机器人先慢慢前进一点，再左转一点，然后伸手挥舞两次。
```

这类文本需要人为二次解析，控制边界不清晰，风险大。

## 10. 机器人侧执行流程

一个完整任务的推荐执行流程如下：

```text
1. 云端智能体生成技能调用
2. 云端中间层下发结构化任务
3. Robot Agent 接收任务
4. Safety Guard 做准入检查
5. Task Manager 分配执行器
6. Motion Executor 或 Speech Executor 执行
7. State Collector 持续上报状态
8. 任务成功/失败后上报结果
9. 若出现异常，立即进入 safe_stop
```

## 11. 推荐的优先级设计

必须从一开始就约束控制优先级。

建议优先级如下：

1. 人工急停
2. 本地安全规则
3. 人工遥控/APP 控制
4. 云端下发任务
5. 自主待机行为

解释：

- 云端智能体永远不能抢过人工控制
- 本地安全逻辑永远高于所有智能决策
- 出现冲突时以停止运动为默认策略

## 12. 推荐技术选型

这是面向 MVP 的现实选型，不追求最复杂，而追求尽快跑通。

### 12.1 机器人侧

- `C++`
  - 对接 Bumi DDS SDK
  - 封装动作控制
- `Python`
  - 实现 Robot Agent
  - WebSocket/gRPC 通信
  - 任务状态机
  - TTS 调度
  - 规则引擎

推荐原因：

- Bumi SDK 示例更贴近 C++ 使用方式
- Python 更适合做中间层编排和智能体接入
- 使用混合架构可以兼顾性能和开发效率

### 12.2 云端

- `FastAPI`
  - 提供 API 与设备管理服务
- `Redis`
  - 管理任务队列和短状态缓存
- `PostgreSQL`
  - 保存设备、任务、日志、告警
- 大模型服务
  - 接 OpenAI 或其他兼容工具调用的模型服务

### 12.3 通信协议

- 机器人与云端：`WebSocket`
- 后台 API：`HTTP REST`
- 后期多服务内部通信：`gRPC`
- 视频流：`WebRTC` 或 `RTSP`

## 13. 推荐代码目录结构

下面是一套比较适合开工的目录结构。

```text
transfer-server/
  docs/
    architecture.md
    protocol.md
    deployment.md
  cloud/
    app/
      api/
      agent/
      services/
      models/
      repositories/
      schemas/
      main.py
    tests/
    requirements.txt
  robot-agent/
    agent/
      gateway/
      router/
      task_manager/
      safety/
      speech/
      state/
      config/
      main.py
    sdk_bridge/
      include/
      src/
      CMakeLists.txt
    scripts/
    tests/
    requirements.txt
  shared/
    protocol/
    config/
    constants/
  deploy/
    docker/
    systemd/
    compose/
```

### 13.1 目录职责说明

`cloud/`

- 云端中间层服务
- 智能体接入
- 任务编排
- 设备管理

`robot-agent/`

- 机器人本地执行代理
- Bumi SDK 封装
- 安全控制
- 任务执行

`shared/`

- 放通信协议定义
- 放机器人技能枚举
- 放通用配置和常量

## 14. 推荐 API 设计

### 14.1 云端对外 API

#### 创建设备任务

`POST /api/v1/robots/{robot_id}/tasks`

请求体示例：

```json
{
  "skill": "speak",
  "params": {
    "text": "你好，欢迎来到这里。"
  },
  "policy": {
    "interruptible": true,
    "timeout_ms": 5000
  }
}
```

#### 获取机器人状态

`GET /api/v1/robots/{robot_id}/state`

#### 取消当前任务

`POST /api/v1/robots/{robot_id}/interrupt`

#### 获取任务详情

`GET /api/v1/tasks/{task_id}`

### 14.2 Robot Agent 内部能力接口

建议在 Robot Agent 本地统一暴露能力：

- `execute_skill(skill, params)`
- `stop_motion()`
- `stop_all()`
- `speak(text)`
- `get_state()`
- `can_execute(skill, params)`

## 15. 语音能力的建议落地

如果你要让机器人“更智能”，语音体验很重要，但第一版不要一下做太复杂。

### 15.1 第一版建议做法

- 云端返回文本
- 本地使用 TTS 生成或播放音频
- 机器人本地负责音频队列和中断

### 15.2 后续增强

- 支持流式 TTS
- 支持边生成边播放
- 支持打断后重说
- 支持多角色音色
- 支持本地唤醒词

## 16. 视觉能力的建议落地

第一版不要让视觉和运动强耦合，建议先做“感知事件化”。

做法：

- 视觉模块不直接驱动机器人
- 视觉模块只输出事件，例如：
  - `person_detected`
  - `user_nearby`
  - `obstacle_in_front`
  - `target_lost`

中间层再根据这些事件决定是否触发技能。

这样做的好处：

- 更容易调试
- 更容易做安全兜底
- 后续能替换视觉算法，不影响控制主线

## 17. 安全机制设计

这是项目里绝对不能省的一部分。

### 17.1 动作安全

- 对 `x` 和 `yaw` 设置最大阈值
- 对动作设置最长执行时长
- 移动结束强制发送停止
- 播放示教动作时禁止叠加其他高风险动作

### 17.2 系统安全

- 云端连接断开后进入降级模式
- 超时未收到续控时停止移动
- 本地缓存最后一次安全状态
- 所有异常默认走 `safe_stop`

### 17.3 运维安全

- 每个机器人有唯一身份认证
- 控制指令要有签名或 Token 鉴权
- 敏感操作写审计日志
- 后台支持禁用某台机器人远程控制

## 18. 降级策略

真实场景下网络波动一定会发生，所以降级策略必须前置设计。

### 18.1 云端不可用时

- 停止接收新的智能任务
- 保留本地基础技能
- 保留本地预设讲解逻辑
- 允许人工遥控接管

### 18.2 机器人状态异常时

- 拒绝执行新运动任务
- 停止当前动作
- 上报告警
- 切换到安全待机状态

## 19. MVP 版本建议

第一阶段不要追求“大而全”，建议只做一个能稳定演示的版本。

### 19.1 MVP 目标

实现以下能力即可：

- 云端智能体下发技能任务
- 机器人执行走路、转向、挥手、示教动作
- 机器人可以播放语音
- 支持任务中断
- 支持状态上报
- 支持低电量拒绝动作

### 19.2 MVP 不建议现在做

- 关节级控制智能生成
- 全自主导航
- 复杂多模态闭环控制
- 多机器人协同调度
- 复杂视觉跟随

## 20. 开发排期建议

下面是一份比较现实的开发顺序。

### 第 1 阶段：打通机器人本地执行链路

- 读取 Bumi SDK
- 封装 `Highcontrol` 为本地 API
- 实现 `move`、`stop`、`gesture`、`play_teach`
- 实现状态采集

输出结果：

- 机器人本地可通过代码稳定执行技能

### 第 2 阶段：搭建 Robot Agent

- 建立云端长连接
- 实现任务状态机
- 实现本地安全层
- 实现任务结果上报

输出结果：

- 机器人可接收远程结构化指令并执行

### 第 3 阶段：接入语音与智能体

- 加入 `speak`
- 云端接入大模型工具调用
- 建立任务编排能力

输出结果：

- 能做“问答 + 动作 + 播报”的基本智能演示

### 第 4 阶段：加视觉与运营能力

- 接相机流
- 识别人、障碍、目标
- 增加控制台、日志、告警

输出结果：

- 项目进入可持续迭代阶段

## 21. 最终推荐结论

如果你的目标是“做一个中间层，让机器人更智能”，最现实、最稳妥、最适合 Bumi 的方案是：

- 以 `Highcontrol` 为第一阶段控制基础
- 构建“云端智能体 + 云端中间层 + 机器人本地 Agent”的三层架构
- 用技能调用替代自由控制
- 用本地安全层兜底所有智能决策

这条路线的优势是：

- 开发难度可控
- 风险可控
- 演示效果好
- 后续可逐步扩展到视觉、语音、知识库、远程运维

它不是最激进的路线，但它是最容易真正做出来并稳定运行的路线。

## 22. 下一步建议

如果继续往下推进，建议立刻做下面三件事：

1. 先定义技能协议和任务消息格式
2. 先在机器人侧封装 `Highcontrol` 本地 API
3. 先做一个最小 Robot Agent 跑通 `move + speak + stop + state report`

当这三步打通以后，再接云端智能体，项目成功率会高很多。
