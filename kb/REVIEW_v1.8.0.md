# AnyControl v1.8.0 지식 검토 (2026-10-19)

현재 코드, 웹 HANDOFF 전체 개선 이력, 한국어/영어 README, 소개서와 기존 답변 364개를 대조했다. 기존 답변 37개를 수정하고 사용법 24개를 추가해 총 388개다. 질문 표현·근거 경로만 보완한 카드는 답변 유지로 분류한다. 모든 카드의 답변이 실제 환경에서 검증됐다는 뜻은 아니다. 상태(info/partial/measured/not_validated/plan 등)와 기존 자체 측정의 제한을 유지한다.

## 기준과 보존 범위
- 현재 구현을 우선하고 이력 속 삭제된 UI를 현재 기능으로 안내하지 않는다. 이전 하이브리드·그리드·종이 등록을 정리했고, 물체 이름 변경 시 현재 ID 연결과 프로필 이름 기반 재연결을 구분했다.
- 초보자 순서: 카메라 고정/선택 → 물체 등록 또는 기본 맨손 활성화 → 마우스 모드 선택 또는 잭 연결 → 선택적 보정 → 가상 데모 → 필요 시 실제 출력. 각 단계, 예외와 대처를 한국어/영어로 설명한다.
- 손 XY/집게 클릭·드래그/스크롤, 맨손 잭의 두 집게 선택, 손 검출 필수 터치/진단 토글, 겹침 보호와 한계, 배치/매핑/전체 초기화, 저장 프로필·사용자 잭·카메라 보존, 시연 120초/자동 초기화를 반영했다.
- 현재 7개 데모, DJ 상단 패치·하우스·차임, 펜 Beta와 제한, 기본 입력 반전·성능 표시를 반영했다.
- 코드 근거: backend/src/vision_input/{auto_calibration,pipeline,mouse,object_touch}.py, server/control.py, mapping/; frontend/src/components/{AutoCalibration,MousePanel,PatchBay,HandInputCard,DisplayControls,CameraView,Hud,DjDemo,FruitDemo,PongDemo}.tsx 및 App.tsx. 정확한 경로는 kb/topic_map.json과 각 카드의 F 근거를 따른다.
- sources는 현재 안내 자료 사본이다. 포스터 원문과 archived 자료는 역사 자료로 보존하며 현재 버전 근거로 우선하지 않는다.
- 김삼 개인정보 제한과 고정 문구는 kb/policy.json을 바꾸지 않고 유지한다. 개인 관련 고정 답변을 확장하지 않았다. log/는 읽어서 답변을 만들거나 수정하지 않았다.
- 35개 자동 사실 점검과 소스 snapshot은 별도로 저장한다. 카드의 질문 문구를 그대로 묻는 검사는 검색 이해도 검증과 구분한다. 새 독립 표현 48문항을 current_v180.json에 추가했지만 실패를 보고 공통 표현을 보완한 개발 세트이며 실제 방문객 정확도로 해석하지 않는다.

## 카드별 처리 내역

