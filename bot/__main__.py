"""명령줄 진입점:  python -m bot serve | ask "질문" | validate | eval | llm-check"""
from __future__ import annotations
import argparse
import json
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .engine import Engine
from .kb import ROOT, load_kb, validate_kb
from .server import App, serve


def _utf8_console() -> None:
    """Windows 한글 콘솔(cp949 등)에서 한글·기호를 출력해도 UnicodeEncodeError 로 멈추지 않게 한다."""
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _load(strict: bool = True):
    kb = load_kb()
    errors, warns = validate_kb(kb)
    for w in warns[:20]:
        print("경고:", w)
    if errors:
        for e in errors[:40]:
            print("오류:", e)
        if strict:
            sys.exit(f"지식 베이스 검증 실패 ({len(errors)}건). `python -m bot validate` 로 확인하세요.")
    return kb


def cmd_serve(a) -> None:
    kb = _load(strict=not a.force)
    engine = Engine(kb)
    engine.cfg["llm_compose"] = bool(a.rag)
    engine.cfg["free_chat"] = bool(a.chat)
    status = {"status": "off", "detail": "LLM 없이 카드 답변으로 동작"}
    app = App(kb, engine, status)
    httpd, port = None, a.port
    for port in range(a.port, a.port + 20):          # 8765 를 다른 프로그램이 쓰고 있으면 다음 번호로 넘어간다
        try:
            httpd = serve(app, a.host, port)
            break
        except OSError:
            continue
    if httpd is None:
        sys.exit(f"포트 {a.port}~{a.port + 19} 를 열 수 없습니다. 다른 프로그램을 끄거나 --port 로 다른 번호를 지정하세요.")
    url = f"http://{'127.0.0.1' if a.host in ('0.0.0.0', '') else a.host}:{port}/"
    print(f"AnyControl 안내 챗봇이 켜졌습니다 · 질문-답 카드 {len(kb.cards)}장\n  주소: {url}  (브라우저가 자동으로 열립니다)\n  끝내려면 이 창을 닫거나 Ctrl+C 를 누르세요.", flush=True)
    rt_holder: list = []

    def _bye(signum, _frame):                         # 종료 신호(창 닫기·kill)에서도 llama-server 를 정리하고 끝낸다
        for r in rt_holder:
            if hasattr(r, "stop"):
                r.stop()
        os._exit(0)
    if sys.platform.startswith("win"):                  # Windows: 콘솔 창의 X 를 누르면 시그널이 아니라 콘솔 이벤트가 온다
        try:
            import ctypes
            HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

            def _on_console(event):                     # 2 창 닫기 · 5 로그오프 · 6 종료
                if event in (2, 5, 6):
                    _bye(event, None)
                return 0
            _keep = HandlerRoutine(_on_console)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_keep, True)  # type: ignore[attr-defined]
            rt_holder.append(_keep)                     # 핸들러가 가비지 컬렉션 되지 않게 붙잡아 둔다
        except Exception:
            pass
    import signal                                      # 시그널 등록은 메인 스레드에서만 가능하다
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), _bye)
            except (ValueError, OSError):
                pass
    if a.llm:
        def boot() -> None:
            from .runtime import LLMRuntime
            rt = LLMRuntime(port=a.llm_port, min_tok_s=a.min_tok_s)
            rt.persona = engine.kb.policy.get("persona", {})
            rt_holder.append(rt)
            import atexit
            import signal
            atexit.register(rt.stop)                      # 창을 닫거나 종료할 때 llama-server 가 남지 않게

            status.update(status="starting", detail="로컬 LLM 확인 중")
            client = rt.start()
            if client:
                engine.llm = client
            status.update(status=rt.status, detail=rt.detail)
            labels = {"on": "켜짐 — 표현이 다른 질문도 알아듣는 데 도움을 줍니다", "no-binary": "꺼짐 (실행 파일 없음) — 카드 검색만 사용", "no-model": "꺼짐 (모델 파일 없음) — 카드 검색만 사용",
                      "low-ram": "꺼짐 (메모리 부족) — 카드 검색만 사용", "slow": "꺼짐 (이 컴퓨터에서는 느림) — 카드 검색만 사용", "failed": "꺼짐 (시작 실패) — 카드 검색만 사용",
                      "no-runtime": "꺼짐 (Windows 에 Visual C++ 런타임이 없음) — 카드 검색만 사용. 설치하면 켜져요: https://aka.ms/vs/17/release/vc_redist.x64.exe"}
            print(f"질문 이해 보조(Qwen): {labels.get(rt.status, rt.status)}  [{rt.detail}]", flush=True)
        threading.Thread(target=boot, daemon=True).start()
    if not a.keep_alive:                                # 브라우저 탭을 닫으면(새 접속이 8초 안에 없으면) 서버와 Qwen 도 끈다
        def _watch() -> None:
            while True:
                time.sleep(1.0)
                if app.should_exit():
                    print("\n브라우저 창이 닫혀서 종료합니다.", flush=True)
                    _bye(0, None)
        threading.Thread(target=_watch, daemon=True).start()
    if a.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        for rt in rt_holder:
            rt.stop()


