"""자연어 대응 보조 (1단계: 규칙 기반, 외부 패키지 없음).

- normalize(): 구어체·반말·음슴체·웃음/추임새를 표준 표현으로 바꾼다 ("이게 왜 좋음?" → "이게 왜 좋아요?")
- is_followup(): "그럼 얼마예요?" 처럼 앞 대화에 기대는 질문인가
- strip_subject(): "이게/이 프로젝트는/AnyControl은" 같은 주어를 떼어 낸 나머지 (일반 질문 의도 판별용)
- GenericIntents: "왜 필요해요/왜 좋아요/뭐가 달라요/단점은" 같이 주제어 없이 묻는 흔한 질문을 카드에 연결
- FuzzyIndex: 글자 2-gram 유사도로 후보 카드를 넓게 모은다 (LLM 이 고를 후보를 만들 때 쓴다)
"""
from __future__ import annotations
import re

# --------------------------------------------------------------------------- 구어체 정규화
_NOISE = re.compile(r"[ㅋㅎㅠㅜㅡ]{1,}|[~^]+|\.{2,}|(?<![가-힣a-z])(ㅇㅇ|ㅇㅋ|ㄱㄱ)(?![가-힣a-z])", re.I)
_FILLER = re.compile(r"(?<![가-힣])(음+|으음+|어+|아+|저기(요)?|있잖아(요)?|혹시|그냥|막|진짜|정말|완전|좀|약간|대체)(?![가-힣])")

# (패턴, 바꿀 말) — 위에서부터 차례로 적용. 반말·명사형 종결·줄임말을 '~요/~나요' 꼴로 맞춘다.
_RULES: list[tuple[re.Pattern, str]] = [(re.compile(p), r) for p, r in [
    (r"ㄱㄴ(\?)?", "가능한가요?"), (r"ㅇㄷ", "어디"), (r"ㅁㅇ", "뭐"),
    (r"않음(\?)?", "않나요?"), (r"좋음(\?)?", "좋아요?"), (r"나쁨(\?)?", "나빠요?"), (r"필요함(\?)?", "필요해요?"), (r"쓸모\s*있음(\?)?", "쓸모 있나요?"),
    (r"되는\s*거야", "되나요"), (r"되는\s*거임", "되나요"), (r"됨(\?)", "되나요?"), (r"안\s*됨(\?)?", "안 되나요?"), (r"되냐", "되나요"), (r"됨\?*$", "되나요?"),
    (r"있음(\?)", "있나요?"), (r"있냐", "있나요"), (r"없음(\?)", "없나요?"), (r"가능함(\?)?", "가능한가요?"), (r"가능해\?*$", "가능해요?"),
    (r"뭐임", "뭐예요"), (r"뭐냐", "뭐예요"), (r"뭐야", "뭐예요"), (r"뭔데", "뭐예요"), (r"뭐지", "뭐예요"), (r"뭐하는\s*거(야|임)", "뭐 하는 거예요"),
    (r"어떻게\s*쓰냐", "어떻게 써요"), (r"어케", "어떻게"), (r"어캐", "어떻게"), (r"왜케", "왜 이렇게"), (r"걍", "그냥"),
    (r"(\S+)(하냐)(\?)?$", r"\1하나요?"), (r"(\S+)(이냐)(\?)?$", r"\1인가요?"),
    (r"어디에다가", "어디에"), (r"어따", "어디에"), (r"써도\s*됨", "써도 되나요"), (r"해도\s*됨", "해도 되나요"),
    (r"얼만데", "얼마예요"), (r"얼마임", "얼마예요"), (r"공짜(야|임)?(\?)?", "무료인가요?"),
    (r"(\S+)(함|임)\?$", r"\1해요?"),
    # 말끝 오타: "~나여/~가여/~에여"(요 대신 여), "되요/대요"
    (r"((?:이에|예|에|나|가|까|니|세|해|어|아|돼|되|있|없|인|할|줘|죠))여(?=[\s?!.~ㅠㅜ]|$)", r"\1요"),
    (r"(?<![가-힣])대요(?=[\s?!.~]|$)", "돼요"), (r"대나요(?=[\s?!.~]|$)", "되나요"), (r"댈까요(?=[\s?!.~]|$)", "될까요"), (r"(에|예)오(?=[\s?!.~]|$)", r"\1요"), (r"(?<![가-힣])머(?=\s|$|에요|예요|야|임|함)", "뭐"), (r"(?<![가-힣])대여(?=[\s?!.~]|$)", "돼요"),
    (r"(\S+?)(어케|어캐)(\s*)(해|하|돼|되|써|쓰|함|하나)", r"\1어떻게\3\4"),
    (r"(?<=[가-힣])염(?=[\s?!.~]|$)", "요"),
]]


