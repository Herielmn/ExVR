use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::os::windows::io::AsRawHandle;
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::Duration;

use serde::Deserialize;
use windows::Win32::Foundation::HANDLE;

use crate::job::Job;

const HANDSHAKE_PREFIX: &str = "EXVR-HANDSHAKE ";
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
pub const READY_TIMEOUT: Duration = Duration::from_secs(90);

#[derive(Debug, Clone, Deserialize)]
pub struct Handshake {
    pub http: u16,
    #[allow(dead_code)]
    pub ws: u16,
    pub token: String,
    #[allow(dead_code)]
    pub pid: u32,
}

impl Handshake {
    pub fn url(&self) -> String {
        format!("http://127.0.0.1:{}/?k={}", self.http, self.token)
    }
}

#[derive(Debug)]
pub enum CoreEvent {
    Ready(Handshake),
    Log(String),
    Exited,
    Stalled,
}

pub struct Plan {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub cwd: PathBuf,
}

fn repo_root_from(start: &Path) -> Option<PathBuf> {
    let mut directory = Some(start);
    while let Some(current) = directory {
        if current.join("main.py").is_file() {
            return Some(current.to_path_buf());
        }
        directory = current.parent();
    }
    None
}

pub fn locate() -> Result<Plan, String> {
    let exe = std::env::current_exe().map_err(|error| error.to_string())?;
    let here = exe.parent().ok_or("the host has no directory")?.to_path_buf();

    if let Ok(explicit) = std::env::var("EXVR_CORE") {
        let program = PathBuf::from(&explicit);
        let cwd = program.parent().unwrap_or(&here).to_path_buf();
        return Ok(Plan { program, args: core_args(), cwd });
    }

    for candidate in [here.join("ExVR.exe"), here.join("core").join("ExVR.exe")] {
        if candidate.is_file() {
            let cwd = candidate.parent().unwrap_or(&here).to_path_buf();
            return Ok(Plan { program: candidate, args: core_args(), cwd });
        }
    }

    if let Some(root) = repo_root_from(&here) {
        let python = std::env::var("EXVR_PYTHON").unwrap_or_else(|_| "python".into());
        let mut args = vec![root.join("main.py").to_string_lossy().into_owned()];
        args.extend(core_args());
        return Ok(Plan { program: PathBuf::from(python), args, cwd: root });
    }

    Err(format!(
        "no core found: expected ExVR.exe next to {}, or main.py in an ancestor \
         directory, or EXVR_CORE set",
        here.display()
    ))
}

fn core_args() -> Vec<String> {
    vec!["--headless".into(), "--handshake".into()]
}

fn classify(line: String) -> CoreEvent {
    match line.strip_prefix(HANDSHAKE_PREFIX) {
        Some(payload) => match serde_json::from_str::<Handshake>(payload) {
            Ok(handshake) => CoreEvent::Ready(handshake),
            Err(error) => CoreEvent::Log(format!("unreadable handshake: {error}")),
        },
        None => CoreEvent::Log(line),
    }
}

pub struct Core {
    child: Child,
    _job: Option<Job>,
}

impl Core {
    pub fn spawn<F>(plan: &Plan, sink: F) -> std::io::Result<Self>
    where
        F: Fn(CoreEvent) + Send + Clone + 'static,
    {
        let mut child = Command::new(&plan.program)
            .args(&plan.args)
            .current_dir(&plan.cwd)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()?;

        let job = Job::new();
        if let Some(job) = job.as_ref() {
            job.adopt(HANDLE(child.as_raw_handle()));
        }

        let stdout = child.stdout.take().expect("stdout was piped");
        let stderr = child.stderr.take().expect("stderr was piped");
        let watchdog = sink.clone();
        let ready_flag = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
        let watched = ready_flag.clone();
        std::thread::Builder::new()
            .name("core-watchdog".into())
            .spawn(move || {
                std::thread::sleep(READY_TIMEOUT);
                if !watched.load(std::sync::atomic::Ordering::Relaxed) {
                    watchdog(CoreEvent::Stalled);
                }
            })?;
        std::thread::Builder::new()
            .name("core-stderr".into())
            .spawn(move || {
                let mut reader = BufReader::new(stderr);
                let mut sink = Vec::new();
                let _ = reader.read_to_end(&mut sink);
            })?;
        std::thread::Builder::new()
            .name("core-stdout".into())
            .spawn(move || {
                let reader = BufReader::new(stdout);
                for line in reader.lines() {
                    let Ok(line) = line else { break };
                    let event = classify(line);
                    if matches!(event, CoreEvent::Ready(_)) {
                        ready_flag.store(true, std::sync::atomic::Ordering::Relaxed);
                    }
                    sink(event);
                }
                sink(CoreEvent::Exited);
            })?;

        Ok(Core { child, _job: job })
    }

