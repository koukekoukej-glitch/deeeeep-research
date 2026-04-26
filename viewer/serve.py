# -*- coding: utf-8 -*-
"""本地报告浏览器的启动脚本。

扫描 ../reports/ 目录、生成 manifest.json、启动 http server、打开浏览器。
每次浏览器请求 /viewer/manifest.json 时会重新扫描目录，
所以新增报告只需在浏览器里刷新即可，不必重启服务。
"""

import sys
if sys.version_info < (3, 7):
    sys.stderr.write("需要 Python 3.7+，当前版本 %s\n" % sys.version)
    sys.exit(1)

import http.server
import json
import re
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
VIEWER = ROOT / "viewer"
PORT = 8765

H1_RE = re.compile(r"^#\s+(.+)$")
META_LINE_RE = re.compile(r"^>\s*(.+?)\s*$")
CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


def count_words(text: str) -> int:
    """中文按字、英文按词。markdown 标记和 sources URL 影响有限，估算够用。"""
    return len(CJK_RE.findall(text)) + len(EN_WORD_RE.findall(text))


def parse_metadata(md_text: str):
    title = None
    meta_lines = []
    summary = None
    saw_h1 = False
    after_meta_text = []
    for raw in md_text.splitlines():
        line = raw.rstrip()
        if not saw_h1:
            m = H1_RE.match(line)
            if m:
                title = m.group(1).strip()
                saw_h1 = True
            continue
        if line.startswith("> "):
            mm = META_LINE_RE.match(line)
            if mm:
                meta_lines.append(mm.group(1))
            continue
        if line.startswith("---") or not line.strip():
            continue
        if line.startswith("#"):
            continue
        after_meta_text.append(line.strip())
        if len(" ".join(after_meta_text)) > 200:
            break
    if after_meta_text:
        summary = " ".join(after_meta_text)
        if len(summary) > 240:
            summary = summary[:240].rstrip() + "…"
    return title, meta_lines, summary


def build_manifest():
    items = []
    if REPORTS.exists():
        for p in sorted(REPORTS.glob("*.md")):
            try:
                text = p.read_text(encoding="utf-8")
            except Exception as e:
                print(f"[warn] failed to read {p}: {e}", file=sys.stderr)
                continue
            title, meta_lines, summary = parse_metadata(text)
            st = p.stat()
            sources = p.with_name(p.stem + ".sources.json")
            items.append({
                "file": f"reports/{p.name}",
                "name": p.stem,
                "title": title or p.stem,
                "meta": meta_lines,
                "summary": summary,
                "mtime": st.st_mtime,
                "size": st.st_size,
                "word_count": count_words(text),
                "has_sources": sources.exists(),
                "sources_file": f"reports/{sources.name}" if sources.exists() else None,
            })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    manifest = {
        "generated_at": time.time(),
        "reports": items,
    }
    out = VIEWER / "manifest.json"
    out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path.rstrip("/") == "/viewer/manifest.json":
            try:
                build_manifest()
            except Exception as e:
                print(f"[warn] rebuild manifest failed: {e}", file=sys.stderr)
        return super().do_GET()


def main():
    build_manifest()
    url = f"http://127.0.0.1:{PORT}/viewer/"
    print()
    print("  Deeeeep Research 报告浏览器")
    print(f"  地址: {url}")
    print(f"  根目录: {ROOT}")
    print("  按 Ctrl+C 停止")
    print()

    threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n  服务已停止。")
    except OSError as e:
        if "Address already in use" in str(e) or getattr(e, "errno", None) in (98, 10048):
            print(f"  端口 {PORT} 已被占用，可能是你已经开过一个浏览器实例。", file=sys.stderr)
            print(f"  直接打开 {url} 试试。", file=sys.stderr)
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
