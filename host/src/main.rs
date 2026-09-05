#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use exvr_host::pycore;

use tao::dpi::LogicalSize;
use tao::event::{Event, StartCause, WindowEvent};
use tao::event_loop::{ControlFlow, EventLoopBuilder};
use tao::window::{Window, WindowBuilder};
use tray_icon::menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tray_icon::{Icon, TrayIconBuilder};
use wry::{WebViewBuilder, WebViewBuilderExtWindows, WebViewExtWindows};

#[derive(Debug)]
enum Host {
    Core(pycore::CoreEvent),
    Ipc(String),
    Menu(MenuKind),
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum MenuKind {
    Show,
    Quit,
}

const SPLASH: &str = include_str!("splash.html");
const TITLE: &str = "ExVR-Next";
const LOGO: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/icon.rgba"));
const LOGO_SIDE: u32 = include!(concat!(env!("OUT_DIR"), "/icon.side"));
const INSTANCE_MUTEX: &str = "Local\\ExVR-Next-host";
const CORE_ALREADY_RUNNING: i32 = 6;

fn only_instance() {
    use windows::core::HSTRING;
    use windows::Win32::Foundation::{
        GetLastError, SetLastError, ERROR_ALREADY_EXISTS, ERROR_SUCCESS,
    };
    use windows::Win32::System::Threading::CreateMutexW;
    use windows::Win32::UI::WindowsAndMessaging::{
        IsIconic, SetForegroundWindow, ShowWindow, SW_RESTORE, SW_SHOW,
    };
    unsafe {
        SetLastError(ERROR_SUCCESS);
        if CreateMutexW(None, false, &HSTRING::from(INSTANCE_MUTEX)).is_err() {
            return;
        }
        if GetLastError() != ERROR_ALREADY_EXISTS {
            return;
        }
        if let Some(window) = running_window() {
            let command = if IsIconic(window).as_bool() { SW_RESTORE } else { SW_SHOW };
            let _ = ShowWindow(window, command);
            let _ = SetForegroundWindow(window);
        }
    }
    std::process::exit(0)
}

fn running_window() -> Option<windows::Win32::Foundation::HWND> {
    use windows::Win32::Foundation::{HWND, LPARAM};
    use windows::Win32::UI::WindowsAndMessaging::EnumWindows;
    let mut found: Option<HWND> = None;
    unsafe {
        let _ = EnumWindows(Some(visit), LPARAM(&mut found as *mut _ as isize));
    }
    found
}

unsafe extern "system" fn visit(
    window: windows::Win32::Foundation::HWND,
    target: windows::Win32::Foundation::LPARAM,
) -> windows::core::BOOL {
    use windows::Win32::UI::WindowsAndMessaging::GetWindowTextW;
    let mut text = [0u16; 64];
    let length = GetWindowTextW(window, &mut text) as usize;
    if String::from_utf16_lossy(&text[..length]) == TITLE && same_program(window) {
        *(target.0 as *mut Option<windows::Win32::Foundation::HWND>) = Some(window);
        return false.into();
    }
    true.into()
}

fn same_program(window: windows::Win32::Foundation::HWND) -> bool {
    use windows::Win32::Foundation::CloseHandle;
    use windows::Win32::System::Threading::{
        GetCurrentProcessId, OpenProcess, QueryFullProcessImageNameW,
        PROCESS_NAME_FORMAT, PROCESS_QUERY_LIMITED_INFORMATION,
    };
    use windows::Win32::UI::WindowsAndMessaging::GetWindowThreadProcessId;
    let Ok(mine) = std::env::current_exe() else {
        return false;
    };
    let mut owner = 0u32;
    unsafe {
        GetWindowThreadProcessId(window, Some(&mut owner));
        if owner == 0 || owner == GetCurrentProcessId() {
            return false;
        }
        let Ok(process) = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, owner)
        else {
            return false;
        };
        let mut path = [0u16; 520];
        let mut length = path.len() as u32;
        let read = QueryFullProcessImageNameW(
            process,
            PROCESS_NAME_FORMAT(0),
            windows::core::PWSTR(path.as_mut_ptr()),
            &mut length,
        );
        let _ = CloseHandle(process);
        if read.is_err() {
            return false;
        }
        let theirs = String::from_utf16_lossy(&path[..length as usize]);
        theirs.eq_ignore_ascii_case(&mine.to_string_lossy())
    }
}

fn tray_icon() -> Option<Icon> {
    Icon::from_rgba(LOGO.to_vec(), LOGO_SIDE, LOGO_SIDE).ok()
}

fn window_icon() -> Option<tao::window::Icon> {
    tao::window::Icon::from_rgba(LOGO.to_vec(), LOGO_SIDE, LOGO_SIDE).ok()
}

fn profile_dir() -> Option<std::path::PathBuf> {
    let local = std::env::var_os("LOCALAPPDATA")?;
    let path = std::path::PathBuf::from(local).join(TITLE).join("WebView2");
    std::fs::create_dir_all(&path).ok()?;
    Some(path)
}

