#!/usr/bin/env python3
"""kb_src/*.txt (사람이 읽고 고치기 쉬운 형식) -> kb/cards/<같은 이름>.json

한 항목 = 빈 줄로 구분된 블록. 줄 머리표:
  @cat <카테고리 id>        이 줄 아래 항목들의 카테고리 (kb/categories.json 의 id)
  I:  카드 id               (생략하면 v-<cat>-<번호>)
  C:  이 카드만 카테고리 바꾸기 (생략하면 위의 @cat)
  Q:  한국어 대표 질문      V: 한국어 비슷한 질문 / 로 / 구분
  EQ: 영어 대표 질문        EV: 영어 비슷한 질문 / 로 / 구분
  A:  한국어 답             EA: 영어 답
  K:  키워드 (쉼표, 한/영 섞어서)
  S:  상태 measured|verified|partial|not_validated|plan|info   (기본 info)
  F:  근거 (자료 위치, 사람이 확인용. 화면에는 안 보임)
  R:  관련 카드 id (쉼표)
  G:  yes 이면 처음 화면의 추천 질문
  B:  yes 이면 금지 표현을 부정문으로 쓴 카드 (allow_banned)
사용:  python3 tools/build_cards.py        # kb_src -> kb/cards 로 다시 만든다
       python3 -m bot validate             # 그 다음 검증
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "kb_src"
OUT = ROOT / "kb" / "cards"
STATUSES = {"measured", "verified", "partial", "not_validated", "plan", "info"}


def split(s: str) -> list[str]:
    return [x.strip() for x in s.split("/") if x.strip()]


def parse(path: Path) -> list[dict]:
    cat, cur, items = None, None, []
    prefix = path.stem
    for ln, raw in enumerate(path.read_text(encoding="utf8").splitlines(), 1):
        line = raw.rstrip()
        if line.startswith("@cat "):
            cat, cur = line[5:].split("|")[0].strip(), None
            continue
        if not line.strip():
            cur = None
            continue
        m = re.match(r"^(EQ|EV|EA|Q|V|A|K|S|F|R|G|B|I|C):\s?(.*)$", line)
        if not m:
            raise SystemExit(f"{path.name}:{ln} 알 수 없는 줄: {line[:50]}")
        tag, val = m.group(1), m.group(2).strip()
        if cur is None:
            cur = {"cat": cat, "at": f"{path.name}:{ln}", "status": "info"}
            items.append(cur)
        if tag == "I":
            cur["id"] = val
        elif tag == "C":
            cur["cat"] = val
        elif tag == "Q":
            cur["ko_q"] = val
        elif tag == "V":
            cur["ko_v"] = split(val)
        elif tag == "EQ":
            cur["en_q"] = val
        elif tag == "EV":
            cur["en_v"] = split(val)
        elif tag == "A":
            cur["ko_a"] = val
        elif tag == "EA":
            cur["en_a"] = val
        elif tag == "K":
            cur["kw"] = [x.strip() for x in val.split(",") if x.strip()]
        elif tag == "S":
            cur["status"] = val
        elif tag == "F":
            cur["src"] = [val]
        elif tag == "R":
            cur["related"] = [x.strip() for x in val.split(",") if x.strip()]
        elif tag == "G":
            cur["suggest"] = val.lower() in ("yes", "y", "true")
        elif tag == "B":
            cur["allow_banned"] = val.lower() in ("yes", "y", "true")
    for i, it in enumerate(items, 1):
        it.setdefault("id", f"v-{it['cat']}-{prefix}-{i:03d}")
    return items


def to_card(it: dict) -> dict:
    for k in ("ko_q", "en_q", "ko_a", "en_a"):
        if not it.get(k):
            raise SystemExit(f"{it['at']} {k} 없음 ({it.get('ko_q') or it.get('id')})")
    if it["status"] not in STATUSES:
        raise SystemExit(f"{it['at']} 알 수 없는 상태 {it['status']}")
    c = {"id": it["id"], "cat": it["cat"], "status": it["status"],
         "q": {"ko": [it["ko_q"]] + it.get("ko_v", []), "en": [it["en_q"]] + it.get("en_v", [])},
         "a": {"ko": it["ko_a"], "en": it["en_a"]},
         "kw": it.get("kw", []), "src": it.get("src", ["kb_src"]), "related": it.get("related", [])}
    if it.get("suggest"):
        c["suggest"] = True
    if it.get("allow_banned"):
        c["allow_banned"] = True
    return c


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for p in sorted(p for p in SRC.glob("*.txt") if not p.name.startswith((".", "_"))):
        cards = [to_card(i) for i in parse(p)]
        (OUT / f"{p.stem}.json").write_text(json.dumps(cards, ensure_ascii=False, indent=1), encoding="utf8")
        print(f"{p.name}: {len(cards)}장")
        total += len(cards)
    print(f"합계 {total}장 -> {OUT}")
    import runpy
    runpy.run_path(str(ROOT / "tools" / "add_variants.py"))   # 손으로 만든 카드에 덧붙이는 표현도 같이 적용
    return 0


if __name__ == "__main__":
    sys.exit(main())
