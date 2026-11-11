"""질문 → 답변. 카드 검색을 먼저 하고, 맞는 카드가 없으면 '자료에 없다'고 솔직하게 답한다.

응답 종류(kind)
  answer    질문과 잘 맞는 카드가 있다 → 카드 답을 그대로 보여 준다 (LLM 을 거치지 않으므로 즉시, 지어낼 수 없다)
  related   정확히 같지는 않지만 가까운 카드가 있다 → 가장 가까운 카드 답 + 관련 질문 (LLM 이 켜져 있으면 카드만 근거로 다듬는다)
  none      자료에 없다 → 모른다고 말하고 관련 질문과 원문 발췌를 보여 준다
  greeting  인사
  empty     빈 질문
LLM 은 선택 기능이다. 켜져 있어도 출력이 검사(숫자·금지 표현·언어)를 통과하지 못하면 카드 원문을 쓴다.
"""
from __future__ import annotations
import re
import time

from .kb import KB, banned_hits
from .search import Index
from . import nlu
from .textutil import detect_lang, numbers_in, tokenize

DEFAULTS = {
    "direct_coverage": 0.60,     # 질문의 중요한 단어 중 이만큼 맞으면 '같은 질문'으로 본다
    "direct_score": 7.0,
    "direct_full_coverage": 0.95,  # 질문의 단어가 거의 다 맞으면 점수가 조금 낮아도 '같은 질문'으로 본다
    "direct_full_score": 3.5,
    "direct_big_score": 25.0,      # 점수가 아주 높으면 긴 질문이라 coverage 가 낮아도 '같은 질문'
    "direct_big_coverage": 0.50,
    "related_coverage": 0.34,    # 이만큼 맞으면 '가까운 질문'
    "related_score": 3.0,
    "near_coverage": 0.12,       # 이 이상이면 '혹시 이런 질문인가요?' 로 가까운 질문을 보여 준다 (답은 단정하지 않는다)
    "max_query_chars": 300,
    "spell_fix": True,             # 철자 교정(카드 단어 사전 + 자모 편집 거리, 모델 불필요)
    "typo_fix": True,              # Qwen 이 오타·띄어쓰기·줄임말을 고쳐 다시 찾는다 (Qwen 이 있을 때만; 평가·테스트에서는 별도로 켠다)
    "typo_timeout_s": 6.0,
    "typo_min_similarity": 0.30,   # 고친 문장이 원래 말과 글자 2-gram 유사도(Dice)가 이 이상이어야 한다
    "llm_compose": False,          # RAG: 검색된 카드만 근거로 Qwen 이 질문에 맞게 답을 정리한다. 기본 꺼짐 — 1.5B 모델은 정리한 답의 약 1/3 이 사실과 다르거나 뜻이 뒤집혔다(HANDOFF §12). 켜려면 --rag
    "free_chat": False,            # 프로젝트와 상관없는 잡담에 Qwen 이 짧게 자유 대답 (bot serve 는 기본 켬, --no-chat 으로 끔). 평가·테스트는 꺼 둔다
    "chat_timeout_s": 12.0,
    "chat_project_coverage": 0.50, # 카드로 못 찾았어도 질문이 카드와 이만큼(높게) 겹치면 프로젝트 질문으로 보고 잡담으로 넘기지 않는다
    "rag_timeout_s": 10.0,         # 정리하는 데 쓸 수 있는 최대 시간
    "rag_sentence_grounded": 0.55, # 답의 모든 문장이 이 비율 이상 카드·질문의 단어로 이루어져야 한다
    "rag_support_score": 1.0,      # "자료와 일치하나요?" 점수의 최소값
    "rag_grounded": 0.50,          # 정리한 답의 내용 단어 중 카드·질문에 실제로 있는 비율의 최소값 (카드에 없는 설명을 덧붙이는 것을 막는다)
    "rag_vias": ["search", "context", "llm"],   # 이 경로로 찾은 답만 정리한다 (정확 일치·일반 의도는 카드 원문이 곧 정답이라 그대로)
    "route_candidates": 12,        # LLM 이 점수를 매길 후보 카드 수 (느린 컴퓨터에서는 시작할 때 잰 속도에 맞춰 줄어듦)
    "route_budget_s": 6.0,         # 한 질문에 쓸 수 있는 LLM 시간 (넘으면 그때까지의 결과만 사용)
    "route_lexical_weight": 15.0,  # 합산 점수 = 모델 점수 + 이 값 × 글자 검색 유사도(0~1) + 앞 대화 카드 가산점
    "route_ctx_bonus": 2.0,
    "route_answer_score": 6.0,     # 합산 점수가 이 이상이고 2등과의 차이가 route_margin 이상일 때만 직접 답한다 (나머지는 순위를 "혹시 이런 질문인가요?"로 보여 줌)
    "route_margin": 2.0,
    "route_suggest_score": 0.0,    # 이 점수 이상인 후보만 "혹시 이런 질문인가요?"에 올린다
    "route_anchors": ["g-what-is", "g-why-made", "v-top-strengths", "v-top-weakness", "g-vs-others", "g-who-for", "g-limits", "g-hardware"],
    "greetings": [r"^\s*(안녕|하이(?![가-힣])|헬로)", r"^\s*(hello|hi|hey)\b"],
}


