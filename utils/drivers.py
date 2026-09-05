from __future__ import annotations

import filecmp
import os
import shutil
import winreg

from utils import elevate
from utils.paths import app_str

DRIVERS = ("vmt", "vrto3d")
VRCFT_DLL = "VRCFT-MediapipePro.dll"

STEAMVR_ONLY = "--steamvr-only"

EXIT_OK = 0
EXIT_STEAMVR_RUNNING = 2
EXIT_VRCFT_RUNNING = 3
EXIT_DENIED = 4
EXIT_FAILED = 5

EXIT_BY_REASON = {
    "steamvr_running": EXIT_STEAMVR_RUNNING,
    "vrcft_running": EXIT_VRCFT_RUNNING,
    "denied": EXIT_DENIED,
}
REASON_BY_EXIT = {code: reason for reason, code in EXIT_BY_REASON.items()}


class DriverError(Exception):

    def __init__(self, reason, detail=""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def source_root():
    return app_str("drivers")


def steam_paths():
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Valve\Steam",
            0,
            winreg.KEY_READ,
        ) as reg_key:
            steam_path, _ = winreg.QueryValueEx(reg_key, "InstallPath")
    except OSError as exc:
        print(f"Error accessing registry or file system: {exc}")
        return None, None, None
    driver_path = os.path.join(steam_path, "steamapps", "common", "SteamVR", "drivers")
    steamvr_bin = os.path.join(steam_path, "steamapps", "common", "SteamVR", "bin")
    if not os.path.exists(steamvr_bin):
        steamvr_bin = None
    vrcft_path = os.path.join(os.getenv("APPDATA"), "VRCFaceTracking", "CustomLibs")
    return driver_path, vrcft_path, steamvr_bin


def file_matches(source, destination):
    return (
        os.path.exists(source)
        and os.path.exists(destination)
        and filecmp.cmp(source, destination, shallow=False)
    )


def driver_files_complete(source_root_path, destination_root):
    if not os.path.isdir(source_root_path) or not os.path.isdir(destination_root):
        return False
    for dir_path, _, filenames in os.walk(source_root_path):
        rel_dir = os.path.relpath(dir_path, source_root_path)
        target_dir = destination_root if rel_dir == "." \
            else os.path.join(destination_root, rel_dir)
        for filename in filenames:
            source = os.path.join(dir_path, filename)
            destination = os.path.join(target_dir, filename)
            if not os.path.exists(destination):
                return False
            if filename.lower().endswith(".dll") \
                    and not filecmp.cmp(source, destination, shallow=False):
                return False
    return True


def state():
    driver_path, vrcft_path, steamvr_bin = steam_paths()
    if driver_path is None:
        return False, None, None, None
    root = source_root()
    complete = all(
        driver_files_complete(os.path.join(root, driver),
                              os.path.join(driver_path, driver))
        for driver in DRIVERS
    )
    dll_ok = file_matches(os.path.join(root, VRCFT_DLL),
                          os.path.join(vrcft_path, VRCFT_DLL))
    return bool(complete and dll_ok), driver_path, vrcft_path, steamvr_bin


def copy_changed_file(source, destination):
    if not os.path.exists(source):
        return False
    if os.path.exists(destination) and filecmp.cmp(source, destination, shallow=False):
        return False
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy2(source, destination)
    return True


def copy_changed_tree(source_root_path, destination_root):
    if not os.path.exists(source_root_path):
        return False
    changed = False
    for dir_path, _, filenames in os.walk(source_root_path):
        rel_dir = os.path.relpath(dir_path, source_root_path)
        target_dir = destination_root if rel_dir == "." \
            else os.path.join(destination_root, rel_dir)
        os.makedirs(target_dir, exist_ok=True)
        for filename in filenames:
            changed = copy_changed_file(os.path.join(dir_path, filename),
                                        os.path.join(target_dir, filename)) or changed
    return changed


