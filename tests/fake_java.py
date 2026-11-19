"""假 Java：模拟一个最小 Minecraft 服务端的标准输出与 stop 行为。

R1 用它验证进程守护与控制台，不需要真的 Java 与 8 GB 内存。
"""

from __future__ import annotations

import sys
import time

PLAYERS = ["Steve", "Alex"]


def main() -> int:
    print("[Server thread/INFO]: Starting minecraft server version 1.20.1")
    print("[Server thread/INFO]: Preparing level \"world\"")
    time.sleep(0.05)
    print('[Server thread/INFO]: Done (0.42s)! For help, type "help"')
    sys.stdout.flush()

    for raw in sys.stdin:
        command = raw.strip()
        if not command:
            continue
        if command == "stop":
            print("[Server thread/INFO]: Stopping the server")
            sys.stdout.flush()
            return 0
        if command == "list":
            print(
                f"There are {len(PLAYERS)} of a max of 20 players online: "
                + ", ".join(PLAYERS)
            )
            sys.stdout.flush()
            continue
        if command == "crash":
            print("[Server thread/ERROR]: simulated crash", flush=True)
            return 1
        print(f"[Server thread/INFO]: executed {command}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
