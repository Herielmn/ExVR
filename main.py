import sys

if __name__ == "__main__" and "--drivers" in sys.argv:
    from utils.drivers import main as drivers_main
    sys.exit(drivers_main(sys.argv))

import warnings

warnings.filterwarnings("ignore")

import onnxruntime as _onnxruntime_preload

from api import server as api_server
from core.app import Core
from utils import bootstrap, drivers, instance, logfile, metrics
from utils.language import bilingual
from utils.paths import app_str

EXIT_ALREADY_RUNNING = 6


def unwritable_warning():
    return (
        bilingual("Settings cannot be saved", "设置无法保存"),
        bilingual("ExVR cannot write to its own folder, so nothing you change "
                  "here will be kept.\n\n"
                  f"Move ExVR out of {app_str()} into a folder you own, "
                  "such as your Documents folder, and start it again.",
                  "ExVR 无法写入自己所在的目录，所以这里改的任何设置都不会被保存。\n\n"
                  f"请把 ExVR 从 {app_str()} 移到你有写权限的目录"
                  "（例如「文档」），然后重新启动。"),
    )


def main(argv):
    logfile.install()
    if not instance.claim():
        print(bilingual("ExVR is already running; this second copy is closing so it "
                        "cannot take the control ports from the first one.",
                        "ExVR 已经在运行，这一份会直接退出，"
                        "以免抢走第一份的控制端口。"))
        return EXIT_ALREADY_RUNNING
    logfile.start_fresh()
    metrics.start_reporter()
    bootstrap.load_all()

    core = Core()
    core.start()
    if not drivers.writable(app_str("settings")):
        core.display_message(*unwritable_warning())

    api_server.start(handshake="--handshake" in argv)
    try:
        core.wait()
    except KeyboardInterrupt:
        pass
    core.shutdown()
    api_server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