def copy_missing_files_and_changed_dlls(source_root_path, destination_root):
    if not os.path.exists(source_root_path):
        return False
    changed = False
    for dir_path, _, filenames in os.walk(source_root_path):
        rel_dir = os.path.relpath(dir_path, source_root_path)
        target_dir = destination_root if rel_dir == "." \
            else os.path.join(destination_root, rel_dir)
        for filename in filenames:
            source = os.path.join(dir_path, filename)
            destination = os.path.join(target_dir, filename)
            if not os.path.exists(destination):
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy2(source, destination)
                changed = True
            elif filename.lower().endswith(".dll") \
                    and not filecmp.cmp(source, destination, shallow=False):
                shutil.copy2(source, destination)
                changed = True
    return changed


def writable(directory):
    if directory is None:
        return False
    probe_dir = directory
    while probe_dir and not os.path.isdir(probe_dir):
        parent = os.path.dirname(probe_dir)
        if parent == probe_dir:
            return False
        probe_dir = parent
    probe = os.path.join(probe_dir, ".exvr-write-probe")
    try:
        with open(probe, "wb"):
            pass
        os.remove(probe)
    except OSError:
        return False
    return True


def open_denied(path):
    try:
        handle = os.open(path, os.O_RDWR)
    except PermissionError:
        return True
    except OSError:
        return False
    os.close(handle)
    return False


def first_locked(destination_root):
    for dir_path, _dirnames, filenames in os.walk(destination_root):
        for filename in filenames:
            path = os.path.join(dir_path, filename)
            if open_denied(path):
                return path
    return None


def first_locked_overwrite(source_root_path, destination_root):
    for dir_path, _dirnames, filenames in os.walk(source_root_path):
        rel_dir = os.path.relpath(dir_path, source_root_path)
        target_dir = destination_root if rel_dir == "." \
            else os.path.join(destination_root, rel_dir)
        for filename in filenames:
            destination = os.path.join(target_dir, filename)
            if not os.path.exists(destination):
                continue
            if filecmp.cmp(os.path.join(dir_path, filename), destination,
                           shallow=False):
                continue
            if open_denied(destination):
                return destination
    return None


def holders(path):
    try:
        import psutil
    except ImportError:
        return []
    wanted = os.path.normcase(os.path.abspath(path))
    found = set()
    for process in psutil.process_iter(["name"]):
        try:
            for mapping in process.memory_maps():
                if os.path.normcase(mapping.path) == wanted:
                    found.add(process.info["name"])
                    break
        except Exception:
            continue
    return sorted(found)


def in_use(path):
    names = holders(path)
    if names:
        return f"{path}\n{', '.join(names)}"
    return path


def restore_missing(source_root_path, destination_root):
    for dir_path, _dirnames, filenames in os.walk(source_root_path):
        rel_dir = os.path.relpath(dir_path, source_root_path)
        target_dir = destination_root if rel_dir == "." \
            else os.path.join(destination_root, rel_dir)
        for filename in filenames:
            destination = os.path.join(target_dir, filename)
            if os.path.exists(destination):
                continue
            try:
                os.makedirs(target_dir, exist_ok=True)
                shutil.copy2(os.path.join(dir_path, filename), destination)
            except OSError:
                pass


def restore(driver_path):
    root = source_root()
    for driver in DRIVERS:
        restore_missing(os.path.join(root, driver),
                        os.path.join(driver_path, driver))


def sync(driver_path, vrcft_path):
    if driver_path is None:
        return {"updated": [], "error": None}
    root = source_root()
    updated = []
    try:
        if writable(driver_path):
            for driver in DRIVERS:
                destination = os.path.join(driver_path, driver)
                if not os.path.isdir(destination):
                    continue
                if copy_missing_files_and_changed_dlls(os.path.join(root, driver),
                                                      destination):
                    updated.append(driver)
        elif not all(driver_files_complete(os.path.join(root, driver),
                                          os.path.join(driver_path, driver))
                     for driver in DRIVERS
                     if os.path.isdir(os.path.join(driver_path, driver))):
            print("The installed SteamVR drivers are out of date; "
                  "use Install Drivers to refresh them.")
        if vrcft_path is not None:
            destination = os.path.join(vrcft_path, VRCFT_DLL)
            if os.path.exists(destination) \
                    and copy_changed_file(os.path.join(root, VRCFT_DLL), destination):
                updated.append(VRCFT_DLL)
    except (PermissionError, OSError) as exc:
        return {"updated": updated, "error": str(exc)}
    if updated:
        print("Updated installed components:", ", ".join(updated))
    return {"updated": updated, "error": None}