    pub fn exit_code(&mut self) -> Option<i32> {
        match self.child.try_wait() {
            Ok(Some(status)) => Some(status.code().unwrap_or(-1)),
            _ => None,
        }
    }

    pub fn shutdown(&mut self, handshake: Option<&Handshake>) {
        if let Some(handshake) = handshake {
            let _ = post_quit(handshake);
            for _ in 0..60 {
                if self.exit_code().is_some() {
                    return;
                }
                std::thread::sleep(Duration::from_millis(100));
            }
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn post_quit(handshake: &Handshake) -> std::io::Result<()> {
    let mut stream = TcpStream::connect(("127.0.0.1", handshake.http))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    let request = format!(
        "POST /api/command/quit HTTP/1.1\r\n\
         Host: 127.0.0.1:{}\r\n\
         X-ExVR-Token: {}\r\n\
         Content-Length: 0\r\n\
         Connection: close\r\n\r\n",
        handshake.http, handshake.token
    );
    stream.write_all(request.as_bytes())?;
    stream.flush()?;
    let mut answer = Vec::new();
    let _ = stream.read_to_end(&mut answer);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;

    #[test]
    fn reads_the_handshake() {
        let line = format!(
            "{HANDSHAKE_PREFIX}{{\"http\": 8890, \"ws\": 8891, \
             \"token\": \"abc-123\", \"pid\": 4242}}"
        );
        match classify(line) {
            CoreEvent::Ready(handshake) => {
                assert_eq!(handshake.http, 8890);
                assert_eq!(handshake.ws, 8891);
                assert_eq!(handshake.token, "abc-123");
                assert_eq!(handshake.url(), "http://127.0.0.1:8890/?k=abc-123");
            }
            other => panic!("expected Ready, got {other:?}"),
        }
    }

    #[test]
    fn a_broken_handshake_is_a_log_line_not_a_panic() {
        let event = classify(format!("{HANDSHAKE_PREFIX}{{not json"));
        assert!(matches!(event, CoreEvent::Log(message) if message.contains("unreadable")));
    }

    #[test]
    fn ordinary_output_stays_ordinary() {
        let event = classify("capture 640.0 480.0 30.0 process 640 480".into());
        assert!(matches!(event, CoreEvent::Log(_)));
    }

    #[test]
    fn a_core_that_exits_is_reported_with_its_code() {
        let plan = Plan {
            program: PathBuf::from("cmd.exe"),
            args: vec!["/c".into(), "exit".into(), "3".into()],
            cwd: std::env::temp_dir(),
        };
        let (sender, receiver) = mpsc::channel();
        let mut core = Core::spawn(&plan, move |event| {
            let _ = sender.send(format!("{event:?}"));
        })
        .expect("cmd.exe should be spawnable");
        let first = receiver
            .recv_timeout(Duration::from_secs(10))
            .expect("no event from a process that exits immediately");
        assert_eq!(first, "Exited");
        for _ in 0..50 {
            if let Some(code) = core.exit_code() {
                assert_eq!(code, 3);
                return;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        panic!("the child never reported an exit code");
    }

    #[test]
    fn the_repository_is_found_by_walking_up() {
        let root = std::env::temp_dir().join("exvr-host-locate-test");
        let deep = root.join("host").join("target").join("release");
        std::fs::create_dir_all(&deep).unwrap();
        std::fs::write(root.join("main.py"), b"# stub\n").unwrap();
        assert_eq!(repo_root_from(&deep).as_deref(), Some(root.as_path()));
        assert_eq!(repo_root_from(std::env::temp_dir().as_path()), None);
        let _ = std::fs::remove_dir_all(&root);
    }
}
