"""이 컴퓨터에서 '질문 이해 보조(Qwen)'가 쓸 만한 속도로 도는지 재는 스크립트. 부스 노트북에서 한 번 실행해 결과를 보고 켤지 정한다.

  python3 tools/bench_llm.py                 # bin/<플랫폼>/llama-server 와 models/*.gguf 로 시험
  python3 tools/bench_llm.py --eval          # 추가로 eval/chat_heldout.json 을 LLM 끔/켬으로 돌려 비교 (몇 분 걸릴 수 있음)
  python3 tools/bench_llm.py --model X.gguf --ctx 2048

측정: (1) 서버 시작까지 걸린 시간 (2) 초당 생성 토큰 (3) '질문 이해' 한 번(예/아니오 점수)의 시간 (4) 표현이 어려운 실제 질문 8개를 챗봇에 물었을 때 전체 응답 시간.
판정 기준: 어려운 질문 한 번에 8초 안(방문객이 기다릴 수 있는 한도). 못 맞추면 챗봇은 시작할 때 자동으로 이 기능을 끄고 카드 검색만 쓴다.
"""
from __future__ import annotations
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.engine import Engine  # noqa: E402
from bot.kb import load_kb  # noqa: E402
from bot.runtime import LLMRuntime, find_model, find_server, platform_tag, total_ram_gb  # noqa: E402

HARD = [("뭐가 별로임?", "ko"), ("누가 만들었음?", "ko"), ("설치 어렵나", "ko"), ("이거 믿을만해?", "ko"), ("가끔 엉뚱한 거 따라가던데 왜 그래", "ko"),
        ("is this thing legit?", "en"), ("does it spy on me", "en"), ("what makes it better than a normal mouse?", "en")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--ctx", type=int, default=2048)
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--eval", action="store_true")
    a = ap.parse_args()
    if a.model:
        import os
        os.environ["ANYCONTROL_CHAT_MODEL"] = a.model
    print(f"플랫폼 {platform_tag()} · RAM {total_ram_gb():.1f}GB · server {find_server()} · model {find_model()}")
    rt = LLMRuntime(ROOT, port=a.port, min_tok_s=0.0, ctx=a.ctx, max_pair_s=1e9)
    t0 = time.time()
    client = rt.start(wait_s=240)
    if not client:
        print("시작하지 못함:", rt.status, rt.detail)
        return 2
    print(f"서버 시작 {time.time() - t0:.1f}s · {client.info}")
    kb = load_kb()
    eng = Engine(kb, client)
    times = []
    try:
        for q, lang in HARD:
            t = time.perf_counter()
            r = eng.ask(q, lang)
            dt = time.perf_counter() - t
            times.append(dt)
            print(f"  {dt:5.1f}s  {r['kind']:7s} {(r.get('card') or {}).get('id', '-'):22s} {q}")
        if a.eval:
            from bot.evalset import run_eval
            p = ROOT / "eval" / "chat_heldout.json"
            print("\n[LLM 끔]")
            run_eval(kb, p)
            print("[LLM 켬]")
            run_eval(kb, p, llm=client)
    finally:
        rt.stop()
    med, worst = statistics.median(times), max(times)
    pair = client.info.get("pair_s", 0)
    print(f"\n어려운 질문 응답 중앙값 {med:.1f}s · 최대 {worst:.1f}s · 질문 이해 1회 {pair * 1000:.0f}ms · {client.info.get('tok_per_s', 0)} tok/s")
    good = worst <= 8
    print("판정:", "켜도 됨 (카드 검색이 기본이고 Qwen 은 표현이 어려운 질문만 돕습니다)" if good else "끄는 게 좋음 — --no-llm 으로 운영하세요 (카드 검색만 사용)")
    print(json.dumps({"median_s": round(med, 2), "max_s": round(worst, 2), "pair_s": pair}))
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
