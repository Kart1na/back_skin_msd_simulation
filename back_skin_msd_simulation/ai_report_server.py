"""Local AI report HTTP service for robot massage data.

The service accepts robot-side file paths, runs the existing alignment and
report pipeline, archives the generated HTML report, and exposes a small report
center for browsing historical reports.
"""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import shutil
import sys
import traceback
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse


MODULE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = MODULE_DIR.parent
INTERFACE_DIR = PROJECT_DIR / "lscure_report_interface"
REPORT_ARCHIVE_DIR = INTERFACE_DIR / "generated_reports"
REPORT_INDEX_PATH = REPORT_ARCHIVE_DIR / "index.json"

if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from report_generator import (  # noqa: E402
    FINAL_REPORT_INTERFACE_PATH,
    OUTPUT_DIR,
    generate_report,
)


REPORT_FILE_RE = re.compile(
    r"(?:report|browser_report|smart_massage|massage_detection|cover_preview|"
    r"body_chart|spine_stiffness_chart|spine_summary|qr)",
    re.IGNORECASE,
)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def _success(url: str, user_id: str, report_id: str) -> dict:
    return {
        "success": True,
        "message": "执行成功",
        "code": "0",
        "data": {"url": url},
    }


def _failure(message: str, code: str = "1") -> dict:
    return {
        "success": False,
        "message": message,
        "code": code,
        "data": {},
    }


def _safe_user_id(raw: str | None) -> str:
    if raw:
        cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")
        if cleaned:
            return cleaned[:60]
    return "force_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        raise ValueError("请求体不能为空，请提交 JSON 数据。")
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 格式错误：{exc.msg}") from exc


def _validate_input_paths(payload: dict) -> tuple[str | None, str, str]:
    point_cloud = payload.get("pointCloudPath")
    acupoints = payload.get("acuCloPath")
    trajectory = payload.get("robotPosToCameraPath")

    missing_fields = [
        name
        for name, value in (
            ("acuCloPath", acupoints),
            ("robotPosToCameraPath", trajectory),
        )
        if not value
    ]
    if missing_fields:
        raise ValueError("缺少必要字段：" + "、".join(missing_fields))

    missing_files = [
        f"{name}={value}"
        for name, value in (
            ("acuCloPath", acupoints),
            ("robotPosToCameraPath", trajectory),
        )
        if not Path(str(value)).is_file()
    ]
    if point_cloud and not Path(str(point_cloud)).is_file():
        missing_files.append(f"pointCloudPath={point_cloud}")

    if missing_files:
        raise FileNotFoundError("输入文件不存在：" + "；".join(missing_files))

    return (
        str(point_cloud) if point_cloud else None,
        str(acupoints),
        str(trajectory),
    )


