# 카드 작성 규칙 (anycontrol-chat 지식 카드)
작업 폴더: /Users/ndtool/Desktop/2026 고려대 AWS 경진대회/2026 고려대 AWS 경진대회 - GPT/anycontrol-chat
출처 문서: sources/*.md (읽기 전용). 프로젝트 원본(코드)은 ../anycontrol-web/ 에 있으며 필요하면 확인해도 됨(수정 금지).
산출물: kb/cards/<파일명>.json — JSON 배열. 한 장의 형식:
{
 "id": "<접두사>-<영문소문자-하이픈>",   // 전체에서 유일
 "cat": "overview|usage|arch|tracking|cursor|pen|depth|hand|stable|calib|eval|limits|process|safety|install|team|code",
 "status": "measured|verified|partial|not_validated|plan|info",
 "q": {"ko": ["대표 질문","다른 표현 2~4개(방문객이 실제로 할 법한 구어체·키워드형 포함)"], "en": ["main question","2~4 paraphrases"]},
 "a": {"ko": "답 (2~6문장, 구체적 수치·메커니즘·파일/모듈명 포함 가능)", "en": "same answer in English"},
 "kw": ["한/영 키워드 5~10개 (동의어, 약어, 영문 용어 포함)"],
 "src": ["sources/파일명#섹션 또는 코드 경로"],
 "related": ["같은 작업에서 만든 다른 카드 id 1~3개"],
 "suggest": true   // 방문객에게 보여 줄 만한 핵심 질문에만 (전체의 15% 정도)
}
엄수 사항:
1. 사실은 반드시 sources/ 문서(또는 코드)에서 확인된 것만. 추측·일반상식으로 채우지 말 것. 문서에 없으면 카드를 만들지 않는다.
2. 수치는 문서 그대로, ko와 en 답의 숫자가 완전히 같아야 한다. 수치에는 측정 조건(영상 수, 합성/실측, 버전)을 같이 쓴다.
3. status 를 정직하게: measured=재현 가능한 벤치로 측정, verified=구현+테스트로 확인, partial=표본 적거나 일부만 검증, not_validated=검증 안 됨(예: 실제 카메라 검증 없음), plan=계획, info=단순 설명.
4. 과장 금지. 다음 표현은 쓰지 않는다: 무지연, 지연 없음, 정확도 보장, 100% 정확, 완벽, 오류 없음, zero latency, perfect, guarantee accuracy. 부정문으로 꼭 써야 하면 그 카드에 "allow_banned": true.
5. 버전을 구분하라: '소개서 v1.0.0'은 macOS 전용이던 초기 문서(수치도 v1.0.0 기준). 현재는 v1.3.0(README, HANDOFF). 답에 해당 버전/기준을 명시.
6. 한계·미검증 사항은 숨기지 말고 별도 카드로 (cat: limits, status: not_validated/partial).
7. 한 카드는 한 가지 질문에만 답한다. 짧고 정확하게, 방문객이 알아듣게 쓰되 심사위원이 파고들 기술 질문에도 답할 수 있게 구체적으로.
8. 영어 답은 직역이 아니라 자연스러운 영어로, 내용·숫자는 동일.
9. JSON 유효성: 큰따옴표 이스케이프 주의. 작성 후 `python3 -c "import json;json.load(open('kb/cards/파일.json'))"` 로 확인하고, 마지막에 `python3 -m bot validate` 를 실행(작업 폴더에서)해 자신의 파일에서 나온 오류·경고를 모두 고친다(다른 파일의 오류는 무시).
10. 파일은 주제별로 2~5개로 나눠 써도 된다(예: kb/cards/<접두사>1_xxx.json). 다른 작업자가 쓴 kb/cards 파일은 건드리지 말 것.
끝나면 만든 카드 수, 파일 목록, 문서 내용이 서로 모순되거나 불확실해서 일부러 뺀 사실을 짧게 보고.
