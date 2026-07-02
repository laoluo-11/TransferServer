# Bumi Transfer Server

面向 Bumi 人形机器人的智能中间层项目。

当前仓库包含三部分：

- `cloud/`
  云端控制服务，提供 REST API、WebSocket、Swagger 和本地调试面板
- `robot-agent/`
  机器人本地代理，负责接收任务、执行动作、上报状态
- `shared/`
  `cloud` 与 `robot-agent` 共用的协议模型、枚举和错误码

另外，仓库里还放了一份厂商 SDK 工程：

- `noetix_sdk_bumi-main/`
  Bumi DDS SDK 源码工程，提供 `highcontrol_py` / `lowcontrol_py` Python 绑定

## 当前状态

- `mock` 模式已经可以跑通完整链路
  `cloud -> robot-agent -> mock bridge`
- `bumi_stub` 模式保留了 Bumi bridge 语义，但不依赖真实 SDK
- `bumi` 模式已经接入真实 SDK 适配器
  但要想真正控制机器人，必须先在机器人本地算力板上把 SDK 编译出来，并让 `robot-agent` 运行在机器人侧

## 推荐架构

- `cloud` 部署在你的服务器
- `robot-agent` 部署在机器人本地算力板
- `noetix_sdk_bumi-main` 也放在机器人本地算力板
- `robot-agent` 通过 `highcontrol_py` 调用 SDK
- SDK 再通过 DDS 与机器人底层控制系统通信

换句话说，真实控制链路应该是：

`cloud -> robot-agent -> highcontrol_py -> Bumi DDS -> robot runtime`

## 推荐环境

- Python: `3.10`
- `cloud` / `mock` 模式：Windows 或 Linux 都可以
- 真实 SDK 模式：建议 `Ubuntu 22.04`，并与 SDK 自身要求保持一致
- 真实 SDK 模式建议运行在机器人本地算力板，而不是云服务器

## 目录结构

```text
TransferServer/
  cloud/
  robot-agent/
  shared/
  noetix_sdk_bumi-main/
  README.md
  Bumi智能中间层方案.md
  Bumi中间层接口协议.md
  Bumi中间层开发计划.md
```

主要入口：

- `cloud/app/main.py`
- `robot-agent/agent/main.py`

## 1. 安装 Python 依赖

### Windows

```powershell
cd C:\Users\15496\Desktop\TransferServer
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r cloud\requirements.txt -r robot-agent\requirements.txt
```

### Linux

```bash
cd /path/to/TransferServer
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r cloud/requirements.txt -r robot-agent/requirements.txt
```

如果你用的是 conda，也可以直接在目标环境里执行最后两条 `pip` 命令。

## 2. 先跑通 mock 模式

这是当前最推荐的第一步，先确认云端、协议、状态机、任务流都是通的。

### 2.1 启动 cloud

#### Windows

```powershell
cd C:\Users\15496\Desktop\TransferServer
.\.venv\Scripts\Activate.ps1
python -m uvicorn cloud.app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### Linux

```bash
cd /path/to/TransferServer
source .venv/bin/activate
python -m uvicorn cloud.app.main:app --host 127.0.0.1 --port 8000 --reload
```

启动后可访问：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/panel`

### 2.2 启动 robot-agent

#### Windows

```powershell
cd C:\Users\15496\Desktop\TransferServer
.\.venv\Scripts\Activate.ps1
$env:BUMI_SERVER_BASE_URL="ws://127.0.0.1:8000"
$env:BUMI_ROBOT_ID="bumi_001"
$env:BUMI_BRIDGE_MODE="mock"
python robot-agent\agent\main.py
```

#### Linux

```bash
cd /path/to/TransferServer
source .venv/bin/activate
export BUMI_SERVER_BASE_URL="ws://127.0.0.1:8000"
export BUMI_ROBOT_ID="bumi_001"
export BUMI_BRIDGE_MODE="mock"
python robot-agent/agent/main.py
```

