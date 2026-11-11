"""표준 라이브러리 unittest. 실행: python3 -m unittest discover -s tests -v"""
from __future__ import annotations
import json
import re
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.engine import Engine, verify_output  # noqa: E402
from bot.kb import banned_hits, load_kb, validate_kb  # noqa: E402
from bot.server import App, make_handler  # noqa: E402
from bot.textutil import detect_lang, numbers_in, tokenize  # noqa: E402

KB = load_kb()
ENG = Engine(KB)
_EQ: dict = {}
for _g in json.loads((Path(__file__).resolve().parents[1] / "eval" / "equiv.json").read_text(encoding="utf8"))["groups"]:
    for _a in _g:
        _EQ.setdefault(_a, set()).update(_g)


def accepted(expect):
    """기대 카드 + 같은 질문에 함께 정답이 될 수 있는 카드(eval/equiv.json)"""
    out = set(expect)
    for e in expect:
        out |= _EQ.get(e, set())
    return out


class TextUtil(unittest.TestCase):
    def test_detect_lang(self):
        self.assertEqual(detect_lang("펜 접촉 판정"), "ko")
        self.assertEqual(detect_lang("How does it work"), "en")
        self.assertEqual(detect_lang("?", "en"), "en")

    def test_korean_endings_are_stripped(self):
        self.assertIn("추적", tokenize("추적을"))
        self.assertNotIn("어요", tokenize("만들었어요"))

    def test_english_stopwords_and_stem(self):
        self.assertEqual(tokenize("What is the tracking?"), ["track"])

    def test_numbers(self):
        self.assertEqual(numbers_in("p95 약 13ms, 0.890, 1,426"), {"95", "13", "0.890", "0.89", "1426"})


class KnowledgeBase(unittest.TestCase):
    def test_validates_without_errors(self):
        errors, _ = validate_kb(KB)
        self.assertEqual(errors, [])

    def test_enough_cards(self):
        self.assertGreaterEqual(len(KB.cards), 100)

    def test_every_card_has_both_languages_and_source(self):
        for c in KB.cards:
            for lang in ("ko", "en"):
                self.assertTrue(c["q"][lang] and c["a"][lang].strip(), c["id"])
            self.assertTrue(c.get("src"), c["id"])

    def test_banned_phrases_detected(self):
        self.assertTrue(banned_hits("지연이 없습니다", KB.policy))
        self.assertTrue(banned_hits("It works perfectly", KB.policy))
        self.assertFalse(banned_hits("지연이 있습니다", KB.policy))


class EngineBehaviour(unittest.TestCase):
    def test_direct_answer(self):
        r = ENG.ask("펜이 책상에 닿은 걸 어떻게 알아요?")
        self.assertIn(r["kind"], ("answer", "related"))
        self.assertEqual(r["card"]["id"], "i-pen-contact")

    def test_english_question_gets_english_answer(self):
        r = ENG.ask("Is my camera video sent to a server?", "en")
        self.assertEqual(r["lang"], "en")
        self.assertNotRegex(r["answer"], r"[가-힣]")

    def test_off_topic_is_none(self):
        for q in ("오늘 점심 뭐 먹을까요", "What is the capital of France?", "비트코인 가격 알려줘"):
            self.assertEqual(ENG.ask(q)["kind"], "none", q)

    def test_none_has_no_answer_card(self):
        self.assertNotIn("card", ENG.ask("파이썬으로 퀵정렬 짜줘"))

    def test_overclaim_questions_get_honest_cards(self):
        self.assertEqual(ENG.ask("무지연인가요?")["card"]["id"], "i-latency-honest")
        self.assertEqual(ENG.ask("정확도가 100%인가요?")["card"]["id"], "i-accuracy-honest")

    def test_empty_and_greeting(self):
        self.assertEqual(ENG.ask("")["kind"], "empty")
        self.assertEqual(ENG.ask("안녕하세요")["kind"], "greeting")

    def test_what_is_this_intent(self):
        self.assertEqual(ENG.ask("이게 뭐야?")["card"]["id"], "g-what-is")

    def test_long_query_is_truncated_not_crashing(self):
        self.assertIn(ENG.ask("추적 " * 2000)["kind"], ("answer", "related", "none"))

    def test_eval_set_quality(self):
        items = json.loads((Path(__file__).resolve().parents[1] / "eval" / "questions.json").read_text(encoding="utf8"))
        wrong_direct = 0
        for it in items:
            r = ENG.ask(it["q"], it.get("lang", "ko"))
            if it.get("none"):
                self.assertEqual(r["kind"], "none", it["q"])
            elif r["kind"] == "answer" and r["card"]["id"] not in accepted(it["expect"]):
                wrong_direct += 1
        self.assertLessEqual(wrong_direct, 0.05 * len(items))   # 목표: 자신 있게 틀린 답 5% 이하 (실제는 거의 0)