def _load_report_index() -> list[dict]:
    if not REPORT_INDEX_PATH.is_file():
        return []
    try:
        data = json.loads(REPORT_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _save_report_index(items: list[dict]) -> None:
    REPORT_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_INDEX_PATH.write_text(
        json.dumps(items[:300], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _reports_for_response(base_url: str) -> list[dict]:
    reports = []
    for item in _load_report_index():
        normalized = dict(item)
        file_name = str(normalized.get("fileName", ""))
        if file_name:
            normalized["url"] = f"{base_url}/reports/{quote(file_name)}"
        reports.append(normalized)
    return reports


def _base_url(handler: BaseHTTPRequestHandler) -> str:
    host = handler.headers.get("Host")
    if host:
        return f"http://{host}"
    address, port = handler.server.server_address[:2]
    return f"http://{address}:{port}"


def _archive_generated_report(
    *,
    user_id: str,
    report_id: str,
    point_cloud: str | None,
    acupoints: str,
    trajectory: str,
    base_url: str,
) -> tuple[str, Path]:
    source_path = Path(FINAL_REPORT_INTERFACE_PATH)
    if not source_path.is_file():
        raise FileNotFoundError(f"报告文件未生成：{source_path}")

    REPORT_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"{user_id}_{timestamp}.html"
    target_path = REPORT_ARCHIVE_DIR / file_name
    shutil.copyfile(source_path, target_path)

    report_url = f"{base_url}/reports/{quote(file_name)}"
    item = {
        "userId": user_id,
        "reportId": report_id,
        "fileName": file_name,
        "url": report_url,
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "sourcePaths": {
            "pointCloudPath": point_cloud,
            "acuCloPath": acupoints,
            "robotPosToCameraPath": trajectory,
        },
    }

    items = _load_report_index()
    items.insert(0, item)
    _save_report_index(items)
    return report_url, target_path


def _cleanup_transient_report_files(user_id: str) -> None:
    output_dir = Path(OUTPUT_DIR)
    if not output_dir.is_dir():
        return
    for path in output_dir.iterdir():
        if not path.is_file():
            continue
        if not path.name.startswith(user_id):
            continue
        if REPORT_FILE_RE.search(path.name):
            try:
                path.unlink()
            except OSError:
                pass


def generate_force_report_from_payload(payload: dict, base_url: str) -> dict:
    point_cloud, acupoints, trajectory = _validate_input_paths(payload)
    user_id = _safe_user_id(payload.get("userId"))
    report_id = payload.get("reportId") or f"AI-FORCE-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    sample_rate = float(payload.get("sampleRate", 20.0))
    threshold_mm = float(payload.get("thresholdMm", 25.0))
    logo_path = payload.get("logoPath")
    if logo_path and not Path(str(logo_path)).is_file():
        logo_path = None

    generate_report(
        user_id=user_id,
        logo_path=logo_path,
        report_id=report_id,
        use_ai_analysis=False,
        acupoints=acupoints,
        trajectory=trajectory,
        sample_rate=sample_rate,
        threshold_mm=threshold_mm,
    )

    report_url, _ = _archive_generated_report(
        user_id=user_id,
        report_id=report_id,
        point_cloud=point_cloud,
        acupoints=acupoints,
        trajectory=trajectory,
        base_url=base_url,
    )
    _cleanup_transient_report_files(user_id)
    return _success(report_url, user_id, report_id)


def _html_page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --navy: #0B2A4A;
      --teal: #00A6A6;
      --line: #E3EDF2;
      --bg: #F6FAFB;
      --text: #263238;
      --muted: #71828A;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--text);
      background: #fff;
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
    }}
    .shell {{
      width: min(1120px, calc(100% - 48px));
      margin: 0 auto;
      padding: 34px 0 52px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 24px;
      border-bottom: 2px solid var(--line);
      padding-bottom: 22px;
      margin-bottom: 24px;
    }}
    h1 {{
      margin: 0 0 7px;
      color: var(--navy);
      font-size: 28px;
      line-height: 1.25;
    }}
    .sub {{ color: var(--muted); font-size: 14px; }}
    .api {{
      color: var(--navy);
      background: var(--bg);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 16px;
      font-size: 13px;
      white-space: nowrap;
    }}
    .toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      margin-bottom: 18px;
    }}
    .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      padding: 0 16px;
      color: #fff;
      background: var(--teal);
      border-radius: 999px;
      text-decoration: none;
      font-weight: 700;
      font-size: 14px;
    }}
    table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0 12px;
    }}
    th {{
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      text-align: left;
      padding: 0 16px 2px;
    }}
    td {{
      background: var(--bg);
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      padding: 16px;
      font-size: 14px;
      vertical-align: middle;
    }}
    td:first-child {{
      border-left: 1px solid var(--line);
      border-radius: 16px 0 0 16px;
      color: var(--navy);
      font-weight: 800;
    }}
    td:last-child {{
      border-right: 1px solid var(--line);
      border-radius: 0 16px 16px 0;
      text-align: right;
    }}
    code {{
      color: var(--navy);
      background: #EEF7F8;
      border-radius: 8px;
      padding: 3px 7px;
    }}
    .empty {{
      padding: 42px;
      border: 1px dashed var(--line);
      border-radius: 18px;
      color: var(--muted);
      background: var(--bg);
      text-align: center;
    }}
  </style>
</head>
<body>
  <main class="shell">{body}</main>
