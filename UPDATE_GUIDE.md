# 챗봇 질문-답 갱신 안내 — AnyControl 이 업데이트됐을 때

AnyControl(`../anycontrol-web`)이 바뀌면 챗봇의 질문-답이 낡을 수 있습니다. 이 문서는 **"AnyControl 이 업데이트됐어. 챗봇 질문-답을 전체 검토하고 갱신해 줘"** 라고 요청받았을 때 (사람이든 AI 든) 그대로 따라 하면 되는 절차입니다.
챗봇은 질문-답 "카드"를 검색해 보여 줄 뿐이라, **카드가 AnyControl 의 현재 사실과 맞는지**가 품질의 전부입니다.

## 0. 한눈에 보는 구조

| 위치 | 역할 |
|---|---|
| `../anycontrol-web/` | **사실의 원천**. 코드 > HANDOFF.md > README. 문서끼리 어긋나면 코드가 이긴다 (예: 마우스 깊이 기본값은 README 가 아니라 `io/mouse.py` 의 `depth_source`). |
| `kb_src/*.txt` | 사람이 고치는 카드 원본(한/영 같이). `python3 tools/build_cards.py` 가 `kb/cards/v*.json` 을 다시 만든다. **v*.json 은 직접 고치지 말 것.** |
| `kb/cards/g1_intro, h1_use, h2_use, i1_how .json` | 먼저 만든 카드(손으로 만든 JSON). 직접 고쳐도 된다. |
| `tools/add_variants.py` | 기존 카드에 질문 표현·키워드를 덧붙이는 표. `build_cards.py` 가 끝에 자동 실행한다. |
| `kb/facts.json` | 카드가 기대는 **사실 목록**(버전, 최대 물체 수, 3초 유예, 필요 사양, 기본값 …)와 그 사실에 의존하는 카드. 코드에서 자동으로 다시 읽는다. |
| `kb/topic_map.json` | 파일 경로 → 바뀌면 다시 봐야 할 카드. |
| `kb/snapshot/` | "카드를 이 상태의 AnyControl 에 맞춰 둠" 기록(문서·코드 사본 + 해시). 다음 업데이트 때 diff 의 기준. |
| `kb/VERSION.json` | 마지막으로 맞춘 앱 버전·날짜. |
| `eval/questions.json`, `eval/new_v.json`, `eval/equiv.json` | 검색 평가 질문과 "같이 정답으로 인정할 카드 묶음". |
| `kb/cards_archive/` | 아주 기술적으로 쓴 옛 카드 189장(사실 근거 확인용, 로드되지 않음). |

## 1. 절차 (이 순서대로)

### 1) 무엇이 바뀌었나 본다
```bash
python3 tools/sync_check.py            # AnyControl 폴더가 ../anycontrol-web 이 아니면 --web 경로
```
출력 구성: ① 사실 확인(현재 사실 목록) ② 변경 파일 수 ③ 바뀐 영역(주제별) ④ 문서의 추가·삭제된 줄(HANDOFF 포함) ⑤ 코드 변경 요약 ⑥ **다시 확인할 카드 목록**.
- 특정 파일 전체 diff: `--diff backend/src/vision_input/pipeline.py`, 전부: `--full`.
- `HANDOFF.md` 의 새로 추가된 부분이 곧 **업데이트 기록**이다. 가장 먼저 읽는다.
- "topic_map 에 없는 파일"이 나오면 어떤 카드와 관련 있는지 판단하고 `kb/topic_map.json` 에 항목을 추가한다.

### 2) 카드를 고친다
- **다시 확인할 카드**마다: 카드 답을 읽고, 코드·문서로 사실을 확인한 뒤 맞으면 그대로, 틀리면 고친다. **ko 와 en 을 항상 같이** 고친다(숫자도 똑같이).
- **새 기능** → 카드 추가(`kb_src/` 에 새 파일 `v6_*.txt` 를 만들거나 기존 파일 끝에). 방문객이 물을 만한 질문 4~6개(한국어) + 3~5개(영어)를 쓴다.
- **없어진 기능** → 카드 삭제하거나 "지금은 없어요"로 바꾸고, 그 카드를 `related` 로 가리키는 곳, `facts.json`/`topic_map.json` 의 id 도 정리한다.
- **수치가 바뀌었을 때**(성능 벤치 결과 등): 카드 본문의 수치, `status`(measured/verified/partial/not_validated/plan/info)도 다시 판단한다. 근거 없는 수치는 쓰지 않는다.
- 사실이 의도대로 바뀐 것이 확인되면 `kb/facts.json` 의 `expect` 를 새 값으로 고친다.
- 카드 형식과 말투 규칙은 `tools/card_spec_v2.md` (쉬운 말, 출처·전문용어 금지, 정직한 상태 표시, 김삼 개인정보 규칙).

