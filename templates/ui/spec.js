export const PANES = [
  {
    id: "tracking",
    t: ["Tracking", "追踪"],
    groups: [
      {
        t: ["What to track", "追踪部位"],
        rows: [
          { kind: "switch", path: "Tracking/Head/enable", t: ["Head", "头部"] },
          { kind: "switch", path: "Tracking/Face/enable", t: ["Face", "面部"] },
          { kind: "switch", path: "Tracking/Tongue/enable", t: ["Tongue", "舌头"] },
          { kind: "switch", path: "Tracking/Hand/enable", t: ["Hands", "手部"] },
          { kind: "switch", path: "Tracking/Finger/enable", t: ["Fingers", "手指"] },
        ],
      },
      {
        t: ["Recentre", "重新居中"],
        rows: [
          {
            kind: "buttons",
            buttons: [
              { command: "reset_head", t: ["Head", "头部"] },
              { command: "reset_eyes", t: ["Eyes", "眼睛"] },
              { command: "reset_left_hand", t: ["Left", "左手"] },
              { command: "reset_right_hand", t: ["Right", "右手"] },
            ],
          },
        ],
      },
      {
        t: ["Hands", "手部"],
        rows: [
          { kind: "slider", path: "Tracking/Hand/x_scalar", t: ["X scale", "X 缩放"],
            min: 0.01, max: 2, step: 0.01, digits: 2 },
          { kind: "slider", path: "Tracking/Hand/y_scalar", t: ["Y scale", "Y 缩放"],
            min: 0.01, max: 2, step: 0.01, digits: 2 },
          { kind: "slider", path: "Tracking/Hand/z_scalar", t: ["Z scale", "Z 缩放"],
            min: 0.01, max: 1, step: 0.01, digits: 2 },
          { kind: "switch", path: "Tracking/Hand/only_front", t: ["Front-facing only", "仅正面朝向"],
            detail: ["Ignore a hand whose palm faces away", "手背朝向摄像头时忽略"] },
          { kind: "switch", path: "Tracking/Hand/enable_hand_down",
            t: ["Lower hands when idle", "空闲时放下手"] },
          { kind: "switch", path: "Tracking/Hand/enable_finger_action",
            t: ["Finger actions", "手指动作"] },
          { kind: "number", path: "Tracking/Hand/hand_return_time",
            t: ["Return time", "回位时间"], min: 0, max: 60, step: 0.1, unit: "s" },
        ],
      },
      {
        t: ["Face", "面部"],
        rows: [
          { kind: "switch", path: "Tracking/Face/block", t: ["Freeze when occluded", "遮挡时冻结"],
            detail: ["Hold the last pose instead of following a partly hidden face",
                     "面部被遮挡时保持上一帧姿态"] },
        ],
      },
      {
        t: ["Smoothing", "平滑"],
        rows: [
          { kind: "switch", path: "Smoothing/enable", t: ["Smoothing thread", "平滑线程"] },
        ],
      },
    ],
  },
  {
    id: "camera",
    t: ["Camera", "相机"],
    groups: [
      {
        t: ["Source", "输入源"],
        rows: [
          { kind: "custom", id: "camera-device", t: ["Camera", "摄像头"] },
          { kind: "text", path: "Setting/camera_ip", t: ["IP camera URL", "IP 摄像头地址"],
            placeholder: ["rtsp:// or http://", "rtsp:// 或 http://"],
            detail: ["Set, this wins over the camera above", "填写后优先于上面的摄像头"] },
        ],
      },
      {
        t: ["Quality", "画质"],
        rows: [
          { kind: "menu", path: "Setting/camera_performance", choices: "camera_performance",
            t: ["Preset", "性能预设"] },
          { kind: "menu", path: "Setting/camera_aspect", choices: "camera_aspect",
            t: ["Aspect", "画面比例"] },
          { kind: "custom", id: "resolution", t: ["Resolution", "分辨率"],
            covers: ["Setting/camera_width", "Setting/camera_height", "Setting/camera_fps"] },
        ],
      },
    ],
  },
  {
    id: "input",
    t: ["Input", "输入"],
    groups: [
      {
        t: ["Mouse", "鼠标"],
        rows: [
          { kind: "switch", path: "Mouse/enable", t: ["Head-driven mouse", "头部控制鼠标"] },
          { kind: "slider", path: "Mouse/scalar_x", t: ["X scale", "X 缩放"],
            min: 0, max: 360, step: 1, digits: 0 },
          { kind: "slider", path: "Mouse/scalar_y", t: ["Y scale", "Y 缩放"],
            min: 0, max: 360, step: 1, digits: 0 },
          { kind: "slider", path: "Mouse/dx", t: ["Turn step", "转身步长"],
            min: 0, max: 0.2, step: 0.01, digits: 2 },
        ],
      },
      {
        t: ["Virtual controllers", "虚拟手柄"],
        rows: [
          { kind: "switch", path: "Tracking/LeftController/enable", t: ["Left", "左手柄"] },
          { kind: "switch", path: "Tracking/RightController/enable", t: ["Right", "右手柄"] },
          { kind: "slider", path: "Tracking/LeftController/base_x",
            mirror: "Tracking/RightController/base_x", negate: true,
            t: ["Base X", "基点 X"], min: -0.5, max: 0.5, step: 0.01, digits: 2 },
          { kind: "slider", path: "Tracking/LeftController/base_y",
            mirror: "Tracking/RightController/base_y",
            t: ["Base Y", "基点 Y"], min: -0.5, max: 0.5, step: 0.01, digits: 2 },
          { kind: "slider", path: "Tracking/LeftController/base_z",
            mirror: "Tracking/RightController/base_z",
            t: ["Base Z", "基点 Z"], min: -0.5, max: 0.5, step: 0.01, digits: 2 },
          { kind: "slider", path: "Tracking/LeftController/length",
            mirror: "Tracking/RightController/length",
            t: ["Arm length", "手臂长度"], min: 0, max: 1, step: 0.01, digits: 2 },
        ],
      },
      {
        t: ["Hotkeys", "热键"],
        rows: [
          { kind: "switch", path: "Hotkey/enable", t: ["Hotkeys", "热键"] },
          {
            kind: "buttons",
            buttons: [
              { command: "reset_hotkeys", t: ["Reload bindings", "重载绑定"] },
              { command: "stop_hotkeys", t: ["Release all", "全部松开"] },
            ],
          },
          { kind: "switch", path: "Setting/only_ingame", t: ["Only in game", "仅游戏内"],
            detail: ["Applies to hotkeys and mouse input, not head movement",
                     "只作用于热键与鼠标，不影响头部"] },
          { kind: "text", path: "Setting/only_ingame_game", t: ["Window or process", "窗口或进程"],
            placeholder: ["VRChat, VRChat.exe, javaw.exe", "VRChat, VRChat.exe, javaw.exe"] },
        ],
      },
      {
        t: ["Phone controller", "手机控制器"],
        rows: [
          { kind: "custom", id: "pairing" },
          { kind: "number", path: "Controller/server_port",
            t: ["Page port", "网页端口"],
            detail: ["The https page the phone opens", "手机打开的 https 页面端口"],
            min: 1024, max: 65535, step: 1 },
          { kind: "number", path: "Controller/websocket_port",
            t: ["Data port", "数据端口"],
            detail: ["The websocket the phone streams over", "手机推送数据用的 websocket"],
            min: 1024, max: 65535, step: 1 },
          { kind: "number", path: "Controller/osc_port",
            t: ["Haptics port", "震动端口"],
            detail: ["Where VMT sends haptic pulses; must match VMT",
                     "VMT 发来震动信号的端口，需与 VMT 一致"],
            min: 1024, max: 65535, step: 1 },
        ],
      },
    ],
  },
  {
    id: "system",
    t: ["System", "系统"],
    groups: [
      {
        t: ["Runtime", "运行"],
        rows: [
          { kind: "text", path: "Sending/address", t: ["Send to", "发送地址"],
            detail: ["Where VMT and VRCFaceTracking listen", "VMT 与 VRCFaceTracking 的地址"] },
        ],
      },
      {
        t: ["Appearance", "外观"],
        rows: [
          { kind: "custom", id: "theme", t: ["Theme", "主题"] },
          { kind: "menu", path: "Setting/language", choices: "language",
            t: ["Language", "语言"] },
        ],
      },
      {
        t: ["Diagnostics", "诊断"],
        rows: [{ kind: "custom", id: "diagnostics" }],
      },
      {
        t: ["About", "关于"],
        rows: [{ kind: "custom", id: "about" }],
      },
    ],
  },
];