def normalize(text: str) -> str:
    t = (text or "").strip()
    t = _NOISE.sub(" ", t)
    for pat, rep in _RULES:
        t = pat.sub(rep, t)
    t = _FILLER.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# --------------------------------------------------------------------------- 이어 묻기·주어
_FOLLOW_KO = re.compile(r"^\s*(그럼|그러면|그렇다면|그래서|그리고|그런데|근데|그건|그거|그것|이건|이것|그쪽|거기|그건요|또|다른|아니면)")
_FOLLOW_EN = re.compile(r"^\s*(and|then|so|but|what about|how about|why not|what else|also)\b", re.I)
_PRONOUN_KO = re.compile(r"(이게|이거|이건|이것|그게|그거|그건|그것|얘|걔|저게)")
_PRONOUN_EN = re.compile(r"\b(it|that|this|those|they)\b", re.I)

_SUBJECT_KO = re.compile(
    r"(이\s*프로젝트|이\s*앱|이\s*프로그램|이\s*서비스|이\s*제품|이\s*물건|이\s*기술|애니\s*컨트롤|any\s*control|anycontrol|이게|이거는|이거|이건|이것은|이것|그게|그건|그거는|그거|그것|얘는|얘가|얘|그럼|그러면|그래서|그리고|근데|그런데|혹시|도대체|대체)"
    r"(은|는|이|가|을|를|도|요)?", re.I)
_SUBJECT_EN = re.compile(r"\b(this project|this app|this thing|this|that|it|anycontrol|the project|then|so|and|but|well|ok|okay)\b", re.I)


def is_followup(q: str, lang: str) -> bool:
    return bool((_FOLLOW_KO if lang == "ko" else _FOLLOW_EN).search(q))


def has_pronoun(q: str, lang: str) -> bool:
    return bool((_PRONOUN_KO if lang == "ko" else _PRONOUN_EN).search(q))


