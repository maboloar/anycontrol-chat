"""텍스트 처리: 토큰화(한국어 글자 n-gram + 영어 단어), 언어 감지, 불용어.

형태소 분석기 없이(외부 패키지 0개) 한국어와 영어를 한 인덱스에서 검색하기 위한 단순한 방식이다.
- 한글 덩어리는 2글자 조각(bigram)으로 쪼갠다: "추적을" → "추적", "적을". 조사가 붙어도 "추적"이 맞는다.
- 한글 덩어리의 첫 글자 1글자 조각은 조사가 아닐 때만 쓴다 ("펜을" → "펜").
- 영어는 소문자 단어로 자르고 -s/-es/-ing/-ed 같은 흔한 어미를 떼어 낸다.
"""
from __future__ import annotations
import re

HANGUL = re.compile(r"[가-힣]+")
LATIN = re.compile(r"[a-z0-9][a-z0-9_.+\-]*", re.I)

# 한글 1글자로 쓰면 잡음이 큰 조사·어미 글자
PARTICLES = set("을를이가은는에의도와과로으서만께요다고며면나니까지서게든")

STOP = {
    # 한국어 질문 표현
    "어떻", "떻게", "어떤", "무엇", "뭐가", "뭔가", "무슨", "있나", "나요", "인가", "가요", "합니", "니다", "습니", "해요", "해주", "주세", "세요",
    "알려", "려줘", "설명", "대해", "대한", "관련", "궁금", "그럼", "그리", "리고", "그런", "이게", "이건", "저건", "하는", "되나", "되는", "할수", "수있", "있는", "있어", "없나",
    "뭐야", "뭐죠", "뭔데", "뭐지", "뭐예", "뭐에", "어디", "얼마", "언제", "왜냐", "이거", "저거", "그거", "것이", "건가", "거야", "건지",
    # 영어
    "the", "a", "an", "is", "are", "was", "were", "be", "to", "of", "in", "on", "for", "and", "or", "it", "its", "this", "that", "these", "those",
    "do", "does", "did", "can", "could", "will", "would", "should", "you", "your", "me", "my", "we", "our", "us", "please", "tell", "about", "what", "how",
    "why", "when", "where", "which", "who", "with", "as", "at", "by", "from", "any", "there", "than", "then", "so", "if", "also", "have", "has", "had",
}

_EN_SUFFIXES = ("ing", "ed", "ly", "es", "s")


def stem_en(w: str) -> str:
    w = w.lower()
    if len(w) <= 3:
        return w
    for suf in _EN_SUFFIXES:
        if suf == "ed" and w.endswith("eed"):   # speed, need, feed 처럼 어간의 일부인 경우
            continue
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def detect_lang(text: str, default: str = "ko") -> str:
    """한글이 하나라도 있으면 ko, 라틴 글자만 3개 이상이면 en, 아니면 default."""
    if HANGUL.search(text):
        return "ko"
    if len(re.findall(r"[A-Za-z]", text)) >= 3:
        return "en"
    return default


# 문장 끝 어미·조사. 어간만 남겨야 "만들었어요", "측정했나요" 같은 말투가 검색 잡음이 되지 않는다.
NOISE_CHARS = set("이그저거쓰뭐내것수등을를은는에의도와과로서만요다고")
_ENDINGS = sorted([
    "이었나요", "였나요", "었나요", "았나요", "었어요", "았어요", "였어요", "에서도", "으로도", "에도서", "했나요", "했어요", "됐나요", "됐어요", "하나요", "되나요", "있나요", "없나요", "인가요", "일까요", "을까요", "ㄹ까요",
    "이에요", "예요", "에요", "어요", "아요", "해요", "돼요", "나요", "까요", "니까", "습니까", "합니까", "합니다", "입니다", "습니다", "세요", "주세요",
    "해줘", "해주세요", "알려줘", "알려주세요", "줘요", "줘", "인지", "는지", "은지", "에서는", "에서", "으로는", "으로", "에게", "까지", "부터", "보다", "처럼",
    "이랑", "랑", "이나", "하고", "이고", "이며", "에는", "에도", "한테", "라고", "이라고", "에", "의", "도", "로", "와", "과", "만", "은", "는", "을", "를", "이", "가",
], key=len, reverse=True)


def _stem_ko(run: str) -> str:
    for _ in range(2):          # "에서" + "도" 처럼 두 겹으로 붙은 경우까지
        for e in _ENDINGS:
            if run.endswith(e) and len(run) - len(e) >= 1:
                # 2글자 단어의 끝 글자가 조사처럼 보여도 단어일 수 있다 (깊이, 아이…): 은/는/을/를 만 뗀다
                if len(run) == 2 and e not in ("은", "는", "을", "를"):
                    continue
                run = run[: -len(e)]
                break
        else:
            break
    return run


def tokenize(text: str) -> list[str]:
    toks: list[str] = []
    low = re.sub(r"\b(tier)[\s-]+(\d)", r"\1\2", text.lower())
    for m in HANGUL.finditer(low):
        run = _stem_ko(m.group())
        if len(run) == 1:
            if run not in NOISE_CHARS:
                toks.append(run)
            continue
        for i in range(len(run) - 1):
            toks.append(run[i:i + 2])
    for m in LATIN.finditer(low):
        w = m.group().strip(".-_+")
        if not w or w in STOP:
            continue
        # tier0, v1.3.0, 5g 같은 식별자는 통째로도 남긴다
        if re.search(r"\d", w) or "-" in w or "_" in w or "." in w:
            toks.append(w)
        for part in re.split(r"[-_.+]", w):
            if len(part) >= 2 and part not in STOP:
                toks.append(stem_en(part))
    return [t for t in toks if t not in STOP]


def numbers_in(text: str) -> set[str]:
    """답변에 나온 숫자(소수·쉼표 포함)를 정규화해 모은다. LLM 출력 검증에 쓴다."""
    out = set()
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text):
        s = m.group().replace(",", "")
        out.add(s)
        if "." in s:
            out.add(s.rstrip("0").rstrip("."))
    return out