class QualityGuards(unittest.TestCase):
    """이번 개선에서 정한 약속들을 지키는지 계속 확인한다."""

    def test_every_card_question_answers_directly(self):
        """카드에 적힌 질문(한국어·영어 모두)을 그대로 물으면 반드시 그 카드의 답이 바로 나와야 한다."""
        bad = []
        for c in KB.cards:
            for lang in ("ko", "en"):
                for q in c["q"][lang]:
                    r = ENG.ask(q, lang)
                    if r["kind"] != "answer":
                        bad.append((c["id"], lang, q, r["kind"]))
        self.assertEqual(bad, [])

    def test_english_answers_have_no_korean_except_names(self):
        import re
        for c in KB.cards:
            t = re.sub(r"\([^)]*[가-힣][^)]*\)", "", c["a"]["en"])      # (아무거나) 처럼 괄호 안의 한글 이름은 허용
            self.assertIsNone(re.search(r"[가-힣]", t), c["id"])
            for q in c["q"]["en"]:
                self.assertIsNone(re.search(r"[가-힣]", q), (c["id"], q))

    def test_every_card_has_english_question_variants(self):
        for c in KB.cards:
            self.assertGreaterEqual(len(c["q"]["en"]), 2, c["id"])

    def test_presenter_and_kimsam_questions_get_the_department_answer(self):
        """발표자·김삼·만든 사람 질문은 '고려대학교 전기전자공학부 재학 중'이라고만 답한다. 그 밖의 개인정보는 말하지 않는다."""
        asks = [("김삼이 누구예요?", "ko"), ("김삼 나이가 어떻게 돼요", "ko"), ("발표자는 누구예요", "ko"), ("발표하는 분 학생이에요", "ko"),
                ("이거 누가 만들었어요", "ko"), ("만든 사람이 누구예요", "ko"), ("Who is Kim Sam?", "en"), ("Who is the presenter?", "en"), ("Who made this?", "en")]
        for q, lang in asks:
            r = ENG.ask(q, lang)
            self.assertEqual(r["card"]["id"], "w-presenter-who", q)
            self.assertTrue("전기전자공학부" in r["answer"] or "Electrical Engineering" in r["answer"], q)
            if r["card"]["id"] == "w-presenter-who":
                self.assertTrue("김삼이에요" in r["answer"] or "is Kim Sam" in r["answer"], q)
            self.assertNotRegex(r["answer"], r"\d{2,4}[- ]\d{3,4}[- ]\d{4}|@|살\b", q)

    def test_where_did_they_go_questions_get_the_stepped_away_answer(self):
        asks = [("발표자는 어디 갔어요", "ko"), ("발표하는 분 어디 갔어요", "ko"), ("소개하는 사람 어디 갔어요", "ko"), ("김삼 어디 있어요", "ko"),
                ("담당자 언제 와요", "ko"), ("아무도 없네요", "ko"), ("Where is the presenter?", "en"), ("Where did Kim Sam go?", "en")]
        for q, lang in asks:
            r = ENG.ask(q, lang)
            self.assertEqual(r["card"]["id"], "w-presenter-away", q)
            self.assertTrue("중간고사" in r["answer"] or "midterm" in r["answer"], q)
            self.assertTrue("김삼" in r["answer"] or "Kim Sam" in r["answer"], q)

    def test_how_to_use_questions_point_to_the_guide_button(self):
        for q, lang in (("어떻게 써?", "ko"), ("사용법 알려줘", "ko"), ("이거 어떻게 사용해요", "ko"), ("How do I use it?", "en")):
            r = ENG.ask(q, lang)
            self.assertEqual(r["card"]["id"], "w-how-to-use", q)
            self.assertTrue("안내" in r["answer"] or "Guide" in r["answer"], q)
        self.assertEqual(ENG.ask("챗봇은 어떻게 써요")["card"]["id"], "w-chat-how-use")      # 챗봇 사용법은 따로

    def test_idle_fade_returns_home_after_60_seconds_and_cancels_on_input(self):
        js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf8")
        self.assertIn("IDLE_MS = 45000", js)
        for ev in ("mousemove", "keydown", "click"):
            self.assertIn('"%s"' % ev, js)
        self.assertIn("stopFade", js)

    def test_hidden_cards_are_not_shown_as_buttons_but_team_answers_say_one_person(self):
        hid = set(KB.policy["menu_hidden"])
        for lang in ("ko", "en"):
            for cat in [None] + [c["id"] for c in KB.cats]:
                self.assertFalse(hid & {x["id"] for x in ENG.suggestions(lang, cat, 40)}, (lang, cat))
        for q, lang in (("팀 소개해 주세요", "ko"), ("팀은 몇 명이에요", "ko"), ("How many people are on the team?", "en")):
            a = ENG.ask(q, lang)["answer"]
            self.assertTrue("1명" in a or "1 listed member" in a, q)
        self.assertEqual(ENG.ask("김삼은 누구예요?")["card"]["id"], "w-presenter-who")      # 직접 물으면 여전히 답한다

    def test_false_premise_numbers_are_corrected_not_confirmed(self):
        r = ENG.ask("99% 정확하고 지연이 0ms라던데 맞죠?")
        self.assertEqual(r["card"]["id"], "w-false-claims")
        self.assertTrue(r["answer"].startswith("아니요"))

    def test_several_questions_in_one_message_are_each_answered(self):
        r = ENG.ask("1) 설치 파일은 어디서 받아요? 2) 비용은요? 3) Windows도 되나요? 4) 영상을 저장하나요? 5) 멈추는 키는요? 각 번호별로 답해 주세요.")
        self.assertEqual(r["via"], "multi")
        self.assertEqual(r["parts"], 5)
        for n in range(1, 6):
            self.assertIn("**%d." % n, r["answer"])
        r = ENG.ask("애니컨트롤 머에여?? 돈 내야댐? ㅋㅋ")
        self.assertEqual(r["via"], "multi")
        self.assertIn("AnyControl은", r["answer"])
        self.assertIn("가격", r["answer"])

    def test_dangling_followup_asks_what_is_meant(self):
        r = ENG.ask("그건 왜요?")
        self.assertEqual(r["via"], "clarify")

    def test_independent_question_is_not_dragged_to_the_previous_topic(self):
        r = ENG.ask("손으로 완전히 가렸다가 다른 위치에 놓아도 다시 찾아요?", "ko", ["v-transparent-shiny"], "투명한 유리컵도 돼요")
        self.assertNotEqual(r["card"]["id"], "v-transparent-shiny")

    def test_project_questions_about_games_and_props_never_become_small_talk(self):
        e, llm = FreeChat().engine("가능할 것 같아요.") if False else (None, None)
        class L(FakeLLM):
            rag_ok = True
            def chat(self, *a, **k): return "가능할 것 같아요."
        eng = Engine(KB, L(None)); eng.cfg["free_chat"] = True
        for q in ("게임에서 방향키와 점프를 컵 두 개에 각각 연결할 수 있나요?", "지우개로 마인크래프트 할 수 있어요?"):
            self.assertNotEqual(eng.ask(q).get("via"), "free_chat", q)

    def test_non_korean_non_english_questions_are_translated_with_qwen_or_politely_declined(self):
        class T(FakeLLM):
            rag_ok = True
            def translate(self, text, target, timeout=10.0, sample="", src=""):
                return "What is AnyControl?" if target == "English" else "AnyControlは、カメラ1台で…"
        eng = Engine(KB, T(None))
        r = eng.ask("AnyControlとは何ですか？", "ko")
        self.assertEqual(r["via"], "translated")
        self.assertTrue(r["answer"].startswith("AnyControlは"))
        self.assertIn("AnyControl turns one camera", r["source_answer"])
        self.assertTrue(r["note"])
        r = Engine(KB).ask("AnyControlとは何ですか？", "ko")                       # Qwen 이 없으면 정중한 안내
        self.assertEqual(r["via"], "unsupported_lang")
        for q in ("¿Qué es AnyControl? ¿Funciona sin internet?", "Bonjour ! Pouvez-vous expliquer AnyControl en français ?", "ما هو AnyControl؟", "AnyControl是什么？"):
            self.assertEqual(Engine(KB).ask(q)["via"], "unsupported_lang", q)
        self.assertNotEqual(Engine(KB).ask("What is AnyControl?")["via"], "unsupported_lang")

    def test_assistant_answers_with_japanese_or_hanzi_are_dropped(self):
        class L(FakeLLM):
            rag_ok = True
            def chat(self, *a, **k): return "지우개については 모릅니다."
        eng = Engine(KB, L(None)); eng.cfg["free_chat"] = True
        self.assertNotEqual(eng.ask("오늘 학교에서 발표했는데 떨렸어").get("via"), "free_chat")

    def test_paper_questions_are_not_answered_as_if_a_paper_existed(self):
        for q, lang in (("논문도 있어요?", "ko"), ("Is there a paper?", "en")):
            r = ENG.ask(q, lang)
            self.assertEqual(r["kind"], "none", q)
            self.assertNotIn("논문", r["answer"])
            self.assertNotIn("paper", r["answer"].lower())

    def test_macos_appledouble_files_in_the_cards_folder_do_not_break_loading(self):
        """macOS 에서 압축·복사하면 생기는 '._이름.json'(UTF-8 이 아닌 바이너리)이 있어도 Windows 에서 시작해야 한다."""
        import shutil, tempfile
        from bot.kb import load_kb
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(Path(__file__).resolve().parents[1] / "kb", root / "kb", ignore=shutil.ignore_patterns("snapshot", "cards_archive"))
            (root / "kb" / "cards" / "._g1_intro.json").write_bytes(b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        \x00\x02" + b"\xb0\xa1" * 20)
            (root / "kb" / "cards" / ".hidden.json").write_bytes(b"\xff\xfe")
            self.assertEqual(len(load_kb(root).cards), len(KB.cards))
            (root / "kb" / "cards" / "v99_broken.json").write_bytes(b"[\xb0\xa1]")
            with self.assertRaises(RuntimeError) as cm:
                load_kb(root)
            self.assertIn("v99_broken.json", str(cm.exception))

    def test_missing_visual_cpp_runtime_is_detected_instead_of_showing_system_error_dialogs(self):
        import os, sys, tempfile
        from unittest import mock
        from bot import runtime
        self.assertEqual(runtime.missing_windows_runtime(None) if not sys.platform.startswith("win") else [], [])
        with tempfile.TemporaryDirectory() as td, mock.patch.object(sys, "platform", "win32"), mock.patch.dict(os.environ, {"SystemRoot": td}):
            srv = Path(td) / "bin" / "llama-server.exe"
            srv.parent.mkdir(parents=True)
            (Path(td) / "System32").mkdir()
            self.assertEqual(runtime.missing_windows_runtime(srv), list(runtime.VC_DLLS))
            (Path(td) / "System32" / "vcruntime140.dll").write_bytes(b"x")
            self.assertEqual(runtime.missing_windows_runtime(srv), ["msvcp140.dll"])
            (srv.parent / "msvcp140.dll").write_bytes(b"x")                       # llama-server.exe 옆에 두어도 인정
            self.assertEqual(runtime.missing_windows_runtime(srv), [])

    def test_windows_runtime_dlls_and_font_ship_with_the_folder(self):
        root = Path(__file__).resolve().parents[1]
        for n in ("vcruntime140.dll", "msvcp140.dll"):
            self.assertTrue((root / "bin" / "windows-x64" / n).is_file(), n)
        self.assertTrue((root / "web" / "fonts" / "PretendardVariable.woff2").is_file())

    def test_chatbot_how_has_no_tool_names(self):
        for lang in ("ko", "en"):
            r = ENG.ask("이 챗봇은 어떻게 만들었어요?" if lang == "ko" else "How was this chatbot made?", lang)
            self.assertNotIn("Claude", r["answer"])

    def test_card_button_shows_followup_questions(self):
        self.assertTrue(ENG.card("g-what-is", "ko")["more"])

    def test_disclaimer_is_configured_in_both_languages(self):
        for lang in ("ko", "en"):
            self.assertTrue(KB.policy["ui"][lang]["disclaimer"].strip())
        self.assertIn("틀릴 수", KB.policy["ui"]["ko"]["disclaimer"])
        web = Path(__file__).resolve().parents[1] / "web"
        self.assertIn('id="disclaimer"', (web / "index.html").read_text(encoding="utf8"))
        self.assertIn('$("disclaimer").textContent', (web / "app.js").read_text(encoding="utf8"))

    def test_korean_is_the_default_language(self):
        js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf8")
        self.assertIn('lang: "ko"', js)
        self.assertNotIn("navigator.language", js)

    def test_new_visitor_eval_set(self):
        """카드 문구와 다르게 쓴 새 질문 세트(eval/new_v.json): 상위 3개 안에 정답, 자신 있게 틀림 5% 이하."""
        items = json.loads((Path(__file__).resolve().parents[1] / "eval" / "new_v.json").read_text(encoding="utf8"))
        equiv_raw = json.loads((Path(__file__).resolve().parents[1] / "eval" / "equiv.json").read_text(encoding="utf8"))["groups"]
        eq = {}
        for g in equiv_raw:
            for a in g:
                eq.setdefault(a, set()).update(g)
        wrong = miss = 0
        for it in items:
            exp = set(it["expect"])
            for e in list(exp):
                exp |= eq.get(e, set())
            r = ENG.ask(it["q"], it["lang"])
            top3 = [KB.cards[i]["id"] for i, _, _ in ENG.card_index.search(it["q"], 3)]
            if r.get("card"):
                top3 = [r["card"]["id"]] + top3
            if not exp & set(top3[:3]):
                miss += 1
            if r["kind"] == "answer" and r["card"]["id"] not in exp:
                wrong += 1
        self.assertLessEqual(miss, 0.05 * len(items))
        self.assertLessEqual(wrong, 0.05 * len(items))

    def test_sync_registry_points_to_existing_cards(self):
        """kb/facts.json, kb/topic_map.json 이 가리키는 카드가 실제로 있어야 한다 (카드를 지우거나 이름을 바꾸면 여기서 알게 된다)."""
        root = Path(__file__).resolve().parents[1] / "kb"
        facts = json.loads((root / "facts.json").read_text(encoding="utf8"))["facts"]
        tmap = json.loads((root / "topic_map.json").read_text(encoding="utf8"))["map"]
        ids = [f["id"] for f in facts]
        self.assertEqual(len(ids), len(set(ids)))
        for cid in [c for f in facts for c in f["cards"]] + [c for t in tmap for c in t["cards"] if c != "*"]:
            self.assertIn(cid, KB.by_id, cid)

    def test_short_stopword_only_questions(self):
        self.assertEqual(ENG.ask("Who are you?", "en")["card"]["id"], "v-who-are-you")
        self.assertEqual(ENG.ask("얼마예요?")["card"]["id"], "g-price")

    def test_hybrid_is_not_a_greeting(self):
        self.assertNotEqual(ENG.ask("하이브리드나 손 클릭은 잘 되나요?")["kind"], "greeting")


class ConversationBehaviour(unittest.TestCase):
    """자연어 대응 1단계(규칙)와 2단계(로컬 LLM 점수, 여기서는 가짜 LLM 으로 논리만 시험)."""

    def test_vague_colloquial_questions_get_the_generic_cards(self):
        cases = [("이게 왜 좋음?", "v-top-strengths"), ("왜 필요해요?", "g-why-made"), ("단점은?", "v-top-weakness"), ("뭐가 달라?", "g-vs-others"),
                 ("어디에 쓰는거임", "g-who-for"), ("이거 얼마임", "g-price"), ("위험하진 않음?", "g-safe-real")]
        for q, cid in cases:
            self.assertEqual(ENG.ask(q)["card"]["id"], cid, q)
        self.assertEqual(ENG.ask("Why is it needed?", "en")["card"]["id"], "g-why-made")
        self.assertEqual(ENG.ask("what's the catch?", "en")["card"]["id"], "v-top-weakness")

    def test_generic_intent_does_not_steal_topic_questions(self):
        from bot.nlu import generic_intent
        self.assertIsNone(generic_intent("펜이 왜 좋아요", "ko"))
        self.assertNotEqual(ENG.ask("필요한 사양은?")["card"]["id"], "g-why-made")

    def test_follow_up_uses_previous_answer(self):
        self.assertEqual(ENG.ask("그럼 얼마예요?", "ko", ["g-what-is"], "AnyControl이 뭐예요?")["card"]["id"], "g-price")
        self.assertEqual(ENG.ask("그럼 단점은?", "ko", ["g-pen-mode"], "펜으로 그림을 그릴 수 있나요?")["card"]["id"], "v-top-weakness")
        self.assertEqual(ENG.ask("and the price?", "en", ["g-what-is"], "What is AnyControl?")["card"]["id"], "g-price")
        self.assertEqual(ENG.ask("그럼 인터넷 필요해?", "ko", ["g-privacy-server"], "개인정보는 안전한가요")["card"]["id"] in ("h-offline", "h-internet-install", "g-ondevice"), True)

    def test_bad_context_is_ignored_safely(self):
        r = ENG.ask("가격이 얼마예요?", "ko", ["no-such-card", 5, None], "x" * 500)   # type: ignore[list-item]
        self.assertIn(r["card"]["id"], accepted(["g-price"]))

    def test_small_talk_is_short_and_invented_nothing(self):
        for q, lang in [("고마워요", "ko"), ("ㅋㅋㅋ", "ko"), ("thanks!", "en"), ("잘 가", "ko"), ("심심해", "ko"), ("무슨 말이야 이해 안 돼", "ko")]:
            r = ENG.ask(q, lang)
            self.assertIn(r["kind"], ("chat", "greeting"), q)
            self.assertNotIn("card", r)
        self.assertEqual(ENG.ask("바이브 코딩이에요?")["kind"], "answer")      # 카드 질문이 잡담 규칙보다 먼저

    def test_out_of_scope_requests_are_refused_not_matched(self):
        for q, lang in [("파이썬 코드 짜줘", "ko"), ("내일 날씨 어때요", "ko"), ("비트코인 가격 알려줘", "ko"), ("Write me a poem about spring", "en"),
                        ("What is the stock price of Amazon?", "en")]:
            r = ENG.ask(q, lang)
            self.assertEqual(r["kind"], "none", q)
            self.assertNotIn("card", r)

    def test_colloquial_normalization(self):
        from bot.nlu import normalize
        self.assertEqual(normalize("이게 왜 좋음?"), "이게 왜 좋아요?")
        self.assertEqual(normalize("ㅋㅋ 이거 얼마임"), "이거 얼마예요")
        self.assertEqual(normalize("윈도우도 됨?"), "윈도우도 되나요?")

    def test_every_new_message_exists_in_both_languages(self):
        for key in ("understood", "related", "near", "none"):
            for lang in ("ko", "en"):
                self.assertTrue(KB.policy["messages"][key][lang].strip(), (key, lang))
        for st in KB.policy["smalltalk"]:
            self.assertTrue(st["ko"].strip() and st["en"].strip())
        self.assertTrue(KB.policy["out_of_scope"]["ko"] and KB.policy["out_of_scope"]["en"])


class FakeLLM:
    """llama-server 없이 2단계 논리를 시험하기 위한 가짜: 후보 중 target 문구에는 높은 점수, 나머지는 낮은 점수를 준다."""
    enabled = True
    pair_s = 0.05

    def __init__(self, target_card: str | None, high: float = 6.0, low: float = -5.0) -> None:
        self.target, self.high, self.low, self.calls = target_card, high, low, 0

    def rank(self, q, lang, topic, candidates, budget_s=6.0):
        self.calls += 1
        tq = KB.by_id[self.target]["q"][lang][0] if self.target else None
        return [self.high if c == tq else self.low for c in candidates]


class LLMRouting(unittest.TestCase):
    def test_llm_is_not_called_when_rules_already_answer(self):
        llm = FakeLLM("g-price")
        eng = Engine(KB, llm)
        self.assertEqual(eng.ask("AnyControl이 뭐예요?")["card"]["id"], "g-what-is")
        self.assertEqual(llm.calls, 0)

    def test_external_device_prices_never_route_to_app_price(self):
        llm = FakeLLM("g-price", high=20.0)
        eng = Engine(KB, llm)
        for q in ("아이폰 17 가격이 얼마인가요?", "What does a Galaxy S25 cost?", "MacBook pricing please"):
            r = eng.ask(q)
            self.assertEqual(r["kind"], "none", q)
            self.assertEqual(r["via"], "external_device_price", q)
        self.assertEqual(llm.calls, 0)
        self.assertIn(eng.ask("AnyControl 가격은 얼마인가요?")["card"]["id"], ("g-price", "h-free"))
        self.assertNotEqual(eng.ask("Can I use an iPhone as a camera?").get("via"), "external_device_price")

    def test_confident_llm_pick_answers_with_understood_note(self):
        eng = Engine(KB, FakeLLM("v-tools-used", high=9.0))
        r = eng.ask("개발할 때 어떤 툴 썼는지 궁금해서 그러는데 말야")
        self.assertEqual(r["via"], "llm")
        self.assertEqual(r["card"]["id"], "v-tools-used")
        self.assertIn(KB.by_id["v-tools-used"]["q"]["ko"][0], r["note"])          # "이렇게 이해했어요: …" 로 어떻게 이해했는지 알려 줌

    def test_unsure_llm_only_suggests(self):
        eng = Engine(KB, FakeLLM("v-tools-used", high=2.0))
        r = eng.ask("개발할 때 어떤 툴 썼는지 궁금해서 그러는데 말야")
        self.assertNotEqual(r.get("via"), "llm")
        self.assertNotIn("card", r) if r["kind"] == "none" else None

    def test_off_topic_words_block_direct_answer(self):
        eng = Engine(KB, FakeLLM("g-price", high=20.0))
        r = eng.ask("아이폰 일곱 십육 프로맥스 시세 알려줘")
        self.assertNotEqual(r.get("via"), "llm")

    def test_llm_failure_falls_back_to_rules(self):
        class Boom(FakeLLM):
            def rank(self, *a, **k):
                raise RuntimeError("down")
        eng = Engine(KB, Boom("g-price"))
        self.assertIn(eng.ask("뭘 쓰는 건지 모르겠다")["kind"], ("answer", "related", "none"))

    def test_disabled_llm_is_ignored(self):
        llm = FakeLLM("g-price")
        llm.enabled = False
        Engine(KB, llm).ask("뭘 쓰는 건지 모르겠다")
        self.assertEqual(llm.calls, 0)

    def test_held_out_conversation_set_quality(self):
        """표현을 맞춰 보지 않고 쓴 대화 세트(eval/chat_heldout.json): LLM 없이도 아래 수준을 유지한다."""
        items = json.loads((Path(__file__).resolve().parents[1] / "eval" / "chat_heldout.json").read_text(encoding="utf8"))
        top3 = wrong = none_ok = n_pos = n_none = n_chat = chat_ok = 0
        for it in items:
            r = ENG.ask(it["q"], it["lang"], it.get("ctx"), it.get("prev", ""))
            if it.get("chat"):
                n_chat += 1; chat_ok += r["kind"] in ("chat", "greeting"); continue
            if it.get("none"):
                n_none += 1; none_ok += r["kind"] == "none"; continue
            n_pos += 1
            exp = accepted(it["expect"])
            ids = [r["card"]["id"]] if r.get("card") else []
            ids += [x["id"] for x in r.get("suggestions", [])] if r.get("near") else []
            ids += [KB.cards[i]["id"] for i, _, _ in ENG.card_index.search(it["q"], 3)]
            top3 += bool(exp & set(ids[:3]))
            wrong += r["kind"] == "answer" and r["card"]["id"] not in exp
        self.assertGreaterEqual(top3 / n_pos, 0.80)
        self.assertLessEqual(wrong / n_pos, 0.10)
        self.assertEqual(none_ok, n_none)
        self.assertEqual(chat_ok, n_chat)


class RagGuards(unittest.TestCase):
    """RAG(Qwen 이 카드를 정리해 답하는 기능)는 기본 꺼짐이고, 켜도 검사를 통과해야만 쓰이며, 김삼 카드는 절대 건드리지 않는다."""

    class FakeRag(FakeLLM):
        rag_ok = True

        def __init__(self, out, support=5.0):
            super().__init__(None)
            self.out, self.support = out, support

        def compose(self, q, lang, texts, history="", timeout=None):
            return self.out

        def supports(self, *a, **k):
            return self.support

    def engine(self, out, support=5.0, **cfg):
        e = Engine(KB, self.FakeRag(out, support))
        e.cfg["llm_compose"] = True
        e.cfg.update(cfg)
        return e

    def test_rag_is_off_by_default(self):
        self.assertFalse(Engine(KB).cfg["llm_compose"])
        e = Engine(KB, self.FakeRag("정리된 답이에요"))
        r = e.ask("가려지면 어떻게 되나요 궁금해요 알려줘")
        self.assertNotEqual(r.get("mode"), "llm")

    def test_good_rewrite_is_used_and_original_kept(self):
        card = KB.by_id["i-occlusion-return"]
        e = self.engine(card["a"]["ko"].split(".")[0] + ".")
        r = e.ask("가려지면 어케됨")
        if r.get("mode") == "llm":
            self.assertIn("source_answer", r)
            self.assertEqual(r["source_answer"], card["a"]["ko"])

    def test_invented_numbers_or_ungrounded_text_are_rejected(self):
        e = self.engine("약 999개의 물체를 동시에 추적하며 클라우드 서버에서 처리해요.")
        r = e.ask("가려지면 어케됨")
        self.assertNotEqual(r.get("mode"), "llm")

    def test_unsupported_answer_is_rejected_by_the_support_check(self):
        card = KB.by_id["i-occlusion-return"]
        e = self.engine(card["a"]["ko"].split(".")[0] + ".", support=-3.0)
        self.assertNotEqual(e.ask("가려지면 어케됨").get("mode"), "llm")

    def test_kimsam_cards_are_never_rewritten(self):
        e = self.engine("김삼은 서울에 사는 25살 학생이에요.")
        r = e.ask("김삼이 누구예요?")
        self.assertNotIn("25", r["answer"])
        self.assertNotEqual(r.get("mode"), "llm")


class FreeChat(unittest.TestCase):
    """잡담 모드: 분명한 잡담 주제에만, 카드 답과 구분해서, 안전 규칙을 먼저 지키며 동작한다."""

    class ChatLLM(FakeLLM):
        rag_ok = True

        def __init__(self, out="비빔밥은 어때요?"):
            super().__init__(None)
            self.out, self.chats = out, 0

        def chat(self, q, lang, timeout=None, persona="", hist=None):
            self.chats += 1
            self.last = {"q": q, "persona": persona, "hist": hist}
            return self.out

    def engine(self, out="비빔밥은 어때요?", on=True):
        llm = self.ChatLLM(out)
        e = Engine(KB, llm)
        e.cfg["free_chat"] = on
        return e, llm

    def test_off_by_default_in_engine(self):
        self.assertFalse(Engine(KB).cfg["free_chat"])
        r = Engine(KB, self.ChatLLM()).ask("내일 뭐 입지")
        self.assertEqual(r["kind"], "none")

    def test_small_talk_topic_gets_a_labelled_free_answer(self):
        e, llm = self.engine()
        r = e.ask("내일 뭐 입지")
        self.assertEqual((r["kind"], r["via"], r["mode"]), ("chat", "free_chat", "llm"))
        self.assertIn("자유롭게", r["note"])                       # 카드 답이 아니라는 표시
        self.assertEqual(llm.chats, 1)
        self.assertNotIn("card", r)

    def test_project_questions_never_go_to_free_chat(self):
        e, llm = self.engine()
        for q in ("AnyControl 가격은 얼마야", "이거 설치하다 막히면 어떡해", "펜으로 그림도 됨?", "김삼이 누구예요?"):
            self.assertNotEqual(e.ask(q).get("via"), "free_chat", q)
        self.assertEqual(llm.chats, 0)

    def test_realtime_questions_are_never_generated(self):
        e, llm = self.engine("오늘은 맑아요")
        r = e.ask("오늘 날씨 어때")
        self.assertEqual(r["via"], "free_chat_blocked")
        self.assertEqual(llm.chats, 0)
        self.assertIn("실시간", r["answer"])

    def test_sensitive_topics_are_refused_without_generation(self):
        e, llm = self.engine()
        for q in ("대통령이 누구야", "ㅅㅂ 짜증나"):
            self.assertEqual(e.ask(q)["via"], "free_chat_blocked", q)
        self.assertEqual(llm.chats, 0)

    def test_self_harm_gets_the_fixed_caring_message_even_when_chat_is_off(self):
        for on in (True, False):
            e, llm = self.engine(on=on)
            r = e.ask("요즘 너무 힘들어서 죽고 싶어")
            self.assertEqual(r["via"], "safety")
            self.assertIn("109", r["answer"])
            self.assertEqual(llm.chats, 0)

    def test_unsafe_generated_text_is_dropped(self):
        for bad in ("내일은 barbecue 어때요", "https://example.com 에 가 보세요", "x" * 400, ""):
            e, _ = self.engine(bad)
            self.assertNotEqual(e.ask("내일 뭐 입지").get("via"), "free_chat", bad)

    def test_everyday_talk_without_keywords_also_goes_to_the_assistant_with_its_persona(self):
        e, llm = self.engine("고생 많으셨어요. 푹 쉬세요.")
        r = e.ask("오늘 학교에서 발표했는데 떨렸어", "ko", hist=[["안녕하세요", "반가워요"]])
        self.assertEqual((r["kind"], r["via"]), ("chat", "free_chat"))
        self.assertIn("AnyControl 안내 챗봇", llm.last["persona"])            # 정체성이 항상 함께 전달된다
        self.assertEqual(llm.last["hist"], [("안녕하세요", "반가워요")])       # 앞 잡담을 이어서 대화
        llm.out = "I am an AI, but I enjoy a good tune."
        r = e.ask("Do you like music?", "en")
        self.assertEqual(r["via"], "free_chat")
        self.assertIn("AnyControl guide chatbot", llm.last["persona"])

    def test_project_questions_without_a_card_stay_honest_instead_of_chatting(self):
        e, llm = self.engine()
        for q in ("AnyControl 라이선스 비용이 얼마예요", "카메라 몇 개까지 연결돼요", "Does it support Linux gamepads?"):
            self.assertNotEqual(e.ask(q).get("via"), "free_chat", q)
        self.assertEqual(llm.chats, 0)

    def test_project_questions_that_miss_every_card_are_never_answered_by_the_assistant(self):
        e, llm = self.engine("네, 어두운 방에서도 잘 작동해요.")           # 잡담 모델이 지어낼 만한 문장
        for q in ("애들 교육용으로 쓰면 어때요", "영상이 유출될 일은 없나요", "코드는 공개대잇나여", "상품으로 팔수있나여", "어두운 방에서도 돼?", "업뎃은 어케 함", "does it spy on me", "who's the dev"):
            self.assertNotEqual(e.ask(q, "en" if q.isascii() else "ko").get("via"), "free_chat", q)
        self.assertEqual(llm.chats, 0)

    def test_assistant_output_that_states_project_facts_is_dropped(self):
        for bad in ("네, 카메라만 있으면 잘 작동해요.", "무료로 쓸 수 있어요.", "Yes, the code is public."):
            e, _ = self.engine(bad)
            r = e.ask("오늘 학교에서 발표했는데 떨렸어" if not bad.isascii() else "Do you like music?", "ko" if not bad.isascii() else "en")
            self.assertNotEqual(r.get("via"), "free_chat", bad)

    def test_answers_after_chatting_use_cards_again(self):
        e, llm = self.engine("그렇군요.")
        self.assertEqual(e.ask("오늘 학교에서 발표했는데 떨렸어")["via"], "free_chat")
        r = e.ask("가격이 얼마예요", "ko", hist=[["오늘 학교에서 발표했는데 떨렸어", "그렇군요."]])
        self.assertEqual(r["kind"], "answer")
        self.assertIn(r["card"]["id"], ("g-price", "h-free"))

    def test_ai_sentences_that_mention_the_project_are_removed(self):
        e, _ = self.engine("고생 많으셨어요. AnyControl은 발표에 아주 좋아요. 푹 쉬세요.")
        r = e.ask("오늘 학교에서 발표했는데 떨렸어")
        self.assertEqual(r["answer"], "고생 많으셨어요. 푹 쉬세요.")
        e, _ = self.engine("저는 AnyControl 안내 챗봇이에요. 반가워요.")
        self.assertIn("AnyControl 안내 챗봇", e.ask("오늘 학교에서 발표했는데 떨렸어").get("answer", ""))
        for bad in ("저는 Qwen이라는 모델이에요.", "저는 ChatGPT예요."):
            e, _ = self.engine(bad)
            self.assertNotEqual(e.ask("오늘 학교에서 발표했는데 떨렸어").get("via"), "free_chat", bad)

    def test_when_the_assistant_fails_the_visitor_gets_a_friendly_guide_not_a_cold_refusal(self):
        class Boom(self.ChatLLM):
            def chat(self, *a, **k):
                raise RuntimeError("down")
        e = Engine(KB, Boom()); e.cfg["free_chat"] = True
        r = e.ask("오늘 학교에서 발표했는데 떨렸어")
        self.assertEqual((r["kind"], r["via"]), ("none", "chat_fallback"))
        self.assertIn("안내 챗봇", r["answer"])

    def test_common_everyday_talk_gets_a_polished_reply_without_the_model(self):
        e, llm = self.engine()
        for q, lang in (("배고파", "ko"), ("시험 망쳤어", "ko"), ("나 오늘 생일이야", "ko"), ("I failed my exam", "en"), ("it's my birthday", "en")):
            r = e.ask(q, lang)
            self.assertEqual((r["kind"], r["via"]), ("chat", "chitchat"), q)
            self.assertEqual(bool(re.search(r"[가-힣]", r["answer"])), lang == "ko", q)
        self.assertEqual(llm.chats, 0)
        self.assertNotEqual(Engine(KB).ask("배고파").get("via"), "chitchat")            # 대화 모드가 꺼져 있으면 건드리지 않는다
        for q in ("설치가 힘들어요?", "ㅅㅂ 짜증나"):                                      # 프로젝트 질문·민감한 말은 가로채지 않는다
            self.assertNotEqual(e.ask(q).get("via"), "chitchat", q)

    def test_chat_keeps_going_when_the_visitor_answers_instead_of_hunting_for_a_card(self):
        e, llm = self.engine("면 요리 맛있죠! 따뜻한 국물이 좋으세요?")
        r = e.ask("면이 좋아요", "ko", hist=[["점심 뭐 먹지", "오늘은 면이 좋으세요, 밥이 좋으세요?"]])
        self.assertEqual((r["kind"], r["via"]), ("chat", "free_chat"))
        self.assertEqual(llm.last["hist"], [("점심 뭐 먹지", "오늘은 면이 좋으세요, 밥이 좋으세요?")])
        r = e.ask("가격이 얼마예요", "ko", hist=[["점심 뭐 먹지", "오늘은 면이 좋으세요, 밥이 좋으세요?"]])      # 프로젝트 질문이면 다시 카드로
        self.assertEqual(r["kind"], "answer")

    def test_chat_speed_is_checked_separately_from_slow_answer_polishing(self):
        class OnlyChat(self.ChatLLM):
            rag_ok = False
            chat_ok = True
        e = Engine(KB, OnlyChat()); e.cfg["free_chat"] = True
        self.assertEqual(e.ask("오늘 학교에서 발표했는데 떨렸어")["via"], "free_chat")
        OnlyChat.chat_ok = False
        self.assertNotEqual(e.ask("오늘 학교에서 발표했는데 떨렸어").get("via"), "free_chat")

    def test_made_up_titles_and_repeated_replies_are_dropped(self):
        e, _ = self.engine()
        self.assertIsNone(e._vet_chat("'시크릿 토끼'는 판타지 책이에요.", "책 추천해줘", "ko"))
        self.assertIsNone(e._vet_chat('How about "The Long Road Home"? It is lovely.', "recommend a movie", "en"))
        self.assertIsNone(e._vet_chat("오늘 정말 고생 많으셨어요. 푹 쉬세요.", "계속 힘들어", "ko", [("힘들어", "오늘 정말 고생 많으셨어요. 푹 쉬세요.")]))
        self.assertIsNone(e._vet_chat("죄송합니다. AI라서 직접 책을 추천하는 능력이 없네요.", "책 추천해줘", "ko"))
        self.assertTrue(e._vet_chat("컴퓨터가 \"창문 좀 닫아 주세요!\"라고 했어요.", "농담 해줘", "ko"))

    def test_llm_failure_falls_back_to_the_fixed_refusal(self):
        class Boom(self.ChatLLM):
            def chat(self, *a, **k):
                raise RuntimeError("down")
        e = Engine(KB, Boom())
        e.cfg["free_chat"] = True
        self.assertEqual(e.ask("내일 뭐 입지")["kind"], "none")


class ModelSelection(unittest.TestCase):
    def test_pinned_model_wins_over_alphabetical_order(self):
        from bot.runtime import find_model
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "models").mkdir()
            for n in ("a-model.gguf", "Qwen3-4B-Q4_K_M.gguf", "qwen2.5-1.5b.gguf"):
                (root / "models" / n).write_bytes(b"x")
            self.assertEqual(find_model(root).name, "a-model.gguf")                      # 고정 안 했으면 이름순(대소문자 무시)
            (root / "models" / "MODEL.txt").write_text("Qwen3-4B-Q4_K_M.gguf\n", encoding="utf8")
            self.assertEqual(find_model(root).name, "Qwen3-4B-Q4_K_M.gguf")
            (root / "models" / "MODEL.txt").write_text("missing.gguf", encoding="utf8")
            self.assertEqual(find_model(root).name, "a-model.gguf")                      # 고정한 파일이 없으면 무시

    def test_thinking_mode_is_disabled_and_think_blocks_are_stripped(self):
        from bot.llm import _clean, _NOTHINK
        self.assertEqual(_NOTHINK["chat_template_kwargs"]["enable_thinking"], False)
        self.assertEqual(_clean("<think>\n\n</think>\n\n안녕하세요"), "안녕하세요")
        self.assertEqual(_clean("<think>생각 중</think>답이에요"), "답이에요")