### 2.3 在面板里验证

打开：

- `http://127.0.0.1:8000/panel`

建议按这个顺序测试：

1. `speak`
2. `gesture`
3. `move`
4. `play_teach`
5. `stop`
6. `interrupt`

## 3. bridge 模式说明

`robot-agent` 当前支持三种模式：

- `mock`
  完全模拟，不依赖真实 SDK
- `bumi_stub`
  使用 Bumi bridge 语义，但底层仍是 stub，不会驱动真实机器人
- `bumi`
  调用真实 `highcontrol_py`，这是接真实 Bumi 的模式

如果只是联调中间层，推荐 `mock`。  
如果要验证真实机器人，必须使用 `bumi`。

## 4. 真实 SDK 模式运行说明

这一部分建议在机器人本地算力板上完成。

### 4.1 你需要先具备什么

- 机器人本地算力板可以正常运行 Linux
- `noetix_sdk_bumi-main` 已拷贝到算力板
- SDK 所需系统依赖已按厂商文档安装
- 机器人底层 DDS 环境可用
- 机器人算力板能访问你的 `cloud` 服务地址

### 4.2 编译 SDK

在机器人本地算力板上进入 SDK 目录：

```bash
cd /path/to/noetix_sdk_bumi-main
chmod +x build.sh
./build.sh
```

编译成功后，通常应该能看到：

- `build/`
- `build/highcontrol_py*.so`
- `build/lowcontrol_py*.so`

如果没有生成 `highcontrol_py`，`robot-agent` 的 `bumi` 模式就无法启动。

### 4.3 启动真实 SDK 模式的 robot-agent

```bash
cd /path/to/TransferServer
source .venv/bin/activate

export BUMI_SERVER_BASE_URL="ws://你的云端服务地址:8000"
export BUMI_ROBOT_ID="bumi_001"
export BUMI_BRIDGE_MODE="bumi"

export BUMI_SDK_ROOT_DIR="/path/to/noetix_sdk_bumi-main"
export BUMI_SDK_BUILD_DIR="/path/to/noetix_sdk_bumi-main/build"
export BUMI_DDS_CONFIG_PATH="/path/to/noetix_sdk_bumi-main/config/dds.xml"
export BUMI_SDK_MODULE_NAME="highcontrol_py"

python robot-agent/agent/main.py
```

说明：

- `BUMI_SDK_ROOT_DIR` 和 `BUMI_SDK_BUILD_DIR` 至少配置一个更稳妥
- `BUMI_DDS_CONFIG_PATH` 推荐显式设置
- 如果系统已经提前设置了 `CYCLONEDDS_URI`，适配器会优先使用它
- `BUMI_SDK_MODULE_NAME` 默认就是 `highcontrol_py`，一般不用改

### 4.4 cloud 端怎么启动

真实机器人模式下，`cloud` 仍然在你的服务器上启动：

```bash
cd /path/to/TransferServer
source .venv/bin/activate
python -m uvicorn cloud.app.main:app --host 0.0.0.0 --port 8000
```

如果服务器有公网 IP 或局域网 IP，机器人侧的 `BUMI_SERVER_BASE_URL` 要填真实可访问地址，例如：

```bash
export BUMI_SERVER_BASE_URL="ws://192.168.1.20:8000"
```

## 5. 真实模式建议验证顺序

不要一上来就做大动作，建议按下面顺序验证：

1. 在 SDK 目录里确认能导入 `highcontrol_py`
2. 单独运行 SDK 自带示例，确认 SDK 本身可用
3. 启动 `robot-agent` 的 `bumi` 模式
4. 观察 `robot-agent` 是否成功连上 `cloud`
5. 先从 `/panel` 发 `speak`
6. 再测 `gesture`
7. 再测小幅度 `move`
8. 最后再测 `play_teach`

### 建议先做的导入测试

