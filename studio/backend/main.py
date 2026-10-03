"""Studio backend entry point.

python -m studio.backend.main [--host 127.0.0.1] [--port 8600]
"""

import argparse
import logging

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="CreativeForge Studio backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8600)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    # 业务日志（showcase 配音链路等 studio.* 命名空间）：uvicorn 默认只配置
    # 自己的 logger，根 logger 保持 WARNING 会吞掉 INFO 级业务日志
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s: %(message)s"))
    studio_log = logging.getLogger("studio")
    studio_log.addHandler(handler)
    studio_log.setLevel(logging.INFO)

    uvicorn.run("studio.backend.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
