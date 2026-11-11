#!/usr/bin/env python3
"""AnyControl 이 업데이트됐을 때, 챗봇의 질문-답이 낡았는지 확인하는 도구.

무엇을 하나
  1. kb/facts.json 의 사실들(버전, 최대 물체 수, 기본값, 필요 사양, 3초 유예 …)을 AnyControl 코드·문서에서 다시 읽어 기대값과 비교한다.
  2. 마지막으로 맞춰 둔 시점(kb/snapshot)과 지금의 AnyControl 폴더를 비교해 바뀐 파일을 찾는다.
  3. kb/topic_map.json 으로 바뀐 파일마다 '다시 확인해야 할 카드'를 알려 주고, 문서(HANDOFF/README 등)의 추가된 줄과 코드 변경 요약을 보여 준다.
  4. 카드를 고치고 검증을 마친 뒤 --accept 로 '이 상태에 맞춰 둠'을 기록한다.

사용
  python3 tools/sync_check.py                 # 점검 (AnyControl 폴더는 ../anycontrol-web, 다르면 --web 경로 또는 환경변수 ANYCONTROL_WEB)
  python3 tools/sync_check.py --diff README.md       # 특정 파일의 전체 diff
  python3 tools/sync_check.py --full                 # 모든 변경 파일의 diff
  python3 tools/sync_check.py --coverage             # 어떤 카드도 감시하지 않는(낡아도 모르는) 카드 목록
  python3 tools/sync_check.py --accept               # 카드 갱신을 마친 뒤: 현재 상태를 새 기준으로 저장
종료 코드: 0 = 변경·어긋남 없음, 1 = 확인할 것이 있음, 2 = 실행 오류
자세한 절차는 UPDATE_GUIDE.md.
"""
from __future__ import annotations
import argparse
import difflib
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "kb" / "snapshot"
SNAP_FILES = SNAP / "web"
MANIFEST = SNAP / "manifest.json"
MAX_SNAP_BYTES = 400_000

# 스냅샷으로 추적하는 파일(AnyControl 폴더 기준 상대 경로 글롭). 코드는 테스트·번들 산출물을 빼고 본체만.
TRACK = [
    "README.md", "README-en.md", "HANDOFF.md", "DEVELOPMENT.md", "INSTALL.md", "THIRD_PARTY.md", "package.json", "server.py",
    "backend/pyproject.toml", "backend/src/vision_input/**/*.py", "frontend/src/**/*.ts", "frontend/src/**/*.tsx", "frontend/package.json",
    "packaging/*.py", "packaging/*.in", "models/*.md", "bench/**/README.md", "bench/README.md",
]
EXCLUDE = ["**/__pycache__/**", "**/*.egg-info/**", "**/node_modules/**", "frontend/src/**/*.test.ts", "frontend/src/**/*.test.tsx", "**/.DS_Store"]
DOC_FILES = {"README.md", "README-en.md", "HANDOFF.md", "DEVELOPMENT.md", "INSTALL.md", "THIRD_PARTY.md", "package.json"}


def glob_to_re(g: str) -> re.Pattern:
    out, i = "", 0
    while i < len(g):
        if g.startswith("**/", i):
            out += "(?:.*/)?"; i += 3
        elif g.startswith("**", i):
            out += ".*"; i += 2
        elif g[i] == "*":
            out += "[^/]*"; i += 1
        elif g[i] == "?":
            out += "[^/]"; i += 1
        else:
            out += re.escape(g[i]); i += 1
    return re.compile("^" + out + "$")


