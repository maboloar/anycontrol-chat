"""지식 베이스 로딩과 검증.

kb/
  categories.json   카테고리 목록 [{id, ko, en}]
  cards/*.json      질문-답 카드 목록 (손으로 다듬은 것, 검색에서 우선)
  glossary.json     영어 ↔ 한국어 용어 (질의 확장)
  policy.json       금지 표현, 임계값, 안내 문구
카드 한 장의 필드:
  id, cat, status, q{ko[],en[]}, a{ko,en}, kw[], src[], related[], suggest(선택), allow_banned(선택)
status: measured(재현 가능하게 측정) · verified(구현·테스트로 확인) · partial(일부 검증/표본 작음)
        not_validated(검증 안 됨) · plan(계획·제안) · info(설명)
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ("measured", "verified", "partial", "not_validated", "plan", "info")
LANGS = ("ko", "en")


@dataclass
class KB:
    cards: list[dict] = field(default_factory=list)
    cats: list[dict] = field(default_factory=list)
    glossary: dict[str, list[str]] = field(default_factory=dict)
    policy: dict = field(default_factory=dict)
    by_id: dict[str, dict] = field(default_factory=dict)
    root: Path = ROOT


def _load(path: Path, default):
    return json.loads(path.read_text(encoding="utf8")) if path.exists() else default


def card_files(d: Path) -> list[Path]:
    """카드 JSON 파일 목록. macOS 압축·복사가 만드는 '._이름.json'(AppleDouble)·숨김 파일은 카드가 아니므로 건너뛴다."""
    return [f for f in sorted(d.glob("*.json")) if not f.name.startswith((".", "_")) and "__MACOSX" not in f.parts]


def load_kb(root: Path | None = None) -> KB:
    root = Path(root) if root else ROOT
    k = root / "kb"
    kb = KB(root=root)
    kb.cats = _load(k / "categories.json", [])
    for f in card_files(k / "cards"):
        try:
            kb.cards.extend(json.loads(f.read_text(encoding="utf-8-sig")))
        except UnicodeDecodeError as e:
            raise RuntimeError(f"카드 파일을 읽을 수 없어요(UTF-8 이 아님): {f}\n"
                               "macOS 에서 압축할 때 생기는 '._' 로 시작하는 파일이거나 다른 인코딩으로 저장된 파일일 수 있어요. 그 파일을 지우고 다시 실행해 주세요.") from e
    kb.glossary = _load(k / "glossary.json", {})
    kb.policy = _load(k / "policy.json", {})
    kb.by_id = {c["id"]: c for c in kb.cards}
    return kb


def banned_hits(text: str, policy: dict) -> list[str]:
    return [p for p in policy.get("banned", []) if re.search(p, text, re.I)]


def validate_kb(kb: KB) -> tuple[list[str], list[str]]:
    """(errors, warnings). errors 가 있으면 챗봇을 배포하지 않는다."""
    errors: list[str] = []
    warns: list[str] = []
    cat_ids = {c["id"] for c in kb.cats}
    seen: set[str] = set()
    for c in kb.cards:
        cid = c.get("id", "?")
        if cid in seen:
            errors.append(f"{cid}: id 중복")
        seen.add(cid)
        if c.get("cat") not in cat_ids:
            errors.append(f"{cid}: 알 수 없는 카테고리 {c.get('cat')!r}")
        if c.get("status") not in STATUSES:
            errors.append(f"{cid}: status 가 올바르지 않음 {c.get('status')!r}")
        for lang in LANGS:
            if not c.get("q", {}).get(lang):
                errors.append(f"{cid}: 질문({lang}) 없음")
            if not str(c.get("a", {}).get(lang, "")).strip():
                errors.append(f"{cid}: 답({lang}) 없음")
        if not c.get("src"):
            warns.append(f"{cid}: 출처(src) 없음")
        if not c.get("kw"):
            warns.append(f"{cid}: 키워드(kw) 없음")
        if not c.get("allow_banned"):
            for lang in LANGS:
                for hit in banned_hits(str(c.get("a", {}).get(lang, "")), kb.policy):
                    errors.append(f"{cid}: 답({lang})에 금지 표현 /{hit}/ — 부정문으로 쓴 거라면 allow_banned 를 true 로")
        for r in c.get("related", []):
            if r not in kb.by_id:
                errors.append(f"{cid}: related 에 없는 id {r}")
        # 한 답에 숫자가 있는데 언어마다 숫자가 다르면 번역 실수일 가능성이 크다
        from .textutil import numbers_in
        nk, ne = numbers_in(str(c.get("a", {}).get("ko", ""))), numbers_in(str(c.get("a", {}).get("en", "")))
        if nk != ne:
            warns.append(f"{cid}: ko/en 답의 숫자가 다름 (ko만 {sorted(nk - ne)}, en만 {sorted(ne - nk)})")
    return errors, warns
