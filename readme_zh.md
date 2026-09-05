# ExVR-Next

[ExVR](https://github.com/xiaofeiyu0723/ExVR)（*Experience Virtual Reality*）的一个分支，
based on ExVR by xiaofeiyu0723。追踪算法、OSC / VMT / VRCFaceTracking 的输出协议、
`settings/*.json` 的键名都没有改，原来的 ExVR 配置可以直接拿过来用。
同样使用 GPL-3.0。原版说明在本文下半部分。

## 与上游的差异

|              | ExVR                                 | ExVR-Next                                                     |
|--------------|--------------------------------------|----------------------------------------------------------------|
| 界面         | PyQt5 窗口                            | `ExVR-Next.exe`：Rust + WebView2 宿主；`ExVR.exe` 是无界面核心，没有 WebView2 时用任意浏览器打开日志里的控制地址 |
| 体积         | 解压后 440 MiB                        | 解压后 165 MiB，安装包 58 MiB                                    |
| 管理员权限   | 每次启动都要                          | 从不要求；只有装 SteamVR 驱动而那个目录不可写时才会问              |
| 全局快捷键   | 低级键盘钩子                          | Windows Raw Input：没有钩子链，机器上的其他程序抢不掉按键          |
| 手机控制器   | HTTP，无认证                          | 配对码 + 逐请求校验，连错五次锁定                                 |
| TLS 证书     | 一把私钥提交进仓库，所有安装共用        | 首次运行时在你自己的机器上生成，到期前自动续签                     |
| OSC 端口     | 监听所有网卡                          | `127.0.0.1`                                                     |
| GPU          | 缺 DirectML 直接启动失败               | 回落到 CPU，并在日志里说明                                        |
| 日志 / 诊断  | 只有控制台                            | `settings/logs/exvr.log`，以及一个按构造不含秘密的诊断包           |

## 安装

1. 运行 `ExVR-Next-<版本>-setup.exe`。不会弹 UAC，装到
   `%LOCALAPPDATA%\Programs\ExVR-Next`。
2. Windows 11 自带 Edge WebView2 运行时。Windows 10 上安装程序会提议帮你下载微软的安装器。
3. 从开始菜单启动 **ExVR-Next**，进 **设置**，点一次 **安装驱动**。这会把 VMT 与 VRto3D 写进
   SteamVR，把 VRCFaceTracking 模块写进 `%APPDATA%\VRCFaceTracking\CustomLibs`。
   之后请重启 SteamVR——它只在启动时加载驱动。

手机控制器扫应用里的二维码打开，每台设备问一次配对码。

## 需要知道的几件事

- **设置保存在程序旁边**的 `_internal\settings` 里。请把 ExVR-Next 放在你有写权限的目录；
  写不进去时启动会提示。升级会保留你的 `settings\*.json`，卸载会删掉。
- **`REALTIME` 进程优先级在没有管理员权限时会被静默降级成 `HIGH`**，Windows 不报错。
  日常用 `HIGH` 就够了。
- **不检查更新、不上报、不主动连外网。** 唯一的监听端口在本机地址上，供界面和手机控制器使用。
- 图标、模型与驱动二进制来自本文末尾「参考项目」里列出的项目。

## 从源码构建

```
pip install -r requirements.txt      # Python 3.12，Windows x64
python main.py                       # 只跑核心，用浏览器打开它日志里的地址

cargo build --release --manifest-path host/Cargo.toml
pip install -r requirements-dev.txt  # onnx，用于 fp16 模型转换
pyinstaller main.spec
copy host\target\release\ExVR-Next.exe dist\ExVR\
iscc installer\exvr-next.iss         # Inno Setup 6
```

`tools/test_*.py` 是独立脚本，每个的最后一行打印 `OK`。

---

# ExVR: 体验虚拟现实
为无VR玩家提供更好的体验

## 语言
[简体中文](readme_zh.md) / [English](readme.md)

## 用法

TODO

## 按键设置
### 快捷键

| **按键**         | **动作**                      |
|-----------------|---------------------------------|
| \\+`             | 切换快捷键                      |
| `ctrl+'`        | 重置头部                         |
| `ctrl+;`        | 重置眼部                         |
| `ctrl+;+1`      | 禁用眼部偏航                     |
| `ctrl+;+2`      | 禁用全部眼球运动                 |
| `ctrl+[`        | 校准手部位置（左）                |
| `ctrl+]`        | 校准手部位置（右）                |
| [+`             | 启用所有手指（左）                |
| `[+1`           | 左手手指0状态切换               |
| `[+2`           | 左手手指1状态切换              |
| `[+3`           | 左手手指2状态切换              |
| `[+4`           | 左手手指3状态切换              |
| `[+5`           | 左手手指4状态切换              |
| ]+`             | 启用所有手指（右）                |
| `]+1`           | 右手手指0状态切换              |
| `]+2`           | 右手手指1状态切换              |
| `]+3`           | 右手手指2状态切换              |
| `]+4`           | 右手手指3状态切换              |
| `]+5`           | 右手手指4状态切换              |
| `ctrl+up`       | 上升                            |
| `ctrl+down`     | 下降                            |
| `ctrl+left`     | 向左移动                         |
| `ctrl+right`    | 向右移动                         |
| `up`            | 抬头                            |
| `down`          | 低头                            |
| `=`             | 左手握持键                       |
| `-`             | 右手握持键                       |
| `[`             | 左手扳机键                       |
| `]`             | 右手扳机键                       |
| `left` (mouse)  | 左手扳机键                       |
| `right` (mouse) | 右手扳机键                       |
| `left` (mouse)  | 左手握持键                       |
| `right` (mouse) | 右手握持键                       |
| `scroll_up`     | 移动摇杆向上                     |
| `scroll_down`   | 移动摇杆向下                     |

### VRChat自带键位

| **按键**        | **动作**                         |
|-----------------|---------------------------------|
| `wsad`          | 前后左右移动                     |
| `ESC`           | 菜单（多次连续点击切换到固定菜单） |
| `,` (<)         | 头部向左偏移                     |
| `.` (>)         | 头部向右偏移                      |

## 配置

### config.json

`config.json` 文件, 被存放在本地root根目录 (`./settings`) 中， 修改用户配置的参数，这些参数包括有摄像机、IP设置、平滑和跟踪参数

#### 常规设置  

| 参数        | 描述                                      |
|------------|-------------------------------------------|
| Camera     | 指定输入的摄像机索引                        |
| IP         | 定义连接设置的IP地址                        |
| Smoothing  | `启用` / `禁用` 平滑移动                        |

#### Tracking设置  

| **项目**  | **参数**                                                    | **描述**              |                                                                
|----------------|-----------------------------------------------------------|------------------------------------------------------------|
| **Head**       | enable                                                    | 激活头部追踪 (`true` / `false`)                              |
|                | x_scalar, y_scalar, z_scalar                              | 调整各个轴上头部位置的灵敏度                                 |         
|                | yaw_rotation_scalar, pitch_rotation_scalar, roll_rotation_scalar | 调整头部的旋转灵敏度 |
| **Face**       | enable                                                    | 启用面捕                                           |
| **Tongue**     | enable                                                    | 启用舌头动态捕捉                        |
|                | tougue_confidence                                         | 舌头动态捕捉的置信度阈值 |
|                | tongue_threshold                                          | 识别舌头运动的阈值 |
|                | tongue_x_scalar, tongue_y_scalar                          | 调整舌头动态捕捉的灵敏度 |
| **Mouth**      | enable                                                    | 启用嘴部动态捕捉                        |
|                | mouth_close_threshold                                     | 嘴部闭合阈值 |
| **Hand**       | enable                                                    | 启用手部追踪 (`true` / `false`)                              |
|                | x_scalar, y_scalar, z_scalar                              | 调整各个轴上手部位置的灵敏度                                 |
|                | hand_confidence                                           | 手部追踪的置信度阈值 |
|                | enable_hand_auto_reset                                    | 自动重置手部位置 (`true` / `false`) |
|                | hand_detection_upper_threshold                            | 手部检测的上限阈值 |
|                | hand_detection_lower_threshold                            | 手部检测的下限阈值 |
|                | hand_count_threshold                                      | 手部的计数阈值 |
|                | only_front                                                | 仅允许手在前方移动  |
| **Finger**     | enable                                                    | 启用手指追踪 (`true` / `false`)                              |
|                | finger_confidence                                         | 手指检测的最低置信度 |
|                | finger_threshold                                          | 手指状态（张开/收紧）的阈值 |



#### 模型设置 

| **模块** | **参数**                     | **描述**              |                                                          
|-----------|-------------------------------|----------|
| **Face Modle** | min_face_detection_confidence | 面部检测所需的最低置信度 |
|             | min_face_presence_confidence  | 检测面部存在的最低置信度 |
|             | min_tracking_confidence       | 维持面部跟踪的最低置信度 |
| **Hand Model** | min_hand_detection_confidence | 手部检测所需的最低置信度 |
|             | min_hand_presence_confidence  | 检测手部存在的最低置信度 |
|             | min_tracking_confidence       | 维持手部跟踪的最低置信度 |  



### data.json

文件`data.json`位于根目录（`./settings`）中，包含虚拟体验的初始设置，包括位置、旋转和形态键

- **Position**：定义头部的3D坐标
- **Rotation**：定义头部绕各个轴的旋转
- **BlendShapes**：包含各种面部表情
- **LeftHandPosition** / **RightHandPosition**：定义左右手的位置
- **LeftHandRotation** / **RightHandRotation**：定义左右手的旋转
- **LeftHandFinger** / **RightHandFinger**：控制每个手指的运动

每个条目包含以下内容：
- **k**：键（属性的名称）
- **v**：属性的默认值
- **s**：调整值的偏移量
- **e**：启用标志（`true` / `false`）以激活或禁用设置


### smoothing.json

文件`smoothing.json`位于根目录（`./settings`）中，用于设置平滑各种运动和形态键

- **OtherBlendShapes**：控制一般面部形态键的平滑度
- **EyeBlink**：平滑眼皮移动
- **EyeLook**：平滑眼睛移动
- **TongueOut**：平滑舌头伸出移动
- **TongueMove**：平滑舌头的左右移动
- **HeadPosition**：平滑头部位置移动
- **HeadRotation**：平滑头部旋转移动
- **LeftHandPosition** / **RightHandPosition**：平滑手部位置
- **LeftHandRotation** / **RightHandRotation**：平滑手部旋转
- **LeftHandFinger** / **RightHandFinger**：平滑手指运动

如果您不是对该应用程序进行二次开发，请避免修改以下参数：
- **key**：键
- **is_rotation**：属性是否为旋转
- **indices**：数据索引
- **shifting**：索引的偏移量

你**可以修改**以下参数以获得对自身更好的体验：  
- **max_delta**：允许的最大变化量。较高的值使动作更敏感，但可能引入抖动
- **deadzone**：忽略小幅运动的死区。较大的死区减少抖动，但可能使动作感觉不够流畅
- **dt_multiplier**：平滑因子。较小的值产生更平滑的运动，但可能降低响应速度


### hotkeys.json

文件`hotkeys.json`被存放在根目录(`./settings`)中，定义了所有可用的键盘和鼠标快捷键,你可以修改这个文件来自定义

## 参考项目

- 基于 xiaofeiyu0723 的 [ExVR](https://github.com/xiaofeiyu0723/ExVR)
- **Tracking Module**
  - [mediapipe-vt](https://github.com/nuekaze/mediapipe-vt)
  - [Mediapipe-VR-Fullbody-Tracking](https://github.com/ju1ce/Mediapipe-VR-Fullbody-Tracking/)
- **HMD OpenVR Drivers**
  - [OpenVR-OpenTrack](https://github.com/r57zone/OpenVR-OpenTrack)
  - [VRto3D](https://github.com/oneup03/VRto3D)
- **Hand OpenVR Driver**
  - [VMT (Virtual Motion Tracker)](https://github.com/gpsnmeajp/VirtualMotionTracker/)
- **VRCFaceTracking Module**
  - [VRCFT-MediaPipe](https://github.com/Codel1417/VRCFT-MediaPipe)
  - [VRCFaceTracking-LiveLink](https://github.com/kusomaigo/VRCFaceTracking-LiveLink/)
