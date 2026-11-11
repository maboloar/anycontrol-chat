"""검색 평가: eval/questions.json 의 질문마다 기대하는 카드가 상위에 나오는지, 자료에 없는 질문을 '없음'으로 처리하는지 잰다.

questions.json = [{"q": "...", "lang": "ko", "expect": ["card-id", ...]}, {"q": "...", "none": true}, ...]
  expect : 이 카드들 중 하나가 1위(hit@1) / 상위 3위(hit@3)에 나와야 한다
  none   : 자료에 없는 질문 — kind 가 none 이어야 한다 (엉뚱한 카드를 자신 있게 내밀면 실패)
"""
from __future__ import annotations
import json
from pathlib import Path

from .engine import Engine
from .kb import KB


def _load_equiv(path: Path) -> dict:
    """eval/equiv.json: 같은 질문에 함께 정답이 될 수 있는 카드 묶음 -> {카드: 같이 인정할 카드들}"""
    out: dict = {}
    if path.exists():
        for g in json.loads(path.read_text(encoding="utf8")).get("groups", []):
            for a in g:
                out.setdefault(a, set()).update(g)
    return out


def run_eval(kb: KB, path: Path, verbose: bool = False, llm=None, rag: bool = False) -> int:
    items = json.loads(path.read_text(encoding="utf8"))
    eng = Engine(kb, llm)
    eng.cfg["llm_compose"] = rag
    equiv = _load_equiv(path.parent / "equiv.json")
    n_exp = h1 = h3 = n_none = ok_none = 0
    wrong_direct = refused = n_llm = 0
    fails = []
    for it in items:
        q, lang = it["q"], it.get("lang", "ko")
        res = eng.ask(q, lang, it.get("ctx"), it.get("prev", ""))
        if it.get("chat"):                  # 인사·감사·잡담: 지어낸 답이 아니라 짧은 반응이어야 한다
            n_exp += 1
            if res["kind"] in ("chat", "greeting"):
                h1 += 1; h3 += 1
            else:
                fails.append((q, "잡담 반응이어야 하는데 " + res["kind"]))
            continue
        if it.get("none"):
            n_none += 1
            if res["kind"] in ("none", "greeting", "empty"):
                ok_none += 1
            else:
                fails.append((q, "none 이어야 하는데 " + res["kind"] + " → " + (res.get("card") or {}).get("id", "?")))
            continue
        n_exp += 1
        hits = eng.card_index.search(q, 5)
        if res.get("via") == "llm":
            n_llm += 1
        ids = [kb.cards[i]["id"] for i, _, _ in hits]
        top = (res.get("card") or {}).get("id")
        shown = [x["id"] for x in res.get("suggestions", [])] if res.get("near") else []   # 화면에 보여 준 "혹시 이런 질문인가요?" 후보
        if shown:
            ids = shown + [x for x in ids if x not in shown]
        if top:   # 인텐트 규칙 등 엔진이 직접 고른 카드를 우선한다
            ids = [top] + [x for x in ids if x != top]
        exp = set(it["expect"])
        for e in list(exp):
            exp |= equiv.get(e, set())
        if ids and ids[0] in exp:
            h1 += 1
        if exp & set(ids[:3]):
            h3 += 1
        else:
            fails.append((q, f"기대 {sorted(exp)} · 실제 {ids[:3]}"))
        near_ids = {x["id"] for x in res.get("suggestions", [])} if res.get("near") else set()
        if res["kind"] == "none" and not (exp & near_ids):
            refused += 1
            fails.append((q, f"카드가 있는데 '자료에 없음'으로 거절 (기대 {sorted(exp)})"))
        if res["kind"] == "answer" and (res.get("card") or {}).get("id") not in exp:
            wrong_direct += 1
            fails.append((q, f"자신 있게 틀린 카드: {(res.get('card') or {}).get('id')} (기대 {sorted(exp)})"))
    print(f"질문 {len(items)}개 — 카드 있는 질문 {n_exp}: hit@1 {h1}/{n_exp} ({h1 / max(n_exp, 1):.0%}), hit@3 {h3}/{n_exp} ({h3 / max(n_exp, 1):.0%}), "
          f"자신 있게 틀림 {wrong_direct}건 · 잘못 거절 {refused}건 · 자료에 없는 질문 {n_none}: 올바르게 '없음' {ok_none}/{n_none}"
          + (f" · LLM 이 고른 질문 {n_llm}개" if llm is not None else ""))
    if verbose or fails:
        for q, why in fails[:60]:
            print("  ✗", q, "→", why)
    return 0 if (not n_none or ok_none / max(n_none, 1) >= 0.8) and (not n_exp or h3 / max(n_exp, 1) >= 0.9) and wrong_direct == 0 else 1
