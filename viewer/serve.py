# -*- coding: utf-8 -*-
"""Deeeeep Research 报告浏览器。

viewer 资源从脚本所在目录读，报告从 CLI 参数（或当前工作目录）的 reports/ 子目录读。
每次浏览器请求 /viewer/manifest.json 时重新扫描 reports 目录，新增报告刷新即可。

用法：
  py serve.py                    # 报告目录 = CWD/reports/
  py serve.py /path/to/project   # 报告目录 = /path/to/project/reports/
"""

import sys
if sys.version_info < (3, 7):
    sys.stderr.write("需要 Python 3.7+，当前版本 %s\n" % sys.version)
    sys.exit(1)

import http.server
import json
import re
import socketserver
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import unquote

VIEWER = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
REPORTS = ROOT / "reports"
PORT = 8765

H1_RE = re.compile(r"^#\s+(.+)$")
META_LINE_RE = re.compile(r"^>\s*(.+?)\s*$")
CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


def count_words(text: str) -> int:
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


def build_manifest_json() -> str:
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
    return json.dumps(manifest, ensure_ascii=False, indent=2)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        raw_path = self.path.split("?", 1)[0].split("#", 1)[0]
        path = unquote(raw_path)

        if path == "/" or path == "":
            self.send_response(302)
            self.send_header("Location", "/viewer/")
            self.end_headers()
            return

        if path.rstrip("/") == "/viewer/manifest.json":
            try:
                data = build_manifest_json().encode("utf-8")
            except Exception as e:
                print(f"[warn] build manifest failed: {e}", file=sys.stderr)
                self.send_error(500)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        if path.startswith("/viewer/"):
            rel = path[len("/viewer/"):]
            if not rel or rel == "":
                rel = "index.html"
            file_path = VIEWER / rel
            self._serve_file(file_path)
            return

        if path.startswith("/reports/"):
            rel = path[len("/reports/"):]
            file_path = REPORTS / rel
            self._serve_file(file_path)
            return

        self.send_error(404)

    def _serve_file(self, file_path: Path):
        file_path = file_path.resolve()
        if not file_path.is_file():
            self.send_error(404)
            return

        ext = file_path.suffix.lower()
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".md": "text/markdown; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
        }
        ct = content_types.get(ext, "application/octet-stream")

        try:
            data = file_path.read_bytes()
        except Exception:
            self.send_error(500)
            return

        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main():
    url = f"http://127.0.0.1:{PORT}/viewer/"
    print()
    print("  Deeeeep Research 报告浏览器")
    print(f"  地址: {url}")
    print(f"  Viewer: {VIEWER}")
    print(f"  报告目录: {REPORTS}")
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
