"""Studio backend entry point.

    python -m studio.backend.main [--host 127.0.0.1] [--port 8600]
"""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="CreativeForge Studio backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8600)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "studio.backend.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )


if __name__ == "__main__":
    main()
