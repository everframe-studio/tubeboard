"""로컬 웹 서버. 127.0.0.1 에서만 듣는다 (남이 내 API 키로 조회하지 못하게)."""
import json
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import cache, logic, youtube

STATIC = Path(__file__).resolve().parent / "static"
DAILY_LIMIT = 10_000
TTL_POPULAR = 30 * 60      # 인기 급상승 30분
TTL_TRENDS = 15 * 60       # 구글 트렌드 15분
TTL_CATEGORIES = 60 * 60  # 카테고리 비교 1시간
TTL_TOPIC = 3 * 60 * 60    # 주제 검색 3시간 (검색은 한 번에 100유닛)


def force(q):
    return q.get("refresh") == "1"


def api_popular(q):
    region = logic.clean_region(q.get("region"))
    return cache.cached(f"popular:{region}", TTL_POPULAR, lambda: youtube.popular(region), force(q))


def api_trends(q):
    region = logic.clean_region(q.get("region"))
    return cache.cached(f"trends:{region}", TTL_TRENDS, lambda: youtube.google_trends(region), force(q))


def api_topic(q):
    region = logic.clean_region(q.get("region"))
    days = logic.clean_days(q.get("days"))
    topic = (q.get("q") or "").strip()[:60]
    if not topic:
        raise youtube.ApiError("주제를 입력해 주세요.")
    return cache.cached(f"topic:{region}:{days}:{topic.lower()}", TTL_TOPIC, lambda: youtube.topic_shorts(topic, region, days), force(q))


def api_categories(q):
    region = logic.clean_region(q.get("region"))
    return cache.cached(f"categories2:{region}", TTL_CATEGORIES, lambda: youtube.categories(region), force(q))


ROUTES = {"/api/categories": api_categories, "/api/popular": api_popular, "/api/trends": api_trends, "/api/topic": api_topic}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_POST(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        origin = self.headers.get("Origin")
        ok_origin = origin is None or urlparse(origin).hostname in ("127.0.0.1", "localhost", "::1")
        if host not in ("127.0.0.1", "localhost", "[::1]") or not ok_origin:
            return self._json(403, {"error": "로컬에서만 접근할 수 있습니다."})
        if urlparse(self.path).path != "/api/key" or "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._json(404, {"error": "없는 주소입니다."})
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 2048)
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            youtube.save_key(body.get("key") if isinstance(body, dict) else None)
            self._json(200, {"ok": True})
        except youtube.ApiError as e:
            self._json(400, {"error": str(e)})
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"error": "요청 형식이 올바르지 않습니다."})

    def do_GET(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "[::1]"):  # DNS 리바인딩 방지
            return self._json(403, {"error": "로컬에서만 접근할 수 있습니다."})
        url = urlparse(self.path)
        if url.path == "/":
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path == "/fonts/PretendardVariable.woff2":  # 글꼴은 이 한 파일만 내려 준다
            body = (STATIC / "fonts" / "PretendardVariable.woff2").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "font/woff2")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            return self.wfile.write(body)
        if url.path == "/api/status":
            try:
                youtube.api_key()
                has_key = True
            except youtube.ApiError:
                has_key = False
            return self._json(200, {"hasKey": has_key, "quotaUsed": cache.quota_used(), "quotaLimit": DAILY_LIMIT,
                                    "regions": {k: v[0] for k, v in logic.REGIONS.items()}})
        fn = ROUTES.get(url.path)
        if not fn:
            return self._json(404, {"error": "없는 주소입니다."})
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            value, from_cache, at = fn(q)
            self._json(200, {"data": value, "cached": from_cache, "at": at,
                             "quotaUsed": cache.quota_used(), "quotaLimit": DAILY_LIMIT})
        except youtube.QuotaExceeded as e:
            self._json(429, {"error": str(e)})
        except youtube.ApiError as e:
            self._json(400, {"error": str(e)})
        except Exception as e:  # 화면이 죽지 않게
            self._json(500, {"error": f"예상하지 못한 오류: {e}"})


def bind(port, fixed):
    """정해 준 포트가 없으면 쓸 수 있는 번호를 찾는다 (더블클릭 실행에서 이미 쓰는 포트 때문에 멈추지 않게)."""
    last = None
    for p in ([port] if fixed else range(port, port + 30)):
        try:
            return ThreadingHTTPServer(("127.0.0.1", p), Handler), p
        except OSError as e:
            last = e
    raise SystemExit(f"포트를 열 수 없습니다: {last}")


def main():
    youtube.load_env()
    fixed = "TREND_PORT" in os.environ
    server, port = bind(int(os.environ.get("TREND_PORT", "8765")), fixed)
    url = f"http://127.0.0.1:{port}"
    print(f"tubeboard: {url}  (끝내려면 이 창을 닫거나 Ctrl+C)")
    if os.environ.get("TREND_NO_BROWSER") != "1":
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