class TypoHandling(unittest.TestCase):
    """오타·부정확한 질문: ① 철자 교정(모델 없이) ② Qwen 교정(가짜 LLM 으로 논리만). 원래 질문이 확실히 풀릴 때는 건드리지 않는다."""

    class FixLLM(FakeLLM):
        def __init__(self, fixed):
            super().__init__(None)
            self.fixed, self.calls_fix = fixed, 0

        def fix_typos(self, q, lang, timeout=6.0):
            self.calls_fix += 1
            return self.fixed

    def test_jamo_distance_and_spell_fixer(self):
        from bot.nlu import jamo_distance
        self.assertEqual(jamo_distance("삭재", "삭제"), 1)
        self.assertEqual(jamo_distance("계휙", "계획"), 1)
        self.assertEqual(jamo_distance("같음", "같음"), 0)
        sp = ENG.spell
        self.assertIn("삭제", sp.fix("어떻게 삭재해요"))
        self.assertIn("계획", sp.fix("앞으로 계휙이 머에요"))
        self.assertIn("클릭", sp.fix("손으로 크릭 어케함"))

    def test_spelling_errors_are_answered_and_the_correction_is_shown(self):
        r = ENG.ask("어떻게 삭재해요")
        self.assertEqual(r["card"]["id"], "h-uninstall")
        self.assertEqual(r["via"], "spell")
        self.assertIn("삭제", r["fixed_q"])
        self.assertIn("이해했어요", r["note"])
        self.assertEqual(ENG.ask("앞으로 계휙이 머에요")["card"]["id"], "g-future")

    def test_ending_typos_are_normalized_without_breaking_real_words(self):
        from bot.nlu import normalize
        self.assertEqual(normalize("영상이 서버로 가나여"), "영상이 서버로 가나요")
        self.assertEqual(normalize("윈도우에서도 대나요"), "윈도우에서도 되나요")
        self.assertEqual(normalize("참여 방법"), "참여 방법")
        self.assertEqual(normalize("얼마에오"), "얼마에요")
        self.assertEqual(normalize("머에요"), "뭐에요")

    def test_valid_questions_are_never_rewritten_by_the_spell_fixer(self):
        for q in ("그럼 얼마예요?", "윈도우 노트북으로 해도 돼요?", "이거 설치하다 막히면 어떡해", "발로도 조작되나요"):
            r = ENG.ask(q, "ko", ["g-what-is"] if q.startswith("그럼") else None, "AnyControl이 뭐예요?")
            self.assertNotEqual(r.get("via"), "spell", q)
            self.assertNotIn("fixed_q", r, q)

    def test_qwen_fix_is_adopted_only_when_it_gives_a_confident_answer(self):
        llm = self.FixLLM("가격이 얼마예요?")
        e = Engine(KB, llm)
        r = e.ask("가격이 얼마엿어용옹")
        self.assertEqual(r["via"], "typo")
        self.assertEqual(r["fixed_q"], "가격이 얼마예요?")
        self.assertIn(r["card"]["id"], accepted(["g-price"]))

    def test_qwen_is_not_called_when_the_original_is_already_confident(self):
        llm = self.FixLLM("엉뚱한 문장이에요")
        e = Engine(KB, llm)
        self.assertEqual(e.ask("AnyControl이 뭐예요?")["card"]["id"], "g-what-is")
        self.assertEqual(llm.calls_fix, 0)

    def test_bad_qwen_fixes_are_rejected(self):
        bads = ["가격이 얼마예요?怎么办", "오늘 날씨가 정말 좋고 하늘이 아주 맑아서 산책하기에 딱 좋은 하루네요 그렇죠", "가격이 12345원이에요?", "x"]
        for bad in bads:
            e = Engine(KB, self.FixLLM(bad))
            self.assertIsNone(e._fix_typos("가격이 얼마엿어용옹", "가격이 얼마엿어용옹", "ko"), bad)

    def test_typo_set_quality_without_any_model(self):
        """eval/typo.json (오타 70개): 모델 없이도 상위 3개 안에 정답 80% 이상, 자료 밖 6/6 거절."""
        items = json.loads((Path(__file__).resolve().parents[1] / "eval" / "typo.json").read_text(encoding="utf8"))
        top3 = n_pos = none_ok = n_none = 0
        for it in items:
            r = ENG.ask(it["q"], it["lang"])
            if it.get("none"):
                n_none += 1; none_ok += r["kind"] == "none"; continue
            n_pos += 1
            ids = [r["card"]["id"]] if r.get("card") else []
            ids += [x["id"] for x in r.get("suggestions", [])] if r.get("near") else []
            ids += [KB.cards[i]["id"] for i, _, _ in ENG.card_index.search(it["q"], 3)]
            top3 += bool(accepted(it["expect"]) & set(ids[:3]))
        self.assertGreaterEqual(top3 / n_pos, 0.80)
        self.assertEqual(none_ok, n_none)