def strip_subject(q: str, lang: str) -> str:
    t = (_SUBJECT_KO if lang == "ko" else _SUBJECT_EN).sub(" ", q)
    t = re.sub(r"[?!.,~]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# --------------------------------------------------------------------------- 일반 질문 의도
# 주어를 뗀 나머지가 이 패턴과 '거의 전체'로 맞을 때만 쓴다 → "펜이 왜 좋아요" 처럼 다른 주제어가 있으면 가로채지 않는다.
_T = r"(?:\s*(?:있|없|않|해|하|돼|되|좋|쓰|뭐|말|알려|주|거|가|이|인)\w{0,5}){0,2}"      # 뒤에 붙을 수 있는 짧은 말 ("뭐예요", "있어요", "알려 주세요")
GENERIC_KO: list[tuple[str, str]] = [
    (r"(?:왜|뭐하러|뭣하러)\s*(?:이런\s*걸\s*)?(?:필요|쓰|써야|만들|만든)\w{0,5}" + _T, "g-why-made"),
    (r"(?:필요|쓸모|쓸\s*데|의미|존재\s*이유)\w{0,3}" + _T, "g-why-made"),
    (r"(?:왜|뭐가|어떤\s*점이|어떤\s*점은|뭐|어디가)\s*(?:더\s*)?(?:좋|괜찮|낫|편하|대단|특별|쓸\s*만)\w{0,5}" + _T, "v-top-strengths"),
    (r"(?:장점|강점|좋은\s*점|매력|특징|내세울\s*점)\w{0,3}" + _T, "v-top-strengths"),
    (r"(?:단점|약점|나쁜\s*점|아쉬운\s*점|문제점|부족한\s*점|한계점?|별로)\w{0,3}" + _T, "v-top-weakness"),
    (r"(?:뭐가|어떤\s*점이|어떤\s*점은|뭐|어디가)\s*(?:더\s*)?(?:달라|다른|차이|다르)\w{0,5}" + _T, "g-vs-others"),
    (r"(?:차이|차별점|다른\s*점|경쟁|기존)\w{0,3}" + _T, "g-vs-others"),
    (r"(?:어디|어떤\s*곳|어떤\s*경우|언제)\s*(?:에|에서)?\s*(?:쓰|써|활용|사용|유용|도움)\w{0,5}" + _T, "g-who-for"),
    (r"(?:용도|활용\s*(?:처|분야|법)?|사용처|쓰임새?)\w{0,2}" + _T, "g-who-for"),
    (r"(?:누가|누구한테|누구에게|누구를\s*위해?)\s*(?:쓰|써|좋|필요|위한)\w{0,5}" + _T, "g-who-for"),
    (r"(?:어떻게|뭘로|뭐로)\s*(?:쓰|써|사용|하는|해|시작|켜)\w{0,5}" + _T, "h-how-to-start"),
    (r"(?:사용법|사용\s*방법|쓰는\s*법|쓰는\s*방법|시작\s*방법|시작하는\s*법)\w{0,2}" + _T, "h-how-to-start"),
    (r"(?:얼마|가격|비용|값|유료|무료|공짜)\w{0,4}" + _T, "g-price"),
    (r"(?:위험|안전)\w{0,4}" + _T, "g-safe-real"),
    (r"(?:신기|대단|멋지|놀랍)\w{0,4}" + _T, "v-wow"),
    (r"(?:뭐|무엇|뭔)\w{0,4}" + _T, "g-what-is"),
]
GENERIC_EN: list[tuple[str, str]] = [
    (r"^why (do|would|should|did) (i|we|you|people|anyone) (need|want|use|care about|build|make)( (it|this|that|anycontrol))?\??$", "g-why-made"),
    (r"^(why|what for)( (is|are|do|does|would|should|did))?( (it|this|that|anycontrol))?( (needed|necessary|useful|made|built|exist|matter|matters))\??$", "g-why-made"),
    (r"^(why|what for)( (is|are|do|does))?( (it|this|that|anycontrol))? ?(needed|necessary|useful|a thing)?\??$", "g-why-made"),
    (r"^(is|are)( (it|this|that|anycontrol))? (really )?(useful|needed|necessary|worth it|worth)\??$", "g-why-made"),
    (r"^(why|what)( (is|are|does|do))?( (it|this|that|anycontrol))?( so| any| really| even)? (good|great|better|special|cool|nice|impressive|useful)\??$", "v-top-strengths"),
    (r"^what'?s? (so )?(good|great|special|cool|nice|impressive|the point)( (about|of) (it|this|anycontrol))?\??$", "v-top-strengths"),
    (r"^(any |what are (its|the) )?(pros|advantages|strengths|benefits|selling points?)\??$", "v-top-strengths"),
    (r"^(any |what are (its|the) )?(cons|downsides|disadvantages|weaknesses|drawbacks|problems|flaws)\??$", "v-top-weakness"),
    (r"^what'?s? (bad|wrong|the catch)( (about|with) (it|this|anycontrol))?\??$", "v-top-weakness"),
    (r"^(how|what)( (is|are|does|do))?( (it|this|that|anycontrol))? (different|unique|special)( from (others|other (things|apps|tools)|the rest))?\??$", "g-vs-others"),
    (r"^(what'?s? )?(the )?(difference|catch)( from (others|other (things|apps|tools)))?\??$", "g-vs-others"),
    (r"^(where|when|what for|who)( (can|could|do|should|would))?( (i|we|you|one|people))? (use|used|apply|need|want)( (it|this|that|anycontrol))?( for)?\??$", "g-who-for"),
    (r"^what can (you|i)( (help|do|ask|tell))( me)?( with| about)?( me)?\??$", "g-what-is"),
    (r"^(what|which)( (is|are))?( (it|this|that|anycontrol))? (used|useful|good) for\??$", "g-who-for"),
    (r"^how( (do|can|should|would))?( (i|we|you))? (use|start|begin|run|get started)( (it|this|that|anycontrol))?\??$", "h-how-to-start"),
    (r"^(how much|price|cost|is it free|is it paid|free|paid)\??$", "g-price"),
    (r"^(is it|is this|are they)( (safe|dangerous|risky|secure))\??$", "g-safe-real"),
    (r"^(wow|cool|amazing|awesome|nice|impressive|neat)( (is this real)?)?[!?]*$", "v-wow"),
    (r"^(tell me|explain|describe|what|so what)( (is|about))?( (it|this|that|anycontrol|this thing|this project))?\??$", "g-what-is"),
]
_GENERIC = {"ko": [(re.compile(p, re.I), c) for p, c in GENERIC_KO], "en": [(re.compile(p, re.I), c) for p, c in GENERIC_EN]}


def generic_intent(q: str, lang: str) -> str | None:
    """주제어 없이 묻는 흔한 질문이면 연결할 카드 id, 아니면 None."""
    if lang == "ko":
        rest = strip_subject(q, lang)
        if not rest or len(rest) > 16:
            return None
        for pat, cid in _GENERIC["ko"]:
            if pat.fullmatch(rest):
                return cid
        return None
    text = re.sub(r"\s+", " ", q.strip().lower())
    text = re.sub(r"[.!,]+$", "", text) if not text.endswith("?") else text
    if len(text) > 60:
        return None
    for pat, cid in _GENERIC["en"]:
        if pat.search(text):
            return cid
    return None


# --------------------------------------------------------------------------- 글자 2-gram 유사도 (후보 넓히기)
def _grams(text: str) -> set[str]:
    t = re.sub(r"[\s\.,!?？！~'\"“”‘’()（）·]+", "", text).lower()
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else {t}


class FuzzyIndex:
    """카드의 모든 질문 문구와 글자 2-gram 으로 비교한다. 단어가 하나도 안 겹쳐도 비슷한 문구를 후보로 올릴 수 있다."""

    def __init__(self, cards: list[dict]) -> None:
        self.rows: list[tuple[int, str, set[str]]] = []
        for i, c in enumerate(cards):
            for lang in ("ko", "en"):
                for q in c["q"][lang]:
                    g = _grams(q)
                    if g:
                        self.rows.append((i, lang, g))

    def top(self, query: str, lang: str, k: int = 6) -> list[tuple[int, float]]:
        g = _grams(query)
        if not g:
            return []
        best: dict[int, float] = {}
        for i, ln, rg in self.rows:
            if ln != lang:
                continue
            inter = len(g & rg)
            if not inter:
                continue
            sim = 2 * inter / (len(g) + len(rg))
            if sim > best.get(i, 0.0):
                best[i] = sim
        return sorted(best.items(), key=lambda x: -x[1])[:k]


def char_similarity(a: str, b: str) -> float:
    """두 문장의 글자 2-gram Dice 유사도 (0~1)."""
    ga, gb = _grams(a), _grams(b)
    return 2 * len(ga & gb) / (len(ga) + len(gb)) if ga and gb else 0.0


# --------------------------------------------------------------------------- 철자 교정 (모델 없이): 카드에 나오는 단어 사전 + 자모 편집 거리
from collections import Counter  # noqa: E402

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def _decompose(word: str) -> list[str]:
    out: list[str] = []
    for ch in word:
        o = ord(ch) - 0xAC00
        if 0 <= o < 11172:
            out += [_CHO[o // 588], _JUNG[(o % 588) // 28], _JONG[o % 28]]
        else:
            out += [ch, "·", "·"]
    return out


def jamo_distance(a: str, b: str) -> int:
    """두 단어를 초성·중성·종성 단위로 쪼갠 뒤의 편집 거리 (받침 하나, 모음 하나 틀린 오타는 1)."""
    x, y = _decompose(a), _decompose(b)
    prev = list(range(len(y) + 1))
    for i, cx in enumerate(x, 1):
        cur = [i]
        for j, cy in enumerate(y, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cx != cy)))
        prev = cur
    return prev[-1]


class SpellFixer:
    """카드 문구(질문·키워드·답)에 나오는 한국어 단어를 사전으로 삼아, 사전에 없는 단어가 사전의 단어와 자모 한두 개만 다르면 고친다.
    "삭재→삭제", "계휙→계획", "크릭→클릭", "정학도→정확도". 모델이 필요 없고 항상 같은 결과를 낸다."""

    def __init__(self, texts: list[str], min_count: int = 2) -> None:
        from .textutil import _stem_ko
        self._stem = _stem_ko
        cnt: Counter = Counter()
        runs: set[str] = set()
        for t in texts:
            for m in HANGUL_RUN.finditer(t):
                runs.add(m.group())
                st = _stem_ko(m.group())
                if len(st) >= 2:
                    cnt[st] += 1
        self.vocab = {w: c for w, c in cnt.items() if c >= min_count}
        self.known = runs | set(self.vocab)
        self.by_len: dict[int, list[str]] = {}
        for w in self.vocab:
            self.by_len.setdefault(len(w), []).append(w)

    # 소리 나는 대로 흔히 잘못 쓰는 말 (자모 거리로는 못 찾는 것)
    COMMON = {"업시": "없이", "엄써": "없어", "먼가": "뭔가", "만드럿": "만들었", "만들엇": "만들었", "잇나": "있나", "잇어": "있어", "잇는": "있는", "안대": "안 돼", "조아": "좋아", "괜찬": "괜찮"}

    def fix_word(self, run: str) -> str:
        for bad, good in self.COMMON.items():
            if run.startswith(bad) and (run == bad or run[len(bad):] in ("요", "여", "도", "은", "는", "가", "이", "어요", "나요", "나여", "다")) and run not in self.known:
                run = good + run[len(bad):]
                break
        if run in self.known or len(run) < 2:
            return run
        stem = self._stem(run)
        if stem in self.vocab or len(stem) < 2:
            return run
        ending = run[len(stem):]
        limit = 1 if len(stem) <= 2 else 2
        best, best_key = None, None
        for L in (len(stem), len(stem) - 1, len(stem) + 1):
            for w in self.by_len.get(L, []):
                d = jamo_distance(stem, w)
                if d <= limit:
                    key = (d, -self.vocab[w])
                    if best_key is None or key < best_key:
                        best, best_key = w, key
        return best + ending if best else run

    def fix(self, text: str) -> str:
        return HANGUL_RUN.sub(lambda m: self.fix_word(m.group()), text)


HANGUL_RUN = re.compile(r"[가-힣]+")


# --------------------------------------------------------------------------- 한국어·영어 밖의 언어 감지 / 여러 질문 나누기
_FOREIGN_LATIN = {
    "fr": ("bonjour", "pouvez", "vous", "est-ce", "qu'est", "expliquer", "fran\u00e7ais", "comment", "fonctionne", "sans", "c'est", "quoi", "les", "des", "une", "pour", "avec", "merci"),
    "es": ("qu\u00e9", "c\u00f3mo", "funciona", "sin", "espa\u00f1ol", "favor", "puedo", "usar", "los", "las", "una", "para", "con", "hola", "gracias", "responde", "es"),
    "de": ("wie", "funktioniert", "ich", "das", "ist", "nicht", "und", "kann", "ohne", "bitte", "was", "ein", "eine", "deutsch", "danke"),
    "pt": ("voc\u00ea", "como", "funciona", "sem", "portugu\u00eas", "obrigado", "uma", "para", "n\u00e3o"),
    "it": ("come", "funziona", "senza", "italiano", "grazie", "una", "per", "che", "cosa", "posso"),
}
_EN_STOP = {"the", "is", "are", "what", "how", "can", "i", "you", "it", "do", "does", "a", "an", "to", "of", "in", "on", "and", "my", "this", "that", "with", "for", "please", "use", "work", "works"}
LANG_NAMES = {"ja": "Japanese", "zh": "Chinese", "ar": "Arabic", "ru": "Russian", "fr": "French", "es": "Spanish", "de": "German", "pt": "Portuguese", "it": "Italian",
              "th": "Thai", "hi": "Hindi", "vi": "Vietnamese"}


def detect_foreign(q: str) -> str | None:
    """한국어·영어가 아닌 언어로 쓴 질문이면 언어 코드(ja/zh/ar/ru/fr/es/de/...), 아니면 None."""
    if re.search(r"[\uac00-\ud7a3\u3131-\u318e]", q):
        return None
    if re.search(r"[\u3040-\u30ff]", q):
        return "ja"
    if len(re.findall(r"[\u4e00-\u9fff]", q)) >= 2:
        return "zh"
    if re.search(r"[\u0600-\u06ff]", q):
        return "ar"
    if re.search(r"[\u0400-\u04ff]", q):
        return "ru"
    if re.search(r"[\u0e00-\u0e7f]", q):
        return "th"
    if re.search(r"[\u0900-\u097f]", q):
        return "hi"
    words = re.findall(r"[a-z\u00c0-\u017f']+(?:-[a-z]+)?", q.lower())
    if len(words) < 2:
        return None
    en = sum(1 for w in words if w in _EN_STOP)
    best, best_n = None, 0
    for code, marks in _FOREIGN_LATIN.items():
        n = sum(1 for w in words if w in marks)
        if n > best_n:
            best, best_n = code, n
    if best and best_n >= 2 and best_n > en:
        return best
    if re.search(r"[\u00e0-\u00ff\u00bf\u00a1]", q.lower()) and en == 0 and len(words) >= 3:
        return best or "other"
    return None


_NUMBERED = re.compile(r"(?:(?<=\s)|^)(?:\(?\d{1,2}[\)\.]|[\u2460-\u2469])\s*")
_Q_END_KO = re.compile(r"(\?|\uff1f|나요|까요|인가요|ㄴ가요|되나요|죠|뭐예요|뭐야|어때요|알려\s*줘|알려\s*주세요|설명해|몇|언제|어디|어떻게|왜|얼마)\s*[.!]*\s*$")
_Q_START_EN = re.compile(r"^\W*(what|how|can|could|does|do|is|are|why|where|when|will|should|which|who|did|would|may)\b", re.I)
_INSTRUCT = re.compile(r"^(각|번호별|answer each|please answer|한국어로|영어로)|(답해\s*주세요|answer (each|all)|each (number|one))\s*[.!]*$", re.I)


def is_question_like(p: str) -> bool:
    return bool("?" in p or "\uff1f" in p or _Q_END_KO.search(p) or _Q_START_EN.search(p))


def split_parts(q: str) -> list[str]:
    """여러 질문이 한꺼번에 들어왔을 때 나눈다 (번호·물음표·문장 단위). 하나로 보이면 [q]."""
    s = _NUMBERED.sub("\n", q.replace("\r", "\n"))
    raw = re.split(r"\n+|(?<=[?\uff1f!])\s+|(?<=[.\u3002])\s+", s)
    parts = []
    for p in raw:
        p = p.strip(" \n,;")
        if len(p) >= 3 and not _INSTRUCT.search(p):
            parts.append(p)
    return parts
