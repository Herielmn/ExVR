# ExVR-Next

A fork of [ExVR](https://github.com/xiaofeiyu0723/ExVR) — *Experience Virtual Reality* —
based on ExVR by xiaofeiyu0723. Same tracking, the same OSC / VMT / VRCFaceTracking
output and the same `settings/*.json` keys, so an existing ExVR configuration works
here unchanged. GPL-3.0, like the original. The original readme follows below.

## What is different

|                     | ExVR                                            | ExVR-Next                                                                                     |
|---------------------|-------------------------------------------------|-----------------------------------------------------------------------------------------------|
| Interface           | PyQt5 window                                    | `ExVR-Next.exe`: a Rust + WebView2 host. `ExVR.exe` is the headless core; with no WebView2, any browser opens the control URL from the log |
| Size                | 440 MiB unpacked                                | 165 MiB unpacked, 58 MiB installer                                                             |
| Administrator       | asked for at every start                        | never asked for; installing the SteamVR drivers asks only when that folder is not writable      |
| Global hotkeys      | low-level keyboard hook                         | Windows Raw Input: no hook chain, so nothing else on the machine can swallow a key              |
| Phone controller    | HTTP, no authentication                         | pairing code, per-request checks, lockout after five wrong codes                                |
| TLS certificate     | one private key committed to the repository, shared by every install | generated on your machine on first run, renewed before it expires                  |
| OSC port            | listening on every network interface            | `127.0.0.1`                                                                                     |
| GPU                 | refuses to start when DirectML is missing       | falls back to the CPU and says so in the log                                                    |
| Logs / diagnostics  | console only                                    | `settings/logs/exvr.log` plus a diagnostics bundle that contains no secrets                     |

## Install

1. Run `ExVR-Next-<version>-setup.exe`. There is no UAC prompt; it installs into
   `%LOCALAPPDATA%\Programs\ExVR-Next`.
2. Windows 11 already has the Edge WebView2 runtime. On Windows 10, setup offers to
   download Microsoft's installer for it.
3. Start **ExVR-Next** from the Start menu, open **Settings** and click **Install
   Drivers** once. That writes VMT and VRto3D into SteamVR and the VRCFaceTracking
   module into `%APPDATA%\VRCFaceTracking\CustomLibs`. Restart SteamVR afterwards —
   it only loads drivers when it starts.

To open the phone controller, scan the QR code in the app. The pairing code is asked
for once per device.

## Worth knowing

- **Settings live next to the program**, in `_internal\settings`. Keep ExVR-Next in a
  folder you can write to; it says so at startup if it cannot. An upgrade keeps your
  `settings\*.json`, an uninstall removes them.
- **`REALTIME` process priority is silently downgraded to `HIGH`** without administrator
  rights. Windows reports no error. `HIGH` is what you want anyway.
- **No update check, no telemetry, no outbound connection.** The only network listeners
  are on this machine's own addresses, for the phone controller and the UI.
- The `logo`, models and driver binaries come from the projects credited at the bottom of
  this file.

## Build from source

```
pip install -r requirements.txt      # Python 3.12, Windows x64
python main.py                       # the core alone; open the URL it logs in a browser

cargo build --release --manifest-path host/Cargo.toml
pip install -r requirements-dev.txt  # onnx, for the fp16 model conversion
pyinstaller main.spec
copy host\target\release\ExVR-Next.exe dist\ExVR\
iscc installer\exvr-next.iss         # Inno Setup 6
```

`tools/test_*.py` are standalone scripts; each prints `OK` on its last line.

---

# ExVR: Experience Virtual Reality

This is a project for PC users who want to experience VR without a headset.

## Language
[简体中文](readme_zh.md) / [English](readme.md)

## Usage

https://exvr-doc.github.io/#/en/home

## Hotkeys

| **Key**        | **Action**                     |
|----------------|--------------------------------|
| \\+`           | Toggle hotkeys                 |
| `ctrl+'`       | Reset head                     |
| `ctrl+;`       | Reset eyes                     |
| `ctrl+;+1`     | Disable eye yaw                |
| `ctrl+;+2`     | Disable all eye movements      |
| `ctrl+[`       | calibrate hand position (left) |
| `ctrl+]`       | calibrate hand position (right) |
| [+`            | Enable all fingers (left)      |
| `[+1`          | Set finger 0 on left hand      |
| `[+2`          | Set finger 1 on left hand      |
| `[+3`          | Set finger 2 on left hand      |
| `[+4`          | Set finger 3 on left hand      |
| `[+5`          | Set finger 4 on left hand      |
| ]+`            | Enable all fingers (right)     |
| `]+1`          | Set finger 0 on right hand     |
| `]+2`          | Set finger 1 on right hand     |
| `]+3`          | Set finger 2 on right hand     |
| `]+4`          | Set finger 3 on right hand     |
| `]+5`          | Set finger 4 on right hand     |
| `[+(F1-F8)`    | Left hand emoji                |
| `]+(F1-F8)`    | Right hand emoji               |
| `ctrl+up`      | Move up                        |
| `ctrl+down`    | Move down                      |
| `ctrl+left`    | Move left                      |
| `ctrl+right`   | Move right                     |
| `ctrl+z`       | Toggle hand mode               |
| `up`           | Head pitch up                  |
| `down`         | Head pitch down                |
| `,` (<)        | Head yaw left                  |
| `.` (>)        | Head yaw right                 |
| `=`            | Grasp with left hand           |
| `-`            | Grasp with right hand          |
| `[`            | Trigger with left hand         |
| `]`            | Trigger with right hand        |
| `left` (mouse) | Trigger with left hand         |
| `right` (mouse) | Trigger with right hand        |
| `left` (mouse) | Grasp with left hand           |
| `right` (mouse) | Grasp with right hand          |
| `scroll_up`    | Move joystick up               |
| `scroll_down`  | Move joystick down             |
| `middle` (mouse) | Activate joystick middle right |



## Configuration

### config.json

The `config.json` file, located in the root (`./settings`) directory, allows users to configure various components, including camera, IP settings, smoothing, and tracking parameters.

#### General Settings  

| Key        | Description                                      |
|------------|--------------------------------------------------|
| Camera     | Specifies the camera index for input.            |
| IP         | Defines the IP address for connection settings.   |
| Smoothing  | Enables or disables smoothing for movements.      |

#### Tracking Settings  

| **Component**  | **Parameter**                                                                  | **Description**                                      |
|----------------|--------------------------------------------------------------------------------|------------------------------------------------------|
| **Head**       | enable                                                                         | Activate head tracking (`true` or `false`).          |
|                | x_scalar, y_scalar, z_scalar                                                   | Adjust sensitivity for head position in each axis.   |
|                | yaw_rotation_scalar, pitch_rotation_scalar, roll_rotation_scalar | Adjust sensitivity for head rotation.                |
| **Face**       | enable                                                                         | Activate face tracking.                              |
| **Tongue**     | enable                                                                         | Activate tongue tracking.                            |
|                | tongue_confidence                                                              | Minimum confidence for tongue detection.             |
|                | tongue_threshold                                                               | Threshold to recognize tongue movements.             |
|                | tongue_x_scalar, tongue_y_scalar                                               | Adjust sensitivity for tongue movements.             |
|                | mouth_close_threshold                                                          | Threshold to detect a closed mouth.                  |
| **Hand**       | enable                                                                         | Activate hand tracking.                              |
|                | x_scalar, y_scalar, z_scalar                                                   | Adjust sensitivity for hand position in each axis.   |
|                | hand_confidence                                                                | Minimum confidence for hand detection.               |
|                | enable_hand_auto_reset                                                         | Automatically resets hand position (`true`/`false`). |
|                | hand_detection_upper_threshold                                                 | Upper threshold for hand detection.                  |
|                | hand_detection_lower_threshold                                                 | Lower threshold for hand detection.                  |
|                | hand_count_threshold                                                           | Minimum number of hands required for detection.      |
|                | only_front                                                                     | Limit tracking to front-facing hands.                |
|                | toggle_hand_tracking_mode                                                      | Toggle hand-tracking mode between Follow and Joint.  |
| **Finger**     | enable                                                                         | Activate finger tracking.                            |
|                | finger_confidence                                                              | Minimum confidence for finger detection.             |
|                | finger_threshold                                                               | Sensitivity threshold for finger movements.          |

#### Model Settings  

| **Model**      | **Parameter**                      | **Description**                                    |
|----------------|------------------------------------|----------------------------------------------------|
| **Face Model** | min_face_detection_confidence      | Minimum confidence required for face detection.    |
|                | min_face_presence_confidence       | Minimum confidence for detecting face presence.    |
|                | min_tracking_confidence            | Minimum confidence for maintaining face tracking. |
| **Hand Model** | min_hand_detection_confidence      | Minimum confidence required for hand detection.    |
|                | min_hand_presence_confidence       | Minimum confidence for detecting hand presence.    |
|                | min_tracking_confidence            | Minimum confidence for maintaining hand tracking. |

### data.json

The `data.json` file, located in the root (`./settings`) directory, contains the initial settings for the virtual experience, including position, rotation, and blend shapes.

- **Position**: Defines the 3D coordinates for the head position.
- **Rotation**: Specifies the head rotation around the axes.
- **BlendShapes**: Contains various facial expressions.
- **LeftHandPosition** / **RightHandPosition**: Specifies the positions of the hands.
- **LeftHandRotation** / **RightHandRotation**: Defines the rotation of the hands.
- **LeftHandFinger** / **RightHandFinger**: Controls the movement of each finger.

Each entry contains the following:
- **k**: Key (the name of the property).
- **v**: Default value for the property.
- **s**: Offset value used for adjustment.
- **e**: Enable flag (`true` or `false`) to activate or deactivate the setting.

### smoothing.json

The `smoothing.json` file, located in the root (`./settings`) directory, contains parameters for smoothing various movements and blend shapes.

- **OtherBlendShapes**: Controls smoothing for general facial blend shapes.  
- **EyeBlink**: Adjusts the responsiveness of eye blinking.  
- **EyeLook**: Smooths eye movement, including gaze direction.  
- **TongueOut**: Controls the tongue-out animation smoothing.  
- **TongueMove**: Smooths left and right tongue movements.  
- **HeadPosition**: Manages smoothing for head position adjustments.  
- **HeadRotation**: Smooths head rotation movements.  
- **LeftHandPosition** / **RightHandPosition**: Adjusts hand position smoothing.  
- **LeftHandRotation** / **RightHandRotation**: Manages the smoothness of hand rotations.  
- **LeftHandFinger** / **RightHandFinger**: Controls smoothing for individual finger movements.

If you are not developing the application, avoid modifying the following fields:
- **key**: Identifies the target property.
- **is_rotation**: Indicates if the property is a rotation.
- **indices**: Specifies the relevant data indices.
- **shifting**: Indices shifting.

You **can modify** the following settings to fine-tune the experience:  
- **max_delta**: Maximum allowed change in value. Higher values make movements more sensitive but can introduce jitter.
- **deadzone**: The range within which small movements are ignored. A larger dead zone reduces jitter but may make movements feel less smooth.
- **dt_multiplier**: Smoothing factor. Smaller values produce smoother movements but may slow down responsiveness.

### hotkeys.json

The `hotkeys.json` file, located in the root (`./settings`) directory, defines all the available keyboard and mouse shortcuts for interacting. You can modify this file to customize.

## Credits

- Based on [ExVR](https://github.com/xiaofeiyu0723/ExVR) by xiaofeiyu0723
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
