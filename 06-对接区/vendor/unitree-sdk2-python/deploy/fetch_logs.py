#!/usr/bin/env python3
"""在笔记本上拉取/实时接收 PC2 上的服务日志，存到本地文件。

不需要 SSH、不需要外接屏幕。直接通过服务的 HTTP 日志接口。

用法（在仓库根目录执行）:
    # 抓最近 200 行，打印到屏幕
    python3 deploy/fetch_logs.py

    # 抓最近 1000 行，存到本地文件
    python3 deploy/fetch_logs.py --n 1000 --out logs.txt

    # 实时流，持续写到本地文件（Ctrl+C 停止）
    python3 deploy/fetch_logs.py --stream --out logs.txt

    # 实时流直接打印到屏幕
    python3 deploy/fetch_logs.py --stream
"""

import argparse
import json
import sys
import time
import urllib.request
from typing import Optional, List

DEFAULT_HOST = "192.168.0.248"
DEFAULT_PORT = 8888


def fetch_recent(host: str, port: int, n: int, token: Optional[str]) -> List[str]:
    url = f"http://{host}:{port}/logs?n={n}"
    req = urllib.request.Request(url)
    if token:
        req.add_header("X-Robot-Token", token)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return data.get("lines", [])


def stream(host: str, port: int, token: Optional[str], out):
    """SSE 实时流，逐行写到 out（文件对象或 sys.stdout）。"""
    url = f"http://{host}:{port}/logs/stream"
    req = urllib.request.Request(url)
    if token:
        req.add_header("X-Robot-Token", token)
    print(f"实时接收日志 {url} ... (Ctrl+C 停止)", file=sys.stderr)
    try:
        with urllib.request.urlopen(req, timeout=None) as resp:
            buf = b""
            for chunk in iter(lambda: resp.read(1024), b""):
                buf += chunk
                while b"\n\n" in buf:
                    raw, buf = buf.split(b"\n\n", 1)
                    for line in raw.decode("utf-8", "replace").splitlines():
                        if line.startswith("data: "):
                            out.write(line[6:] + "\n")
                            out.flush()
                        # 以 ": " 开头的是心跳注释，忽略
    except KeyboardInterrupt:
        print("\n已停止", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="拉取/实时接收 PC2 服务日志到本地")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--token", default=None)
    p.add_argument("--n", type=int, default=200, help="抓取最近 N 行（非 stream 模式）")
    p.add_argument("--stream", action="store_true", help="实时流模式")
    p.add_argument("--out", default=None, help="存到本地文件（不给则打印到屏幕）")
    args = p.parse_args()

    out = open(args.out, "a", encoding="utf-8") if args.out else sys.stdout

    if args.stream:
        stream(args.host, args.port, args.token, out)
    else:
        lines = fetch_recent(args.host, args.port, args.n, args.token)
        for line in lines:
            out.write(line + "\n")
        if args.out:
            print(f"已写入 {len(lines)} 行到 {args.out}", file=sys.stderr)

    if args.out:
        out.close()


if __name__ == "__main__":
    main()
