# -*- coding: utf-8 -*-
"""一次性工具：下载 resumable.js 到 static/vendor/（proxy 上传通道的前端库）。"""
import os
import sys
import urllib.request

URL = "https://unpkg.com/resumablejs@1.1.0/resumable.js"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "static", "vendor", "resumable.js")


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "study-assistant/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()
    with open(OUT, "wb") as fh:
        fh.write(body)
    print("downloaded", len(body), "bytes ->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
