"""키오스크용 로컬 웹 서버 (표준 라이브러리 http.server, 외부 패키지 없음).

보안: 기본은 127.0.0.1 에만 바인딩한다. 인증이 없는 로컬 서버이므로 --host 0.0.0.0 으로 열면 같은 네트워크의 누구나 접속할 수 있다.
관리 화면(/admin.html, /api/admin/*)은 접속한 쪽이 이 컴퓨터(127.0.0.1)일 때만 열어 준다.
방문객이 입력한 질문은 이 컴퓨터의 log/ 폴더의 실행 시각 이름 파일(예: 2026-10-14_15-30-00.jsonl)에만 저장하고 어디로도 보내지 않는다.
"""
from __future__ import annotations
import json
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .engine import Engine
from .kb import KB

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
MAX_BODY = 4096
MIN_INTERVAL = 0.35     # 같은 접속자의 질문 간 최소 간격 (초)

STATUS_LABEL = {
    "measured": {"ko": "직접 재 본 결과", "en": "Measured in our tests"},
    "verified": {"ko": "동작 확인됨", "en": "Confirmed working"},
    "partial": {"ko": "일부만 확인", "en": "Partly confirmed"},
    "not_validated": {"ko": "아직 확인 못 함", "en": "Not confirmed yet"},
    "plan": {"ko": "앞으로의 계획", "en": "Future plan"},
    "info": {"ko": "설명", "en": "Overview"},
}