| ID | 질문 | 처리 | 상태 |
|---|---|---|---|
| h-how-to-start | 처음에 어떻게 시작하나요? | 답변 갱신 | info |
| h-need-list | 준비물이 뭐예요? | 답변 유지 | info |
| h-mac-spec | 컴퓨터 사양이 어떻게 돼요? | 답변 유지 | info |
| h-memory-disk | 용량은 얼마나 필요해요? | 답변 유지 | info |
| h-windows | 윈도우에서도 되나요? | 답변 유지 | info |
| h-intel-mac | 인텔 맥에서도 되나요? | 답변 유지 | info |
| h-phone-app | 아이폰이나 안드로이드에서 앱으로 쓸 수 있나요? | 답변 유지 | info |
| h-iphone-camera | 아이폰을 카메라로 쓸 수 있나요? | 답변 유지 | info |
| h-iphone-conditions | 아이폰은 어떤 모델이어야 해요? | 답변 유지 | info |
| h-webcam | 일반 웹캠도 되나요? | 답변 유지 | partial |
| h-camera-required | 카메라가 꼭 있어야 해요? | 답변 유지 | info |
| h-where-download | 어디서 다운로드해요? | 답변 유지 | info |
| h-install-how | 설치는 어떻게 하나요? | 답변 유지 | info |
| h-install-time | 설치하는 데 얼마나 걸려요? | 답변 유지 | info |
| h-internet-install | 설치할 때 인터넷이 필요해요? | 답변 유지 | info |
| h-offline | 인터넷 없이도 쓸 수 있어요? | 답변 유지 | info |
| h-free | 무료인가요? | 답변 유지 | not_validated |
| h-security-block | 처음 열 때 보안 때문에 막혀요 | 답변 유지 | info |
| h-exec-permission | '적절한 접근 권한이 없기 때문에' 라고 나와요 | 답변 유지 | info |
| h-uninstall | 어떻게 삭제해요? | 답변 유지 | info |
| h-update | 업데이트는 어떻게 해요? | 답변 유지 | info |
| g-what-is | AnyControl이 뭐예요? | 답변 유지 | info |
| g-why-made | 왜 만들었어요? | 답변 유지 | info |
| g-who-for | 누구를 위한 서비스예요? | 답변 유지 | info |
| g-accessibility | 몸이 불편한 사람도 쓸 수 있나요? | 답변 유지 | partial |
| g-exhibit | 전시장이나 키오스크에도 쓸 수 있나요? | 답변 유지 | info |
| g-no-mouse | 마우스가 없을 때 쓸 수 있나요? | 답변 유지 | info |
| g-edu-game-create | 교육이나 게임, 창작에도 쓸 수 있나요? | 답변 유지 | info |
| g-examples | 어떻게 쓸 수 있는지 예를 들어 주세요 | 답변 유지 | info |
| g-three-inputs | 어떤 입력 방식이 있어요? | 답변 유지 | info |
| g-object-mode | 물체로 마우스를 움직이는 법 | 답변 갱신 | info |
| g-hand-mode | 맨손으로 조작할 수 있나요? | 답변 갱신 | info |
| g-pen-mode | 펜으로 그림을 그릴 수 있나요? | 답변 유지 | partial |
| g-multi-object | 물체 여러 개를 한 번에 쓸 수 있어요? | 답변 유지 | verified |
| g-any-motion | 어떤 움직임을 입력으로 쓸 수 있어요? | 답변 유지 | info |
| g-demos | 체험해 볼 수 있는 데모가 있어요? | 답변 갱신 | info |
| g-vs-others | 다른 방식이랑 뭐가 달라요? | 답변 유지 | info |
| g-recover | 가려져도 다시 찾는다는 게 무슨 뜻이에요? | 답변 갱신 | partial |
| g-recover-numbers | 얼마나 잘 다시 찾아요? | 답변 유지 | partial |
| g-hardware | 뭐가 필요해요? | 답변 유지 | info |
| g-os-support | 윈도우에서도 되나요? | 답변 유지 | plan |
| g-ondevice | 왜 클라우드가 아니라 내 컴퓨터에서 처리해요? | 답변 유지 | info |
| g-aws | AWS를 쓰나요? | 답변 유지 | plan |
| g-llm | LLM이나 생성형 AI를 쓰나요? | 답변 유지 | plan |
| g-tech-short | 기술적으로 어떻게 동작해요? | 답변 유지 | info |
| g-team | 팀 소개해 주세요 | 답변 유지 | info |
| g-contest | 어떤 대회에 나온 거예요? | 답변 유지 | info |
| g-kiro | Kiro로 어떻게 만들었어요? | 답변 유지 | info |
| g-hardest | 만들면서 가장 어려웠던 점은요? | 답변 유지 | partial |
| g-limits | 아직 부족한 점은 뭐예요? | 답변 유지 | partial |
| g-tablet-deck | 그림 태블릿이나 스트림덱을 대체할 수 있어요? | 답변 유지 | partial |
| g-business | 상품으로 팔 수 있어요? | 답변 유지 | not_validated |
| g-price | 얼마예요? | 답변 유지 | not_validated |
| g-future | 앞으로 계획이 뭐예요? | 답변 유지 | plan |
| g-name | 이름이 무슨 뜻이에요? | 답변 유지 | info |
| g-safe-real | 내 마우스를 마음대로 움직이면 위험하지 않나요? | 답변 유지 | verified |
| g-try | 직접 써 볼 수 있어요? | 답변 유지 | info |
| g-setup-flow | 처음 쓸 때 어떻게 시작해요? | 답변 갱신 | info |
| g-tested | 테스트는 해 봤나요? | 답변 유지 | partial |
| g-speed | 반응 속도가 빨라요? | 답변 유지 | measured |
| g-privacy-server | 개인정보는 안전한가요 | 답변 유지 | verified |
| g-kids-glasses | 아이도 쓸 수 있나요? | 답변 유지 | not_validated |
| g-open-source | 코드는 공개돼 있어요? | 답변 유지 | info |
| w-one-line | 한 문장으로 말하면 뭐예요? | 답변 유지 | info |
| w-explain-child | 어린이에게 설명하듯이 알려 주세요 | 답변 유지 | info |
| w-first-impression | 이 프로젝트의 가장 신기한 장면은 뭐예요? | 답변 유지 | info |
| w-favorite | 팀에서 가장 마음에 들어 하는 기능이 뭐예요? | 답변 유지 | info |
| w-secret-sauce | 핵심 아이디어를 한 번 더 쉽게 알려 주세요 | 답변 유지 | info |
| w-object-fruit | 바나나나 사과 같은 과일로도 돼요? | 답변 유지 | not_validated |
| w-object-toy | 인형이나 레고 같은 장난감도 돼요? | 답변 유지 | partial |
| w-object-stationery | 지우개나 리모컨으로도 마우스를 쓸 수 있어요? | 답변 유지 | info |
| w-object-phone | 스마트폰을 물체로 등록해도 돼요? | 답변 유지 | not_validated |
| w-two-hands | 두 손을 동시에 쓸 수 있어요? | 답변 갱신 | partial |
| w-mapping-combine | 물체 두 개를 같은 입력에 연결하면 어떻게 돼요? | 답변 유지 | info |
| w-mapping-limit | 연결 설정은 몇 개까지 만들 수 있어요? | 답변 유지 | info |
| w-lantern-game | 서바이벌 게임 데모는 어떤 게임이에요? | 답변 갱신 | info |
| w-paint-demo | 그림판 데모에서는 뭘 해 볼 수 있어요? | 답변 유지 | partial |
| w-virtual-desktop-demo | 가상 데스크톱 데모는 뭐예요? | 답변 유지 | info |
| w-wasd | WASD 설정은 뭐예요? | 답변 유지 | info |
| w-joystick-mouse | 조이스틱 마우스는 뭐예요? | 답변 유지 | info |
| w-calib-steps | 자동 보정에서는 어떤 동작을 해요? | 답변 갱신 | info |
| w-who-school | 어느 학교 학생이 만들었어요? | 답변 유지 | info |
| w-howlong-built | 만드는 데 얼마나 걸렸어요? | 답변 갱신 | not_validated |
| w-why-built-alone | 혼자 만든 거예요? | 답변 유지 | info |
| w-learn-to-build | 이런 걸 만들려면 뭘 공부해야 해요? | 답변 유지 | info |
| w-developer-use | 개발자인데 제 프로그램에 붙여 쓸 수 있어요? | 답변 유지 | partial |
| w-office-school | 학교나 회사에서도 쓸 수 있어요? | 답변 유지 | not_validated |
| w-elderly | 어르신도 쓸 수 있어요? | 답변 유지 | not_validated |
| w-child-safe | 아이가 써도 안전해요? | 답변 유지 | partial |
| w-not-covered-ideas | 스마트홈이나 로봇, VR에도 쓸 수 있어요? | 답변 유지 | not_validated |
| w-music-art | 악기나 예술 작품에 쓰면 어때요? | 답변 유지 | not_validated |
| w-learn-ai | AI를 직접 학습시켰어요? | 답변 유지 | info |
| w-why-fast-ai | AI 모델을 고르는 데 속도를 어떻게 쟀어요? | 답변 유지 | measured |
| w-hand-engines | 손 인식은 어떤 방식이 더 잘 돼요? | 답변 유지 | partial |
| w-sam-difference | SAM 같은 분할 AI랑 뭐가 달라요? | 답변 유지 | info |
| w-vs-depth-camera | 키넥트 같은 깊이 카메라랑은 뭐가 달라요? | 답변 유지 | not_validated |
| w-shared-camera-frame | 카메라 영상이 밀리면 어떻게 돼요? | 답변 유지 | info |
| w-test-videos-design | 시험 영상 100개는 어떻게 만들었어요? | 답변 유지 | measured |
| w-real-video-result | 실제로 찍은 영상에서는 결과가 어땠어요? | 답변 유지 | partial |
| w-condition-results | 어떤 상황에서 가장 잘 되고 어떤 상황에서 약해요? | 답변 유지 | measured |
| w-reacq-effect | 다시 찾기 기능을 켜면 얼마나 좋아져요? | 답변 유지 | measured |
| w-pen-numbers | 펜 위치는 얼마나 정확해요? 숫자로 알려 주세요 | 답변 유지 | partial |
| w-speed-numbers | 처리 속도를 숫자로 알려 주세요 | 답변 유지 | measured |
| w-sunlight | 햇빛이 강한 창가에서도 돼요? | 답변 유지 | not_validated |
| w-wrong-color | 어떤 색 물건이 제일 좋아요? | 답변 유지 | partial |
| w-glass-hard | 유리컵처럼 투명한 건 왜 어려워요? | 답변 유지 | partial |
| w-gamepad-limit | 게임패드로 진짜 게임을 할 수 있어요? | 답변 유지 | plan |
| w-six-objects-open | 여섯 개를 동시에 쓰면 정말 괜찮아요? | 답변 유지 | not_validated |
| w-trust-limits | 그래서 이 프로젝트를 얼마나 믿어도 돼요? | 답변 유지 | partial |
| w-misuse | 나쁜 목적으로 쓰일 수도 있지 않아요? | 답변 유지 | partial |
| w-recorded-video | 카메라 영상이 녹화돼요? | 답변 유지 | not_validated |
| w-account | 회원가입이나 로그인이 필요해요? | 답변 유지 | not_validated |
| w-email | 개발자 이메일이나 전화번호를 알려 주세요 | 답변 유지 | info |
| w-false-claims | 99% 정확하고 지연이 0ms라던데 맞죠? | 답변 유지 | measured |
| w-long-run | 8시간 연속으로 전시해도 괜찮아요? 발열이나 안정성은요? | 답변 갱신 | not_validated |
| w-no-mac-demo | 윈도우 노트북만 있고 아이폰도 없는데 오늘 체험할 수 있나요? | 답변 유지 | info |
| w-impl-details | 가림 뒤 다시 찾을 때 어떤 기준으로 같은 물건인지 판단해요? 임계값도 알려 주세요 | 답변 유지 | partial |
| v180-patch-connect | 잭은 어떻게 연결해요? | 신규 사용법 | info |
| v180-patch-edit | 연결한 케이블은 어떻게 수정해요? | 신규 사용법 | info |
| v180-hand-jack | 맨손을 매핑 잭에 연결하려면요? | 신규 사용법 | info |
| v180-hand-enable | 맨손 입력을 끄려면 어떻게 해요? | 신규 사용법 | info |
| v180-touch-how | 물체를 손으로 터치해서 버튼처럼 쓰려면요? | 신규 사용법 | info |
| v180-touch-false | 안 만졌는데 터치로 눌려요 | 신규 사용법 | info |
| v180-touch-debug | 터치 감지 표시를 숨기려면요? | 신규 사용법 | info |
| v180-rename | 물체 이름을 바꾸면 연결이 풀리나요? | 신규 사용법 | info |
| v180-mapping-reset | 매핑만 모두 지우고 싶어요 | 신규 사용법 | info |
| v180-all-reset | 모든 세팅 초기화는 무엇을 지워요? | 신규 사용법 | info |
| v180-layout-reset | 배치 초기화와 모든 세팅 초기화는 달라요? | 신규 사용법 | info |
| v180-panels | 패널 위치를 옮길 수 있어요? | 신규 사용법 | info |
| v180-idle | 가만히 두면 시연 영상으로 바뀌나요? | 신규 사용법 | info |
| v180-performance | 성능 패널은 어떻게 읽어요? | 신규 사용법 | info |
| v180-flip | 영상 좌우 반전과 입력 좌우 반전 차이 | 신규 사용법 | info |
| v180-dj-how | DJ 셋은 어떻게 조작해요? | 신규 사용법 | info |
| v180-dj-sound | DJ 음악은 무슨 곡이에요? | 신규 사용법 | info |
| v180-fruit | 과일 받기는 어떻게 해요? | 신규 사용법 | info |
| v180-pong | 퐁 게임은 어떻게 해요? | 신규 사용법 | info |
| v180-removed | 그리드나 두더지 게임이 안 보여요 | 신규 사용법 | info |
| v180-calibration-center | 보정할 때 매번 중앙에 다시 놔야 하나요? | 신규 사용법 | info |
| v180-calibration-options | 보정에서 클릭도 꼭 해야 해요? | 신규 사용법 | info |
| v180-missing-jacks | 잭이나 연결선이 갑자기 없어져요 | 신규 사용법 | info |
| v180-object-touch-or-hand | 물체 터치와 맨손 집게는 뭐가 달라요? | 신규 사용법 | info |
| w-passerby | 지나가다가 들렀어요. 간단히 알려 주세요 | 답변 유지 | info |
| w-judge | 심사위원인데 핵심 평가 포인트만 알려 주세요 | 답변 유지 | info |
| w-professor | 교수님이나 전문가가 볼 만한 기술적인 부분이 있어요? | 답변 유지 | info |
| w-student-report | 과제나 리포트에 이 내용을 인용해도 돼요? | 답변 유지 | info |
| w-press | 취재나 기사 때문에 문의하고 싶어요 | 답변 유지 | not_validated |
| w-venue | 화장실이나 와이파이는 어디에 있어요? | 답변 유지 | info |
| w-english-visitor | 영어로 설명해 줄 수 있어요? | 답변 유지 | info |
| w-text-size | 글씨가 너무 작아요. 크게 볼 수 있어요? | 답변 유지 | info |
| w-my-name | 제 이름은 민수예요 | 답변 유지 | info |
| w-quiz | AnyControl 퀴즈를 내 주세요 | 답변 유지 | info |
| w-fun-facts | 재미있는 사실 하나만 알려 주세요 | 답변 유지 | info |
| w-why-mac-only | 왜 Mac에서만 되는 거예요? | 답변 유지 | info |
| w-cloud-mode | 나중에 클라우드로 더 정확하게 만들 수 있어요? | 답변 유지 | plan |
| w-text-register | 말로 "빨간 펜을 추적해 줘"처럼 등록할 수 있어요? | 답변 유지 | plan |
| w-ground-truth | 시험의 정답은 어떻게 정했어요? | 답변 유지 | info |
| w-reproduce | 결과를 직접 다시 재현해 볼 수 있어요? | 답변 유지 | partial |
| w-quit-time | 브라우저를 닫으면 얼마 뒤에 꺼져요? | 답변 유지 | info |
| w-install-where | 설치하면 어느 폴더에 깔려요? | 답변 유지 | info |
| w-better-than-mouse | 그냥 마우스를 쓰는 것보다 더 좋아요? | 답변 유지 | partial |
| w-arm-fatigue | 오래 쓰면 팔이나 손이 안 아파요? | 답변 유지 | not_validated |
| w-other-surface | 책상이 아니라 벽이나 바닥에서도 써요? | 답변 유지 | not_validated |
| w-why-not-phone-app | 왜 아이폰 앱으로 만들지 않았어요? | 답변 유지 | info |
| w-gpu-need | 그래픽 카드가 꼭 있어야 해요? | 답변 유지 | plan |
| w-first-fail | 가장 먼저 실패하는 상황은 뭐예요? | 답변 유지 | partial |
| w-how-to-use | 어떻게 써요? | 답변 갱신 | info |
| v-tools-used | 어떤 도구로 개발했어요? | 답변 유지 | info |
| v-ai-made | AI로 만든 건가요? 직접 만든 건가요? | 답변 유지 | info |
| v-spec-driven | 요구사항을 먼저 글로 쓰고 개발했다는 게 무슨 뜻이에요? | 답변 유지 | info |
| v-failed-ideas | 시도했다가 실패하거나 버린 방법도 있어요? | 답변 유지 | info |
| v-chatbot-how | 이 챗봇은 어떻게 만들었어요? | 답변 유지 | info |
| v-chatbot-structure | 이 챗봇은 어떤 구조로 동작해요? | 답변 유지 | info |
| v-chatbot-wrong | 챗봇이 틀린 답을 할 수도 있나요? | 답변 유지 | info |
| v-chatbot-unknown | 모르는 질문을 하면 어떻게 돼요? | 답변 유지 | info |
| v-chatbot-offline | 이 챗봇은 인터넷이 필요해요? | 답변 유지 | info |
| v-chatbot-llm | 이 챗봇은 ChatGPT 같은 생성형 AI인가요? | 답변 유지 | info |
| v-chatbot-languages | 영어로도 질문할 수 있나요? | 답변 유지 | info |
| v-kimsam | 김삼은 누구예요? | 답변 유지 | info |
| v-team-people | 팀은 몇 명이에요? | 답변 유지 | info |
| v-explain-easy | 아주 쉽게 설명해 주세요 | 답변 유지 | info |
| v-summary-30s | 30초로 요약해 주세요 | 답변 유지 | info |
| v-top-strengths | 가장 큰 장점이 뭐예요? | 답변 갱신 | info |
| v-top-weakness | 가장 아쉬운 점이 뭐예요? | 답변 유지 | partial |
| v-version | 지금 버전이 몇이에요? | 답변 갱신 | info |
| v-app-or-web | 앱이에요, 웹사이트예요? | 답변 유지 | info |
| v-vision-input | 비전 인풋(Vision Input)이 뭐예요? | 답변 유지 | info |
| v-poster-demo-video | 시연 영상이나 포스터를 볼 수 있어요? | 답변 갱신 | info |
| v-virtual-vs-real | 가상 모드와 실제 입력은 뭐가 달라요? | 답변 유지 | verified |
| v-register-pen | 펜은 어떻게 등록해요? | 답변 유지 | partial |
| v-calib-time | 설정하는 데 시간이 얼마나 걸려요? | 답변 갱신 | info |
| v-racing-how | 레이싱 게임은 어떻게 조작해요? | 답변 갱신 | partial |
| v-presets | 바로 쓸 수 있는 준비된 설정이 있어요? | 답변 유지 | info |
| v-show-and-set | 동작을 보여 주면 설정이 된다는 게 무슨 뜻이에요? | 답변 유지 | info |
| v-sensitivity | 커서가 너무 빠르거나 느려요. 조절할 수 있나요? | 답변 갱신 | info |
| v-tutorial | 처음 쓰는 사람을 위한 안내가 있어요? | 답변 유지 | info |
| v-view-camera | 내 카메라 화면을 볼 수 있어요? | 답변 유지 | info |
| v-typing | 키보드처럼 글자를 칠 수 있어요? | 답변 유지 | info |
| v-voice | 목소리로 명령할 수 있어요? | 답변 유지 | plan |
| v-project-size | 얼마나 큰 프로젝트예요? | 답변 유지 | info |
| v-mascot | 포스터에 있는 캐릭터는 뭐예요? | 답변 유지 | not_validated |
| v-wow | 신기해요! 진짜 되는 거예요? | 답변 유지 | info |
| v-already-exists | 이런 건 이미 있지 않아요? | 답변 유지 | info |
| v-vs-products | 다른 회사 제품과 비교하면 어때요? | 답변 유지 | not_validated |
| v-desk-controller | 책상 위 물건이 곧 컨트롤러라는 게 무슨 뜻이에요? | 답변 유지 | partial |
| v-why-ai | 이게 왜 AI 프로젝트예요? | 답변 유지 | info |
| v-proud | 가장 자랑스러운 점은 뭐예요? | 답변 유지 | info |
| v-honesty-why | 왜 이렇게 단점과 한계를 솔직하게 알려 줘요? | 답변 유지 | info |
| v-confirmed-vs-not | 확실히 확인된 것과 아닌 것을 정리해 주세요 | 답변 유지 | partial |
| v-fair-comparison | 평가에서 일부러 유리한 조건만 고른 건 아닌가요? | 답변 유지 | measured |
| v-model-names | 정확히 어떤 AI 모델을 써요? 모델 이름이 뭐예요? | 답변 유지 | info |
| v-deep-tech | 전문 용어(칼만 필터, 광학 흐름, 마스크 등)를 쉽게 설명해 주세요 | 답변 유지 | info |
| v-recovery-meaning | 복구 시간이 뭐예요? 단축됐다는 게 무슨 뜻이에요? | 답변 유지 | measured |
| v-no-search-while-tracking | 잘 따라가는 동안에는 왜 다시 찾지 않아요? | 답변 유지 | info |
| v-hand-not-in-memory | 물건을 쥐어도 손 모양이 물건의 기억에 섞이지 않아요? | 답변 갱신 | partial |
| v-dev-mode | 개발자 모드가 뭐예요? | 답변 갱신 | info |
| v-code-quality | 코드 품질은 어떻게 관리했어요? | 답변 갱신 | verified |
| v-modify-code | 코드를 직접 고쳐서 써 볼 수 있어요? | 답변 유지 | info |
| v-camera-distance | 카메라는 책상에서 얼마나 떨어져 있어야 해요? | 답변 유지 | not_validated |
| v-desk-area | 책상 영역을 설정한다는 건 뭐예요? | 답변 갱신 | info |
| v-resolution | 카메라 화질이나 해상도는 어느 정도여야 해요? | 답변 유지 | partial |
| v-phone-call | iPhone에 전화가 오거나 화면이 잠기면 어떻게 돼요? | 답변 유지 | not_validated |
| v-click-styles | 클릭 방식이 두 가지라던데요? | 답변 갱신 | partial |
| v-pinch-sensitivity | 집기 민감도가 뭐예요? | 답변 갱신 | info |
| v-3sec | 3초 유예가 뭐예요? | 답변 유지 | verified |
| v-ipad-macmini | 아이패드나 맥 미니에서도 쓸 수 있어요? | 답변 유지 | plan |
| v-presentation | 발표할 때 슬라이드를 넘기는 데 쓸 수 있어요? | 답변 유지 | plan |
| v-body-foot | 발이나 몸으로도 조작할 수 있어요? | 답변 유지 | plan |
| v-pen-accuracy | 펜 입력은 얼마나 정확해요? | 답변 유지 | partial |
| v-pen-flip | 펜을 거꾸로 잡으면 어떻게 돼요? | 답변 유지 | partial |
| v-pen-color | 펜 색이나 굵기를 바꿀 수 있어요? | 답변 갱신 | not_validated |
| v-iphone-wireless | 아이폰을 케이블 없이 무선으로 연결해도 돼요? | 답변 유지 | info |
| v-camera-count | 카메라는 몇 대 필요해요? | 답변 유지 | info |
| v-desk-view | 위에서 내려다보는 카메라(Desk View)도 돼요? | 답변 갱신 | partial |
| v-camera-conflict | 화상회의나 다른 카메라 앱과 같이 쓸 수 있어요? | 답변 유지 | not_validated |
| v-permission-denied | 권한을 허용하지 않으면 어떻게 돼요? | 답변 유지 | info |
| v-install-changes | 설치하면 내 Mac에 어떤 변화가 생겨요? | 답변 유지 | info |
| v-safe-download | 서명이 안 된 파일이라는데 안전한가요? | 답변 유지 | info |
| v-file-size | 설치 파일이 왜 이렇게 커요? | 답변 유지 | info |
| v-terminal-window | 검은 터미널 창이 같이 열리는데 닫아도 돼요? | 답변 유지 | info |
| v-browser-choice | 어떤 브라우저로 열어야 해요? | 답변 유지 | info |
| v-no-camera-try | 카메라 없이 체험해 볼 수 있어요? | 답변 유지 | info |
| v-remote-hack | 다른 사람이 인터넷으로 내 컴퓨터를 조종할 수 있어요? | 답변 유지 | verified |
| v-camera-always-on | 카메라가 계속 켜져 있는 거 아니에요? | 답변 유지 | verified |
| v-people-in-view | 지나가는 사람이 카메라에 찍히면 어떻게 돼요? | 답변 유지 | not_validated |
| v-real-input-verified | 진짜 마우스를 움직이는 건 확인했어요? | 답변 유지 | not_validated |
| v-ui-state | 화면(UI)은 완성됐어요? | 답변 갱신 | plan |
| v-3d | 3D로도 추적하나요? | 답변 유지 | plan |
| v-multi-user | 여러 사람이 동시에 쓸 수 있어요? | 답변 갱신 | not_validated |
| v-judging | 대회에서 뭘 평가해요? | 답변 유지 | info |
| v-lookalike-plan | 닮은 물건 문제는 앞으로 어떻게 해결할 거예요? | 답변 유지 | plan |
| v-windows-when | Windows 버전은 언제 나와요? | 답변 유지 | plan |
| v-easy-install | 컴퓨터를 잘 몰라도 설치할 수 있어요? | 답변 유지 | partial |
| v-who-are-you | 너는 누구야? | 답변 유지 | info |
| v-pets | 고양이나 강아지가 지나가면 어떻게 돼요? | 답변 유지 | not_validated |
| v-weird-objects | 어떤 물건으로 해 봤어요? 재밌는 사용 예가 있어요? | 답변 유지 | info |
| v-contact | 개발팀에게 질문하거나 오류를 알리려면 어떻게 해요? | 답변 유지 | info |
| w-booth-what | 여기는 뭘 하는 부스예요? | 답변 유지 | info |
| w-what-to-see | 부스에서 볼 수 있는 게 뭐예요? | 답변 유지 | info |
| w-presenter | 설명해 줄 사람은 어디서 만날 수 있어요? | 답변 유지 | info |
| w-presenter-who | 발표자는 누구예요? | 답변 유지 | info |
| w-presenter-away | 발표자는 어디 갔어요? | 답변 유지 | info |
| w-schedule | 발표나 시연은 몇 시에 해요? | 답변 유지 | not_validated |
| w-demo-here | 지금 여기서 직접 해 볼 수 있어요? | 답변 유지 | info |
| w-photo | 사진이나 영상을 찍어도 돼요? | 답변 유지 | not_validated |
| w-materials | 발표 자료나 포스터를 받을 수 있어요? | 답변 유지 | info |
| w-link-qr | 링크나 QR코드가 있어요? | 답변 유지 | info |
| w-contest-more | 이 대회는 어떤 대회예요? | 답변 유지 | info |
| w-prize | 상 받았어요? 몇 등이에요? | 답변 유지 | not_validated |
| w-other-teams | 다른 팀 작품도 알려 줄 수 있어요? | 답변 유지 | info |
| w-poster-explain | 포스터에 적힌 내용을 쉽게 설명해 주세요 | 답변 유지 | info |
| w-poster-numbers | 포스터의 "약 2.2배"는 무슨 뜻이에요? | 답변 유지 | measured |
| w-more-confusion | 성능이 좋아졌는데 약해진 부분도 있어요? | 답변 유지 | measured |
| w-poster-limits | 포스터 맨 아래에 적힌 후속 과제가 뭐예요? | 답변 유지 | partial |
| w-research-refs | 어떤 연구를 참고했어요? | 답변 유지 | info |
| w-next-steps | 다음에는 뭘 가장 먼저 개선할 거예요? | 답변 유지 | plan |
| w-chat-how-use | 이 챗봇은 어떻게 쓰면 돼요? | 답변 유지 | info |
| w-chat-smalltalk | AnyControl 말고 다른 이야기도 할 수 있어요? | 답변 유지 | info |
| w-chat-model | 이 챗봇 안에 들어 있는 AI는 뭐예요? | 답변 유지 | info |
| w-chat-slow | 왜 가끔 답이 느려요? | 답변 유지 | info |
| w-chat-feedback | 챗봇에 의견이나 잘못된 답을 알리려면요? | 답변 유지 | info |
| w-bot-human | 너 사람이야? | 답변 유지 | info |
| w-bot-age | 몇 살이에요? | 답변 유지 | info |
| w-bot-feel | 지금 기분이 어때요? | 답변 유지 | info |
| w-bot-can | 너 뭘 할 수 있어? | 답변 유지 | info |
| i-how-simple | 어떻게 동작해요? | 답변 유지 | info |
| i-camera-to-mouse | 카메라로 본 걸 어떻게 마우스로 바꿔요? | 답변 유지 | info |
| i-fast-plus-ai | 빠른 추적이랑 AI는 어떻게 같이 써요? | 답변 유지 | verified |
| i-why-not-ai-only | AI만 쓰면 안 되나요? | 답변 유지 | measured |
| i-occlusion-return | 손으로 가리면 어떻게 돼요? | 답변 유지 | partial |
| i-offscreen-return | 화면 밖으로 나갔다 들어오면요? | 답변 유지 | measured |
| i-why-find-again | 어떻게 다시 찾아요? | 답변 유지 | verified |
| i-lookalike | 비슷한 물건이 있으면요? | 답변 유지 | verified |
| i-why-no-guess | 왜 헷갈리면 안 고르고 기다려요? | 답변 유지 | verified |
| i-reselect | 잘못 따라가면 어떻게 고쳐요? | 답변 유지 | verified |
| i-lighting | 조명이 바뀌어도 되나요? | 답변 유지 | partial |
| i-background | 배경이 복잡해도 돼요? | 답변 유지 | partial |
| i-rotation | 물체를 돌리면요? | 답변 유지 | partial |
| i-dark-shiny | 어두운 곳에서도 되나요? | 답변 유지 | partial |
| i-max-objects | 물체를 몇 개까지 쓸 수 있어요? | 답변 유지 | verified |
| i-many-objects-perf | 여러 개 쓰면 느려지나요? | 답변 유지 | not_validated |
| i-pen-contact | 펜이 책상에 닿은 걸 어떻게 알아요? | 답변 유지 | measured |
| i-pen-shadow | 그림자도 쓰나요? | 답변 유지 | measured |
| i-pen-few-videos | 펜은 얼마나 검증됐어요? | 답변 유지 | partial |
| i-pen-hidden | 손이 펜을 가리면 어떻게 돼요? | 답변 유지 | verified |
| i-stroke-flick | 그림 그릴 때 선 끝이 튀지 않게 했다던데요 | 답변 유지 | measured |
| i-stroke-tradeoff | 선 끝을 줄이면 단점은 없나요? | 답변 유지 | measured |
| i-still-jitter | 가만히 두면 커서가 떨리지 않나요? | 답변 유지 | measured |
| i-still-why | 가만히 있는데 왜 커서가 흘러갔어요? | 답변 유지 | measured |
| i-cursor-spike | 커서 튐을 줄이는 기능이 있어요? | 답변 유지 | verified |
| i-spike-unmeasured | 튐 줄이는 기능 효과는 확인했어요? | 답변 유지 | not_validated |
| i-anchor-point | 물건을 쥐면 커서가 흔들리지 않나요? | 답변 유지 | verified |
| i-anchor-limit | 기준점을 써도 여전히 흔들리는 게 있나요? | 답변 유지 | partial |
| i-depth-how | 앞뒤 움직임은 어떻게 알아요? | 답변 유지 | partial |
| i-depth-camera-setup | 카메라는 어디에 둬요? | 답변 유지 | partial |
| i-depth-ai | 깊이용 AI도 있어요? | 답변 유지 | info |
| i-depth-not-validated | 깊이 AI가 크기 방식보다 좋은가요? | 답변 유지 | not_validated |
| i-which-ai | 어떤 AI를 써요? | 답변 유지 | info |
| i-why-that-ai | 왜 그 AI를 골랐어요? | 답변 유지 | measured |
| i-hand-find | 손은 어떻게 찾아요? | 답변 유지 | partial |
| i-vs-classic | 성능이 얼마나 좋아요? | 답변 유지 | measured |
| i-weak-cases | 어떤 상황에 약해요? | 답변 유지 | measured |
| i-real-video-few | 실제 영상으로도 시험했어요? | 답변 유지 | partial |
| i-latency-honest | 반응 속도는 어때요? | 답변 유지 | partial |
| i-accuracy-honest | 정확도가 100%예요? | 답변 유지 | partial |
| i-environment-honest | 다른 환경에서도 잘 되나요? | 답변 유지 | not_validated |
| i-commercial | 상용 수준이에요? | 답변 유지 | info |
| i-unverified | 아직 검증 못 한 게 뭐예요? | 답변 유지 | not_validated |
| i-no-sota | 최신 연구들과 비교했어요? | 답변 유지 | not_validated |
| h-object-mouse | 물체를 마우스로 쓰려면 어떻게 해요? | 답변 갱신 | info |
| h-object-kinds | 어떤 물체를 쓸 수 있어요? | 답변 유지 | partial |
| h-bare-hand | 맨손으로 마우스를 쓸 수 있어요? | 답변 갱신 | partial |
| h-pen-draw | 펜으로 그릴 수 있어요? | 답변 유지 | partial |
| h-hybrid-easy | 한 손 하이브리드가 뭐예요? | 답변 갱신 | partial |
| h-hybrid-limit | 하이브리드나 손 클릭은 잘 되나요? | 답변 갱신 | not_validated |
| h-games | 게임에도 쓸 수 있어요? | 답변 유지 | not_validated |
| h-calibration | 보정이 뭐예요? | 답변 갱신 | partial |
| h-practice-mode | 연습해 볼 수 있는 모드가 있어요? | 답변 유지 | partial |
| h-save-settings | 설정을 저장할 수 있어요? | 답변 갱신 | info |
| h-quit | 어떻게 꺼요? | 답변 유지 | info |
| h-emergency-stop | 마우스가 제멋대로 움직이면 어떻게 해요? | 답변 유지 | info |
| h-privacy | 내 영상이 밖으로 나가나요? | 답변 유지 | info |
| h-permissions | 어떤 권한이 필요해요? | 답변 유지 | info |
| h-why-accessibility | 손쉬운 사용 권한이 왜 필요해요? | 답변 유지 | info |
| h-safety-guards | 안전장치가 있어요? | 답변 유지 | partial |
| h-tip-setup | 잘 쓰려면 어떻게 놓아야 해요? | 답변 유지 | info |
| h-tip-dark | 어두운 곳에서도 되나요? | 답변 유지 | not_validated |
| h-tip-reflection | 반사가 심한 책상에서도 되나요? | 답변 유지 | not_validated |
| h-similar-objects | 똑같이 생긴 물체가 둘이면 어떻게 돼요? | 답변 유지 | info |
| h-hand-cover | 손으로 물체를 가리면 어떻게 돼요? | 답변 유지 | info |
| h-unknown-people | 안경 써도 돼요? | 답변 유지 | not_validated |
| h-ts-camera | 카메라가 안 보여요 | 답변 유지 | info |
| h-ts-iphone-missing | 아이폰이 카메라 목록에 안 나와요 | 답변 유지 | info |
| h-ts-shaky | 추적이 흔들려요 | 답변 유지 | info |
| h-ts-mouse-no-move | 마우스가 안 움직여요 | 답변 유지 | info |
| h-ts-browser | 브라우저가 저절로 안 열려요 | 답변 유지 | info |
| h-ts-install-fail | 설치가 중간에 멈췄어요 | 답변 유지 | info |
| h-ts-wont-quit | 탭을 닫아도 안 꺼져요 | 답변 유지 | info |
| h-opensource | 오픈소스인가요? | 답변 유지 | info |
| v-why-depth-updown | 물건을 앞뒤로 움직이면 왜 커서가 위아래로 가요? | 답변 유지 | partial |
| v-camera-place | 카메라는 어디에 어떻게 놓아야 해요? | 답변 유지 | info |
| v-object-size | 아주 작은 물건이나 큰 물건도 되나요? | 답변 유지 | not_validated |
| v-transparent-shiny | 투명하거나 반짝이는 물건도 되나요? | 답변 유지 | partial |
| v-hold-object | 물건을 손에 쥐고 움직여도 돼요? | 답변 유지 | partial |
| v-lost-input | 물건이 안 보이면 입력은 어떻게 돼요? | 답변 유지 | verified |
| v-face | 얼굴이나 고개로도 조작할 수 있어요? | 답변 유지 | not_validated |
| v-click-drag-scroll | 클릭, 드래그, 스크롤은 손으로 어떻게 해요? | 답변 갱신 | partial |
| v-hand-wrong-click | 손으로 했는데 클릭이 엉뚱하게 돼요 | 답변 갱신 | partial |
| v-left-hand | 왼손잡이도 쓸 수 있어요? 장갑을 껴도 돼요? | 답변 유지 | not_validated |
| v-pen-beta | 펜 기능이 왜 베타예요? | 답변 유지 | partial |
| v-pen-air | 펜이 공중에 떠 있는데 그려지기도 하나요? | 답변 유지 | partial |
| v-pen-pressure | 필압(세게 누르면 굵어지는 것)도 되나요? | 답변 유지 | plan |
| v-pen-types | 연필이나 마커 같은 다른 필기구도 되나요? | 답변 유지 | not_validated |
| v-pen-finger | 펜 없이 손가락으로 그릴 수 있어요? | 답변 유지 | info |
| v-pen-writing | 글씨 쓰기나 필기도 되나요? | 답변 유지 | partial |
| v-objects-overlap | 물건끼리 겹치면 서로 뒤섞이지 않나요? | 답변 갱신 | partial |
| v-paper-buttons | 종이에 버튼을 그려 써도 되나요? | 답변 유지 | plan |
| v-launch-apps | 물건을 움직이면 앱이 켜지게 할 수 있어요? | 답변 유지 | plan |
| v-fast-move | 물건을 빨리 움직여도 따라오나요? | 답변 유지 | measured |
| v-never-lose | 절대 안 놓치나요? | 답변 유지 | partial |
| v-hijack | 엉뚱한 물건을 따라가면 어떻게 해요? | 답변 유지 | partial |
| v-states-simple | 추적 상태에는 어떤 게 있어요? | 답변 유지 | verified |
| v-similar-color-bg | 배경과 색이 비슷한 물건이면 어떻게 돼요? | 답변 유지 | partial |
| v-memory-fixed | 물건의 기억은 계속 새로 바뀌나요? | 답변 유지 | info |
| v-fps | 초당 몇 장을 처리해요? 부드러워요? | 답변 유지 | measured |
| v-success-rate-meaning | 성공률 89%는 무슨 뜻이에요? | 답변 유지 | measured |
| v-synthetic | 직접 만든 테스트 영상이 뭐예요? 가짜 영상으로 시험한 건가요? | 답변 유지 | measured |
| v-trust-numbers | 이 수치를 믿어도 돼요? 유리하게 잰 거 아니에요? | 답변 유지 | measured |
| v-resource-use | 컴퓨터가 많이 느려지거나 뜨거워지지 않나요? | 답변 유지 | partial |