</body>
</html>""".encode("utf-8")


def _render_report_center(handler: BaseHTTPRequestHandler) -> bytes:
    base_url = _base_url(handler)
    items = _load_report_index()
    rows = []
    for item in items:
        file_name = html.escape(str(item.get("fileName", "")))
        user_id = html.escape(str(item.get("userId", "")))
        report_id = html.escape(str(item.get("reportId", "")))
        created_at = html.escape(str(item.get("createdAt", "")))
        url = f"/reports/{quote(str(item.get('fileName', '')))}"
        rows.append(
            "<tr>"
            f"<td>{user_id}</td>"
            f"<td>{report_id}</td>"
            f"<td>{created_at}</td>"
            f"<td>{file_name}</td>"
            f'<td><a class="button" href="{url}" target="_blank" rel="noopener">查看报告</a></td>'
            "</tr>"
        )

    table = (
        "<table><thead><tr><th>用户编号</th><th>报告编号</th><th>生成时间</th>"
        "<th>报告文件</th><th></th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        if rows
        else '<div class="empty">还没有归档报告。机器人 POST 成功后，这里会自动出现可查看的报告。</div>'
    )

    body = f"""
<header>
  <div>
    <h1>LSCURE AI 报告中心</h1>
    <div class="sub">选择已经生成的智能按摩检测报告进行查看。</div>
  </div>
  <div class="api">POST <code>{html.escape(base_url)}/ai-report/force</code></div>
</header>
<div class="toolbar">
  <div class="sub">当前报告：<a href="/final" target="_blank" rel="noopener">打开最新报告</a></div>
  <a class="button" href="/api/reports">JSON 列表</a>
</div>
{table}
"""
    return _html_page("LSCURE AI 报告中心", body)


def _serve_bytes(
    handler: BaseHTTPRequestHandler,
    content: bytes,
    content_type: str,
    status: int = HTTPStatus.OK,
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def _serve_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    if not path.is_file():
        _serve_bytes(
            handler,
            _html_page("未找到报告", '<div class="empty">报告文件不存在。</div>'),
            "text/html; charset=utf-8",
            HTTPStatus.NOT_FOUND,
        )
        return
    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if path.suffix.lower() in {".html", ".htm"}:
        content_type = "text/html; charset=utf-8"
    data = path.read_bytes()
    _serve_bytes(handler, data, content_type)


class AIReportHandler(BaseHTTPRequestHandler):
    server_version = "LSCUREAIReport/1.0"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sys.stdout.write(f"[{timestamp}] {self.address_string()} {format % args}\n")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") != "/ai-report/force":
            _json_response(self, HTTPStatus.NOT_FOUND, _failure("接口不存在", "404"))
            return

        try:
            payload = _read_json_body(self)
            result = generate_force_report_from_payload(payload, _base_url(self))
            _json_response(self, HTTPStatus.OK, result)
        except Exception as exc:  # pragma: no cover - exercised by real server.
            traceback.print_exc()
            _json_response(self, HTTPStatus.OK, _failure(str(exc)))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path in {"/", "/reports"}:
            _serve_bytes(self, _render_report_center(self), "text/html; charset=utf-8")
            return

        if path == "/api/reports":
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "success": True,
                    "message": "执行成功",
                    "code": "0",
                    "data": {"reports": _reports_for_response(_base_url(self))},
                },
            )
            return

        if path == "/final":
            _serve_file(self, Path(FINAL_REPORT_INTERFACE_PATH))
            return

        if path.startswith("/reports/"):
            file_name = Path(unquote(path[len("/reports/") :])).name
            _serve_file(self, REPORT_ARCHIVE_DIR / file_name)
            return

        _serve_bytes(
            self,
            _html_page("未找到页面", '<div class="empty">页面不存在。</div>'),
            "text/html; charset=utf-8",
            HTTPStatus.NOT_FOUND,
        )


def run_server(host: str = "127.0.0.1", port: int = 9090) -> None:
    INTERFACE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), AIReportHandler)
    actual_host, actual_port = server.server_address[:2]
    print("LSCURE AI 报告服务已启动")
    print(f"报告中心: http://{actual_host}:{actual_port}/reports")
    print(f"机器人接口: http://{actual_host}:{actual_port}/ai-report/force")
    print("按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the local LSCURE AI report service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9090)
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