class Engine:
    def __init__(self, kb: KB, llm=None) -> None:
        self.kb = kb
        self.llm = llm
        self.cfg = {**DEFAULTS, **kb.policy.get("thresholds", {})}
        self.card_index = Index(
            [[(" ".join(c["q"]["ko"]), 3.0), (" ".join(c["q"]["en"]), 3.0), (" ".join(c.get("kw", [])), 2.5),
              (c["a"]["ko"], 1.0), (c["a"]["en"], 1.0)] for c in kb.cards], kb.glossary)
        self.suggested = [c for c in kb.cards if c.get("suggest")]
        self.fuzzy = nlu.FuzzyIndex(kb.cards)
        self.spell = nlu.SpellFixer([t for c in kb.cards for t in (c["q"]["ko"] + c.get("kw", []) + [c["a"]["ko"]])])   # 철자 교정 사전(카드 문구의 한국어 단어)
        # 카드에 적어 둔 질문과 글자 그대로 같은 질문은 검색 없이 바로 그 카드로 연결한다 ("Who are you?" 처럼 불용어뿐인 짧은 질문 포함)
        self.exact: dict[tuple[str, str], dict] = {}
        for c in kb.cards:
            for lang in ("ko", "en"):
                for qq in c["q"][lang]:
                    self.exact.setdefault((lang, _norm(qq)), c)

    # ------------------------------------------------------------------ 공개 API
    def ask(self, query: str, ui_lang: str = "ko", ctx: list[str] | None = None, prev: str = "", hist: list | None = None) -> dict:
        t0 = time.perf_counter()
        q = (query or "").strip()[: int(self.cfg["max_query_chars"])]
        lang = detect_lang(q, ui_lang) if q else ui_lang
        hist = [(str(h[0])[:200], str(h[1])[:300]) for h in (hist or []) if isinstance(h, (list, tuple)) and len(h) == 2][-3:]
        ctx = [c for c in (ctx or []) if isinstance(c, str)][:3]
        prev = (prev or "")[:120]
        foreign = nlu.detect_foreign(q) if q else None
        if foreign:                                                  # 한국어·영어가 아닌 질문: Qwen 으로 영어로 옮겨 묻고 답을 다시 그 언어로 옮긴다 (없으면 안내)
            res = self._foreign(q, foreign, ui_lang, ctx, prev)
        else:
            res = self._ask_multi(q, lang, ui_lang, ctx, prev, hist)
        if ui_lang in ("ko", "en"):
            self._relang(res, ui_lang)
        res["lang"] = lang
        res["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return res

    def suggestions(self, lang: str, cat: str | None = None, n: int = 8) -> list[dict]:
        if cat:
            pool = [c for c in self.suggested if c["cat"] == cat] or [c for c in self.kb.cards if c["cat"] == cat]
            return self._uniq([self._brief(c, lang) for c in pool], lang)[:n]
        # 처음 화면: 보이는 카테고리마다 한 장씩 돌아가며 골라 다양한 질문이 나오게 한다
        hidden = {c["id"] for c in self.kb.cats if c.get("hidden")}
        order = [c["id"] for c in self.kb.cats if not c.get("hidden")]
        buckets = {cid: [c for c in self.suggested if c["cat"] == cid] for cid in order}
        pool: list[dict] = []
        while len(pool) < n and any(buckets.values()):
            for cid in order:
                if buckets[cid] and len(pool) < n:
                    pool.append(buckets[cid].pop(0))
        if not pool:
            pool = [c for c in self.kb.cards if c["cat"] not in hidden][:n]
        return self._uniq([self._brief(c, lang) for c in pool], lang)[:n]

    def _uniq(self, items: list[dict], lang: str, skip: str = "") -> list[dict]:
        """같은 질문 문구가 버튼으로 두 번 나오지 않게 하고, policy.menu_hidden 의 카드는 버튼으로 보이지 않게 한다 (직접 물어보면 답은 한다)."""
        seen = {_norm(skip)} if skip else set()
        menu_hidden = set(self.kb.policy.get("menu_hidden", []))
        out = []
        for it in items:
            if it.get("id") in menu_hidden:
                continue
            k = _norm(it["q"])
            if k not in seen:
                seen.add(k)
                out.append(it)
        return out

    def labels(self, ids: list[str], lang: str) -> dict[str, str]:
        """카드 id -> 그 언어의 대표 질문 (화면 언어를 바꿀 때 이미 떠 있는 버튼 문구를 바꾸는 데 쓴다)"""
        return {i: self.kb.by_id[i]["q"][lang][0] for i in ids if i in self.kb.by_id}

    def _relang(self, res: dict, ui_lang: str) -> dict:
        """답은 질문한 언어로 하되, 이어지는 질문·추천 버튼은 항상 화면(UI) 언어로 보여 준다."""
        for key in ("more", "suggestions"):
            if res.get(key):
                items = [self._brief(self.kb.by_id[x["id"]], ui_lang) if x.get("id") in self.kb.by_id else x for x in res[key]]
                cid = (res.get("card") or {}).get("id")
                own = self.kb.by_id[cid]["q"][ui_lang][0] if key == "more" and cid in self.kb.by_id else ""     # 지금 답한 카드의 질문은 버튼에서 뺀다
                res[key] = self._uniq(items, ui_lang, own)
        return res

    def card(self, cid: str, lang: str) -> dict | None:
        c = self.kb.by_id.get(cid)
        if not c:
            return None
        out = self._full(c, lang)
        out["more"] = self._rel(c, lang, exclude=[])      # 버튼으로 열어도 '이어서 물어볼 만한 질문'을 보여 준다
        return out

    # ------------------------------------------------------------------ 내부
    def _ask_multi(self, q: str, lang: str, ui_lang: str, ctx: list[str], prev: str, hist: list) -> dict:
        """여러 질문이 한 번에 들어오면(번호·물음표) 질문마다 답하고, 긴 문장이 통째로는 안 풀리면 문장별로 다시 찾는다."""
        parts = nlu.split_parts(q)
        qparts = [p for p in parts if nlu.is_question_like(p)]
        multi = 2 <= len(qparts) <= 6 and len(q) > 20
        if not multi:
            res = self._ask(q, lang, ui_lang, ctx, prev, hist)
            if not (res.get("kind") in ("none", "chat", "related") and res.get("via") not in ("smalltalk", "safety", "free_chat", "free_chat_blocked", "chitchat")
                    and len(parts) >= 2 and qparts and len(q) >= 25):
                return res
            if len(qparts) < 2:
                sub_res = self._ask(qparts[0], detect_lang(qparts[0], lang), ui_lang, ctx, prev, hist, allow_chat=False) if qparts else None
                if sub_res is not None and sub_res.get("kind") in ("answer", "related") and sub_res.get("via") not in ("free_chat", "chitchat"):
                    return sub_res
                return res
            qparts_to_run = qparts
        else:
            qparts_to_run = qparts
        items = []
        for p in qparts_to_run[:5]:
            pl = detect_lang(p, lang)
            r = self._ask(p, pl, ui_lang, ctx, prev, hist, allow_chat=False)
            items.append((p, pl, r))
        got = [(p, pl, r) for p, pl, r in items if r.get("kind") in ("answer", "related")]
        if not got:
            return self._ask(q, lang, ui_lang, ctx, prev, hist) if not multi else items[0][2]
        if len(items) == 1:
            return got[0][2]
        none_msg = {"ko": "이 부분은 제가 가진 자료에 없어요.", "en": "This part is not in my notes."}[lang if lang in ("ko", "en") else "ko"]
        lines, seen_ids = [], []
        for i, (p, pl, r) in enumerate(items, 1):
            label = re.sub(r"\s+", " ", p).strip()
            label = label[:48] + ("…" if len(label) > 48 else "")
            ans = r["answer"] if r.get("kind") in ("answer", "related") else (none_msg if pl == lang else {"ko": "이 부분은 제가 가진 자료에 없어요.", "en": "This part is not in my notes."}[pl if pl in ("ko", "en") else "ko"])
            lines.append(f"**{i}. {label}**\n{ans}")
            if r.get("card"):
                seen_ids.append(r["card"]["id"])
        more = []
        for cid in seen_ids[:3]:
            more += self._rel(self.kb.by_id[cid], lang, exclude=[])
        return {"kind": "answer", "answer": "\n\n".join(lines), "mode": "cards", "via": "multi", "score": 50.0, "coverage": 1.0,
                "more": more[:3], "suggestions": self.suggestions(lang), "parts": len(items)}

    def _foreign(self, q: str, code: str, ui_lang: str, ctx: list[str], prev: str) -> dict:
        """한국어·영어가 아닌 질문. 카드는 한/영만 있으므로 Qwen 이 질문을 영어로 옮기고, 영어 답을 다시 질문 언어로 옮긴다. 불가능하면 한/영만 지원한다고 안내."""
        llm = self.llm
        msg = self.kb.policy.get("messages", {})
        name = nlu.LANG_NAMES.get(code, "")
        unsupported = {"kind": "none", "answer": _m(msg, "unsupported_lang", ui_lang), "suggestions": self.suggestions(ui_lang), "via": "unsupported_lang", "score": 0.0, "coverage": 0.0}
        if llm is None or not getattr(llm, "enabled", False) or not hasattr(llm, "translate"):
            return unsupported
        try:
            en_q = re.sub(r"\s+", " ", (llm.translate(q[:400], "English", timeout=8.0, src=name) or "")).strip()
        except Exception:
            return unsupported
        stripped = re.sub(r"\b(please\s+)?(answer|reply|respond|explain|tell me|say)\b[^.?!]*\bin\s+(chinese|japanese|spanish|french|german|arabic|russian|portuguese|italian|thai|hindi|vietnamese)\b[^.?!]*[.?!]?", " ", en_q, flags=re.I)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        if len(stripped) >= 5:
            en_q = stripped                               # "중국어로 답해 주세요" 같은 요청 문장은 질문에서 뺀다 (답은 어차피 그 언어로 옮긴다)
        if not en_q or len(en_q) > len(q) * 6 + 40 or re.search(r"[\uac00-\ud7a3]", en_q) or nlu.detect_foreign(en_q):
            return unsupported
        res = self._ask_multi(en_q, "en", "en", ctx, prev, [])
        if res.get("kind") in ("chat",) or res.get("via") in ("free_chat", "free_chat_blocked", "chitchat"):
            return unsupported
        en_ans = res.get("answer", "")
        try:
            tr = re.sub(r"[ \t]+", " ", (llm.translate(en_ans, name, timeout=12.0, sample=q) or "")).strip()
        except Exception:
            return unsupported
        if not tr or len(tr) > len(en_ans) * 5 + 60 or re.search(r"[\uac00-\ud7a3]", tr):
            return unsupported
        res["source_answer"] = en_ans
        res["answer"] = tr
        res["note"] = _m(msg, "translated", ui_lang)
        res["via"] = "translated"
        res["mode"] = "llm"
        res.pop("card", None)
        return res

    def _ask(self, q: str, lang: str, ui_lang: str, ctx: list[str] | None = None, prev: str = "", hist: list | None = None, allow_chat: bool = True) -> dict:
        msg = self.kb.policy.get("messages", {})
        if not q:
            return {"kind": "empty", "answer": _m(msg, "empty", lang), "suggestions": self.suggestions(lang)}
        if any(re.search(p, q, re.I) for p in self.cfg["greetings"]) and len(q) < 20:
            return {"kind": "greeting", "answer": _m(msg, "greeting", lang), "suggestions": self.suggestions(lang)}
        raw = q
        if len(q) < 80 and any(re.search(p, q, re.I) for p in self.kb.policy.get("no_info", [])):      # 자료에 없다고 정한 주제(논문 등)는 아는 척하지 않고 '자료에 없어요'
            return {"kind": "none", "answer": _m(msg, "none", lang), "excerpts": [], "suggestions": self.suggestions(lang), "near": False, "via": "no_info", "score": 0.0, "coverage": 0.0}
        fc = self.kb.policy.get("free_chat", {})
        if fc and re.search(fc["self_harm"]["re"], raw, re.I):         # 자해 언급은 어떤 설정에서도 정해진 따뜻한 안내만 (생성·검색 안 함)
            return {"kind": "chat", "answer": fc["self_harm"][lang], "suggestions": [], "via": "safety"}
        # 외부 기기 가격을 프로젝트 가격 카드로 오인하지 않는다. 카메라 호환 질문은 그대로 검색한다.
        device_price = re.search(r"아이폰|갤럭시|맥북|아이패드|\b(?:iphone|galaxy|macbook|ipad)\b", raw, re.I) and re.search(
            r"가격|시세|얼마|\b(?:price|cost|costs|pricing)\b|how much", raw, re.I)
        if device_price:
            return {"kind": "none", "answer": _m(msg, "none", lang), "excerpts": [], "suggestions": self.suggestions(lang),
                    "near": False, "via": "external_device_price", "score": 0.0, "coverage": 0.0}
        exact_first = self.exact.get((lang, _norm(raw)))      # 카드에 적힌 질문과 같으면 잡담 규칙보다 카드가 먼저
        for st in ([] if exact_first is not None else self.kb.policy.get("smalltalk", [])):      # 인사·감사·잡담·"이해 안 돼요" — 정해진 짧은 반응 (지어내지 않는다)
            if re.search(st["re"], raw, re.I) and len(raw) < 40:
                near = []
                ctx_c = next((self.kb.by_id[c] for c in (ctx or []) if c in self.kb.by_id), None)
                if st.get("hint") == "ctx" and ctx_c is not None:
                    near = self._rel(ctx_c, lang, exclude=[])
                return {"kind": "chat", "answer": st[lang], "suggestions": near or self.suggestions(lang), "via": "smalltalk"}
        if self.cfg.get("free_chat") and exact_first is None and len(raw) < 45:      # 가장 흔한 일상 말(배고파·피곤해·시험 망쳤어 …)은 미리 다듬은 따뜻한 반응
            cc = self._chitchat(raw, lang)
            if cc is not None:
                return cc
        oos = self.kb.policy.get("out_of_scope")            # 날씨·주식·코드 작성 같은 범위 밖 요청은 분명히 거절 (엉뚱한 카드로 연결하지 않는다)
        if oos and exact_first is None and any(re.search(p, raw, re.I) for p in oos["re"]):
            chat = self._free_chat(raw, lang, hist) if allow_chat else None
            if chat is not None:
                return chat
            if allow_chat and self.cfg.get("free_chat"):         # 대화가 켜져 있는데 모델이 답하지 못했다면 "범위 밖"이라고 잘라 말하지 않고 부드럽게
                return {"kind": "none", "answer": _m(msg, "chat_fallback", lang), "excerpts": [], "suggestions": self.suggestions(lang), "near": False,
                        "via": "chat_fallback", "score": 0.0, "coverage": 0.0}
            return {"kind": "none", "answer": oos[lang], "excerpts": [], "suggestions": self.suggestions(lang), "near": False, "via": "out_of_scope",
                    "score": 0.0, "coverage": 0.0}
        q = nlu.normalize(q) or raw                      # 구어체·반말·웃음/추임새 정리

        def done(res: dict) -> dict:                      # 고친 문장으로 찾은 답이면 어떻게 이해했는지 알려 준다 (res["fixed_q"] 가 있을 때)
            if res.get("fixed_q") and res.get("kind") in ("answer", "related") and not res.get("note"):
                res["note"] = _m(msg, "understood", lang).replace("{q}", res["fixed_q"])
            return res
        ctx_card = next((self.kb.by_id[c] for c in (ctx or []) if c in self.kb.by_id), None)
        cfg = self.cfg
        if ctx_card is None and not hist and len(raw) <= 14 and nlu.is_followup(raw, lang) and nlu.has_pronoun(raw, lang) is not None \
                and not re.search(self.kb.policy.get("project_terms", "(?!x)x"), re.sub(r"그건|그거|이건|이거|이것|그것|그럼|그러면|그래서|걔|얘", "", raw), re.I) and exact_first is None:
            return {"kind": "none", "answer": _m(msg, "clarify", lang), "suggestions": self.suggestions(lang), "via": "clarify", "score": 0.0, "coverage": 0.0}
        direct, hits, verdict, via = self._stage1(q, raw, lang, ctx_card, prev)
        if direct is not None:
            return done(direct)
        if hist and allow_chat and cfg.get("free_chat") and verdict[0] != "answer" and not self._project_related(raw, hits):
            chat = self._free_chat(raw, lang, hist)         # 잡담이 이어지는 중이면("면이 좋아요", "yeah I like games") 그 말을 프로젝트 질문으로 풀어 엉뚱한 카드로 가지 않고 대화를 잇는다
            if chat is not None:
                return chat
        # 원래 질문이 확실히 풀리지 않으면 고친 문장으로 같은 단계를 다시 돌려 본다: ① 철자 교정(사전·자모, 모델 불필요) ② Qwen 의 오타·띄어쓰기·줄임말 교정.
        # 고친 문장은 "확실한 답"이 나올 때만 채택한다 (멀쩡한 말을 잘못 고쳐서 엉뚱한 답을 내지 않게).
        fixed_q = None
        chat_gate = bool(cfg.get("free_chat"))         # 잡담이 켜져 있으면 일상 대화를 오타 교정이 엉뚱한 카드로 끌고 가지 않게 한다
        if verdict[0] != "answer":
            tried = {_norm(q)}
            spelled = self.spell.fix(q) if lang == "ko" and cfg.get("spell_fix", True) else q
            for cand, tag in ((spelled, "spell"), (None, "typo")):
                if cand is None:
                    cand = self._fix_typos(q, raw, lang)
                if not cand or _norm(cand) in tried:
                    continue
                tried.add(_norm(cand))
                direct2, hits2, verdict2, via2 = self._stage1(cand, cand, lang, ctx_card, prev)
                if direct2 is not None:
                    direct2["fixed_q"], direct2["via"] = cand, tag
                    return done(direct2)
                if verdict2[0] == "answer" or (verdict2[0] == "related" and verdict[0] is None and (not chat_gate or self._project_related(raw, hits2))):
                    hits, verdict, via, fixed_q = hits2, verdict2, tag, cand
                    break
                if tag == "typo":
                    if verdict2[0] == "related" and verdict[0] is None and (not chat_gate or self._project_related(raw, hits2)):
                        hits, verdict, via = hits2, verdict2, tag
                    q = cand                              # 이후 순위 매기기(Qwen)는 고친 문장으로 한다
        if verdict[0] == "answer":
            res = self._build(hits, verdict, lang, "answer")
            res["via"] = via
            if fixed_q:
                res["fixed_q"] = fixed_q
                res["note"] = _m(msg, "understood", lang).replace("{q}", fixed_q)
            return done(self._rag(res, q, lang, hits, prev))
        # 2단계: 로컬 LLM 이 후보 카드 중에서 고른다 (답은 카드 원문)
        follow_ctx = ctx_card if (nlu.is_followup(q, lang) or (nlu.has_pronoun(q, lang) and len(q) <= 24)) else None      # 독립 질문은 앞 대화에 끌려가지 않는다
        routed, llm_top, llm_info = self._route(q, lang, hits, follow_ctx, prev)
        if routed is not None:
            res = self._direct(routed, lang, "llm")
            res["llm"] = llm_info
            res["note"] = _m(msg, "understood", lang).replace("{q}", routed["q"][lang][0])
            return done(self._rag(res, q, lang, hits, prev))
        if verdict[0] == "related" and (not chat_gate or self._project_related(raw, hits)):
            res = self._build(hits, verdict, lang, "related", q=q, note=_m(msg, "related", lang))
            res["via"] = via
            if fixed_q:
                res["fixed_q"] = fixed_q
            return done(self._rag(res, q, lang, hits, prev))
        if allow_chat and not self._project_related(raw, hits):            # 프로젝트와 상관없는 말이면 안내 챗봇이 직접 대화한다 (프로젝트 질문이면 지어내지 않고 아래로)
            chat = self._free_chat(raw, lang, hist)
            if chat is not None:
                return chat
            if cfg.get("free_chat"):                       # 잡담으로 답하지 못했을 때(출력 검사 탈락·시간 초과)도 "자료에 없어요"가 아니라 부드러운 안내로
                return {"kind": "none", "answer": _m(msg, "chat_fallback", lang), "excerpts": [], "llm": llm_info, "suggestions": self.suggestions(lang),
                        "near": False, "score": 0.0, "coverage": 0.0, "via": "chat_fallback"}
        near = []
        if hits and hits[0][2] >= cfg["near_coverage"]:
            near = [self._brief(self.kb.cards[j], lang) for j, _, cv in hits[:3] if cv >= cfg["near_coverage"]]
        if llm_top:                                        # LLM 이 매긴 순서가 더 믿을 만하다
            near = [self._brief(c, lang) for c in llm_top]
        elif not near:
            near = [self._brief(self.kb.cards[i], lang) for i, sim in self.fuzzy.top(q, lang, 3) if sim >= 0.30]
        return {"kind": "none", "answer": _m(msg, "near" if near else "none", lang), "excerpts": [], "llm": llm_info,
                "suggestions": near or self.suggestions(lang), "near": bool(near),
                "score": round(hits[0][1], 2) if hits else 0.0, "coverage": round(hits[0][2], 2) if hits else 0.0}

    def _stage1(self, q: str, raw: str, lang: str, ctx_card: dict | None, prev: str) -> tuple:
        """규칙 단계: 정책 intents → 정확 일치 → 일반 질문 의도 → BM25(+이어 묻기 보강).
        돌려주는 값: (바로 답한 응답 or None, hits, verdict, via)"""
        for it in self.kb.policy.get("intents", []):
            c = self.kb.by_id.get(it["card"])
            if c and re.search(it["re"], q, re.I) and len(q) < int(it.get("max", 40)):
                return self._direct(c, lang, "intent"), [], (None, 0, 0.0, 0.0), "intent"
        ex = self.exact.get((lang, _norm(q))) or self.exact.get((lang, _norm(raw)))
        if ex is not None:
            return self._direct(ex, lang, "exact"), [], (None, 0, 0.0, 0.0), "exact"
        gi = nlu.generic_intent(q, lang)                  # "이게 왜 좋음?", "왜 필요해요?" 같은 주제어 없는 흔한 질문
        if gi and gi in self.kb.by_id:
            return self._direct(self.kb.by_id[gi], lang, "intent"), [], (None, 0, 0.0, 0.0), "intent"
        hits = self.card_index.search(q, 6)
        verdict = self._verdict(hits)
        via = "search"
        # 이어 묻기("그럼 ~", "그건 ~")는 앞 대화를 보탠 검색을 우선한다. 그 밖에는 검색이 약할 때만 보태 본다.
        follow = ctx_card is not None and nlu.is_followup(q, lang)
        if verdict[0] != "answer" or follow:
            best_aug = None
            for aug, tag in self._augmented(q, lang, ctx_card, prev):
                h2 = self.card_index.search(aug, 6)
                v2 = self._verdict(h2)
                if v2[0] in ("answer", "related") and (best_aug is None or v2[2] > best_aug[1][2]):
                    best_aug = (h2, v2, tag)
            if best_aug is not None and (follow or best_aug[1][0] == "answer" or verdict[0] is None):
                hits, verdict, via = best_aug
        return None, hits, verdict, via

    def _fix_typos(self, q: str, raw: str, lang: str) -> str | None:
        """Qwen 으로 오타·띄어쓰기·줄임말을 고친 문장을 얻는다. 뜻이 바뀐 것 같으면(길이·언어·숫자·글자 유사도 검사) 버린다."""
        llm = self.llm
        if not self.cfg.get("typo_fix") or llm is None or not getattr(llm, "enabled", False) or not hasattr(llm, "fix_typos"):
            return None
        try:
            out = llm.fix_typos(raw, lang, timeout=float(self.cfg["typo_timeout_s"]))
        except Exception:
            return None
        out = (out or "").strip().split("\n")[0].strip().strip("\"'“”‘’「」")
        out = re.sub(r"^(교정|수정|고친 문장|corrected)\s*[:：]\s*", "", out, flags=re.I)
        if not out or _norm(out) == _norm(raw) or len(out) < 2 or len(out) > len(raw) * 1.6 + 8:
            return None
        if (lang == "ko") != (re.search(r"[가-힣]", out) is not None) and lang == "ko":
            return None
        if lang == "en" and re.search(r"[가-힣]", out):
            return None
        if re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", out):
            return None                                   # 한자·일본어가 섞이면 거절 (Qwen 이 가끔 중국어를 섞는다)
        if set(re.findall(r"\d+", out)) - set(re.findall(r"\d+", raw)):
            return None                                   # 없던 숫자를 덧붙이면 거절
        if re.search(self.kb.policy.get("free_chat", {}).get("blocked", {}).get("re", "(?!x)x"), out, re.I):
            return None
        if nlu.char_similarity(raw, out) < float(self.cfg.get("typo_min_similarity", 0.30)):
            return None                                   # 원래 말과 너무 다르게 바꿨다
        return out

    # -- 판정·응답 조립 -------------------------------------------------------
    def _verdict(self, hits: list) -> tuple:
        cfg = self.cfg
        if not hits:
            return (None, 0, 0.0, 0.0)
        i, score, cov = hits[0]
        if (cov >= cfg["direct_coverage"] and score >= cfg["direct_score"]) \
                or (cov >= cfg["direct_full_coverage"] and score >= cfg["direct_full_score"]) \
                or (cov >= cfg["direct_big_coverage"] and score >= cfg["direct_big_score"]):
            return ("answer", i, score, cov)
        if cov >= cfg["related_coverage"] and score >= cfg["related_score"]:
            return ("related", i, score, cov)
        return (None, i, score, cov)

    def _build(self, hits: list, verdict: tuple, lang: str, kind: str, q: str = "", note: str = "") -> dict:
        _, i, score, cov = verdict
        card = self.kb.cards[i]
        cfg = self.cfg
        others = [self._brief(self.kb.cards[j], lang) for j, s, cv in hits[1:] if cv >= cfg["related_coverage"] * 0.8][:3]
        res = {"kind": kind, "answer": card["a"][lang], "card": self._full(card, lang), "score": round(score, 2), "coverage": round(cov, 2),
               "more": others + self._rel(card, lang, exclude=others), "mode": "cards"}
        if kind == "related":
            res["note"] = note
        return res

    def _direct(self, c: dict, lang: str, via: str) -> dict:
        return {"kind": "answer", "answer": c["a"][lang], "card": self._full(c, lang), "score": 99.0, "coverage": 1.0,
                "more": self._rel(c, lang, exclude=[]), "mode": "cards", "via": via}

    def _augmented(self, q: str, lang: str, ctx_card: dict | None, prev: str) -> list[tuple[str, str]]:
        """검색이 약할 때 덧붙여 다시 찾을 질문들: (질문, 태그)"""
        out: list[tuple[str, str]] = []
        follow = nlu.is_followup(q, lang) or (nlu.has_pronoun(q, lang) and len(q) <= 24)
        if ctx_card is not None and follow:
            topic = ctx_card["q"][lang][0]
            out.append((f"{q} {topic}", "context"))
            if prev:
                out.append((f"{q} {prev}", "context"))
        return out

    def _route(self, q: str, lang: str, hits: list, ctx_card: dict | None, prev: str) -> tuple[dict | None, list[dict], dict]:
        """로컬 LLM 이 '이 질문은 어느 카드의 질문과 같은 뜻인가'를 후보마다 예/아니오 점수로 매긴다.
        돌려주는 값: (확신할 때만 카드, LLM 이 매긴 상위 후보 카드들, {점수 정보}). LLM 이 꺼져 있거나 시간이 모자라면 (None, [], {})."""
        if self.llm is None or not getattr(self.llm, "enabled", False) or not hasattr(self.llm, "rank"):
            return None, [], {}
        pair_s = getattr(self.llm, "pair_s", None) or 0.3
        budget = float(self.cfg.get("route_budget_s", 6.0))
        limit = max(4, min(int(self.cfg.get("route_candidates", 12)), int(budget / max(pair_s, 0.01))))
        cand: list[int] = []

        def add(i: int) -> None:
            if i not in cand and len(cand) < limit:
                cand.append(i)
        if ctx_card is not None:
            add(self.kb.cards.index(ctx_card))
        for i, _s, _c in hits[:4]:
            add(i)
        for i, _sim in self.fuzzy.top(q, lang, 4):
            add(i)
        if ctx_card is not None:
            for r in ctx_card.get("related", [])[:2]:
                if r in self.kb.by_id:
                    add(self.kb.cards.index(self.kb.by_id[r]))
        for cid in self.cfg.get("route_anchors", []):          # 아주 막연한 질문을 위한 기본 후보
            if cid in self.kb.by_id:
                add(self.kb.cards.index(self.kb.by_id[cid]))
        if not cand:
            return None, [], {}
        topic = ctx_card["q"][lang][0] if ctx_card is not None else ""
        try:
            scores = self.llm.rank(q, lang, topic, [self.kb.cards[i]["q"][lang][0] for i in cand], budget)
        except Exception:
            return None, [], {}
        # 모델 점수(같은 뜻일 가능성)와 글자 검색 점수(단어·문구가 얼마나 겹치나)를 합친다 — 서로 약점이 달라 합치면 더 낫다
        cov = {i: c for i, _s, c in hits}
        fz = dict(self.fuzzy.top(q, lang, 8))
        ctx_i = self.kb.cards.index(ctx_card) if ctx_card is not None else -1
        w_lex, w_ctx = float(self.cfg.get("route_lexical_weight", 15.0)), float(self.cfg.get("route_ctx_bonus", 2.0))
        fused = [(s + w_lex * max(cov.get(i, 0.0), fz.get(i, 0.0)) + (w_ctx if i == ctx_i else 0.0), i)
                 for s, i in zip(scores, cand) if s is not None]
        if not fused:
            return None, [], {}
        fused.sort(reverse=True)
        top = [self.kb.cards[i] for sc, i in fused[:3] if sc >= float(self.cfg.get("route_suggest_score", 0.0))]
        best, second = fused[0][0], (fused[1][0] if len(fused) > 1 else -99.0)
        margin = best - second
        pick_i = fused[0][1]
        # 질문의 중요한 단어 중 자료에 한 번도 안 나온 말이 많으면(비트코인, 날씨 …) 자료 밖 질문일 가능성이 커서 직접 답하지 않는다
        toks = [t for t in tokenize(nlu.strip_subject(q, lang)) if len(t) > 1]
        unseen = [t for t in toks if t not in self.card_index.idf]
        off_topic = bool(toks) and len(unseen) >= max(1, int(0.6 * len(toks) + 0.5))
        info = {"best": round(best, 2), "margin": round(margin, 2), "n": len(fused), "pick": self.kb.cards[pick_i]["id"], "off_topic": off_topic}
        confident = (not off_topic) and best >= float(self.cfg.get("route_answer_score", 6.0)) and margin >= float(self.cfg.get("route_margin", 2.0))
        if confident:
            return self.kb.cards[pick_i], top, info
        return None, top, info

    def _project_related(self, raw: str, hits: list) -> bool:
        """카드로 못 찾은 질문이 그래도 AnyControl 에 대한 것인지 본다. 그렇다면 모델이 지어내지 않고 '자료에 없어요'로 답한다."""
        pt = self.kb.policy.get("project_terms")
        if pt and re.search(pt, raw, re.I):
            return True
        return bool(hits and hits[0][2] >= self.cfg["chat_project_coverage"])

    def _chitchat(self, raw: str, lang: str) -> dict | None:
        """흔한 일상 말에 미리 쓴 반응을 돌려준다 (정책 chitchat). 프로젝트 말이 섞여 있으면 건드리지 않는다. 같은 말에도 돌아가며 다른 문장을 쓴다."""
        fc = self.kb.policy.get("free_chat", {})
        if fc and (re.search(fc["blocked"]["re"], raw, re.I) or re.search(fc["realtime"]["re"], raw, re.I)):
            return None                                       # 욕설·민감 주제·실시간 정보는 아래 대화 단계의 고정 답으로
        pt = self.kb.policy.get("project_terms")
        bare = re.sub(r"\b(it|this|that)(?:\x27s)?\b|이거|이것|이게|이건|그거|그건", " ", raw, flags=re.I)         # 대명사만으로는 프로젝트 말로 보지 않는다 ("it\x27s my birthday")
        if pt and re.search(pt, bare, re.I):
            return None
        key = "re_ko" if lang == "ko" else "re_en"
        for it in self.kb.policy.get("chitchat", []):
            if re.search(it[key], raw, re.I):
                self._cc_n = getattr(self, "_cc_n", 0) + 1
                pool = it[lang]
                return {"kind": "chat", "answer": pool[self._cc_n % len(pool)], "suggestions": self.suggestions(lang), "via": "chitchat"}
        return None

    def _free_chat(self, raw: str, lang: str, hist: list | None = None) -> dict | None:
        """프로젝트와 상관없는 말: 'AnyControl 안내 챗봇' 정체성(persona)을 가진 Qwen 이 짧게 대화한다. 카드 답과 구분하기 위해 note 로 표시한다.
        꺼져 있거나 Qwen 이 없거나 느리면, 민감 주제이거나 출력 검사에 걸리면 None (정해진 거절·안내 문구로 돌아간다)."""
        cfg = self.cfg
        fc = self.kb.policy.get("free_chat", {})
        if not cfg.get("free_chat") or not fc:
            return None
        if re.search(fc["realtime"]["re"], raw, re.I):                      # 날씨·시각·뉴스·시세: 모델이 지어내기 쉬우므로 생성하지 않고 모른다고 말한다
            return {"kind": "chat", "answer": fc["realtime"][lang], "suggestions": self.suggestions(lang), "via": "free_chat_blocked"}
        if re.search(fc["blocked"]["re"], raw, re.I):                       # 욕설·성적·정치·의료·법률·투자: 생성하지 않고 정중히 거절
            return {"kind": "chat", "answer": fc["blocked"][lang], "suggestions": self.suggestions(lang), "via": "free_chat_blocked"}
        llm = self.llm
        if llm is None or not getattr(llm, "enabled", False) or not getattr(llm, "chat_ok", getattr(llm, "rag_ok", False)) or not hasattr(llm, "chat"):
            return None
        persona = self.kb.policy.get("persona", {}).get(lang, "")
        t_start = time.perf_counter()
        for temp in (0.3, 0.7):                                              # 첫 답이 검사에서 떨어지면 온도를 올려 한 번 더 (너무 오래 걸렸으면 다시 하지 않는다)
            try:
                setattr(llm, "chat_temperature", temp)
                out = llm.chat(raw, lang, timeout=float(cfg["chat_timeout_s"]), persona=persona, hist=hist)
            except Exception:
                return None
            good = self._vet_chat(out, raw, lang, hist)
            if good:
                return {"kind": "chat", "answer": good, "note": fc["note"][lang], "suggestions": self.suggestions(lang), "via": "free_chat", "mode": "llm"}
            if time.perf_counter() - t_start > float(cfg["chat_timeout_s"]) * 0.5:
                break
        return None

    def _vet_chat(self, out: str, raw: str, lang: str, hist: list | None = None) -> str | None:
        """잡담 답 검사·다듬기. 쓸 수 있으면 다듬은 문장을, 아니면 None (정해진 안내 문구로 돌아가거나 한 번 더 시도)."""
        out = re.sub(r"\s+", " ", (out or "").strip())
        if out and not re.search(r"[.!?。…~요다죠까]\s*[\"')”]?$", out):         # 길이 제한에 걸려 끊겼으면 마지막 완성 문장까지만
            cut = [x for x in re.finditer(r"[.!?。…][\"')”]?(?=\s|$)", out)]
            out = out[:cut[-1].end()] if cut else ""
        ident = r"(저는|I'm|I am)\s*(the\s*)?AnyControl\s*(안내\s*챗봇|guide\s*chatbot)"          # 자기소개 문장만 AnyControl 을 말할 수 있다
        out = " ".join(s for s in re.split(r"(?<=[.!?。…])\s+", out) if not re.search(r"anycontrol|애니\s*컨트롤", s, re.I) or re.search(ident, s, re.I)).strip()
        if lang == "ko":
            out = re.sub(r"^(그럼에도\s*불구하고|그렇다면|그러면|그럼)[,\s]+", "", out).strip()      # 질문에 이어 붙는 어색한 접속사로 시작하는 답
        blk = self.kb.policy.get("chat_output_block")
        if blk and re.search(blk, out, re.I):                                 # 잡담 답이 프로젝트 사실(기능·성능·가격·보안 …)을 말하기 시작하면 버린다 — 그건 카드의 일이다
            return None
        plain = re.sub(r"AnyControl|AWS|AI|Innovators Challenge", "", out)           # 정체성 소개에 쓰는 고유명은 허용
        has_hangul = re.search(r"[가-힣]", out) is not None
        if re.search(r"[぀-ヿ一-鿿]", out):                       # 일본어·한자가 섞인 답은 버린다
            return None
        if not out or len(out) > 320 or (lang == "ko") != has_hangul or banned_hits(out, self.kb.policy) \
                or (lang == "ko" and re.search(r"[A-Za-z]{3,}", plain)) \
                or re.search(r"qwen|alibaba|큐웬|알리바바|openai|chatgpt|gpt|anthropic|claude|https?://|www\.|\d{2,4}[- ]\d{3,4}[- ]\d{4}", out, re.I):
            return None                                                      # 프로젝트 사실을 지어내거나 모델 이름·연락처·링크를 말하면 버린다
        nq = _norm(raw)
        if len(nq) >= 4 and _norm(out).startswith(nq):                        # 질문을 그대로 따라 읽기만 한 답
            return None
        if not re.search(r"안녕|hello|hi\b|hey|반가|처음", raw, re.I) and re.match(r"\s*(안녕하세요|안녕!|hello|hi\b|hey)", out, re.I):       # 인사가 아닌데 인사로 시작
            return None
        if re.search(r"(대화|답변|이야기|도와)[^.!?]{0,8}(할\s*수\s*없|못\s*해|어렵습니다)|can'?t (chat|talk|help)|cannot (chat|talk)|(여러분|everyone)", out, re.I):
            return None                                                      # 대화 자체를 못 한다는 엉뚱한 사과, 방문객 한 명에게 '여러분'
        if re.search(r"(AI|인공지능)(라서|이라서|이기\s*때문에|여서)[^.!?]{0,24}(없|못|어렵|수\s*없)|(노력|도와드리|최선을\s*다하)겠습니다|I (will|shall) (try|do my best)|(as an AI|since I am an AI)[^.!?]{0,40}(cannot|can\x27t|unable)", out, re.I):
            return None                                                      # "AI라서 못 해요" 식의 엉뚱한 사과·다짐 (공감·되묻기로 이어 가야 한다)
        quote_open, quote_close = "'\"“‘『「《", "'\"”’』」》"
        if not re.search(r"농담|웃긴|개그|joke|funny|riddle|수수께끼", raw, re.I) \
                and re.search("[" + quote_open + "][^" + quote_open + quote_close + "]{2,40}[" + quote_close + "]", out) \
                and not re.search("^\\s*[" + quote_open + "]?(안녕|네|아니|맞|좋|감사|고마)", out):
            return None                                                      # 작품·책·노래 제목을 따옴표로 지어내는 답 (농담이 아니면 버린다)
        for _q, prev_a in (hist or [])[-2:]:
            if len(out) >= 12 and _norm(out)[:18] == _norm(str(prev_a))[:18]:
                return None                                                  # 바로 앞 답을 되풀이
        words = re.findall(r"[가-힣A-Za-z]{2,}", out)
        if len(words) >= 6 and len(set(words)) <= len(words) * 0.55:           # 같은 말을 되풀이
            return None
        return out

    def _rag(self, res: dict, q: str, lang: str, hits: list, prev: str) -> dict:
        """RAG: 찾은 카드(+가까운 카드 최대 2장)만 근거로 Qwen 이 질문에 맞게 답을 정리한다.
        검사(숫자·금지 표현·언어·근거 단어)를 통과하지 못하거나 시간이 넘으면 카드 원문을 그대로 쓴다."""
        card = res.get("card")
        cfg = self.cfg
        if not card or not cfg.get("llm_compose") or res.get("via") not in cfg["rag_vias"]:
            return res
        llm = self.llm
        if llm is None or not getattr(llm, "enabled", False) or not getattr(llm, "rag_ok", False):
            return res
        primary = self.kb.by_id.get(card["id"])
        if primary is None or primary["id"] in self.kb.policy.get("rag_exclude", []) or primary.get("allow_banned") or primary["status"] == "not_validated":
            return res                                    # 개인정보 규칙·정직성 카드는 원문 그대로
        texts = [primary["a"][lang]]                      # 카드 한 장만 근거로 쓴다 (여러 장을 주면 서로 다른 카드 내용이 섞인다)
        try:
            out = llm.compose(q, lang, texts, prev, timeout=float(cfg["rag_timeout_s"]))
        except Exception:
            return res
        out = re.sub(r"^\s*(답변|답|Answer)\s*[:：]\s*", "", (out or "").strip())
        ok, _why = verify_output(out, texts, lang, self.kb.policy, q, float(cfg["rag_grounded"]))
        if not ok or re.search(r"자료에\s*없|Not covered", out) or not _sentences_grounded(out, texts[0], q, float(cfg["rag_sentence_grounded"])):
            return res
        if hasattr(llm, "supports"):                      # 마지막 확인: 모델에게 "이 답이 자료와 일치하나요?"를 한 번 더 묻는다
            try:
                if llm.supports(texts[0], out, q, lang) < float(cfg["rag_support_score"]):
                    return res
            except Exception:
                return res
        res["source_answer"] = res["answer"]
        res["answer"] = out
        res["mode"] = "llm"
        return res

    def _rel(self, card: dict, lang: str, exclude: list[dict]) -> list[dict]:
        seen = {e["id"] for e in exclude}
        hid = set(self.kb.policy.get("menu_hidden", []))
        return [self._brief(self.kb.by_id[r], lang) for r in card.get("related", []) if r in self.kb.by_id and r not in seen and r not in hid][:3]

    def _brief(self, c: dict, lang: str) -> dict:
        return {"id": c["id"], "cat": c["cat"], "q": c["q"][lang][0], "status": c["status"]}

    def _full(self, c: dict, lang: str) -> dict:
        return {"id": c["id"], "cat": c["cat"], "q": c["q"][lang][0], "status": c["status"], "src": c.get("src", []),
                "a": c["a"][lang]}


def _sentences_grounded(out: str, card_text: str, question: str, min_ratio: float) -> bool:
    """답의 문장마다 내용 단어가 카드·질문에 충분히 있는지 본다 (한 문장이라도 근거가 약하면 거절)."""
    src = set(tokenize(card_text)) | set(tokenize(question))
    for sent in re.split(r"(?<=[.!?。])\s+|\n+", out.strip()):
        toks = [w for w in tokenize(sent) if len(w) > 1]
        if len(toks) >= 3 and sum(1 for w in toks if w in src) / len(toks) < min_ratio:
            return False
    return True


def _norm(text: str) -> str:
    """대소문자·공백·문장부호를 없앤 비교용 문자열 (질문이 카드의 질문과 같은지 볼 때 쓴다)"""
    return re.sub(r"[\s\.,!?？！。~'\"“”‘’()（）\[\]·]+", "", text).lower()


def _m(msg: dict, key: str, lang: str) -> str:
    return msg.get(key, {}).get(lang, "")


def verify_output(text: str, card_texts: list[str], lang: str, policy: dict, question: str = "", min_grounded: float = 0.0) -> tuple[bool, str]:
    """LLM 출력 검사: 비어 있지 않고, 너무 길지 않고, 언어가 맞고, 금지 표현이 없고, 카드에 없는 숫자를 지어내지 않았나."""
    t = (text or "").strip()
    if not t:
        return False, "empty"
    if len(t) > 900:
        return False, "too long"
    has_hangul = re.search(r"[가-힣]", t) is not None
    if lang == "ko" and not has_hangul:
        return False, "language"
    if lang == "en" and has_hangul:
        return False, "language"
    if banned_hits(t, policy):
        return False, "banned"
    allowed = set()
    for c in card_texts:
        allowed |= numbers_in(c)
    extra = {n for n in numbers_in(t) if n not in allowed and not (len(n) == 1 and n.isdigit())}
    if extra:
        return False, f"numbers {sorted(extra)}"
    if min_grounded > 0:                                   # 답에 쓴 내용 단어가 카드·질문에 실제로 있어야 한다 (없는 설명을 덧붙이지 못하게)
        src = set()
        for c in card_texts + [question]:
            src |= set(tokenize(c))
        toks = [w for w in tokenize(t) if len(w) > 1]
        if toks and sum(1 for w in toks if w in src) / len(toks) < min_grounded:
            return False, "ungrounded"
    return True, "ok"