fn dark(theme: tao::window::Theme) -> bool {
    matches!(theme, tao::window::Theme::Dark)
}

fn page_theme(theme: tao::window::Theme) -> wry::Theme {
    if dark(theme) {
        wry::Theme::Dark
    } else {
        wry::Theme::Light
    }
}

fn page_background(theme: tao::window::Theme) -> wry::RGBA {
    if dark(theme) {
        (0x1C, 0x1C, 0x1E, 0xFF)
    } else {
        (0xF2, 0xF2, 0xF7, 0xFF)
    }
}

fn main() {
    only_instance();

    let event_loop = EventLoopBuilder::<Host>::with_user_event().build();
    let proxy = event_loop.create_proxy();

    let window = WindowBuilder::new()
        .with_title(TITLE)
        .with_window_icon(window_icon())
        .with_decorations(false)
        .with_inner_size(LogicalSize::new(1120.0, 740.0))
        .with_min_inner_size(LogicalSize::new(880.0, 600.0))
        .with_visible(false)
        .build(&event_loop)
        .expect("the host could not create its window");

    let ipc_proxy = proxy.clone();
    let mut context = wry::WebContext::new(profile_dir());
    let webview = WebViewBuilder::new_with_web_context(&mut context)
        .with_background_color(page_background(window.theme()))
        .with_theme(page_theme(window.theme()))
        .with_html(SPLASH)
        .with_ipc_handler(move |request: wry::http::Request<String>| {
            let _ = ipc_proxy.send_event(Host::Ipc(request.into_body()));
        })
        .build(&window)
        .unwrap_or_else(|error| {
            fatal(&format!(
                "ExVR-Next needs the Microsoft Edge WebView2 runtime, which this \
                 system does not appear to have.\n\n\
                 Install \"Evergreen Bootstrapper\" from Microsoft's WebView2 page \
                 and start ExVR-Next again.\n\n{error}"
            ))
        });

    window.set_visible(true);
    window.set_focus();

    let menu_show = MenuItem::new("Show ExVR-Next", true, None);
    let menu_quit = MenuItem::new("Quit", true, None);
    let menu = Menu::new();
    let _ = menu.append_items(&[
        &menu_show,
        &PredefinedMenuItem::separator(),
        &menu_quit,
    ]);
    let show_id = menu_show.id().clone();
    let quit_id = menu_quit.id().clone();
    let _tray = TrayIconBuilder::new()
        .with_tooltip(TITLE)
        .with_menu(Box::new(menu))
        .with_icon(tray_icon().expect("the tray icon could not be built"))
        .build();

    let menu_proxy = proxy.clone();
    std::thread::Builder::new()
        .name("tray-menu".into())
        .spawn(move || {
            while let Ok(event) = MenuEvent::receiver().recv() {
                let kind = if event.id == show_id {
                    MenuKind::Show
                } else if event.id == quit_id {
                    MenuKind::Quit
                } else {
                    continue;
                };
                if menu_proxy.send_event(Host::Menu(kind)).is_err() {
                    break;
                }
            }
        })
        .expect("the tray menu thread could not start");

    run(event_loop, window, webview, proxy);
}

fn fatal(message: &str) -> ! {
    use windows::core::HSTRING;
    use windows::Win32::UI::WindowsAndMessaging::{
        MessageBoxW, MB_ICONERROR, MB_OK,
    };
    unsafe {
        MessageBoxW(
            None,
            &HSTRING::from(message),
            &HSTRING::from(TITLE),
            MB_OK | MB_ICONERROR,
        );
    }
    std::process::exit(1)
}

fn size_pair(spec: &str) -> Option<LogicalSize<f64>> {
    let (width, height) = spec.split_once('x')?;
    let width: f64 = width.trim().parse().ok()?;
    let height: f64 = height.trim().parse().ok()?;
    if width < 1.0 || height < 1.0 {
        return None;
    }
    Some(LogicalSize::new(width, height))
}

fn screen_room(window: &Window) -> LogicalSize<f64> {
    match window.current_monitor() {
        Some(monitor) => {
            let bounds = monitor.size().to_logical::<f64>(monitor.scale_factor());
            LogicalSize::new((bounds.width - 40.0).max(480.0),
                             (bounds.height - 80.0).max(480.0))
        }
        None => LogicalSize::new(f64::INFINITY, f64::INFINITY),
    }
}

fn resize(
    window: &Window,
    spec: &str,
    saved: &mut Option<LogicalSize<f64>>,
    back: bool,
) {
    let mut parts = spec.split(':');
    let want = match parts.next().and_then(size_pair) {
        Some(size) => size,
        None => return,
    };
    let least = parts.next().and_then(size_pair).unwrap_or(want);
    let target = if back {
        saved.take().unwrap_or(want)
    } else {
        if saved.is_none() {
            *saved = Some(window.inner_size().to_logical(window.scale_factor()));
        }
        want
    };
    let room = screen_room(window);
    let inner = LogicalSize::new(target.width.min(room.width),
                                 target.height.min(room.height));
    let floor = LogicalSize::new(least.width.min(inner.width),
                                 least.height.min(inner.height));
    if window.is_maximized() {
        window.set_maximized(false);
    }
    window.set_min_inner_size(Some(floor));
    window.set_inner_size(inner);
}

