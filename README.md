# Bumi Transfer Server

一个面向 Bumi 机器人的智能中间层项目，当前包含两部分：

- `cloud/`
  - 云端控制服务
  - 提供 REST API、WebSocket、Swagger 和本地调试面板
- `robot-agent/`
  - 机器人本地执行代理
  - 负责接收任务、执行技能、上报状态

当前项目已经能跑通一条完整的**模拟链路**：

`cloud -> robot-agent -> bridge(mock)`

这意味着你现在可以验证：

- 任务创建
- 状态上报
- 任务执行流程
- 中断任务
- 调试面板联调

但**还不能直接控制真实 Bumi 机器人**，因为真实 `Bumi DDS SDK` 还没有接入。

## 1. 当前项目结构

```text
TransferSever/
  cloud/
  robot-agent/
  shared/
  README.md
  Bumi智能中间层方案.md
  Bumi中间层接口协议.md
  Bumi中间层开发计划.md
```

主要入口：

- `cloud/app/main.py`
- `robot-agent/agent/main.py`

## 2. 推荐环境

推荐 Python 版本：

- `Python 3.10`

原因：

- 当前代码语法对 `3.10+` 兼容
- 后续如果接 Jetson、DDS SDK、厂家依赖，`3.10` 更稳妥

## 3. 安装依赖

在项目根目录打开 PowerShell：

```powershell
cd C:\Users\15496\Desktop\TransferSever
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r cloud\requirements.txt -r robot-agent\requirements.txt
```

## 4. 启动项目

需要两个终端窗口。

### 4.1 启动 cloud

```powershell
cd C:\Users\15496\Desktop\TransferSever
.\.venv\Scripts\Activate.ps1
python -m uvicorn cloud.app.main:app --host 127.0.0.1 --port 8000 --reload
```

启动后可访问：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/panel`

### 4.2 启动 robot-agent

当前推荐先跑模拟模式：

```powershell
cd C:\Users\15496\Desktop\TransferSever
.\.venv\Scripts\Activate.ps1
$env:BUMI_SERVER_BASE_URL="ws://127.0.0.1:8000"
$env:BUMI_ROBOT_ID="bumi_001"
$env:BUMI_BRIDGE_MODE="mock"
python robot-agent\agent\main.py
```

## 5. 当前如何验证功能

推荐先打开本地调试面板：

- `http://127.0.0.1:8000/panel`

你可以在面板里直接测试：

- `speak`
- `move`
- `gesture`
- `play_teach`
- `stop`
- `interrupt`

也可以用 Swagger：

- `http://127.0.0.1:8000/docs`

## 6. 当前模式说明

### 6.1 mock 模式

这是当前默认可用模式：

- `BUMI_BRIDGE_MODE=mock`

行为：

- 会模拟机器人技能执行
- 会更新任务状态和机器人状态
- 不会控制真实 Bumi

适合：

- 联调 `cloud`
- 联调 `robot-agent`
- 验证协议、状态机、任务流

### 6.2 bumi 模式

代码里已经预留了 Bumi bridge：

- `BUMI_BRIDGE_MODE=bumi`

但要注意：

- 目前这还是**SDK 对接骨架**
- 没有真实 `Bumi DDS SDK` 时，不能实现真机控制
- 等拿到 SDK 后，需要补 `robot-agent/agent/bridge/bumi_sdk.py` 的真实适配器实现

## 7. 常用环境变量

`robot-agent` 当前支持的主要环境变量：

- `BUMI_SERVER_BASE_URL`
  - 默认：`ws://127.0.0.1:8000`
- `BUMI_ROBOT_ID`
  - 默认：`bumi_001`
- `BUMI_BRIDGE_MODE`
  - 可选：`mock` / `bumi`
- `BUMI_CONTROL_MODE`
  - 默认：`highcontrol`
- `BUMI_DDS_HOST`
  - 默认：`192.168.55.101`
- `BUMI_DDS_DOMAIN_ID`
  - 默认：`0`
- `BUMI_DDS_NETWORK_INTERFACE`
  - 默认空
- `BUMI_STATE_POLL_INTERVAL_SECONDS`
  - 默认：`0.2`
- `BUMI_MOVE_X_LIMIT`
  - 默认：`0.2`
- `BUMI_MOVE_YAW_LIMIT`
  - 默认：`0.3`
- `BUMI_ACTION_EDGE_DELAY_MS`
  - 默认：`80`
- `BUMI_TTS_MODE`
  - 默认：`local_stub`

## 8. 真实 Bumi 接入位置

拿到 SDK 后，主要改下面这些文件：

- `robot-agent/agent/bridge/bumi_sdk.py`
  - 实现真实 DDS SDK 适配器
- `robot-agent/agent/bridge/bumi_bridge.py`
  - 保留控制语义和安全策略
- `robot-agent/agent/config.py`
  - 补全真实部署配置

当前代码已经预留了这些能力：

- Highcontrol 枚举
- 动作边沿触发
- `PLAYTEACH -> DEFAULT`
- 状态轮询和状态回调入口
- `x / yaw` 限幅
- `safe_stop`

## 9. 建议验证顺序

如果只是验证当前代码：

1. 启动 `cloud`
2. 启动 `robot-agent` mock 模式
3. 打开 `/panel`
4. 发 `speak`
5. 发 `gesture`
6. 发 `move`
7. 点 `interrupt`
8. 去 `/api/v1/tasks` 和 `/api/v1/alerts` 查看结果

如果以后拿到 SDK，建议按这个顺序验证：

1. 单独验证 DDS SDK 连接
2. 单独验证 bridge 的命令发布和状态订阅
3. 再跑 `robot-agent`
4. 最后跑 `cloud` 全链路

## 10. 当前限制

当前版本的限制：

- 没有真实 Bumi DDS SDK
- 没有真实 TTS
- 没有数据库持久化
- `cloud` 目前主要是内存态
- `robot-agent` 当前真机部分仍是骨架

这不影响：

- 做协议联调
- 做任务流联调
- 做中间层结构验证
- 为后续 SDK 接入预留接口

## 11. 相关文档

- `Bumi智能中间层方案.md`
- `Bumi中间层接口协议.md`
- `Bumi中间层开发计划.md`

如果后续需要让别人接手项目，建议先读这三份文档，再看本 README。