class ButtonsFollowTheScreenLanguage(unittest.TestCase):
    def test_follow_up_and_suggestion_buttons_use_the_ui_language_even_for_korean_questions(self):
        import re
        hangul = re.compile(r"[가-힣]")
        for q in ("PC에서도 쓸 수 있나요", "AWS는 어디에 들어가 있어요", "내일 뭐 입지", "안녕", "AI 모델을 쓰나요"):
            r = ENG.ask(q, "en")
            for key in ("more", "suggestions"):
                for it in r.get(key, []):
                    self.assertIsNone(hangul.search(it["q"]), (q, key, it["q"]))
        r = ENG.ask("Does it work on Windows?", "ko")                  # 반대로 한국어 화면에서 영어로 물으면 버튼은 한국어
        for it in r.get("more", []):
            self.assertIsNone(re.search(r"[A-Za-z]{4,} [A-Za-z]{3,}", it["q"]), it["q"])

    def test_no_duplicate_buttons_in_any_suggestion_list(self):
        for lang in ("ko", "en"):
            for cat in [None] + [c["id"] for c in KB.cats]:
                qs = [x["q"] for x in ENG.suggestions(lang, cat, 12)]
                self.assertEqual(len(qs), len(set(qs)), (lang, cat))
        r = ENG.ask("PC에서도 쓸 수 있나요", "ko")
        qs = [r["card"]["q"]] + [x["q"] for x in r["more"]]
        self.assertEqual(len(qs), len(set(qs)), qs)                    # 지금 답한 카드의 질문이 버튼으로 또 나오지 않는다

    def test_labels_endpoint_returns_the_requested_language(self):
        ids = ["g-price", "v-kimsam", "does-not-exist"]
        self.assertEqual(set(ENG.labels(ids, "en")), {"g-price", "v-kimsam"})
        self.assertEqual(ENG.labels(["g-price"], "en")["g-price"], KB.by_id["g-price"]["q"]["en"][0])
        self.assertEqual(ENG.labels(["g-price"], "ko")["g-price"], KB.by_id["g-price"]["q"]["ko"][0])

    def test_free_chat_mode_button_and_endpoint_are_gone(self):
        web = Path(__file__).resolve().parents[1] / "web"
        self.assertNotIn('id="free"', (web / "index.html").read_text(encoding="utf8"))
        self.assertNotIn("/api/chat", (web / "app.js").read_text(encoding="utf8"))
        self.assertNotIn("/api/chat", (Path(__file__).resolve().parents[1] / "bot" / "server.py").read_text(encoding="utf8"))