export const SIDEBAR = [
  {
    t: ["Image", "图像"],
    rows: [
      { kind: "switch", path: "Setting/flip_x", t: ["Flip horizontally", "水平翻转"] },
      { kind: "switch", path: "Setting/flip_y", t: ["Flip vertically", "垂直翻转"] },
    ],
  },
  {
    t: ["Basic settings", "基本设置"],
    rows: [
      { kind: "menu", path: "Model/provider", choices: "model_provider",
        t: ["Inference", "推理设备"] },
      { kind: "menu", path: "Setting/priority", choices: "priority",
        t: ["Process priority", "进程优先级"] },
    ],
  },
  {
    t: ["SteamVR", "SteamVR"],
    rows: [{ kind: "custom", id: "driver" }],
  },
];

export const ADVANCED = [
  { id: "blendshapes", t: ["Blend shapes", "表情参数"],
    detail: ["63 rows: value, shifting, weight, max, enabled -- the Face Setting dialog",
             "63 行：值、偏移、权重、上限、启用 —— 原「面部设置」对话框"] },
  { id: "metrics", t: ["Metrics", "性能指标"],
    detail: ["Live timings; empty unless metrics are on", "实时耗时；未开启 metrics 时为空"] },
  { id: "tree:config", t: ["All settings", "全部设置"],
    detail: ["Every leaf in settings/config.json", "settings/config.json 的每一项"] },
  { id: "tree:hotkey_config", t: ["Hotkeys", "热键表"] },
  { id: "tree:smoothing_config", t: ["Smoothing", "平滑表"] },
  { id: "tree:gesture_config", t: ["Gestures", "手势表"] },
];

export const DEFAULTS = {
  "Tracking/Hand/x_scalar": 0.8,
  "Tracking/Hand/y_scalar": 0.75,
  "Tracking/Hand/z_scalar": 0.8,
  "Tracking/Hand/hand_return_time": 0.5,
  "Mouse/scalar_x": 200.0,
  "Mouse/scalar_y": 150.0,
  "Mouse/dx": 0.15,
  "Tracking/LeftController/base_x": -0.3,
  "Tracking/LeftController/base_y": -0.38,
  "Tracking/LeftController/base_z": -0.15,
  "Tracking/LeftController/length": 0.38,
  "Controller/server_port": 8888,
  "Controller/websocket_port": 8889,
  "Controller/osc_port": 39571,
};