class App:
    def __init__(self, kb: KB, engine: Engine, llm_status: dict | None = None, log_path: Path | None = None) -> None:
        self.kb, self.engine = kb, engine
        self.llm_status = llm_status or {"status": "off", "detail": ""}
        # 서버를 켤 때마다 log/<날짜_시각>.jsonl 새 파일에 질문·답을 모은다 (첫 질문이 들어올 때 만들어진다)
        self.log_path = log_path or (ROOT / "log" / (time.strftime("%Y-%m-%d_%H-%M-%S") + ".jsonl"))
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        self.pages: set[str] = set()            # 열려 있는 화면(채팅·운영자 화면 …)의 id. 마지막 화면이 닫혀야 종료를 예약한다
        self.bye_at: float | None = None       # 브라우저 탭이 닫혔다고 알려 온 뒤 이 시각까지 새 접속이 없으면 서버를 끈다

    def allow(self, who: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if now - self._last.get(who, 0.0) < MIN_INTERVAL:
                return False
            self._last[who] = now
            if len(self._last) > 500:
                self._last = {k: v for k, v in self._last.items() if now - v < 60}
        return True

    def page_open(self, pid: str) -> None:
        with self._lock:
            if pid:
                self.pages.add(pid[:40])
                if len(self.pages) > 50:
                    self.pages = {pid[:40]}
        self.bye_at = None

    def tab_closed(self, pid: str = "", grace_s: float = 3.0) -> None:
        with self._lock:
            self.pages.discard(pid[:40])
            if self.pages:                      # 다른 화면(예: 채팅 탭)이 아직 열려 있으면 끄지 않는다
                return
        self.bye_at = time.monotonic() + grace_s

    def tab_alive(self) -> None:
        self.bye_at = None                      # 새로고침이거나 다른 탭이 열려 있다 → 취소

    def should_exit(self) -> bool:
        return self.bye_at is not None and time.monotonic() >= self.bye_at

    def log(self, q: str, res: dict) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            row = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "q": q[:300], "a": str(res.get("answer") or (res.get("card") or {}).get("a") or "")[:1500], "lang": res.get("lang"), "kind": res.get("kind"),
                   "card": (res.get("card") or {}).get("id"), "score": res.get("score"), "coverage": res.get("coverage"),
                   "mode": res.get("mode"), "via": res.get("via"), "ms": res.get("ms")}
            with self._lock, open(self.log_path, "a", encoding="utf8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def config(self) -> dict:
        return {"title": self.kb.policy.get("title", {"ko": "AnyControl 안내 챗봇", "en": "AnyControl Guide Chatbot"}),
                "cats": self.kb.cats, "statuses": STATUS_LABEL, "llm": self.llm_status,
                "ui": self.kb.policy.get("ui", {}), "cards": len(self.kb.cards),
                "messages": self.kb.policy.get("messages", {})}


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AnyControlChat/1.0"

        def log_message(self, *a):   # 콘솔 소음을 줄인다
            pass

        # ---------------------------------------------------------------- 도우미
        def _json(self, obj, code: int = 200) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _local(self) -> bool:
            return self.client_address[0] in ("127.0.0.1", "::1")

        def _static(self, path: str) -> None:
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            if rel in ("admin.html",) and not self._local():
                return self._json({"error": "forbidden"}, 403)
            f = (WEB / rel).resolve()
            if WEB.resolve() not in f.parents or not f.is_file():
                return self._json({"error": "not found"}, 404)
            data = f.read_bytes()
            ctype = "font/woff2" if f.suffix == ".woff2" else (mimetypes.guess_type(str(f))[0] or "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400" if f.suffix == ".woff2" else "no-store")
            self.end_headers()
            self.wfile.write(data)

        # ---------------------------------------------------------------- 라우팅
        def do_GET(self) -> None:
            u = urlparse(self.path)
            qs = parse_qs(u.query)
            if self._local() or not u.path.startswith("/api/admin"):
                app.tab_alive()                       # 운영자 화면으로 이동하는 중에 온 종료 신호도 이 요청으로 취소된다
            lang = qs.get("lang", ["ko"])[0]
            lang = lang if lang in ("ko", "en") else "ko"
            if u.path == "/api/config":
                return self._json(app.config())
            if u.path == "/api/suggest":
                return self._json({"items": app.engine.suggestions(lang, qs.get("cat", [None])[0], int(qs.get("n", ["8"])[0]))})
            if u.path == "/api/labels":                  # 화면 언어를 바꿀 때 버튼 문구를 새 언어로 바꾸기 위한 조회
                ids = [i for i in qs.get("ids", [""])[0].split(",") if i][:40]
                return self._json({"labels": app.engine.labels(ids, lang)})
            if u.path == "/api/card":
                c = app.engine.card(qs.get("id", [""])[0], lang)
                return self._json(c or {"error": "not found"}, 200 if c else 404)
            if u.path == "/api/admin/log":
                if not self._local():
                    return self._json({"error": "forbidden"}, 403)
                rows = []
                if app.log_path.exists():
                    rows = [json.loads(x) for x in app.log_path.read_text(encoding="utf8").splitlines()[-500:] if x.strip()]
                return self._json({"rows": rows})
            if u.path.startswith("/api/"):
                return self._json({"error": "not found"}, 404)
            return self._static(u.path)

        def do_POST(self) -> None:
            u = urlparse(self.path)
            if u.path in ("/api/bye", "/api/hello"):      # 화면이 열릴 때(hello)·탭/창이 닫힐 때(bye) 보내는 신호 (이 컴퓨터에서 온 것만)
                if self._local():
                    try:
                        pid = str(json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 512)) or b"{}").get("pid") or "")
                    except (ValueError, AttributeError):
                        pid = ""
                    if u.path == "/api/hello":
                        app.page_open(pid)
                    else:
                        app.tab_closed(pid)
                return self._json({"ok": True})
            app.tab_alive()
            if u.path != "/api/ask":
                return self._json({"error": "not found"}, 404)
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = 0
            if n <= 0 or n > MAX_BODY:
                return self._json({"error": "bad size"}, 413 if n > MAX_BODY else 400)
            try:
                body = json.loads(self.rfile.read(n))
                q = str(body.get("q", ""))
                lang = body.get("lang", "ko")
                ctx = [c for c in (body.get("ctx") or []) if isinstance(c, str) and len(c) < 80][:3]     # 직전에 답한 카드 id (이어 묻기용)
                prev = str(body.get("prev", ""))[:120]                                                    # 직전 질문 글
                hist = [[str(h.get("q", ""))[:200], str(h.get("a", ""))[:300]] for h in (body.get("hist") or [])[:3] if isinstance(h, dict)]   # 직전 잡담(이어서 대화하기 위해)
            except (ValueError, AttributeError):
                return self._json({"error": "bad json"}, 400)
            if not app.allow(self.client_address[0]):
                return self._json({"error": "too fast"}, 429)
            res = app.engine.ask(q, lang if lang in ("ko", "en") else "ko", ctx, prev, hist)
            app.log(q, res)
            return self._json(res)

    return Handler


def serve(app: App, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    return httpd