fn run(
    event_loop: tao::event_loop::EventLoop<Host>,
    window: Window,
    webview: wry::WebView,
    proxy: tao::event_loop::EventLoopProxy<Host>,
) -> ! {
    let mut core: Option<pycore::Core> = None;
    let mut handshake: Option<pycore::Handshake> = None;
    let mut quitting = false;
    let mut previous: Option<LogicalSize<f64>> = None;

    event_loop.run(move |event, _target, control_flow| {
        *control_flow = ControlFlow::Wait;
        match event {
            Event::NewEvents(StartCause::Init) => {
                match pycore::locate() {
                    Ok(plan) => {
                        let sink_proxy = proxy.clone();
                        match pycore::Core::spawn(&plan, move |event| {
                            let _ = sink_proxy.send_event(Host::Core(event));
                        }) {
                            Ok(started) => core = Some(started),
                            Err(error) => fail(&webview, &format!(
                                "Could not start the core:<br>{} {}<br><br>{}",
                                plan.program.display(),
                                plan.args.join(" "),
                                error
                            )),
                        }
                    }
                    Err(error) => fail(&webview, &error),
                }
            }

            Event::UserEvent(Host::Core(pycore::CoreEvent::Ready(ready))) => {
                webview.load_url(&ready.url()).ok();
                handshake = Some(ready);
            }
            Event::UserEvent(Host::Core(pycore::CoreEvent::Log(line))) => {
                #[cfg(debug_assertions)]
                println!("[core] {line}");
                #[cfg(not(debug_assertions))]
                let _ = line;
            }
            Event::UserEvent(Host::Core(pycore::CoreEvent::Exited)) => {
                if quitting {
                    *control_flow = ControlFlow::Exit;
                } else {
                    let code = core.as_mut().and_then(|c| c.exit_code());
                    if code == Some(CORE_ALREADY_RUNNING) {
                        fail(&webview, "ExVR is already running.<br><br>Its window is \
                             open somewhere, or its icon is in the notification area \
                             next to the clock.");
                    } else {
                        fail(&webview, &format!(
                            "The ExVR core stopped unexpectedly (exit code {}).\
                             <br><br>settings/logs/exvr.log has what it printed.",
                            code.map(|c| c.to_string()).unwrap_or_else(|| "unknown".into())
                        ));
                    }
                }
            }
            Event::UserEvent(Host::Core(pycore::CoreEvent::Stalled)) => {
                fail(&webview, "The core has not finished starting.<br><br>It is \
                     still running, so this may just be a slow first launch after \
                     an update. settings/logs/exvr.log says how far it got.");
            }

            Event::UserEvent(Host::Ipc(message)) => match message.as_str() {
                "drag" => {
                    let _ = window.drag_window();
                }
                "minimize" => window.set_minimized(true),
                "maximize" => window.set_maximized(!window.is_maximized()),
                "hide" => window.set_visible(false),
                "close" => {
                    quitting = true;
                    stop(&mut core, handshake.as_ref());
                    *control_flow = ControlFlow::Exit;
                }
                spec if spec.starts_with("size:") || spec.starts_with("size-back:") => {
                    let back = spec.starts_with("size-back:");
                    if let Some((_, body)) = spec.split_once(':') {
                        resize(&window, body, &mut previous, back);
                    }
                }
                other => {
                    #[cfg(debug_assertions)]
                    println!("[host] unknown ipc message: {other}");
                    #[cfg(not(debug_assertions))]
                    let _ = other;
                }
            },

            Event::UserEvent(Host::Menu(MenuKind::Show)) => {
                window.set_visible(true);
                window.set_focus();
            }
            Event::UserEvent(Host::Menu(MenuKind::Quit)) => {
                quitting = true;
                stop(&mut core, handshake.as_ref());
                *control_flow = ControlFlow::Exit;
            }

            Event::WindowEvent {
                event: WindowEvent::ThemeChanged(theme),
                ..
            } => {
                let _ = webview.set_theme(page_theme(theme));
                let _ = webview.set_background_color(page_background(theme));
            }

            Event::WindowEvent {
                event: WindowEvent::CloseRequested,
                ..
            } => {
                quitting = true;
                stop(&mut core, handshake.as_ref());
                *control_flow = ControlFlow::Exit;
            }

            _ => {}
        }
    })
}

fn stop(core: &mut Option<pycore::Core>, handshake: Option<&pycore::Handshake>) {
    if let Some(core) = core.as_mut() {
        core.shutdown(handshake);
    }
}

fn fail(webview: &wry::WebView, html: &str) {
    let escaped = serde_json::to_string(html).unwrap_or_else(|_| "\"\"".into());
    let _ = webview.evaluate_script(&format!("window.exvrFail && window.exvrFail({escaped})"));
}