def cmd_ask(a) -> None:
    kb = _load(strict=False)
    res = Engine(kb).ask(a.question, a.lang)
    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else f"[{res['kind']} · {res.get('coverage')}/{res.get('score')}] {res['answer']}")


def cmd_validate(a) -> None:
    kb = load_kb()
    errors, warns = validate_kb(kb)
    by_status: dict[str, int] = {}
    for c in kb.cards:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1
    print(f"카드 {len(kb.cards)}장 · 카테고리 {len(kb.cats)}개 · 상태별 {by_status}")
    for w in warns:
        print("경고:", w)
    for e in errors:
        print("오류:", e)
    sys.exit(1 if errors else 0)


def cmd_eval(a) -> None:
    from .evalset import run_eval
    rt = None
    client = None
    if a.llm:
        from .runtime import LLMRuntime
        rt = LLMRuntime(port=a.llm_port, min_tok_s=a.min_tok_s)
        client = rt.start()
        print("LLM:", rt.status, rt.detail, flush=True)
        if client is None:
            sys.exit("LLM 을 켤 수 없어 평가를 중단합니다.")
    try:
        sys.exit(run_eval(load_kb(), Path(a.file), verbose=a.verbose, llm=client, rag=a.rag))
    finally:
        if rt:
            rt.stop()


def cmd_llm(a) -> None:
    from .runtime import LLMRuntime, find_model, find_server, platform_tag, total_ram_gb
    print("플랫폼", platform_tag(), "· RAM", round(total_ram_gb(), 1), "GB · llama-server", find_server(), "· 모델", find_model())
    rt = LLMRuntime(port=a.llm_port, min_tok_s=a.min_tok_s)
    c = rt.start()
    print("결과:", rt.status, rt.detail)
    if c:
        kb = _load(strict=False)
        eng = Engine(kb, c)
        for q in a.questions or ["펜 접촉 판정은 어떻게 하나요?", "How does the tracker recover after occlusion?"]:
            r = eng.ask(q)
            print(f"\nQ: {q}\n[{r['kind']}/{r.get('mode')}] {r['answer']}")
    rt.stop()


def main(argv: list[str] | None = None) -> None:
    _utf8_console()
    p = argparse.ArgumentParser(prog="bot")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--llm", action=argparse.BooleanOptionalAction, default=True,
                   help="로컬 LLM(llama-server)으로 질문 이해를 돕는다 (기본 켬: 모델·실행 파일이 없거나 컴퓨터가 느리면 자동으로 끄고 카드 검색만 쓴다). 끄려면 --no-llm")
    s.add_argument("--chat", action=argparse.BooleanOptionalAction, default=True,
                   help="프로젝트와 상관없는 잡담(\"내일 뭐 먹지\")에 Qwen 이 짧게 자유롭게 답한다 (기본 켬, 끄려면 --no-chat). 카드 답과 구분되게 표시된다")
    s.add_argument("--rag", action="store_true", help="RAG: Qwen 이 찾은 카드를 질문에 맞게 정리해 답한다 (실험 기능 — 정리한 답이 사실과 다를 수 있어 기본 꺼짐)")
    s.add_argument("--open", action="store_true", help="브라우저를 자동으로 연다")
    s.add_argument("--keep-alive", action="store_true", help="브라우저 탭을 닫아도 서버를 끄지 않는다 (기본: 탭을 닫으면 자동 종료)")
    s.add_argument("--force", action="store_true", help="검증 오류가 있어도 실행")
    s.add_argument("--llm-port", type=int, default=8081)
    s.add_argument("--min-tok-s", type=float, default=3.0)
    s.set_defaults(fn=cmd_serve)
    k = sub.add_parser("ask")
    k.add_argument("question")
    k.add_argument("--lang", default="ko")
    k.add_argument("--json", action="store_true")
    k.set_defaults(fn=cmd_ask)
    v = sub.add_parser("validate")
    v.set_defaults(fn=cmd_validate)
    e = sub.add_parser("eval")
    e.add_argument("--file", default=str(ROOT / "eval" / "questions.json"))
    e.add_argument("--verbose", action="store_true")
    e.add_argument("--llm", action="store_true", help="로컬 LLM 을 켠 상태로 평가")
    e.add_argument("--rag", action="store_true", help="(--llm 과 함께) RAG 답 정리도 켜고 평가")
    e.add_argument("--llm-port", type=int, default=8081)
    e.add_argument("--min-tok-s", type=float, default=3.0)
    e.set_defaults(fn=cmd_eval)
    l = sub.add_parser("llm-check")
    l.add_argument("questions", nargs="*")
    l.add_argument("--llm-port", type=int, default=8081)
    l.add_argument("--min-tok-s", type=float, default=3.0)
    l.set_defaults(fn=cmd_llm)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