```bash
cd /path/to/noetix_sdk_bumi-main
python -c "import sys; sys.path.insert(0, './build'); import highcontrol_py; print(highcontrol_py)"
```

如果这一步失败，先不要启动 `robot-agent`，先解决 SDK 编译或依赖问题。

## 6. 常用环境变量

### cloud / agent 通信

- `BUMI_SERVER_BASE_URL`
  默认：`ws://127.0.0.1:8000`
- `BUMI_ROBOT_ID`
  默认：`bumi_001`
- `BUMI_HEARTBEAT_INTERVAL_SECONDS`
  默认：`5`

### bridge 控制

- `BUMI_BRIDGE_MODE`
  可选：`mock` / `bumi_stub` / `bumi`
- `BUMI_CONTROL_MODE`
  默认：`highcontrol`
- `BUMI_MOVE_X_LIMIT`
  默认：`0.2`
- `BUMI_MOVE_YAW_LIMIT`
  默认：`0.3`
- `BUMI_ACTION_EDGE_DELAY_MS`
  默认：`80`
- `BUMI_STATE_POLL_INTERVAL_SECONDS`
  默认：`0.2`

### SDK 相关

- `BUMI_SDK_ROOT_DIR`
  SDK 根目录
- `BUMI_SDK_BUILD_DIR`
  SDK 编译产物目录，通常是 `.../noetix_sdk_bumi-main/build`
- `BUMI_SDK_MODULE_NAME`
  默认：`highcontrol_py`
- `BUMI_DDS_CONFIG_PATH`
  `dds.xml` 路径
- `CYCLONEDDS_URI`
  如果系统层面已配置，SDK 适配器会优先使用

### 预留或部署相关

- `BUMI_DDS_HOST`
- `BUMI_DDS_DOMAIN_ID`
- `BUMI_DDS_NETWORK_INTERFACE`
- `BUMI_TTS_MODE`

## 7. 当前真实 SDK 适配了什么

`robot-agent` 现在已经接入了这些能力：

- 自动尝试导入 `highcontrol_py`
- 自动设置或复用 `CYCLONEDDS_URI`
- 调用 `HighController.instance().init()`
- 调用 `publish_cmd(ver, hor, action, index)`
- 读取 `get_mode()`
- 读取 `get_robot_bms_data()`
- 读取 `get_imu_data()`
- 读取 `get_joint_state()`
- 将 SDK 状态同步到 `robot-agent` 的桥接快照

当前动作映射主要覆盖：

- `move -> WALK`
- `gesture(wave_hand) -> SWING`
- `gesture(shake_hand) -> SHAKE`
- `gesture(cheer) -> CHEER`
- `gesture(tear) -> TEAR`
- `play_teach(index) -> PLAYTEACH`
- `stop / safe_stop -> DEFAULT`

## 8. 常见问题

### 1. 启动时报 `No module named highcontrol_py`

说明 SDK 没编译出来，或者 `BUMI_SDK_BUILD_DIR` / `BUMI_SDK_ROOT_DIR` 没配对。

先检查：

```bash
ls /path/to/noetix_sdk_bumi-main/build
```

### 2. 启动时报 `BUMI_DDS_CONFIG_PATH does not exist`

说明 `dds.xml` 路径写错了，直接改环境变量即可。

### 3. `robot-agent` 连上了，但机器人没动作

优先排查：

1. `highcontrol_py` 是否真的跑在机器人本地算力板
2. DDS 网络和配置是否正确
3. 机器人底层控制系统是否就绪
4. 当前动作是否被安全状态拦截

### 4. 运行时报 `ModuleNotFoundError: No module named pydantic`

说明 Python 依赖没装完整，重新执行：

```bash
python -m pip install -r cloud/requirements.txt -r robot-agent/requirements.txt
```

## 9. 相关文档

- `Bumi智能中间层方案.md`
- `Bumi中间层接口协议.md`
- `Bumi中间层开发计划.md`

如果后续要交接项目，建议先读这三份文档，再读本 README。