def matches(path: str, globs: list[str]) -> bool:
    return any(glob_to_re(g).match(path) for g in globs)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def scan(web: Path) -> dict[str, dict]:
    files: dict[str, dict] = {}
    for p in sorted(web.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(web).as_posix()
        if rel.startswith(("frontend/node_modules", "backend/.venv", ".git/")) or "/__pycache__/" in rel or "/.venv/" in rel:
            continue
        if matches(rel, EXCLUDE) or not matches(rel, TRACK):
            continue
        if p.stat().st_size > MAX_SNAP_BYTES:
            continue
        files[rel] = {"sha256": sha(p), "size": p.stat().st_size}
    return files


def release_names(web: Path) -> list[str]:
    d = web / "releases"
    return sorted(x.name for x in d.iterdir() if x.is_file() and x.name != ".DS_Store") if d.exists() else []


# ------------------------------------------------------------------ 사실 확인
def check_facts(web: Path, facts: list[dict]) -> list[dict]:
    out = []
    for f in facts:
        res = {"id": f["id"], "desc": f.get("desc", ""), "cards": f.get("cards", []), "ok": False, "actual": None, "expect": f.get("expect", f.get("texts"))}
        try:
            kind = f["kind"]
            if kind == "regex":
                text = (web / f["file"]).read_text(encoding="utf8")
                m = re.search(f["pattern"], text)
                res["actual"] = m.group(1).strip() if m else "(패턴을 찾지 못함)"
                res["ok"] = bool(m) and res["actual"] == str(f["expect"])
            elif kind == "exists":
                found = [p for p in f["paths"] if any(True for _ in web.glob(p))]
                res["actual"] = bool(found)
                res["ok"] = bool(found) == bool(f["expect"])
                if found and not f["expect"]:
                    res["actual"] = f"있음: {found}"
            elif kind == "contains":
                text = (web / f["file"]).read_text(encoding="utf8")
                missing = [t for t in f.get("texts", []) if t not in text]
                present_bad = [t for t in f.get("not_texts", []) if t in text]
                res["actual"] = "모두 있음" if not missing and not present_bad else (f"없음: {missing}" if missing else "") + (f" 새로 생김: {present_bad}" if present_bad else "")
                res["ok"] = not missing and not present_bad
            else:
                res["actual"] = f"알 수 없는 kind {kind}"
        except (OSError, KeyError, re.error) as e:
            res["actual"] = f"확인 실패: {e}"
        out.append(res)
    return out


# ------------------------------------------------------------------ 보고
def load_cards() -> dict[str, dict]:
    cards = {}
    for f in sorted(p for p in (ROOT / "kb" / "cards").glob("*.json") if not p.name.startswith((".", "_"))):
        for c in json.loads(f.read_text(encoding="utf8")):
            cards[c["id"]] = c
    return cards


def topics_for(rel: str, tmap: list[dict]) -> list[dict]:
    """맞는 항목 전부. 단, '분류 안 됨'(cards 가 빈 포괄 항목)은 더 구체적인 항목이 하나도 없을 때만 쓴다."""
    hit = [t for t in tmap if matches(rel, [t["glob"]])]
    specific = [t for t in hit if t["cards"] or "HANDOFF" in t["topic"]]
    return specific or hit


def diff_lines(old: str, new: str, rel: str) -> list[str]:
    return list(difflib.unified_diff(old.splitlines(), new.splitlines(), f"기준/{rel}", f"현재/{rel}", lineterm="", n=2))


def print_section(title: str) -> None:
    print("\n" + "=" * 8 + " " + title + " " + "=" * 8)


def main() -> int:
    ap = argparse.ArgumentParser(description="AnyControl 업데이트 후 챗봇 카드 점검")
    ap.add_argument("--web", default=os.environ.get("ANYCONTROL_WEB") or str(ROOT.parent / "anycontrol-web"))
    ap.add_argument("--diff", metavar="REL", help="이 파일의 전체 diff 를 보여 준다")
    ap.add_argument("--full", action="store_true", help="모든 변경 파일의 diff 를 보여 준다")
    ap.add_argument("--coverage", action="store_true", help="감시되지 않는 카드 목록")
    ap.add_argument("--accept", action="store_true", help="카드 갱신을 마친 뒤 현재 상태를 새 기준으로 저장")
    ap.add_argument("--force", action="store_true", help="사실 어긋남이 있어도 --accept")
    a = ap.parse_args()

    web = Path(a.web).resolve()
    if not (web / "package.json").exists():
        print(f"AnyControl 폴더를 찾지 못했습니다: {web}\n  --web 경로 또는 환경변수 ANYCONTROL_WEB 로 알려 주세요.")
        return 2
    facts = json.loads((ROOT / "kb" / "facts.json").read_text(encoding="utf8"))["facts"]
    tmap = json.loads((ROOT / "kb" / "topic_map.json").read_text(encoding="utf8"))["map"]
    cards = load_cards()
    cur = scan(web)
    manifest = json.loads(MANIFEST.read_text(encoding="utf8")) if MANIFEST.exists() else None

    # 1) 사실 확인
    results = check_facts(web, facts)
    bad = [r for r in results if not r["ok"]]
    print_section(f"사실 확인 ({len(results) - len(bad)}/{len(results)} 일치)  ·  AnyControl 폴더: {web}")
    for r in results:
        if not r["ok"]:
            print(f"  ✗ {r['id']}: {r['desc']}\n      기대 {r['expect']!r} · 지금 {r['actual']!r}\n      → 다시 볼 카드: {', '.join(r['cards'])}")
    if not bad:
        print("  모든 사실이 기대값과 같습니다.")

    if a.coverage:
        watched = {c for r in results for c in r["cards"]} | {c for t in tmap for c in t["cards"] if c != "*"}
        loose = [cid for cid in cards if cid not in watched]
        print_section(f"감시되지 않는 카드 {len(loose)}장 (코드가 바뀌어도 자동으로는 알 수 없음 — 갱신 때 직접 훑어볼 것)")
        for cid in loose:
            print(f"  {cid:28s} {cards[cid]['q']['ko'][0]}")
        return 0

    # 2) 변경 파일
    added = removed = modified = []
    if manifest is None:
        print_section("기준(스냅샷) 없음")
        print("  아직 '이 상태에 맞춰 둠' 기록이 없습니다. 카드가 현재 AnyControl 과 맞는다고 확인했다면:\n    python3 tools/sync_check.py --accept")
        changed: list[str] = []
    else:
        old = manifest["files"]
        added = sorted(set(cur) - set(old))
        removed = sorted(set(old) - set(cur))
        modified = sorted(p for p in cur if p in old and cur[p]["sha256"] != old[p]["sha256"])
        changed = added + removed + modified
        rel_old, rel_new = manifest.get("releases", []), release_names(web)
        print_section(f"변경 파일  (기준: {manifest.get('synced_at')} · 앱 {manifest.get('app_version')}  →  지금: 앱 {json.loads((web / 'package.json').read_text(encoding='utf8')).get('version')})")
        print(f"  추가 {len(added)} · 삭제 {len(removed)} · 수정 {len(modified)}   (추적 파일 {len(cur)}개)")
        if rel_old != rel_new:
            print(f"  배포 파일 목록 변경: {sorted(set(rel_new) - set(rel_old))} 추가 / {sorted(set(rel_old) - set(rel_new))} 삭제")

    # 3) 영향받는 카드
    affected: dict[str, set[str]] = {}
    unmapped: list[str] = []
    topics_seen: dict[str, list[str]] = {}
    for rel in changed:
        ts = topics_for(rel, tmap)
        if not ts:
            unmapped.append(rel)
        for t in ts:
            topics_seen.setdefault(t["topic"], []).append(rel)
            for cid in t["cards"]:
                for real in (list(cards) if cid == "*" else [cid]):
                    affected.setdefault(real, set()).add(rel)
    for r in bad:
        for cid in r["cards"]:
            affected.setdefault(cid, set()).add(f"(사실 {r['id']})")
    if changed:
        print_section("바뀐 영역")
        for topic, rels in topics_seen.items():
            print(f"  · {topic}  ({len(rels)}개): {', '.join(rels[:4])}{' …' if len(rels) > 4 else ''}")
        if unmapped:
            print(f"  · topic_map 에 없는 파일 {len(unmapped)}개 → 직접 판단하고 kb/topic_map.json 에 추가: {', '.join(unmapped[:8])}")

    # 4) 문서 변경: 추가된 줄 / 코드 변경: 요약
    def snap_text(rel: str) -> str:
        p = SNAP_FILES / rel
        return p.read_text(encoding="utf8") if p.exists() else ""

    def cur_text(rel: str) -> str:
        return (web / rel).read_text(encoding="utf8") if (web / rel).exists() else ""

    shown = 0
    if changed and manifest is not None:
        print_section("문서 변경 (기준 대비 새로 추가·삭제된 줄)")
        for rel in changed:
            if rel not in DOC_FILES:
                continue
            d = diff_lines(snap_text(rel), cur_text(rel), rel)
            lim = 10_000 if (a.full or a.diff == rel) else (400 if rel == "HANDOFF.md" else 120)
            print(f"\n--- {rel}  ({sum(1 for x in d if x.startswith('+') and not x.startswith('+++'))}줄 추가, {sum(1 for x in d if x.startswith('-') and not x.startswith('---'))}줄 삭제)")
            for x in d[:lim]:
                print("  " + x)
            if len(d) > lim:
                print(f"  … {len(d) - lim}줄 더 (전체: --diff {rel})")
            shown += 1
        if not shown:
            print("  (추적하는 문서 변경 없음)")
        print_section("코드 변경 요약")
        for rel in changed:
            if rel in DOC_FILES:
                continue
            if rel in added:
                print(f"  + {rel}  (새 파일, {cur[rel]['size']}바이트)")
            elif rel in removed:
                print(f"  - {rel}  (삭제됨)")
            else:
                d = diff_lines(snap_text(rel), cur_text(rel), rel)
                plus = sum(1 for x in d if x.startswith("+") and not x.startswith("+++"))
                minus = sum(1 for x in d if x.startswith("-") and not x.startswith("---"))
                print(f"  ~ {rel}  (+{plus} / -{minus})")
                if a.full or a.diff == rel:
                    for x in d:
                        print("      " + x)
        if a.diff and a.diff not in changed:
            print(f"\n  ({a.diff} 는 변경 목록에 없음)")

    # 5) 다시 볼 카드
    if affected:
        print_section(f"다시 확인할 카드 {len(affected)}장")
        missing = [c for c in affected if c not in cards]
        for cid in sorted(c for c in affected if c in cards):
            print(f"  {cid:28s} [{cards[cid]['status']}] {cards[cid]['q']['ko'][0]}   ← {', '.join(sorted(affected[cid])[:2])}")
        for cid in missing:
            print(f"  ⚠ {cid}: topic_map/facts 에 적힌 카드가 없음 (지워졌거나 이름이 바뀜 → 지도 수정)")
    if changed or bad:
        print_section("다음 단계")
        print("  1) 위 diff 를 읽고, 다시 확인할 카드의 답이 아직 맞는지 코드·문서로 확인한다 (UPDATE_GUIDE.md)")
        print("  2) 틀어진 카드 수정 / 새 기능 카드 추가 / 없어진 기능 카드 삭제 (kb_src/*.txt 는 python3 tools/build_cards.py 로 다시 생성)")
        print("  3) 검증: python3 -m bot validate && python3 -m unittest discover -s tests && python3 -m bot eval && python3 -m bot eval --file eval/new_v.json")
        print("  4) 값이 의도대로 바뀐 사실은 kb/facts.json 의 expect 를 고친다")
        print("  5) python3 tools/sync_check.py --accept   (현재 상태를 새 기준으로 저장)")

    # 6) 기준 저장
    if a.accept:
        if bad and not a.force:
            print("\n--accept 거절: 사실 어긋남이 남아 있습니다. 카드나 kb/facts.json 을 고친 뒤 다시 하세요 (그래도 저장하려면 --force).")
            return 1
        if SNAP_FILES.exists():
            shutil.rmtree(SNAP_FILES)
        for rel in cur:
            dst = SNAP_FILES / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(web / rel, dst)
        version = json.loads((web / "package.json").read_text(encoding="utf8")).get("version")
        MANIFEST.write_text(json.dumps({"synced_at": time.strftime("%Y-%m-%d %H:%M"), "app_version": version, "files": cur,
                                        "releases": release_names(web)}, ensure_ascii=False, indent=1), encoding="utf8")
        (ROOT / "kb" / "VERSION.json").write_text(json.dumps({"app_version": version, "synced_at": time.strftime("%Y-%m-%d"), "cards": len(cards)},
                                                             ensure_ascii=False, indent=1), encoding="utf8")
        print(f"\n기준을 저장했습니다: 앱 {version} · 추적 파일 {len(cur)}개 → kb/snapshot/")
        return 0

    return 1 if (changed or bad) else (0 if manifest is not None else 1)


if __name__ == "__main__":
    sys.exit(main())
