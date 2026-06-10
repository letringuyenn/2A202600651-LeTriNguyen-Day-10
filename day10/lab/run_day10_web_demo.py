"""Launch the Day 10 FastAPI demo."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is not installed. Run: "
            f"{sys.executable} -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    print("Day 10 Web Demo running at http://127.0.0.1:8000")
    uvicorn.run("day10_web_demo:app", host="127.0.0.1", port=8000, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
