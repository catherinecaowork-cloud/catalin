from __future__ import annotations

import argparse
import sys
from pathlib import Path

from autotest_executor.worker import WorkerDaemon


def _default_workspace() -> Path:
    return Path.cwd() / "var" / "worker"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runner", description="autotest-platform 执行器")
    sub = parser.add_subparsers(dest="command", required=True)

    worker = sub.add_parser("worker", help="常驻领任务并执行")
    worker.add_argument("--server", default="http://127.0.0.1:8910", help="控制面地址")
    worker.add_argument("--name", default="local-worker", help="执行器名称")
    worker.add_argument("--workspace", type=Path, default=None, help="本地产物目录")
    worker.add_argument("--project", default="default", help="项目 ID")
    worker.add_argument(
        "--no-headed",
        action="store_true",
        help="声明本机不能开窗（容器 / 无桌面服务器）",
    )
    worker.add_argument("--once", action="store_true", help="只执行一个任务后退出（CI 用）")

    args = parser.parse_args(argv)

    if args.command == "worker":
        daemon = WorkerDaemon(
            server=args.server,
            name=args.name,
            workspace=args.workspace or _default_workspace(),
            headed_capable=not args.no_headed,
            project_id=args.project,
        )
        try:
            if args.once:
                had_job = daemon.run_once()
                if not had_job:
                    print("队列里没有任务")
                    return 1
                return 0
            daemon.run_forever()
        except KeyboardInterrupt:
            print("\n已停止")
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