### 3) "전체 검토"를 요청받았다면 (변경 diff 가 작아도)
```bash
python3 tools/sync_check.py --coverage     # 어떤 사실·영역에도 연결되지 않은 카드 = 낡아도 자동으로는 모르는 카드
```
이 목록의 카드는 사람이/AI 가 직접 AnyControl 폴더를 보고 확인한다. 그리고 모든 카드를 아래 기준으로 한 번씩 읽는다.
- 사실: 지금 코드·문서와 맞는가? 숫자·기본값·지원 환경·버전.
- 말투: 쉬운 말인가? 출처 표현("~기준", "소개서", "README", 파일명, 명령어)·전문용어·과장 표현이 없는가?
- 정직함: 확인 못 한 것을 확인된 것처럼 쓰지 않았는가? `status` 가 맞는가?
- 영어: 한국어와 같은 내용인가? 자연스러운가?
- 새로 생긴 질문거리: 업데이트로 방문객이 새로 궁금해할 만한 것이 없는가?

### 4) 검증 (모두 통과해야 함)
```bash
python3 tools/build_cards.py                          # kb_src → kb/cards (기존 표현 추가분 적용)
python3 -m bot validate                               # 카드 검증: 금지 표현, ko/en 숫자 일치, related 깨짐 …
python3 -m unittest discover -s tests                 # 55개 테스트(영어 답에 한글 없음, 김삼 규칙, 고정 문구, 한국어 기본 …)
python3 -m bot eval                                   # 기존 평가: 자신 있게 틀림 0~1건 유지
python3 -m bot eval --file eval/new_v.json            # 새 질문 평가: hit@3 100% 근처 유지
python3 -m bot eval --file eval/chat_heldout.json     # 대화체·이어 묻기·잡담·자료 밖: 상위3 88% 근처, 자료 밖 7/7 유지
python3 -m bot eval --file eval/chat_heldout.json --llm   # Qwen 켠 상태 (로컬에 모델이 있을 때)
```
새 카드를 추가했다면 그 카드를 다르게 표현한 질문 몇 개를 `eval/new_v.json` 에 `{"q": "...", "lang": "ko|en", "expect": ["카드id"]}` 로 추가한다. 같은 질문에 정당하게 함께 답이 될 수 있는 카드는 `eval/equiv.json` 의 묶음에 넣는다(서로 **다른 내용**을 답하는 카드는 묶지 말 것).

### 5) 기준을 저장하고 배포본을 만든다
```bash
python3 tools/sync_check.py --accept       # 사실이 모두 맞아야 저장됨. 현재 AnyControl 상태를 새 기준으로 (kb/snapshot, kb/VERSION.json)
python3 tools/make_package.py              # dist/anycontrol-chat.zip (부스 노트북용)
```
`HANDOFF.md` 에 이번 갱신을 몇 줄 적어 둔다(어떤 앱 버전, 무엇을 고쳤는지, 남은 불확실한 점).

## 2. 주의할 점
- **사실의 원천은 현재의 `../anycontrol-web`** 이다. `sources/` 폴더는 처음 카드를 만들 때 복사해 둔 옛 문서라서 낡았을 수 있다(근거 확인용으로만).
- 대회 소개서(`../AnyControl 소개서.md`)는 현재 v1.8.0 기능으로 갱신되어 있다. 그 안의 과거 성능 수치(2배 등)는 이전 측정이며 현재 버전에서 재측정한 값이 아니다. 벤치를 다시 돌린 결과가 `bench/` 에 새로 생겼다면 수치 카드를 갱신한다.
- 가격·라이선스·시장성·팀 구성 같은 것은 **자료에 없으면 "확인된 내용이 없어요"** 로 답한다. 지어내지 않는다.
- **김삼**: 질문받으면 "고려대학교 전기전자공학부에 재학 중인 학생이며 AWS AI Innovators Challenge 에서 이 프로젝트를 만들었다"는 것만 말하고, 나이·연락처·주소·이메일 등 다른 개인정보는 말하지 않는다 (`v-kimsam`, `g-team`, `v-team-people`; 테스트 `test_kimsam_only_discloses_department` 가 지킨다). 이 규칙은 앞으로도 유지한다.
- 개발 도구는 "주로 Kiro IDE" (카드 `v-tools-used`, `g-kiro`). 이 챗봇 자체는 Claude Code 의 도움으로 만들었다고 답한다 (`v-chatbot-how`). 바뀌면 카드를 고친다.
- 화면의 고정 문구(챗봇은 틀릴 수 있습니다 …)는 `kb/policy.json` 의 `ui.ko.disclaimer` / `ui.en.disclaimer` 에 있다.
- 카드 수가 늘면 질문끼리 서로 가로챌 수 있다. 검증 후 `eval` 에서 "자신 있게 틀림"이 생기면 카드의 질문 표현·`kw` 를 조정한다(평가 문장을 카드에 그대로 베끼는 것은 과적합이니 피한다).
- 새 컴퓨터에서의 실행 점검: `python3 tools/make_package.py` 로 zip 을 만들고, 다른 폴더(공백·한글 경로)에 풀어 `run.command`(Mac) / `run.bat`(Windows)로 실행해 본다. Windows 는 이 개발 환경에서 실제로 돌려 보지 못했다.