def install(driver_path=None, vrcft_path=None):
    root = source_root()
    if driver_path is not None:
        for driver in DRIVERS:
            locked = first_locked_overwrite(os.path.join(root, driver),
                                            os.path.join(driver_path, driver))
            if locked is not None:
                raise DriverError("steamvr_running", in_use(locked))
        try:
            for driver in DRIVERS:
                source = os.path.join(root, driver)
                destination = os.path.join(driver_path, driver)
                if not os.path.exists(destination):
                    shutil.copytree(source, destination)
                else:
                    copy_changed_tree(source, destination)
        except PermissionError as exc:
            raise DriverError("steamvr_running", str(exc)) from exc
    if vrcft_path is not None:
        destination = os.path.join(vrcft_path, VRCFT_DLL)
        try:
            if not os.path.exists(destination):
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy(os.path.join(root, VRCFT_DLL), destination)
            else:
                copy_changed_file(os.path.join(root, VRCFT_DLL), destination)
        except PermissionError as exc:
            raise DriverError("vrcft_running", str(exc)) from exc


def uninstall(driver_path=None, vrcft_path=None):
    if driver_path is not None:
        for driver in DRIVERS:
            locked = first_locked(os.path.join(driver_path, driver))
            if locked is not None:
                raise DriverError("steamvr_running", in_use(locked))
        for driver in DRIVERS:
            dir_path = os.path.join(driver_path, driver)
            try:
                shutil.rmtree(dir_path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                detail = str(exc)
                restore(driver_path)
                raise DriverError("steamvr_running", detail) from exc
            if os.path.exists(dir_path):
                restore(driver_path)
                raise DriverError("steamvr_running", in_use(dir_path))
    if vrcft_path is not None:
        try:
            os.remove(os.path.join(vrcft_path, VRCFT_DLL))
        except FileNotFoundError:
            pass
        except PermissionError as exc:
            raise DriverError("vrcft_running", str(exc)) from exc


def apply(action, driver_path, vrcft_path):
    if driver_path is None:
        return DriverError("no_steamvr")
    worker = install if action == "install" else uninstall
    if writable(driver_path) or elevate.is_admin():
        try:
            worker(driver_path, None)
        except DriverError as exc:
            return exc
        except OSError as exc:
            return DriverError("failed", str(exc))
    else:
        code = elevate.run(["--drivers", action, STEAMVR_ONLY])
        if code is elevate.DECLINED:
            return DriverError("declined")
        if code != EXIT_OK:
            return DriverError(REASON_BY_EXIT.get(code, "failed"))
    if vrcft_path is not None:
        try:
            worker(None, vrcft_path)
        except DriverError as exc:
            return exc
        except OSError as exc:
            return DriverError("failed", str(exc))
    return None


def main(argv):
    action = None
    for index, argument in enumerate(argv):
        if argument == "--drivers" and index + 1 < len(argv):
            action = argv[index + 1]
    if action not in ("install", "uninstall"):
        print(f"unknown --drivers action {action!r}")
        return EXIT_FAILED
    driver_path, vrcft_path, steamvr_bin = steam_paths()
    if driver_path is None or steamvr_bin is None:
        print("SteamVR is not installed or could not be found.")
        return EXIT_FAILED
    if STEAMVR_ONLY in argv:
        vrcft_path = None
        try:
            (install if action == "install" else uninstall)(driver_path, None)
        except DriverError as exc:
            problem = exc
        except OSError as exc:
            problem = DriverError("failed", str(exc))
        else:
            problem = None
    else:
        problem = apply(action, driver_path, vrcft_path)
    if problem is not None:
        print(f"{action} failed: {problem.reason} {problem.detail}")
        return EXIT_BY_REASON.get(problem.reason, EXIT_FAILED)
    print(f"drivers {action} complete")
    return EXIT_OK