class OutputVerification(unittest.TestCase):
    cards = ["EfficientTAM-Ti는 55ms 입니다."]

    def test_ok(self):
        self.assertTrue(verify_output("55ms 입니다.", self.cards, "ko", KB.policy)[0])

    def test_invented_number_rejected(self):
        self.assertFalse(verify_output("77ms 입니다.", self.cards, "ko", KB.policy)[0])

    def test_banned_rejected(self):
        self.assertFalse(verify_output("완벽하게 55ms 입니다.", self.cards, "ko", KB.policy)[0])

    def test_wrong_language_rejected(self):
        self.assertFalse(verify_output("It takes 55ms.", self.cards, "ko", KB.policy)[0])
        self.assertFalse(verify_output("55ms 입니다", self.cards, "en", KB.policy)[0])

    def test_too_long_or_empty_rejected(self):
        self.assertFalse(verify_output("", self.cards, "ko", KB.policy)[0])
        self.assertFalse(verify_output("가" * 1000, self.cards, "ko", KB.policy)[0])


class ServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app = App(KB, ENG, log_path=Path(cls.tmp.name) / "q.jsonl")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def url(self, p):
        return f"http://127.0.0.1:{self.port}{p}"

    def get(self, p):
        with urllib.request.urlopen(self.url(p)) as r:
            return r.status, r.read()

    def post(self, body: bytes):
        req = urllib.request.Request(self.url("/api/ask"), data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_config_has_messages(self):
        s, b = self.get("/api/config")
        cfg = json.loads(b)
        self.assertEqual(s, 200)
        self.assertIn("greeting", cfg["messages"])
        self.assertGreaterEqual(cfg["cards"], 100)

    def test_index_and_missing(self):
        self.assertEqual(self.get("/")[0], 200)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/nope.html")
        self.assertEqual(cm.exception.code, 404)

    def test_path_traversal_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/..%2fbot%2fserver.py")
        self.assertIn(cm.exception.code, (403, 404))

    def test_suggest_and_card(self):
        s, b = self.get("/api/suggest?lang=en&n=3")
        items = json.loads(b)["items"]
        self.assertTrue(0 < len(items) <= 3)
        s, b = self.get("/api/card?id=g-what-is&lang=en")
        self.assertIn("AnyControl", json.loads(b)["a"])

    def test_ask_ok_bad_and_too_large(self):
        s, r = self.post(json.dumps({"q": "가만히 두면 커서가 떨리나요", "lang": "ko"}).encode())
        self.assertEqual(s, 200)
        self.assertIn(r["kind"], ("answer", "related"))
        self.assertTrue(r["card"]["id"].startswith("i-still"))
        self.assertEqual(self.post(b"not json")[0], 400)
        self.assertEqual(self.post(b"x" * 5000)[0], 413)

    def test_ask_accepts_conversation_context(self):
        self.app._last.clear()
        s, r = self.post(json.dumps({"q": "그럼 얼마예요?", "lang": "ko", "ctx": ["g-what-is"], "prev": "AnyControl이 뭐예요?"}).encode())
        self.assertEqual(s, 200)
        self.assertEqual(r["card"]["id"], "g-price")
        self.app._last.clear()
        s, r = self.post(json.dumps({"q": "가격은요", "lang": "ko", "ctx": "not-a-list", "prev": 123}).encode())
        self.assertIn(s, (200, 400))
        self.app._last.clear()

    def test_bye_schedules_exit_and_any_request_cancels_it(self):
        """탭이 닫히면(/api/bye) 종료가 예약되고, 새로고침처럼 곧 다시 접속하면 취소된다."""
        self.app.bye_at = None
        self.assertFalse(self.app.should_exit())
        self.assertEqual(self.post_path("/api/bye", b"{}")[0], 200)
        self.assertIsNotNone(self.app.bye_at)
        self.assertFalse(self.app.should_exit())              # 유예(8초) 안에는 아직 안 꺼진다
        self.get("/api/config")                                # 새로고침 후 다시 접속
        self.assertIsNone(self.app.bye_at)
        self.app.bye_at = time.monotonic() - 1                 # 유예가 지났다면
        self.assertTrue(self.app.should_exit())
        self.app.bye_at = None
        self.app.tab_closed()
        self.assertLessEqual(self.app.bye_at - time.monotonic(), 3.0)      # 유예는 3초
        self.app.bye_at = None

    def test_moving_to_admin_or_extra_tab_does_not_shut_down(self):
        a = self.app
        a.pages.clear(); a.bye_at = None
        self.assertEqual(self.post_path("/api/hello", b'{"pid":"main"}')[0], 200)
        # 채팅 화면에서 같은 탭으로 운영자 화면으로 이동: 채팅이 bye → 곧바로 운영자 화면이 hello
        self.post_path("/api/bye", b'{"pid":"main"}')
        self.assertIsNotNone(a.bye_at)
        self.post_path("/api/hello", b'{"pid":"admin"}')
        self.assertIsNone(a.bye_at)
        self.assertFalse(a.should_exit())
        # 운영자 화면 요청(정적 페이지·로그 조회)만 와도 예약이 취소된다
        self.post_path("/api/bye", b'{"pid":"admin"}')
        self.assertIsNotNone(a.bye_at)
        self.get("/admin.html"); self.assertIsNone(a.bye_at)
        # 새 탭으로 연 운영자 화면을 닫아도 채팅 탭이 열려 있으면 끄지 않는다
        a.pages.clear(); a.bye_at = None
        self.post_path("/api/hello", b'{"pid":"main"}'); self.post_path("/api/hello", b'{"pid":"admin"}')
        self.post_path("/api/bye", b'{"pid":"admin"}')
        self.assertIsNone(a.bye_at)
        self.post_path("/api/bye", b'{"pid":"main"}')                       # 마지막 화면이 닫히면 예약
        self.assertIsNotNone(a.bye_at)
        a.pages.clear(); a.bye_at = None

    def post_path(self, path, body: bytes):
        req = urllib.request.Request(self.url(path), data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())

    def test_rate_limit(self):
        self.app._last.clear()
        body = json.dumps({"q": "안녕", "lang": "ko"}).encode()
        self.post(body)
        self.assertEqual(self.post(body)[0], 429)
        self.app._last.clear()

    def test_question_logged(self):
        self.app._last.clear()
        self.post(json.dumps({"q": "로그 확인용 질문", "lang": "ko"}).encode())
        self.assertIn("로그 확인용 질문", self.app.log_path.read_text(encoding="utf8"))
        self.app._last.clear()

    def test_log_records_question_and_answer_and_default_name_is_timestamp(self):
        import re
        self.app._last.clear()
        self.post(json.dumps({"q": "가격이 얼마예요", "lang": "ko"}).encode())
        row = json.loads(self.app.log_path.read_text(encoding="utf8").splitlines()[-1])
        self.assertEqual(row["q"], "가격이 얼마예요")
        self.assertTrue(row["a"])
        self.app._last.clear()
        default = App(KB, ENG).log_path                                 # 기본 경로: log/<날짜_시각>.jsonl
        self.assertEqual(default.parent.name, "log")
        self.assertRegex(default.name, r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.jsonl$")


if __name__ == "__main__":
    unittest.main()
