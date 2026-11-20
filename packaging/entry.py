"""打包入口：Nuitka 从这里开始，避免直接编译 __main__。"""

from hoshi.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
