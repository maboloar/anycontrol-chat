# 현재 소스 버전: v1.8.0

# HANDOFF — AnyControl 개선 작업 인계 문서

작성 시점: 2026-10-13 (아래 §9 에 같은 날 후속 변경을 덧붙였다). 작업 폴더: `anycontrol-web` (※ `anycontrol-web claude fork` 가 아님). 프로젝트는 git 저장소가 아니다.
이 문서만 읽고 다른 세션에서 바로 이어갈 수 있게, 지금까지 한 일·기본값·검증 결과·한계·다음 할 일을 모았다.

## 0. 빠른 시작

```bash
cd "…/2026 고려대 AWS 경진대회 - GPT/anycontrol-web"
# 백엔드 테스트 (v1.8.0: 500 passed)
PYTHONPATH=backend/src:third_party/EfficientTAM backend/.venv/bin/python -m pytest backend/tests -p no:warnings -o addopts="" -q
# 프론트엔드 (v1.8.0: 164 passed) / 빌드
npm --prefix frontend test
npm --prefix frontend run build
```

- zsh 주의: `for c in $list; do set -- $c` 식 분할이 안 된다. 명령을 풀어 쓰거나 함수를 쓴다. `--include=*.py` 같은 글롭은 따옴표로 감싼다.
- 도구 출력은 빈 줄이 접혀 보일 수 있다. 파일을 문자열 치환으로 고칠 때는 `read_file` 로 실제 줄 구성을 확인한다 (치환 실패를 한 번 겪음).
- 변경 전 백업: `/tmp/anycontrol_backup2/`, `/tmp/anycontrol_pen_backup` (재부팅하면 사라질 수 있음).
- 샘플 영상: `samples/pen_test.mov`, `samples/IMG_0002.MOV`, `samples/test.mov`.
- 깊이 모델 가중치는 이 컴퓨터에 이미 내려받아 있다: `~/Library/Caches/AnyControl/depth` (환경변수 `ANYCONTROL_DEPTH_DIR` 로 변경).

## 1. 프로젝트 개요

카메라로 물체·펜·맨손을 추적해 마우스/키보드/게임패드 입력으로 바꾸는 웹앱. Python/FastAPI 백엔드(`backend/src/vision_input`) + React/TS 프론트엔드(`frontend/src`).
추적은 ViTracker(Tier 0 경량 + Tier 1 EfficientTAM 정밀 마스크 + 주기적 segmentation 재분할). 펜은 `pen.py`(펜촉·접촉·획) + `pen_floor.py`(바닥 기하 접촉 판정).

## 2. 사용자 요청과 처리 현황 (시간순)

| # | 요청 | 상태 |
|---|---|---|
| 1 | 독립 펜 알고리즘(`independent_pen_algorithm_test`, METHOD.md)을 연구해 AnyControl 펜 접촉 정확도 개선 | 완료. `contact_method="floor"` (기본은 `legacy`) |
| 2 | 물체 기억(복귀용) 이미지 보기 | 완료 (`tracking/memory_view.py`, `GET /api/objects/{id}/memory`, `MemoryView.tsx`) |
| 3 | "다른 분할 후보"가 선택을 바꾸는 문제, 기억 보기 토글이 선택 바꿔도 유지 | 완료 (`replacingId/replaceObject`, `memoryOpen`) |
| 4 | 멈춘 물체 흔들림/drift 해결 | 완료 (`StillLock`, 기본 켬) |
| 5 | 펜 바닥 평면 모델 + 바닥 그라데이션 맵 | 완료 |
| 6 | 개발자 모드 UI (렌치 버튼, 배지, 개발자 전용 버튼, 진한 녹색 테두리) | 완료 |
| 7 | 깊이 모델(Depth Anything V2 Small) 비교 실험 | 완료, 이후 펜 기본 기울기로 승격 (§3.5) |
| 8 | 모든 물체·펜에 실시간 EMA(선택 토글) | 완료 (§3.6) |
| 9 | 펜 가림/재등장 강건성 + 펜 뼈대 표시 + 가려진 부분 예측 | 완료 (§3.7) |
| 10 | 물체 마우스의 깊이를 깊이 모델로 (선택지로 남김) | 완료, 기본은 크기 (§3.8) |

## 3. 구현 상세

### 3.1 펜 바닥 기하 접촉 판정 (`pen_floor.py`, `pen.py`)
- `PenConfig.contact_method`: `"legacy"`(기본) | `"floor"`. 패널의 "바닥 기하 접촉 판정 (실험)" 체크박스(개발자 모드 전용)나 `POST /api/objects/{id}/pen/config {"contact_method":"floor"}` 로 켠다.
- floor 모드 구성: RANSAC 바닥 모델 + σ 문턱 + 상태기계 + 그림자 링 + 분할 탈락 중 접촉 유지(객체 영속성) + 획 소급/끝 정리.
- 기본값 판단: pen_test(30fps) legacy F1 0.649 → floor 0.946. IMG_0002 legacy 0.785(step1) → floor 0.813. **검증 영상이 2개뿐이라 기본값은 legacy 유지.** 사용자가 새 영상을 주면 재검증 후 결정.
- `floor_drift` 기본 `off` (책상 모서리 추적은 IMG_0002 에서 해로웠음).
- 알려진 주의: 손가락이 펜 가운데를 쥐어 펜이 두 조각이면 등록 시 펜촉~손가락 아래 조각만 찍어야 한다 (`configs/img_0002.json`).

### 3.2 멈춘 물체 안정화 (`tracking/still.py`, `vi_tracker.py`)
- 원인: 2초마다 도는 segmentation 재분할이 크기를 ~0.7% 바꿔 크기 기반 깊이 커서가 초당 24px 움직이고 10초에 50px drift.
- 해결: `StillLock` — LK 점이 ≥10프레임 조용하면 잠금, 증분은 잡음을 넘을 때만 커밋, 영역/T1/갱신 측정은 3회 연속 어긋남 확인 전까지 막고 마스크는 다수결로 고정. 움직임·손·상태 변화·순간이동·재개·점 소실 시 해제. 펜은 잠그지 않음. 기본 켬 (`TrackerConfig.still.enabled`), 끄려면 `vi_nostill` 트래커.
- 결과(`bench/still`): synthetic-still 커서 경로 24.2→0.37 px/s, drift 50.6→3.5 px, 마스크 중심 표준편차 0.54→0. move 시작 지연 5→4프레임, 멈춘 뒤 꼬리 3.6→2.6px. 합성 평가 모음(tune 50) 변화 없음.
- **한계**: 합성 중심 검증. 실영상(test.mov)은 손에 든 카메라라 잠금이 694프레임 중 69프레임에만 걸림(독립 Tier‑1 기준 오차 15.5→12.7px). `real-still` 장면 지표는 baseline 과 동일. 느린 움직임은 ≥~1px 단위로 한꺼번에 반영(양자화). 비동기 Tier‑1 실시간 모드는 따로 검증 안 함.
- 자세한 설명: `bench/still/README.md`.

### 3.3 바닥 평면 모델 + 그라데이션 맵
- `FloorModel`: `d = k·w + a·x − c` (x = tip_x/W − 0.5). `floor_roll`(기본 켬)은 a(좌우 기울기)를 터치/자동 학습으로 맞춤. `a_fixed` 가 있으면 a 를 고정하고 (k, c)만 맞춤 (§3.5). `a_max_px` 상한 + 약한 릿지 정규화.
- 터치 3점 보정: `set_touches`, 자동 보정 적용 시 `pipeline.apply_auto_calibration` → `pen.floor.set_touch_plane` (표본 ≥2).
- 맵: `render_map` → PNG data URI `image`/`overlay`. `GET /api/objects/{id}/pen/floor-map`. 프론트: `FloorMapView.tsx`(패널) + `CameraView` 의 `<img class="floor-overlay">`(오버레이, 좌우 반전 대응).
- `floor_region()` 은 평면이 학습되기 전에도 책상 색만 있으면 바닥 영역을 만든다 (깊이 롤용).
- 벤치(30fps, F1): pen_test 롤 항 유무 동일 0.946, +4° 0.875→0.906, −4° 0.938→0.963, IMG_0002 0.785→0.813. **60fps +4° 는 오히려 0.944→0.920** → 롤 항이 항상 이득은 아님. 끄려면 `floor_roll=False`.

### 3.4 개발자 모드 UI
- 스토어 `devMode` (localStorage `anycontrol.devMode`). 상단 렌치 버튼(`DevMode.tsx` `DevModeToggle`), 제목 옆 "개발자 모드" 배지(`DevBadge`).
- 개발자 모드에서만 보이는 것: 물체 기억 보기 버튼, 바닥 그라데이션 맵 버튼, 바닥 접촉 체크박스, 깊이 모델 설정. 모두 클래스 `dev-btn`/`dev-check`, 색 `--dev:#1f7a3d`. 끄면 열린 보기들을 닫고 오버레이를 지움.

### 3.5 깊이 모델 기울기 — 펜 기본 설정 (`depth_model.py`, `pen.py`)
- 모델: Apple Core ML Depth Anything V2 Small F16 (Apache‑2.0, ~50MB), pyobjc CoreML(24–80ms). **내려받기는 개발자 모드에서 사용자가 확인창에 동의했을 때만**, SHA‑256 고정 `fa60d9b6…0fed`. 상태 `GET /api/dev/depth-model`, `POST /api/dev/depth-model/download`, 비교 `GET /api/dev/pen/{oid}/depth-compare` (`server/dev.py`).
- `DepthService`: 별도 스레드 추론. `submit()` 은 기다리지 않고 바쁘면 버림, 프레임 복사. 펜 기울기와 마우스 깊이가 공유 (`VisionProcessor.depth`; dev 엔드포인트도 같은 모델 인스턴스).
- `PenConfig.floor_depth_roll=True`(기본): floor 모드에서 2초마다 책상 영역에 깊이 평면(`fit_depth_plane`, RANSAC)을 맞춰 롤(`atan2(A/W, B/H)`)을 구하고, 최근 5개 중 ≥3개가 2.5° 안·내점비율 ≥0.55·|롤|≤20° 이면 `a_fixed = −W·tan(roll)` 로 고정(`DepthRoll`). 모델 없음/끔/미측정이면 터치로 배운 롤. 상태는 pen state `depth_roll` 과 floor-map 응답에 포함.
- `POST …/pen/config {"floor_depth_roll": bool}` 로 토글. UI: `DepthCompareView.tsx` 한 줄(상태 문구 + 체크박스 + 필요 시 내려받기 + "비교 이미지" 버튼).
- **벤치 결과: 깊이 롤과 터치 롤의 F1 이 4개 영상 모두 동일** (0.946/0.906/0.963/0.889). 롤 크기는 깊이 쪽이 회전량을 더 크게 따라감(터치 롤은 과소 추정 경향)이지만 정답 롤이 없어 어느 쪽이 맞는지는 미확정. 사용자는 실사용에서 더 잘 된다고 보고함.
- 이 기능은 `contact_method="floor"` 일 때만 작동한다 (기본 legacy).
- 실험 스크립트: `bench/pen/depth_compare.py`, `bench/pen/depth_prior.py`. 벤치 변종 `floor+all+touchroll` / `floor+all+depth` (벤치는 동기 추론 `_Sync`).

### 3.6 실시간 EMA (`tracking/smooth.py` `SpikeEma`)
- `SpikeEma(tau=0.08, spike_k=5, spike_tau=0.8, confirm_s=0.18)`: 평소엔 시간상수 EMA, 평소 변화량×5 를 넘는 점프는 아주 느리게만 따라가다 0.18초 넘게 지속되면 진짜 이동으로 인정.
- 적용: ① 물체 축(`AxisState.sample(..., t, ema)`; 중립을 빼기 전 절대 값에 적용: cx, cy, log scale, angle, log elongation, bottom) ② 펜촉(`PenTracker.ema_x/ema_y`, tau 0.04, 단위=펜 굵기×0.3; 접촉 판정은 원시 측정 사용이라 F1 불변) ③ 물체 마우스 좌표(`VisionProcessor._mouse_ema`).
- 토글: `VisionProcessor.ema`(기본 **True**), `PUT /api/tracking {"ema":bool}`, GET /api/tracking 의 `ema`. UI: ObjectPanel "튐 억제 (실시간 EMA)".
- 긴 가림 후 재등장(>0.3초)·재정의·소실 시 필터 리셋.
- 테스트: `test_ema.py`.

### 3.7 펜 뼈대 / 가림 강건성 (`pen_skeleton.py`)
- `PenSkeleton.observe(mask, expected_dir, length, pred_tip, pred_tail, occluder, bgr)`: 마스크를 PCA 로 곧은 선에 맞추고(축에서 먼 덩어리 제거), 축 방향 단면으로 보이는 구간을 만들고 펜 굵기보다 큰 틈은 "가려진 구간". 상태 `seen | middle_hidden | tip_hidden | tail_hidden`.
- 끝이 가려졌다는 판정은 **손의 증거가 있을 때만**: 손 가림 처리의 손 마스크(`occluder`, 펜촉·꼬리 모두 가능) 또는 피부색(꼬리 쪽만). 근거 없으면 늘리지 않음(`evidence ""`).
  - 포즈 예측만으로 늘리면 실제 영상(pen_test)에서 카메라 쪽으로 기울어 짧아 보이는 펜을 가림으로 착각해 펜촉을 책상 위로 늘렸다 → 제거.
  - 피부색으로 펜촉 쪽 판정+측정 중단을 하면 베이지색 책상 때문에 IMG_0002 F1 0.889→0.772 → 피부색은 꼬리 쪽 표시 전용, 측정 중단은 `occluder` 증거에서만.
- 길이 기억: `PenTracker._sk_len0`(뼈대 길이/(배율·√가로세로비)), 강체 예측용 `_anchor_tail`, `_rigid_map/_rigid_tip/_rigid_tail`.
- 끝 색 기억(`learn_ends`): 처음 온전히 보인 모습에서 펜촉/꼬리 끝 색(Lab). 두 색이 14 이상 다를 때만 `should_flip` 로 재등장 시 방향 뒤집힘을 바로잡음(마진 10).
- `PenTracker.update` 흐름: `mask_now`(Tier1 이면 워프) → 뼈대 관측 → (뒤집힘 보정) → `hand_hides_tip`(occluder 증거) 또는 기존 `t0 & shortened & displaced` 규칙이면 측정 중단하고 뼈대 펜촉(없으면 강체 예측)으로 잇기(`debug.src = skeleton|rigid`).
- 손 마스크 전달: `VisionProcessor._occluder` → `pen.occluder` (손 가림 처리 `hand_occlusion` 을 켜야 존재; 기본 꺼짐).
- 상태: pen state `skeleton` {tip, tail, state, evidence, visible[], hidden[]}. 프론트 `overlay.ts drawPenSkeleton`(보이는 구간 실선 청록, 가려진 구간 주황 점선, 가려진 끝은 속 빈 원), `drawPen` 이 호출.
- 실제 영상 분포(pen_test 30fps 267프레임): seen 210, middle_hidden 16, tail_hidden 24(대부분 엄지에 가림), tip_hidden 8. 접촉 F1 불변 (0.946 / 0.889).
- 테스트: `test_pen_skeleton.py` (합성 장면), `test_pen.py::test_shortened_pen_mask_keeps_rigid_tip…` 는 이제 증거 없으면 `rigid`.

### 3.8 물체 마우스 깊이 모델 옵션 (`MouseSettings.depth_source`)
- `"size"`(기본) | `"model"`. `VisionProcessor._model_depth_scale()`: 설정이 model, 모델 설치, 일반 물체(펜 제외), 깊이 커서 모드일 때 ~10Hz 로 `object_depth_position()` 계산 → 크기 자리에 `1+u`(u: 책상 평면 먼 쪽 0 ~ 가까운 쪽 1, 들어올리면 커짐) 전달. 결과가 0.6초보다 오래되면 크기로 복귀하고 `depth_cursor.reset()`(점프 방지). 모델 모드에서는 크기 기반 사선 보정(`depth_perspective`)을 끔. 모델 값에도 SpikeEma 적용.
- 평면 적합: 프레임 아래 70% 에서 모든 물체 마스크를 뺀 영역에 RANSAC. 내점비율 하한 0.35 (0.5 로 두면 pen_test 129프레임 중 4프레임만 성공 → 낮춤).
- 모델이 없으면 `set_mouse` 가 409(ValueError) — `mouse_info.depth_model_available` 로 UI 가 옵션을 비활성화. 상태 `depth_source: desk|size|model`.
- UI: MousePanel "앞뒤(깊이) 신호" 선택 + "지금 깊이 모델로 계산 중" 표시. 테스트 `test_mouse_depth_model.py`, `MousePanel.test.tsx`.
- **검증 한계**: 마우스 물체 영상이 없어 pen_test 의 펜 마스크로만 확인(129프레임 모두 값이 나옴, 화면 아래쪽 위치와 상관 0.6). 크기 방식보다 낫다는 근거는 없음 → 기본 크기 유지.

## 4. 파일 지도 (이번 작업에서 추가·변경)

백엔드 (`backend/src/vision_input/`)
- 신규: `tracking/still.py`, `tracking/memory_view.py`, `pen_skeleton.py`, `depth_model.py`, `server/dev.py`
- 변경: `tracking/vi_tracker.py`(still, memory()), `tracking/smooth.py`(SpikeEma), `tracking/axes.py`(EMA), `pen.py`(EMA, 깊이 롤, 뼈대, floor_map), `pen_floor.py`(평면, a_fixed, floor_region/floor_planes, render_map, fit 빈 버퍼 가드), `pipeline.py`(ema, depth service, occluder, 모델 깊이 스케일, set_ema, mouse_info), `io/mouse.py`(depth_source, model_depth), `server/control.py`(/api/tracking ema), `server/objects.py`(PenBody.floor_depth_roll, floor-map, memory), `server/app.py`(dev 라우터)

프론트엔드 (`frontend/src/`)
- 신규: `components/DevMode.tsx`, `FloorMapView.tsx`, `DepthCompareView.tsx`, `MemoryView.tsx`
- 변경: `store.ts`, `App.tsx`, `ObjectPanel.tsx`(dev 버튼, EMA 토글), `DrawingPad.tsx`, `MousePanel.tsx`, `CameraView.tsx`, `overlay.ts`(drawPenSkeleton), `protocol.ts`, `api.ts`, `styles.css`

벤치·문서
- `bench/still/{metrics,scenarios,run}.py` + `README.md`
- `bench/pen/{track_cache,run,metrics,sweep,depth_compare,depth_prior}.py`, `configs/{pen_test,img_0002,pen_test_roll4,pen_test_roll-4}.json`(`"rotate"` 지원), `labels/`, `README.md`(결과 1~3, 개발자 도구, 기본 설정 변경, 펜 뼈대)

테스트(추가)
- 백엔드: `test_still.py`, `test_memory_view.py`, `test_pen_floor.py`(평면/터치/probe/map), `test_depth_model.py`, `test_depth_roll.py`, `test_ema.py`, `test_pen_skeleton.py`, `test_mouse_depth_model.py`, `test_server.py`(floor-map, memory)
- 프론트: `DevMode.test.tsx`, `FloorMapView.test.tsx`, `DepthCompareView.test.tsx`, `MousePanel.test.tsx`, `ObjectPanel.test.tsx`(EMA 토글), `overlay.test.ts`(drawPenSkeleton), DrawingPad dev 게이팅

## 5. 현재 기본값 요약

| 항목 | 기본값 |
|---|---|
| 펜 `contact_method` | `legacy` (floor 는 선택) |
| `floor_roll` | True |
| `floor_drift` | `off` |
| `floor_depth_roll` | True (floor 모드 + 모델 설치 시에만 실제 작동) |
| StillLock | 켬 |
| EMA (`/api/tracking.ema`) | 켬 |
| 손 가림 처리 `hand_occlusion` | 꺼짐 (켜야 손 마스크 증거 사용) |
| 마우스 `depth_source` | `size` |
| 개발자 모드 | 꺼짐 |

## 6. 알려진 한계 / 주의

1. 펜 접촉 검증은 **영상 2개**(pen_test, IMG_0002; 롤 영상은 pen_test 회전본). IMG_0002 라벨은 사람 검수 전(Kiro 가 확대 크롭으로 판정).
2. 깊이 롤은 벤치 F1 이 터치 롤과 같음. 실사용 체감은 사용자 보고뿐이며 객관 지표 없음. 정답 롤 데이터 필요.
3. 롤 항은 60fps +4° 에서 오히려 낮음(0.944→0.920).
4. StillLock 은 합성 위주 검증, 느린 움직임 양자화, 비동기 Tier‑1 미검증.
5. EMA 는 합성 단위 테스트와 펜 접촉 F1 불변만 확인. 실제 마우스 커서 체감 지연/튐 개선은 미측정. 합성 평가 모음(`vision_input.eval`)은 ViTracker 단에서 돌아 EMA 영향이 없음.
6. 펜 뼈대: 손 가림 처리를 끄면 펜촉 가림 판정 근거가 없어 펜촉은 늘리지 않음. 피부색은 베이지 책상과 혼동 가능. 끝 색 방향 보정은 두 끝 색이 비슷한 펜에서는 작동하지 않음. 방향 뒤집힘 보정은 합성 테스트만으로 검증(실영상 재등장 시나리오 영상 없음).
7. 마우스 깊이 모델: 마우스 영상으로 정확도 비교 안 함. 약 10Hz 갱신.
8. 깊이 모델은 macOS(pyobjc CoreML) 전용. 다른 OS 에서는 `available` 이 False 이거나 추론 오류로 기능만 꺼진다 (오류는 `depth_roll.error` 로 노출).
9. 네트워크 사용은 깊이 모델 내려받기(사용자 동의 후)뿐.

## 7. 다음에 할 일 (우선순위 제안)

1. **새 테스트 영상 확보 후 재검증**: 다른 조명·각도·펜·책상에서 legacy vs floor, 깊이 롤 on/off 비교 → `contact_method` 기본값 변경 여부 결정. 새 영상은 `bench/pen/configs/<name>.json` + `labels/<name>.json` 추가 후 `track_cache.py` 로 캐시.
2. **마우스 물체 영상**으로 `depth_source` size vs model 비교 (커서 경로 매끄러움, 앞뒤 이동 선형성, 기울어진 카메라). 이득이 확인되면 기본값 재검토.
3. 손 가림 처리를 켠 상태의 실제 영상으로 펜 뼈대 `occluder` 경로(펜촉 가림 복원) 확인. 재등장 시 방향 뒤집힘 사례 수집.
4. 깊이 롤 정답 검증: 카메라를 알려진 각도로 기울인 촬영 또는 수평계 사용.
5. EMA 파라미터(`tau`, `spike_k`, `confirm_s`) 실제 체감 튜닝, 필요하면 UI 강도 슬라이더.
6. StillLock: 느린 움직임 양자화 완화, 비동기 Tier‑1 모드 검증.
7. 정리 후보: `bench/pen/README.md` 의 오래된 표(결과 1·2)와 새 결과 표 통합, `DrawingPad` 에서 floor 사용 시 깊이 롤 상태 한 줄 노출(현재는 개발자 모드 바닥 맵 화면에만 있음).

## 8. 재현 명령 모음

```bash
PY="PYTHONPATH=backend/src:third_party/EfficientTAM backend/.venv/bin/python"
# 멈춘 물체 벤치
$PY bench/still/run.py --variant baseline still_lock
# 펜 접촉 벤치 (캐시 먼저: bench/pen/track_cache.py <config> [--step 2])
$PY bench/pen/run.py bench/pen/configs/pen_test.json --step 2 --variant legacy floor+all floor+all+touchroll floor+all+depth
$PY bench/pen/run.py bench/pen/configs/img_0002.json --step 2 --variant legacy floor+all
$PY bench/pen/run.py bench/pen/configs/pen_test_roll4.json --step 2 --variant floor+all+noroll floor+all
# 깊이 모델 실험 (모델 설치 필요)
$PY bench/pen/depth_compare.py bench/pen/configs/pen_test_roll4.json --step 2
$PY bench/pen/depth_prior.py  bench/pen/configs/pen_test_roll4.json --step 2
```

최신 벤치 수치(30fps, step 2, F1): pen_test legacy 0.649 / floor 0.946, IMG_0002 floor 0.889(step 2) · 0.813(step 1) — 두 값은 step 이 달라 직접 비교 금지.

## 9. 후속 변경 (같은 날): 깊이 모델 번들·기본값 승격·마우스 민감도·획 삐침

이 절이 §3·§5 보다 **최신**이다. 충돌하는 내용(기본값 표 등)은 이 절을 따른다.

### 9.1 Depth Anything V2 Small 가중치를 프로그램에 포함
- `models/DepthAnythingV2SmallF16.mlpackage/`(약 50MB, Apache‑2.0) + `models/DepthAnythingV2SmallF16.README.md`(모델 카드). `weight.bin` SHA‑256 `fa60d9b6…0fed` 고정.
- `depth_model.cache_dir()` 우선순위: 환경변수 `ANYCONTROL_DEPTH_DIR` > 번들(`VI_MODELS_DIR` 또는 `<프로젝트>/models`) > 사용자 캐시. 내려받기(`Downloader`)는 **번들이 없을 때의 대비책**으로만 남음(저장은 `user_cache_dir()`). `is_bundled()`, `verify_weights()`(SHA 검사, 시작 때 호출하려면 50MB 읽음) 추가. 상태 `state()["bundled"]`.
- `packaging/build_bundle.py` 는 `models/` 전체를 이미 묶고, 필수 자산 목록에 `weight.bin` 추가. `THIRD_PARTY.md` 에 항목 추가. (번들 빌드 자체는 이 세션에서 실행하지 않음, `py_compile` 만 확인.)
- 테스트: `test_depth_model.py::test_bundled_weights_…`.

### 9.2 펜: 깊이 모델 + 바닥 기하가 기본
- `PenConfig.contact_method` 기본이 **`floor`** (legacy 는 선택). `floor_depth_roll=True` 유지(가중치가 번들이라 항상 작동).
- UI: DrawingPad 의 "바닥 기하 접촉 판정 (기본)" 체크박스는 이제 개발자 모드 전용이 아님(끄면 legacy). 그 아래 "책상 기울기를 깊이 모델로 재기 (기본)" 체크박스 추가 — 끄면 **펜으로 배운 기울기**(선택지). 개발자 모드의 `DepthCompareView` 는 상태 줄 + (번들이 없을 때만) 내려받기 + "비교 이미지"로 간소화(체크박스 제거).
- 기존 테스트 5개를 새 기본값에 맞게 수정(legacy 를 명시하거나 기대값 변경).

### 9.3 개발자 모드: 깊이 맵 카메라 오버레이
- `GET /api/dev/depth-map` (`server/dev.py`): 요청 시 최신 깊이 맵이 0.3초보다 오래됐으면 백그라운드로 새로 계산, `{ready, age, ms, size, image, overlay}`(INFERNO 색, 가까움=밝음, 2~98% 늘림). `DepthService.latest` 에 마지막 깊이 맵 보관, `depth_map_images()`.
- 프론트: 스토어 `depthMapOverlay/depthMap`, `CameraTools.tsx` 의 `DepthMapButton`(개발자 모드에서만 보임, 켜 있는 동안만 350ms 마다 폴링), `CameraView` 의 `<img class="depth-overlay">`(영상 반전 대응). 개발자 모드를 끄면 오버레이도 꺼짐. 테스트 `DepthMapButton.test.tsx`.

### 9.4 마우스: 깊이 모델이 기본, 물체 크기는 선택지, 훨씬 민감
- `MouseSettings.depth_source` 기본 **`model`**, `depth_model_range`(기본 **3.0**, 0.5–10) 추가. 모델이 없거나 결과가 오래되면 자동으로 크기를 쓴다(`set_mouse` 는 더 이상 거부하지 않음). 펜에는 적용 안 됨.
- 감도: 커서의 세로 이동 = Δu × `depth_model_range` (화면 높이 배수; u = 책상 먼 쪽 0 ~ 가까운 쪽 1). 이전 크기 방식(물체가 30% 커지는 이동)보다 3배 이상 크게 움직이는 것을 테스트로 고정(`test_a_full_desk_traverse…`). 모델 모드에서는 `depth_gain`·`depth_sensitivity` 를 쓰지 않고 `gain = range/depth_sensitivity` 로 상쇄하며, 사선 보정은 끔, 데드존은 `max(depth_deadzone, 0.003)`(정지한 펜 쌍에서 잰 u 의 프레임 잡음 중앙값 0.005 / p90 0.011 에 맞춤).
- **갱신 방식(질문에 대한 결정)**: "주기적 자동 + 수동 버튼" 혼합.
  - 깊이 맵은 ~10Hz 로 계속 새로 만들어 물체 위치 u 를 잰다(프레임마다 깊이 모델의 스케일·이동이 달라 같은 프레임의 책상 평면 RANSAC 으로 정규화).
  - 책상 가장자리 행(기준)은 평면 **내점**의 3~97% 행으로 잡고(셔츠·벽 제외), 처음 몇 번은 빨리, 이후 `REF_RATE=0.05`로 천천히 따라간다(주기적 자동 갱신). 기준이 6% 이상 어긋난 채 5번 이어지면 카메라가 움직인 것으로 보고 자동으로 다시 잡는다.
  - 사용자는 MousePanel 의 "깊이 기준 다시 잡기" 버튼(`POST /api/mouse/depth-reference`)으로 즉시 다시 잡을 수 있다. 기준을 다시 잡으면 커서도 리셋해 점프를 막는다.
- UI(`MousePanel.tsx`): "앞뒤(깊이) 신호" 선택(깊이 모델(기본)/물체 크기), "깊이 감도 ×N" 슬라이더, "깊이 기준 다시 잡기" 버튼, 상태 문구. `mouse_info` 에 `depth_model_available`, `depth_reference{samples,resets,ready}`.
- 코드: `depth_model.object_depth_position()`, `ObjectDepth`, `pipeline._model_depth_scale()`, `reset_depth_reference()`, `io/mouse.py`(model_depth, MODEL_DEPTH_DEADZONE).
- **한계**: 마우스 물체 영상이 없어 pen_test 의 펜 마스크로만 확인(258프레임 모두 값 나옴, u 범위 0.15–0.80, 화면 아래쪽 위치와 상관 0.6). 잡음 대비 감도 3.0 은 마우스 영상으로 체감 확인이 필요. 크기 방식보다 정확하다는 객관 비교는 아직 없다(사용자 요청으로 기본값만 승격).

### 9.5 펜 획 처음·끝의 삐침 방지
- 원인(`bench/pen/strokes.py` 로 획을 그려 확인): 펜을 내리고 올릴 때 펜촉의 y 가 변하는데, 책상 좌표 변환 `Z = f/(y − 소실선)` 이 소실선 근처에서 몇 px 를 크게 증폭해 세로로 긴 선이 획 처음·끝에 생겼다. 접촉 직후 몇 프레임은 펜이 아직 안착하지 않았고, 디바운스 때문에 접촉이 유지되는 동안 이미 들어 올리는 점이 찍히기도 했다.
- 해결(모두 `PenConfig`, floor 자동 판정일 때만; 수동/legacy 는 그대로):
  - `stroke_start_delay_s=0.07`: 접촉 근거 시각(`onset_t`, 소급 포함)부터 이 시간의 점은 건너뜀(안착 후부터 그림).
  - `stroke_end_trim_s=0.07`: 이탈 근거 시각(`offset_t`) 직전 이 시간의 점을 뺌.
  - `stroke_hover_gate=0.35`: 접촉이 유지돼도 펜촉이 0.35D 이상 떠 있으면 점을 찍지 않음(`_hovering`).
  - `draw_project=True`(+`draw_project_dead=0.2`, `draw_project_max=3.0`): 떠 있는 펜촉을 같은 굵기에서 닿았을 y 로 내려 그림 좌표를 계산(`hover_px()`는 바닥 모델의 `info["w"]·info["hover"]`). 안정적으로 닿은 동안(hover<0.35D)에는 적용 안 함 — 처음에 항상 적용했더니 평면 잡음이 계단으로 새서 획이 들쭉날쭉해졌다.
- 결과(`bench/pen/strokes.py`, 30fps): pen_test 시작·끝 걸음의 최대 길이비 5.12→2.46, 중앙값 2.0→0.78. 그림으로 보면 획 시작의 긴 내부 세로선이 사라지고 끝 꼬리가 짧아졌으나 **한 획(첫 획)의 끝에 짧은 꼬리가 남음**(들어 올릴 때 펜 굵기 측정이 흔들려 바닥 모델의 높이가 0 으로 보이는 구간 — 굵기 기반 높이의 한계).
- 비용: 기록된 획의 프레임 F1 이 pen_test 0.946→0.924, IMG_0002 0.878→0.823 로 낮아짐(양 끝 ~0.14초를 일부러 버림; 3~4점짜리 조각 획은 사라져 5개→3개). 접촉 판정 F1(0.946 / 0.889)은 변화 없음. 더 짧게/길게 하려면 `stroke_*` 값을 조정(30fps 에서는 0.07~0.10초가 같은 2프레임이라 효과가 같음).
- 한계: 삐침 지표(`flick_len`)는 합성 라벨이 없어 그림과 걸음 길이로만 봄. 정답 획이 없다.
- 테스트 `test_pen_strokes.py`.

### 9.6 갱신된 기본값 요약 (§5 대체)
| 항목 | 기본값 |
|---|---|
| 펜 `contact_method` | **`floor`** |
| `floor_depth_roll` | True (가중치 번들) |
| `draw_project` / `stroke_start_delay_s` / `stroke_end_trim_s` / `stroke_hover_gate` | True / 0.07 / 0.07 / 0.35 |
| 마우스 `depth_source` / `depth_model_range` | **`model`** / **3.0** |
| EMA, StillLock | 켬 |
| 손 가림 처리 | 꺼짐 |
| 개발자 모드 | 꺼짐 (깊이 맵 오버레이·바닥 맵·기억 보기는 개발자 모드 전용) |

### 9.7 검증 상태
백엔드 382개(마지막 실행 381 + 번들 가중치 테스트 1), 프론트 123개 통과, `npm run build` OK. 실제 모델을 번들 경로에서 불러 추론 확인(392×518, 약 95ms 첫 호출 포함). 그림·벤치 확인은 pen_test, IMG_0002 에서만 했다.

### 9.8 다음에 할 일 (갱신)
1. 마우스 물체(예: 실제 마우스)를 책상 앞뒤로 움직이는 영상으로 `depth_source` model vs size 비교, `depth_model_range` 기본값(3.0)·데드존 0.003 튜닝.
2. 획 끝 꼬리가 남는 사례 개선: 들어 올릴 때 굵기 측정이 흔들리는 문제(예: 펜촉 근처 굵기를 좌우 위치와 함께 더 안정적으로 재거나 y 속도 신호 병용). 정답 획 데이터가 있으면 지표화.
3. 기록 획 F1 하락(0.946→0.924) 완화: 짧은 탭(<0.25s)은 지연·정리 제외 등.
4. 번들 빌드(`packaging/build_bundle.py`)와 `bootstrap.py` 의 모델 검증 단계에 깊이 모델 SHA 검사 추가 및 실제 빌드 실행.
5. §7 의 기존 항목(새 영상 재검증, 깊이 롤 정답 검증 등)도 유효.

## 10. `anycontrol-web claude fork` 도입 (같은 날 후속)

`anycontrol-web claude fork/HANDOFF.md` 에 적힌 구현을 이 프로젝트로 가져왔다. 포크는 같은 기반(물체 기억 보기·펜 floor 판정까지의 상태, `/tmp/anycontrol_backup2` 와 일치)에서 갈라졌고 **펜 코드(`pen.py`, `pen_floor.py`)와 `objects.py`, `store.ts`, `api.ts` 는 건드리지 않았다.** 그래서 우리 쪽 펜·깊이·EMA·StillLock 작업과 겹치는 파일은 `pipeline.py`, `vi_tracker.py`, `io/mouse.py`, 프런트 몇 개뿐이었다. 도입 전 우리 상태 백업: `/tmp/anycontrol_ours_before_fork_merge/` (models·node_modules 제외).

### 10.1 포크에서 가져온 것 (포크 HANDOFF 의 내용)
- **손가락 클릭 방식(물체 마우스):** `hands/finger_click.py`(검지·중지를 든 채 내려서 클릭, 중지=왼쪽/검지=오른쪽), `io/mouse.py` 의 `hand_click_style`, `finger_press`, `object_tap_distance` 의미 변경, 물체 모드에서 엄지 집기·스크롤 제거, 가장 가까운 손 선택.
- **끝점 직접 추적:** `hands/tip_track.py`(LK+NCC+살색), `tip_click.py`, `tip_refine.py`(EfficientTAM 살색 분할 보정), 설정 `finger_track`, `tip_drop`, `tip_refine`. `pipeline._tip_frame`.
- **한 손 하이브리드:** `io/hybrid.py` `HybridRouter`(물체 이동 ↔ 맨손 클릭만, 커서 고정), 설정 `object_hybrid`, `hybrid_detach`, `hybrid_hand_control`(호환용).
- **손 가림 보완 마스크(amodal):** `vi_tracker._completed_mask()`/`_output()` — 손 마스크가 있으면 출력 마스크 = 보이는 마스크 ∪ (기억 모양 ∩ 손 영역). 펜은 제외. 전제: `hand_occlusion` 켬.
- **자동 보정 간소화:** `auto_calibration.py`(합성 단계 rest→lr→nf→clicks, 펜 6단계, 하이브리드는 3단계) + `AutoCalibration.tsx`(3초 카운트다운 자동 시작, 단계 점).
- **UI:** `BetaBadge.tsx`(펜 입력 Beta 표시), `WorkspaceGuide.tsx`(3단계 시작 안내), `Panel.tsx`·`Tutorial.tsx`(handguide.png, 하이브리드 설명)·`VirtualDesktop.tsx`·`App.tsx`(고정 헤더, 긴급 정지 버튼, 연결 칩, 건너뛰기 링크), `styles.css`(작업 화면 정리), `MousePanel.tsx`(시작 순서·상태 칩·접이식 3구역·클릭 방식/민감도), `ObjectPanel.tsx`(추적 보정 설정을 접이식으로), `overlay.ts` `drawTips`(검지 빨강·중지 초록 원).
- **창을 닫으면 서버 종료 보강:** `connection.ts` 의 `sendBeacon('/api/bye')`, `server/app.py` `/api/bye`, `__main__.py` 종료 워치독(8초 후 `os._exit`).
- **롤백된 것은 가져오지 않음(포크도 코드에 없음):** 물체를 들면 커서 멈춤(`lift`), 손 인식 ROI/게이트(`roi.py`).
- 포크의 새 테스트: `test_finger_click.py`, `test_hybrid_mouse.py`, `test_tip_track.py`, 수정된 `test_auto_calibration.py`, `test_browser_session.py`, `test_depth_mouse.py`, `test_hand_occlusion.py`, `test_mouse.py`, `test_object_tap.py`, `test_touchpad.py`, 프런트 `WorkspaceGuide.test.tsx`, `AutoCalibration.test.tsx`, `connection.test.ts`, `MousePanel.test.tsx`(포크 4건).

### 10.2 병합 방식과 충돌 해결
- 3-way 병합(`git merge-file`, 기준 = `/tmp/anycontrol_backup2`): `pipeline.py`, `tracking/vi_tracker.py`, `App.tsx`, `ObjectPanel.tsx`, `styles.css`, `protocol.ts`, `CameraView.tsx`, `DrawingPad.tsx`. 충돌 4곳은 수동 해결:
  - `pipeline.py`: `pen_scale = self._model_depth_scale(...)`(우리)와 `tip_frame = self._tip_frame(...)`(포크)를 둘 다 유지(우리 줄이 먼저).
  - `App.tsx`: 포크의 헤더(버전·연결 칩·긴급 정지)에 우리의 `DevBadge`(제목 옆)와 `DevModeToggle`(안내 버튼 옆)을 추가.
  - `ObjectPanel.tsx`: 포크의 접이식 "추적 보정 설정" 안에 우리의 "튐 억제 (실시간 EMA)" 체크박스를 넣음.
  - `styles.css`: 두 쪽 블록을 모두 유지.
- 포크 파일을 그대로 가져온 것(우리가 안 건드린 파일): `__main__.py`, `auto_calibration.py`, `AutoCalibration.tsx(+test)`, `Panel.tsx`, `Tutorial.tsx`, `VirtualDesktop.tsx`, `connection.ts(+test)`, 위 포크 테스트들, `README.md`/`README-en.md`(우리 깊이 모델·EMA 설명 2줄을 추가).
- 포크 파일에 우리 수정을 다시 얹은 것: `io/mouse.py`(`depth_source`/`depth_model_range`/`MODEL_DEPTH_DEADZONE`/`model_depth`, 물체 모드와 하이브리드 물체 단계의 깊이 커서에 모델 감도·데드존·원근 보정 끔 적용; 하이브리드의 맨손 단계는 `route.source == 'object'` 일 때만 모델 값), `server/app.py`(`/api/dev` 라우터 + 포크의 `/api/bye`, `tip_refiner.segmenter` 주입), `server/control.py`(`ema`, `/api/mouse/depth-reference`), `MousePanel.tsx`(깊이 신호 선택·감도·기준 다시 잡기 블록을 "물체 이동 방식" 바로 아래에), `overlay.ts`(포크 `drawTips` + 우리 `drawPenSkeleton`), `ObjectPanel.test.tsx`/`DrawingPad.test.tsx`(펜 탭·버튼 이름이 "… Beta" 로 바뀐 것 반영), `MousePanel.test.tsx`(포크 4건 + 우리 3건을 `vi.spyOn(api, …)` 방식으로 합침).
- 우리 것을 그대로 둔 것: `pen.py`, `pen_floor.py`, `objects.py`, `tracking/{axes,smooth,still}.py`, `eval/trackers.py`, `CameraTools.tsx`(깊이 맵 버튼), `MemoryView.tsx`, `store.ts`, `api.ts`, `bench/`, 우리 테스트들.

### 10.3 상호작용 (주의)
- **모델 깊이와 하이브리드:** 하이브리드에서 물체가 커서를 움직이는 동안은 모델 깊이(`depth_source=model`)가 기본으로 적용되고, 맨손 단계는 클릭만 하며 커서가 고정이라 깊이를 쓰지 않는다. `coordinate_mode="image"`(상대 XY)인 경우 깊이 신호를 쓰지 않는다(`_model_depth_scale` 은 `coordinate_mode == "depth"` 일 때만).
- **amodal 출력 마스크와 우리 기능:** 펜 뼈대는 펜을 대상으로 하므로 amodal 완성(펜 제외)의 영향이 없다. 물체 마우스 깊이(`object_depth_position`)는 출력 마스크(손 가림 보완 후)의 아래쪽 절반 중앙값을 쓰므로, 손 가림 처리를 켜면 손이 가린 부분도 기억 모양으로 채워진 마스크에서 값을 읽는다 — 이 조합은 실영상으로 확인하지 않았다.
- **StillLock/EMA 와 amodal:** 둘 다 추적 내부 상태 위에서 동작하고 amodal 은 출력 단계에서만 마스크를 합성하므로 충돌 없음(StillLock 테스트 통과). 하이브리드/끝점 클릭 판정은 EMA 를 거친 `center` 를 받는다(`_mouse_object` 에서 EMA 적용) — 클릭 거리 판정에 쓰는 박스는 EMA 이전 값이다. 이 차이가 접촉 거리 판정에 영향을 주는지는 미검증.
- **번들 빌드:** `packaging/build_bundle.py` 는 우리 쪽(깊이 가중치 필수 자산 검사 포함)을 유지. 포크가 만든 배포 파일(`releases/…hybrid…`, `…ui-polish…`)은 가져오지 않았다. 새 번들은 필요하면 다시 빌드해야 한다(이번에는 빌드하지 않음).

### 10.4 검증
- 백엔드 **444개 통과**(우리 382 + 포크 신규/수정 테스트), 프런트 **132개 통과**, `tsc --noEmit` 오류 없음, `npm run build` 성공(`dist/handguide.png` 포함).
- 포크가 보고한 한계는 그대로다: 실제 카메라·손 검증 없음(문턱값은 합성 기준), 접촉은 영상상 박스 거리 추정, 하이브리드는 쥠 분류기가 아니라 영상 근접·분리 기반, 끝점 추적은 곧게 든 순간에만 점을 찍음, EfficientTAM 손끝 보정의 효과 미입증.
- 우리 쪽 벤치(`bench/pen`, `bench/still`)는 이 병합에서 파일을 바꾸지 않았다. 이번 병합 뒤에 다시 돌리지는 않았다.

### 10.5 다음에 할 일 (추가)
1. 서버를 재시작하고 실카메라로: 물체 마우스(깊이 모델 기본 + 손가락 클릭), 하이브리드, 펜(floor+깊이) 순서로 화면 리허설. 특히 **손 가림 처리 켠 상태에서 amodal 마스크 + 모델 깊이** 조합과 **EMA 가 클릭 접촉 거리에 미치는 영향** 확인.
2. 하이브리드 `coordinate_mode="depth"` 에서 모델 깊이 감도(`depth_model_range`)가 적절한지 확인(맨손 단계 전환 시 커서 점프 없는지).
3. 새 번들(`packaging/build_bundle.py`) 빌드 + README/INSTALL 의 버전·설명 정리(포크 HANDOFF 의 "남은 것"과 동일).

## 11. UI 롤백 · 마우스 깊이 기본값 복귀 · 물체 바닥 기준점(anchor)

### 11.1 UI 롤백 (`anycontrol-web-1.4` 구성으로)
- `anycontrol-web-1.4` 는 fork 도입 **직전** 우리 상태와 프런트·백엔드 소스가 같았다(`diff` 로 확인). 그 폴더의 파일로 UI만 되돌렸다: `App.tsx`, `AutoCalibration.tsx(+test)`, `CameraView.tsx`, `DrawingPad.tsx(+test)`, `MousePanel.tsx(+test)`, `ObjectPanel.tsx(+test)`, `Panel.tsx`, `Tutorial.tsx`, `VirtualDesktop.tsx`, `styles.css`.
- 삭제: `BetaBadge.tsx`, `WorkspaceGuide.tsx`(+test) — 요청한 **위쪽 3단 안내 요소**, `frontend/public/handguide.png`.
- 유지(UI가 아닌 것): `connection.ts`(창 닫을 때 `/api/bye`), `overlay.ts`(drawTips·drawPenSkeleton), `protocol.ts`, 백엔드 전부(finger click / 끝점 추적 / 하이브리드 / amodal 마스크 / 간소화된 자동 보정은 동작은 그대로).
- **부작용(중요):** 롤백한 `MousePanel.tsx` 에는 fork 가 추가한 컨트롤이 없다 — 한 손 하이브리드 선택, 손가락 클릭 방식/민감도(`finger_press`), 끝점 추적(`finger_track`, `tip_drop`, `tip_refine`) 슬라이더. 백엔드 기본값(손가락 클릭, 끝점 추적 켬, 하이브리드 꺼짐)은 그대로 작동하지만 UI로 바꿀 수 없다. 필요하면 fork 의 `MousePanel.tsx` 에서 해당 블록만 다시 가져온다. 자동 보정 화면도 1.4 모양(단계 점·3초 카운트다운 없음)이다.
- 펜 Beta 배지가 사라졌고(`BetaBadge` 삭제) 상단 헤더는 1.4 모양(고정 긴급 정지 버튼·연결 칩 없음, 개발자 모드 렌치/배지는 있음).

### 11.2 마우스 깊이 기본값을 예전 방식으로
- `MouseSettings.depth_source` 기본 `size`(물체 크기). Depth Anything 은 마우스 패널의 "앞뒤(깊이) 신호"에서 고르는 **선택지**로 남김(감도 슬라이더·기준 다시 잡기 포함). 모델이 없으면 자동으로 크기. (펜의 깊이 모델 기울기 기본 켬은 그대로.)

### 11.3 물체가 쥐어질 때 커서가 흔들리는 문제: 바닥 기준점(`tracking/anchor.py`)
- **원인:** 물체를 쥐면 분할 영역이 손 때문에 늘었다 줄었다 해서, 영역 중심(포즈)과 크기로 정한 커서가 같이 떤다.
- **해결:** 물체마다(펜 제외) **바닥에 가까운 가장 가운데 아랫부분** 한 점을 기준점으로 잡아 영상에 **항상 표시**(물체 색 점, `ObjectInfo.anchor`, `overlay.drawObjects`)하고, 커서는 이 점으로 움직인다.
  - 시작: 마스크 아래 20% 띠의 x 중앙값, y 는 맨 아랫행에서 높이의 10% 안쪽.
  - 추적: 기준점 둘레(아래 가운데)의 모서리 특징점 ≤40개를 LK 광학 흐름(앞뒤 오차 검사)으로 따라가 **유사변환(이동·확대·회전)** 을 구해 기준점을 옮긴다. 점 하나만 쓰면 곧은 아랫 모서리를 따라 미끄러졌다(조리개 문제) → 여러 점으로 해결. 분할 영역은 따라가는 데 쓰지 않는다.
  - 보정: 마스크의 아래-가운데 측정으로 프레임당 5% 씩 당기되, ① 손이 덮은 비율이 15% 미만이고(손 가림 처리를 켠 경우) ② 마스크 높이·너비가 기대값(처음 크기 × 흐름으로 잰 크기 변화)과 3프레임 연속 맞고(손 가림 처리를 꺼도 동작) ③ 측정이 기준점에서 물체 높이의 30% 이내일 때만. 쥐는 동안에는 당기지 않고 흐름만 쓴다. 흐름을 6프레임 못 믿거나 45프레임 어긋나면 마스크에서 다시 찍는다. 재검출 순간이동·45프레임 이상 안 보임이면 초기화.
  - 크기(깊이): 같은 유사변환의 확대율을 누적한 **흐름 크기**(출력은 프레임당 α=0.3 로 거름)를 크기 기반 깊이 신호로 쓴다 — 마스크 크기가 흔들려도 영향이 없다. 마스크를 믿을 때만 포즈 크기로 3%씩 천천히 맞춘다. 기준점을 새로 찍으면(`generation`) 깊이 커서를 리셋해 점프를 막는다.
- 연동: `pipeline._update_anchors/_anchor_xy/_anchor_norm/_anchor_scale`, `_mouse_object`(커서 위치), 데스크 보정 시 `mouse_foot` 도 기준점. 설정 `MouseSettings.anchor_cursor`(기본 켬; 끄면 예전 분할 중심·크기). UI: 마우스 패널 "바닥 기준점으로 커서 움직이기 (떨림 방지)".
- **측정 (`bench/anchor/run.py`, samples/test.mov, 지갑을 쥐고 움직이는 290프레임, Tier‑0 추적, 손 마스크 없음):**
  | 지표 | 분할 중심(예전) | 바닥 기준점(새) |
  |---|---|---|
  | 위치 고주파 떨림 (1280 폭 px) | 41.9 | **16.2** |
  | 커서 x 떨림 (화면 1000 기준) | 37.2 | **15.1** |
  | 커서 y 떨림 (깊이=크기) | 36.4 | 36.6 (변화 없음) |
  | log-크기 떨림 | 0.0196 | 0.0179 |
  - 눈으로 확인(`--png`): 쥐고 있는 모든 샘플 프레임에서 빨간 기준점이 지갑 아래-가운데에 머문다(첫 구현은 모서리를 따라 미끄러졌다 → 특징점 방식으로 교체).
  - 크기 상관(포즈 vs 흐름) 0.955, 범위 비슷(1.12 / 1.09).
- **한계:** (1) **세로(깊이) 떨림은 그대로**다 — 크기 기반 깊이 신호의 잡음이 비슷하게 큼. 이 영상은 손에 든 카메라라 실제 크기 변화도 섞여 있어 어느 쪽이 진짜 흔들림인지 정답 없이 가를 수 없다. 개선 후보: 기준점 y 위치(바닥 거리)를 깊이 신호에 섞기. (2) 손 마스크 없이 측정(실제 앱은 손 가림 처리를 켜면 신뢰 판정이 더 정확). (3) 정답 좌표가 없어 떨림(고주파)과 눈으로만 평가. (4) 무늬 없는 바닥 가장자리(검은 물체 등)에서는 특징점이 적어 흐름을 못 믿고 `held`/재시작이 늘 수 있다(이 영상에서 `held` 18/290프레임). (5) 물체가 크게 회전해 너비가 변하면 마스크 보정이 꺼져 드리프트를 흐름만으로 견딘다.
- 테스트: `test_anchor.py`(8건: 마스크가 손으로 끌려가도 4px 이내, 반쪽 마스크, 흐름 크기, 재시작/세대, 해상도 변환, 파이프라인 연동·설정 끄기·보이지 않을 때 숨김), `overlay.test.ts`(기준점 그리기·반전·숨김), `MousePanel.test.tsx`(체크박스). 전체: 백엔드 452, 프런트 127 통과, 빌드 OK.
- **배포 파일:** `releases/`에 보관 중인 이전 배포 파일 는 이번 변경 **이전** 빌드다. 필요하면 다시 빌드해야 한다.

### 11.4 롤백 후 다시 넣은 것 (요청)
- **펜 Beta 배지:** `BetaBadge.tsx`, `Panel` 의 `badge` prop, 위치: 그리기 데모 탭·패널 제목(펜일 때)·"펜" 버튼·물체 탭(펜)·카메라의 "펜 (두 점)" 버튼·펜 자동 보정 버튼·마우스 패널 펜 설정 안내(`feature-note`)와 펜 선택 항목. CSS `.beta-badge`, `.feature-note`. 소스는 `demos/anycontrol-web-1.4-claudeforkbranch` (fork 스냅샷).
- **`handguide.png`:** `frontend/public/handguide.png` + 튜토리얼(`Tutorial.tsx`는 fork 것으로 교체: 펜 Beta 문구, 엄지·새끼 그림, 손가락 클릭 안내, 하이브리드 설명) + CSS `.tour-guide`.
- **마우스 패널 (`MousePanel.tsx`):** "한 손 하이브리드" 모드 버튼(일반 물체·손 모델 필요, 펜 제외), 하이브리드 설명과 "맨손 전환 거리" 슬라이더, 물체 마우스의 "손으로 클릭하기", 끝점 추적 체크박스·EfficientTAM 손끝 보정 체크박스·"내려야 하는 거리" 슬라이더·"클릭 민감도"·"물체 접촉 거리", 맨손 마우스의 "클릭 방식"(손가락 클릭/엄지 집기+스크롤)과 클릭 민감도, 집기 민감도는 집기 방식·하이브리드에서만, 상태 표시(하이브리드 제어, 검지/중지 내려온 정도·물체까지 거리), 방식별 제스처 안내. 자동 보정은 하이브리드에서 `movementOnly`.
- **카메라 영상:** 검지(빨강)·중지(초록) 끝점 원(`drawTips`)을 다시 그린다.
- **같이 복구한 것:** `AutoCalibration.tsx` 의 `cues` 글리프(`lr`, `nf`, `clicks`, `touch`, `lift`, `rest`)와 `movementOnly` prop. 자동 보정 카운트다운·단계 점은 되살리지 않았다(요청 아님).
- **되살리지 않은 것(요청대로):** 위쪽 3단 안내(`WorkspaceGuide`), 고정 헤더/긴급 정지 버튼, 마우스 패널 접이식 3구역·시작 순서·상태 칩, 작업 화면 CSS 정리.
- 테스트: 프런트 131개 통과(MousePanel 하이브리드·끝점 추적·클릭 방식 테스트 4건 추가, 펜 탭/버튼 이름이 "… Beta"), `tsc` 오류 없음, `npm run build` OK (dist 에 `handguide.png`).

## 12. 정지 배경 모델 (색 + Depth Anything) — 일반 물체 추적 강화 (2026-10-16)

자세한 설명·결과·실행법: `bench/fg/README.md`. 변경 전 백업: `../anycontrol-web-backup-before-depthfg/` (models·samples·node_modules 제외).

- 신규 `tracking/scene.py` `SceneModel`: 픽셀별 색 배경(밝기·카메라 미세 이동 보정, 그림자 약화, 추적 물체·손은 학습 제외, 물체가 떠난 자리 채우기) + Depth Anything 깊이 배경(프레임마다 아핀 정렬, '가까워짐'만 전경). 배경 20% 이상이 바뀌면 그 프레임 무효 → 기존 동작.
- `vi_tracker.py`: `TrackerConfig.scene`(기본 켬), `scene_w`, `scene_absent`, `scene_t1`(기본 끔), `scene_refresh`. 영역 마스크·'여기 없음' 판정·점 재표본·재분할 후보·등록 후보에 사용. **펜은 제외**(접촉 F1 하락). `observe()`(물체 없을 때 배경 학습), `depth_submit`(앱)/`depth_predict`(평가 sim), `memory()["scene"]`.
- `tier0.refine_mask(scene_logit, scene_w)`, `refresh.RefreshAnchor.scene`, `register.choose_candidate(..., scene)` / `register(..., scene)`.
- `pipeline.py`: `_wire_tracker()`(공유 `DepthService` 연결, 리셋 때도), 물체 없을 때 `tracker.observe`, `scene_snapshot()`. `server/objects.py` 등록이 스냅샷을 넘긴다.
- 평가: `eval/trackers.py` 에 `vi_noscene`(이전 동작), `vi_fgd`(색+깊이), `vi_fg_t1`. `bench/pen/track_cache.py` 에 `PEN_TRACKER` 환경변수. 정답 도구 `bench/fg/make_gt.py`, `bench/fg/pen_iou.py`, 정답 `bench/fg/gt/*.json`.
- 결과 요약: 합성 tune 성공률 0.870→0.907, 비가시 오검출 0.234→0.016 / 합성 eval(튜닝 안 함) 성공률 0.886→0.883(동일), 오검출 0.142→0.068 / 실영상 test.mov 0.954→1.0(실시간 0.861→0.884), 깊이까지 켜면 중심 오차 0.114→0.099. 펜 접촉 F1 변화 없음. 처리 시간 +약 3~4ms/프레임.
- 테스트 `backend/tests/test_scene.py`(14건). 백엔드 전체 466 통과. 프런트 변경 없음.
- **다음 할 일**: 실카메라로 체감 확인(특히 물체를 쥐고 움직일 때, 조명 변화, 카메라를 건드렸을 때), 손 가림 처리를 켠 상태와의 조합 확인.
- 개발자 보기 확장: 카메라 도구줄 "깊이 맵 보기"(개발자 모드)가 응답을 받는 대로 다시 요청(약 6Hz, 서버는 추적기가 계산해 둔 최신 깊이를 재사용, 0.15초보다 오래되면 직접 요청). 선택 상자로 "깊이 / 배경 모델(전경 판정)" 전환, "진하기" 슬라이더. 새 API `GET /api/dev/scene-map`(빨강 = 배경과 달라짐, 파랑 = 배경 그대로, 투명 = 모름), `dm.scene_map_images`. 스토어 `depthMapKind`, `depthMapOpacity`. 테스트: `DepthMapButton.test.tsx`(3건), `test_depth_model.py::test_scene_map_images_and_endpoint`.

## 13. 가만히 놓인 물체: 기준점 바닥 복귀 · 자동 분할 재지정 · 분할 후보 2개 (2026-10-16)

- 신규 `tracking/settle.py` `SettleWatch`(물체마다, pipeline `_settle`): 추적 중·쥐지 않음·손 거의 없음에서 중심이 물체 크기의 4%, 크기가 5% 안에 머물면 '정지'. 0.3초 넘게 안 보였다 다시 잡히면 '재추적'.
- **기준점 바닥 복귀**: 정지가 1초 이어지면(정지 구간마다 한 번) `ObjectAnchor.rebase(mask)` — 기준점이 마스크 바닥 아래-가운데에서 물체 높이의 12% 넘게 벗어나 있으면 그 자리로 다시 찍는다(세대 +1 → 깊이 커서 기준 새로 시작). 흔들기·뒤집기 뒤 내려놓고 손을 떼면 점이 바닥으로 돌아온다.
- **자동 분할 재지정**(`pipeline.auto_reseg`, 기본 켬): 재추적 뒤 1초 정지, 그리고 30초 정지할 때마다(최소 5초 간격) 지금 프레임에서 지금 추적 박스(6% 여유)를 프롬프트로 다시 분할한다. '다시 선택'과 같은 경로(`processor.reselect`: id·이름·매핑·마우스 연결 유지)이고, 후보 번호는 사용자가 고른 것(0/1)을 쓴다. 분할 중 움직였거나 새 박스가 지금 박스와 IoU < 0.5·면적비 0.5~2 밖이면 버린다. 펜·자동 보정 중 제외. 실행: `server/objects.py` `auto_reseg_once/loop`(0.25초 간격, `app.py` lifespan 에서 시작, `app.state.objects_router`).
  - '분할 후보 재지정' 버튼(수동)은 예전처럼 등록 때 프레임·프롬프트를 쓴다. 자동은 그 방식이 물체가 움직인 뒤 옛 위치로 되돌리므로 다시 선택 방식을 택했다.
- **분할 후보 2개**: `register.MAX_CANDIDATES = 2`. 세 번째 후보를 뺐고, 버튼은 서버가 알려 주는 후보 수로 순환하므로 1↔2만 오간다(프런트 변경 없음).
- 테스트 `test_settle.py`(7건). 백엔드 474 통과. 실카메라 확인 필요: 정지 판정 문턱(4%·5%)이 손에 든 카메라에서 너무 엄격하거나 느슨한지, 자동 재지정 직후 커서가 튀지 않는지.

### 13.1 개발자 설정·격자 판정 (같은 날 후속)
- **자동 분할 재지정 설정(개발자 모드)**: 물체 패널(일반 물체)의 `AutoResegControl` — "자동 분할 재지정" 체크박스, "오래 정지 기준 N초"(기본 **15초**, 3~600). 모든 일반 물체 공통, 이미 있는 물체에도 바로 적용. API `GET/PUT /api/dev/auto-reseg` `{enabled, long_s}`, `processor.set_auto_reseg()`. 테스트 `AutoResegControl.test.tsx`, `test_settle.py::test_dev_auto_reseg_settings…`.
- **배경에서 사람이 오갈 때**: 배경 모델의 무효 판정을 픽셀 비율(20%)에서 **격자 칸 단위**로 바꿨다(`SceneConfig.grid=(8,6)`, 칸 안 배경 픽셀 15% 이상 변하면 '바뀐 칸', 배경을 아는 칸의 50% 이상이 바뀌면 무효). 카메라 이동·조명 급변은 화면 전체에 퍼지고 사람은 몇 칸에 몰리므로, 뒤에서 사람이 지나가도 꺼지거나(그동안 사람까지 배경으로 다시 배움) 하지 않는다. 물체 판정은 원래 물체 주변 ROI·형태 제약 안에서만 쓰므로 먼 사람의 영향은 작다. 테스트 `test_people_walking_in_the_far_background…`. test.mov 결과 동일(1.0 / 0.103).
- **배경 모델 보기에 격자**: "깊이 맵 보기 → 배경 모델" 겹침에 주황 테두리(바뀐 칸, 숫자 = 바뀐 %), 회색(물체·손이 덮어 세지 않는 칸), 가는 흰 선(그대로인 칸). 무효일 때도 격자만 그려 왜 꺼졌는지 보이고, 상태 줄에 "바뀐 칸 a/b (c칸 이상이면 끔)".

## 14. 기본 모드 / 고급 모드 · 물체 사진 카드 · 패치 케이블 · 실시간 기억 삭제 · 60초 시연 화면 · 카메라 기본값 (2026-10-18)

발표·부스 전 정리 작업. 요청: 자잘한 설정은 고급 모드로, 기본 모드에는 잘 되는 것만. **튜토리얼(`Tutorial.tsx`, `tutorial.ts`)과 `anycontrol-chat` 은 요청대로 건드리지 않았다** → 튜토리얼에는 아직 "개발자 모드"·"한 손 하이브리드" 설명이 남아 있다(나중에 한 번에 반영). 당시에는 버전 번호와 `releases/`를 바꾸지 않았다. 현재 버전은 문서 상단 최신 기록을 따른다.

### 14.1 개발자 모드 → 고급 모드
- 내부 이름은 그대로 `devMode`(localStorage `anycontrol.devMode`). 화면 글자만 "고급 모드"로 바꿨다. 상단 버튼(`DevModeToggle`)은 렌치 + "기본"/"고급" 글자, 켜면 제목 옆 배지 "고급 모드".
- 고급 모드를 끄면 개발용 보기(바닥 맵·깊이 겹침)를 닫고, 선택 모드가 펜·종이·수평 보정이면 일반 물체 선택으로 되돌린다(`store.setDevMode`). **실시간 기억 보기는 기본 기능이 되어 닫지 않는다.**

### 14.2 기본 모드에 남긴 것 / 고급 모드로 옮긴 것
| 영역 | 기본 모드 | 고급 모드에만 |
|---|---|---|
| 데모 탭 (`App.tsx` `BASIC_DEMOS`) | 매핑·게임패드, 레이싱, 좀비 서바이벌 | 가상 데스크톱(Beta, 클릭 불안정), 펜·맨손 그리기(Beta) |
| 출력 대상 | 그대로 (가상/실제 = "컴퓨터로 시연") | – |
| 마우스 (`MousePanel.tsx`) | 끄기/맨손/물체, 긴급 정지, 자동 보정, 커서로 쓸 물체, 손으로 클릭하기, 커서 감도·반전, 부드럽게↔빠르게, 맨손 제스처 안내 | 손 인식 엔진, 물체 이동 방식·바닥 기준점·깊이 신호(모델)·깊이 감도, 끝점 추적·EfficientTAM 보정·클릭 민감도·접촉 거리, 좌우·깊이 감도, 가장자리 사선 보정(종이), 스크롤 반전, 집기 민감도, 손 이동 방식·클릭 방식·터치패드 슬라이더, 펜 설정, 상태 표(dl) |
| 카메라 패널 (`SourcePanel.tsx`) | 카메라 켜기/끄기, 영상 정지, 장치 새로고침, 자동 선택 + 카메라 목록(**17sa 숨김**), **데모 영상 표시**(test.mov·pen_test.mov) | Desk View 체크·설정·구도 적용, 17sa 카메라, 합성 장면 |
| 카메라 미리보기 (`CameraView.tsx`, `CameraTools.tsx`) | 영상 정지, 영상 좌우 반전, 긴급 정지, 물체(드래그·클릭) 등록 | 전체 입력 좌우 반전, 표시 체크(물체·손·펜촉), 깊이 맵 보기, 펜(두 점) 등록, 종이 선택, 수평 보정, 책상 구역 표시 |
| 물체 (`ObjectPanel.tsx`) | 사진 카드, 이름 바꾸기, 상태·신뢰도, 경고, 중립·다시 선택·다른 분할 후보·삭제·모두 삭제, **실시간 기억 관리** | 추적 상태/재분할/EMA/손 가림 토글, 축 값 막대, 무늬·대비, 자동 분할 재지정, 바닥 맵, 기억 세부 수치(정지 잠금·모양·색·재획득 기준·AI 앵커 수) |
| 매핑 (`MappingPanel.tsx`) | 프로필 이름·저장·불러오기·예시, 보기만/출력, **패치 베이**, 매핑 줄(입력→출력, 보여 주며 설정, 삭제) | 프로필 삭제, 매핑 줄 "세부 설정"(범위·데드존·곡선 등) |
| 성능(Hud) | – | 전체 |
| 헤더 | 화면 초기화, 글씨 크기, 언어, 안내, 기본/고급 | "60초 시연 화면" 체크 |

### 14.3 한 손 하이브리드 삭제
- 마우스 모드 버튼에서 뺐고 관련 설명·슬라이더·상태 줄도 지웠다. 예전에 `object_hybrid: true` 로 저장된 설정을 받으면 프런트가 자동으로 `false` 로 보낸다. 백엔드 하이브리드 코드는 남아 있지만(꺼진 채) UI로는 켤 수 없다.

### 14.4 카메라: homese → FaceTime (`capture/devices.py`, `server/app.py`)
- 자동 선택(index −1) 순서: 이름에 `homese` → `facetime` → (없으면) 연속성 카메라 → 첫 카메라. `ANYCONTROL_CAMERA_PREFER="이름1,이름2"` 로 바꿀 수 있다(`CAMERA_PREFER`, `preferred_camera`).
- **실행 중 폴백** `camera_fallback_loop`: 자동 선택으로 연 카메라가 4초 넘게 프레임을 못 보내면(iPhone 잠김·멀어짐) 그 카메라를 건너뛰고 다음으로 바꾼다. **지정한 순서(homese·FaceTime) 안에서만** 바꾸고 17sa 등으로는 넘어가지 않는다. 사용자가 카메라를 직접 고르면 건너뛰기 목록(`app.state.camera_exclude`)을 비운다. 확인: homese 무응답 → 7초 뒤 FaceTime 으로 전환(로그 `falling back to …`).
- 17sa 는 기본 모드 카메라 목록에서 숨김(`SourcePanel.isHiddenCamera`), 고급 모드에서는 보인다.
- 테스트 `test_desk_view.py::test_auto_select_prefers_homese_then_facetime_and_skips_stalled`.

### 14.5 물체 패널 사진 카드
- 물체 탭을 카드로 교체: 등록(다시 선택) 때 기억한 모습 사진 + 상태 점 + 이름. 사진은 새 API `GET /api/objects/{id}/thumbnail` → `{image}` (`ViTracker.thumbnail` → `memory_view.render_icon`: 물체 바깥만 살짝 어둡게, 윤곽선 없음). 물체·후보가 바뀌거나 다시 선택이 끝나면, 그리고 15초마다 다시 받는다(자동 재분할 반영). 사진이 없으면 색 점.
- CSS `.obj-cards`, `.obj-card`, `.obj-photo`, `.obj-state`.

### 14.6 패치 케이블 매핑 (`patch.ts`, `components/PatchCables.tsx`)
- 매핑 탭이 열려 있는 동안 물체 카드 오른쪽에 **잭**이 생기고, 매핑 패널 위쪽 **패치 베이**에 기능 잭 8개가 있다: 조향(왼쪽 스틱 X ← 좌우), 앞뒤(스틱 Y ← 깊이), 가속(RT ← 밀기), 브레이크(LT ← 당기기), A 버튼·스페이스 키·마우스 클릭(← 위로 들기), 오른쪽 스틱 X(← 기울이기). 기본값은 `PATCH_FNS` 의 range·deadzone·curve.
- 연결: 잭을 끌어 반대쪽 잭에 놓기, 또는 한 번 눌러 집은 뒤 반대쪽 잭 누르기. **양방향**(물체→기능, 기능→물체). ESC·빈 곳 클릭 = 취소. 케이블을 누르면 뺀다.
- 규칙: 기능 잭 하나에 선 하나(새로 꽂으면 같은 출력의 예전 매핑은 빠짐), 물체 잭에는 여러 선. 연결은 그냥 일반 매핑 하나(`makeMapping`)라 매핑 줄 목록·저장·레이싱/좀비 데모에 그대로 쓰인다. 손 제스처 매핑은 선으로 그리지 않는다.
- 그리기: 화면 전체를 덮는 SVG 하나(`svg.patch-cables`, fixed, z 60)에 처진 베지어 곡선, 물체 색. 잭 위치는 rAF 로 매 프레임 읽고 바뀔 때만 다시 그린다(접힌 패널이면 생략). 케이블 끝이 잭을 덮으므로, 케이블을 눌렀을 때 아래에 잭이 있으면 잭을 누른 것으로 처리한다(`jackUnder`).
- 스토어: `patchDrag`(끄는 중인 선), `patchConnect`(매핑 패널이 등록하는 연결 함수, null 이면 잭 숨김).
- 테스트 `patch.test.ts`(3건). 실제 브라우저에서 끌기·클릭 두 번·케이블 빼기·서버 반영 확인.

### 14.7 실시간 기억 선택 삭제
- 물체 상세의 **[실시간 기억 관리]**(기본 모드)로 기억 보기를 열면, AI 앵커·재획득 그림마다 체크박스가 있고 [선택한 기억 삭제 (n)] / [모두 선택]. **등록 모습은 지울 수 없다**(재획득 기준이라서; [다시 선택]으로만 바뀜).
- API `POST /api/objects/{id}/memory/forget {items:[{kind,t}]}` → 새 기억 보기 + `removed`. `ViTracker.forget_memory`: 그림을 지우고, Tier 1(EfficientTAM)의 해당 앵커 조건 프레임도 GPU 스레드에서 지운다(`StreamingTAM.forget`, 앵커 시각 `ObjectMemory.cond_t` 로 매칭, `anchor_scales` 도 같이, 최근 비조건 메모리는 비워 새로 쌓음). 재획득 그림을 지우면 그때 다시 고정한 앵커도 같이 빠진다.
- 실제 확인(test.mov): 앵커 체크 → 삭제 → 그림 사라짐, Tier 1 앵커 2→1. 테스트 `test_memory_forget.py`(3건), `ObjectPanel.test.tsx`(삭제·사진 카드).

### 14.8 60초 무입력 시연 화면 (`components/IdleShowcase.tsx`, `presence.py`, `server/idle.py`)
- 창이 보이는 상태에서 60초 동안 입력이 없으면 화면을 어둡게 덮고 **"시연영상placeholder"** 를 띄운다(영상이 준비되면 이 자리에 `<video>` 를 넣으면 된다).
- 입력으로 치는 것: 마우스 이동·클릭·휠·키보드·터치, 그리고 **카메라 입력**(맨손 마우스에서 손이 보임, 커서가 1% 넘게 움직임, 매핑 값이 0.05 넘게 바뀜 — 부스에서 마우스 없이 물체로만 노는 경우). 이 중 하나면 바로 닫힌다.
- **사람 접근 감지**: 시연 화면이 떠 있는 동안 약 3Hz 로 `GET /api/idle/presence` (처음 한 번 `reset=true` = 뜬 순간의 장면을 배경 깊이로). `PresenceWatch`: Depth Anything 깊이를 64×48 로 줄여 배경에 아핀(a·d+b) 두 번 맞추고(두 번째는 크게 어긋난 픽셀 제외), 배경 범위(5~95%)의 12% 넘게 가까워진 픽셀이 화면의 6% 를 넘으면 `present`. 사람이 없을 때만 배경을 5%씩 따라간다. 깊이 모델이 없으면 `ready:false` → 마우스·키보드로만 복귀.
- 고급 모드 헤더의 "60초 시연 화면" 체크로 끌 수 있다(localStorage `anycontrol.idleShowcase`, 기본 켬). **발표 중에는 끄기 권장**(말만 하고 60초 지나면 어두워진다).
- 테스트 `test_presence.py`(2건), `IdleShowcase.test.tsx`(4건). 실제 브라우저에서 60초 뒤 표시·마우스로 닫힘 확인. **사람이 실제로 다가올 때 닫히는지는 카메라 프레임이 없는 환경이라 실측 못 함 → 부스 카메라로 확인 필요**(문턱: `PresenceConfig.thr/min_frac`).

### 14.9 파일 지도 (이번 작업)
- 백엔드: `capture/devices.py`(선호 순서·exclude), `server/app.py`(폴백 루프, idle 라우터), `server/objects.py`(thumbnail, memory/forget), `server/idle.py`(신규), `presence.py`(신규), `pipeline.py`(`object_thumbnail`, `forget_object_memory`), `tracking/vi_tracker.py`(`thumbnail`, `forget_memory`), `tracking/tier1.py`(`cond_t`, `forget`), `tracking/memory_view.py`(`render_icon`). 테스트 `test_memory_forget.py`, `test_presence.py`(신규), `test_desk_view.py`(추가).
- 프런트: `App.tsx`, `store.ts`, `api.ts`, `patch.ts`(신규), `components/PatchCables.tsx`·`IdleShowcase.tsx`(신규), `DevMode.tsx`, `MousePanel.tsx`, `SourcePanel.tsx`, `CameraView.tsx`, `CameraTools.tsx`, `ObjectPanel.tsx`, `MemoryView.tsx`, `MappingPanel.tsx`, `styles.css`. 테스트 갱신: `DevMode/MousePanel/SourcePanel/ObjectPanel/FloorMapView.test.tsx`, 신규 `patch.test.ts`, `IdleShowcase.test.tsx`.

### 14.10 검증
- 백엔드 482 passed, 프런트 143 passed, `tsc` 오류 없음, `npm run build` OK(`frontend/dist` 갱신).
- 실제 앱(브라우저, test.mov): 기본/고급 화면 전환, 17sa 숨김, 사진 카드, 케이블 끌기·클릭 두 번·빼기, 기억 삭제, 60초 화면 표시·해제. 카메라 폴백 로그 확인.

### 14.11 다음에 할 일
- 튜토리얼·anycontrol-chat 을 이번 변경(고급 모드 이름, 하이브리드 삭제, 패치 케이블, 기억 관리, 시연 화면)에 맞게 한 번에 갱신.
- 시연 영상이 준비되면 `IdleShowcase` 의 placeholder 를 `<video autoplay muted loop>` 로 교체.
- 부스 카메라로 사람 접근 문턱(`thr 0.12`, `min_frac 0.06`) 확인·조정.
- 버전 1.8.0 표기·릴리스 빌드는 아직(요청 시).

## 15. 후속 정리 (2026-10-18 같은 날): 펜·가상 데스크톱 기본 모드, 성능 패널, 패널 끌어 옮기기, 호버링, 끝점 추적 삭제, 창 닫으면 종료

### 15.1 기본 모드 범위 조정 (§14.2 표 갱신)
- **펜**: 기본 모드에도 보인다. "펜 (두 점)" 등록 버튼, 펜·맨손 그리기 탭(Beta 유지), 마우스 패널의 펜 설정(상대 이동·감도·깊이 보정). 종이 선택·수평 보정은 여전히 고급 모드. 고급 모드를 끌 때 펜 선택 모드는 유지하고 종이·수평 보정 선택만 되돌린다.
- **가상 데스크톱**: 기본 모드에 넣고 Beta 딱지를 뗐다. 데모 탭은 이제 모드와 상관없이 5개 모두 보인다.
- **성능 패널**: 기본 모드에도 보인다. 기본 모드는 연결·카메라·카메라 fps·처리 fps·화면 지연(p50) 5줄만, 고급 모드는 예전 전체 표(p50/p95).

### 15.2 패널 배치 + 제목 줄로 끌어 옮기기 (`panelLayout.ts`, `App.tsx`)
- 기본 배치: 메인 열 = 카메라 미리보기 · 데모(탭+패널) / 설정 왼쪽 = **출력 대상 → 성능 → 물체** / 설정 오른쪽 = **카메라 → 마우스**.
- 모든 패널(메인 열 2개 포함 7개)을 **제목 줄을 잡고 끌어** 세 열 어디로든 옮길 수 있다. 6px 넘게 움직이면 끌기 시작, 놓은 패널의 위/아래 절반에 따라 앞/뒤로 들어가고(파란 선 표시), 빈 열은 점선 테두리로 표시돼 끝에 들어간다. 제목 줄의 버튼(최소화·ⓘ 등)은 끌기에 쓰지 않는다.
- 배치는 localStorage `anycontrol.panelLayout` 에 저장, [화면 초기화]로 기본 배치 복원. 좁은 화면(한 열)에서는 배치 순서대로 쌓인다.
- 테스트 `panelLayout.test.ts`. 실제 브라우저에서 마우스 패널을 다른 열 맨 위로 옮겨 저장되는 것 확인.

### 15.3 실시간 카메라 호버링
- 기본 위치를 **왼쪽 아래**로(CSS `bottom/left: 1rem`). 끌어 옮긴 위치는 그대로 저장되고, 두 번 클릭하면 왼쪽 아래로 돌아간다.
- 고급 모드 헤더에 **"카메라 호버링"** 체크(localStorage `anycontrol.floatingCamera`, 기본 켬). 끄면 스크롤해도 작은 카메라 창이 뜨지 않는다.
- 헤더 순서: … 안내 · **[60초 시연] [카메라 호버링]**(고급 모드에서만) · [기본/고급]. "60초 시연 화면" 이름을 "60초 시연"으로 바꿨다.

### 15.4 검지·중지 끝점 추적 삭제
- 마우스 패널의 "검지·중지 끝점 직접 추적", "EfficientTAM 손끝 보정", "내려야 하는 거리", 검지/중지 상태 줄, 영상의 빨강·초록 손끝 원(`drawTips` 호출)을 지웠다.
- 백엔드 `MouseSettings.finger_track` 은 기본 `False` 이고 validator 로 **항상 False**(예전 저장값이 켜져 있어도). 그래서 끝점 추적·손끝 분할(`TipRefiner`)은 돌지 않고, 물체 마우스의 손 클릭은 손 인식(랜드마크) 판정만 쓴다. 코드(`hands/tip_track.py`, `tip_refine.py`, `overlay.drawTips`)는 남아 있다.
- 테스트: `test_tip_track.py` 의 끝점 추적 컨트롤러 테스트 2건을 "항상 꺼짐" 테스트로 교체, `MousePanel.test.tsx` 갱신.

### 15.5 창을 닫으면 서버 종료 (bye 후에도 안 꺼지던 문제)
- 재현: 창 하나를 닫는 정상 경우는 원래도 bye → 5초 뒤 종료됐다. 남는 경우의 원인은 **숨은 예전 탭**이었다. AnyControl 을 다시 켜면 새 탭이 열리는데, 예전 탭이 자동 재연결해 연결을 붙잡고 있어서 보이는 창을 닫아도 연결이 0이 되지 않았다.
- 해결: 한 번에 **한 창만 연결**.
  - 페이지가 처음 붙을 때 `/ws?fresh=1`. 서버는 fresh 연결이 오면 다른 창에 `replaced` 를 보내고, 받은 창은 연결을 닫고 다시 붙지 않는다(안내 화면 "다른 창에서 AnyControl을 열었습니다 · [이 창에서 계속]" — 누르면 새로고침해 이 창이 연결을 가져온다).
  - hello 에 `boot_id`(서버 실행마다 새 값)와 `browser_auto_open` 을 담는다. 재연결한 창이 boot_id 가 바뀐 것을 보고 서버가 브라우저를 자동으로 열었으면(=새 탭이 열렸으면) 스스로 물러난다("AnyControl이 새 창에서 열렸습니다"). `--no-browser` 로 켰으면 예전 탭이 그대로 다시 붙는다(예전 동작).
- 확인: 창 두 개 → 첫 창이 물러남. 물러난 창이 열려 있는 채로 연결된 창을 닫자 약 5초 뒤 서버 프로세스 종료(로그 "웹앱 연결이 모두 닫혀 AnyControl을 종료합니다.").
- 파일: `server/hub.py`(`others`), `server/app.py`(ws fresh·hello), `__main__.py`(`browser_auto_open`), `connection.ts`(fresh·boot_id·dormant), `store.ts`(`dormant`), `App.tsx`(안내 화면).

### 15.6 검증
- 백엔드 481 passed, 프런트 145 passed, `tsc` 오류 없음, 빌드 OK. 브라우저에서 배치·끌어 옮기기·헤더 토글·한 창 연결·종료 확인. 튜토리얼·anycontrol-chat 은 여전히 손대지 않음.

## 16. 게임·터치 입력 대량 추가 (2026-10-18 같은 날)

### 16.1 작은 변경
- **카메라 호버링 기본 위치: 오른쪽 아래**(§15.3 의 왼쪽 아래를 다시 바꿈).
- **게임 옆 '이 물체로 게임 연결' 창 삭제** (`GameControls.tsx` 삭제). 게임 입력은 매핑 탭(패치 케이블)에서 정하고, 일부 게임은 카메라 물체를 직접 읽는다(아래).
- **모든 게임: Space = 시작/일시정지**(`gameSession.ts` 창 전체 keydown, 입력창·버튼에 초점이 있으면 양보). 레이싱의 Space 브레이크는 없앴다(S/↓).
- 게임은 이제 **'보기만' 모드에서도 계산된 매핑 값을 쓴다**(`inputActive` 가 `sent` 를 요구하지 않음). 게임은 앱 안의 가상 입력이라서.
- 게임 공통 버튼 줄 `GameButtons.tsx`, 카메라 물체 직접 읽기 `gameObjects()`/`s.objectsInput()`(보이는 일반 물체, 입력 반전 반영 화면 기준 왼쪽부터 정렬 → 2인 게임은 왼쪽 물체 = 1P).

### 16.2 물체 터치 입력 (매핑 입력 `touch`)
- 백엔드 `touch_input.ObjectTouch`: 손 인식 랜드마크의 검지·중지 끝이 물체 박스(긴 변 8% 넓힘) 안에 들어오면 닿음. 2프레임 연속이면 켜고 3프레임 연속 벗어나면 끈다. 펜·안 보이는 물체는 제외.
- 스키마 `ObjectTouchInput {source:"touch", object}` → 버튼·키 출력에 쓴다. 매핑이 쓰면 손 인식이 자동으로 돈다(`needs_hands`). 상태 `state.touch`.
- UI: 매핑 줄 입력 종류 "손가락이 물체에 닿음", 패치 케이블 편집기의 입력 "손가락이 닿음", DJ 버튼 잭의 기본 입력.
- **한계**: 카메라 한 대라 화면상 겹침으로 판정한다. 물체를 쥔 손가락도 닿음으로 본다.

### 16.3 바닥 3×3 그리드 터치 (매핑 입력 `grid`, 두더지·틱택토)
- 백엔드 `touch_input.GridTouch`: 구역 = 종이 4점 보정(또는 Desk View)이 있으면 그 책상 면(원근 변환), 없으면 카메라 화면 전체. 손바닥 중심(랜드마크 0,5,9,13,17 평균)을 3×3 칸으로 나눈다. **손바닥이 한 칸에서 0.12초 멈추면 터치**. 다른 칸으로 옮기거나, 빠르게 움직이거나, 손 크기가 12% 넘게 바뀌거나(들어 올림), 손이 사라지면 뗀 것으로 본다. RGB 한 장으로는 실제 접촉을 알 수 없어 '멈춤'을 터치로 쓴다. 바닥에 물체가 없어야 손 인식이 안정적이다.
- API `PUT /api/touch/grid {enabled}`(그리드 게임이 열려 있는 동안 켬, 손 인식도 같이 돔). 매핑이 `{source:"grid", cell:0..8}` 을 쓰면 자동으로 돈다. 상태 `state.grid {mode, point, hover, pressed, taps, history}`.
- **카메라 영상 위 그리드 표시**: 그리드가 켜지면 영상 위에 3×3 점선 그리드(종이 보정이 있으면 원근대로), 손바닥이 머무는 칸(파랑)·터치 중인 칸(초록), 손바닥 십자 표시, 최근 터치 자리(노란 점)를 그린다(`overlay.drawFloorGrid`, `homography`). 끄기: 카메라 도구 "바닥 3×3 그리드 표시"(기본 모드에서는 그리드가 켜져 있을 때만 보임) / 고급 모드 표시 체크.
- 매핑 줄 입력 종류 "바닥 3×3 칸 터치" + 칸 선택 → 아무 버튼·키에 매핑 가능.
- 테스트 `test_touch_input.py`(3건). 실영상(test.mov)에서 손으로 두더지가 잡히는 것 확인.

### 16.4 새 게임 (탭 순서: 매핑 · 레이싱 · 퐁 · 과일 받기 · 두더지 잡기 · 틱택토 · 좀비 · DJ · 가상 데스크톱 · 그리기)
- **두더지 잡기** (`WhackDemo.tsx`, `grid.ts`): 45초, 두더지가 나온 칸 터치. 금색 300점. 헛손질 집계.
- **틱택토** (`TicTacToeDemo.tsx`): 1인(컴퓨터 = 미니맥스, 지지 않음) / 2인 번갈아. 전적 유지.
- 두 게임 공통(`gridInput.ts`): 왼쪽 판 + 오른쪽 **입력 피드백 그림**(바닥 구역 축소판에 손바닥 위치 십자, 머무는 칸, 최근 터치 좌표 점, "터치! 칸 n" 문구, 구역 종류). 마우스 클릭·숫자 키(7 8 9 / 4 5 6 / 1 2 3)도 됨.
- **퐁** (`PongDemo.tsx`, `pong.ts`): 1인(컴퓨터) / 2인. **물체 크기(깊이 축)로 패들 상하**: 가까이 = 위, ±0.35 면 끝까지(`sizeToPaddle`). 2인은 왼쪽 물체 = 왼쪽 패들. W/S, ↑/↓ 키. 7점 선승.
- **과일 받기** (`FruitDemo.tsx`, `fruit.ts`): **물체 2개 = 그물 양쪽 손잡이**(물체 화면 위치 그대로, 이름 표시) — 실시간 다중 추적 시연. 60초, 💣 받으면 생명 −1, 연속 받기 배수. 물체 1개 = 짧은 그물, 0개 = ←/→.
- **레이싱 개선** (`racing.ts`, `RacingDemo.tsx`): 최고 속도 2→3, 가속↑, 굽은 길(원심력으로 바깥으로 밀림, 화면도 굽음), 부스터(초록 화살표, 1.6초 최고속 3.8 + 속도선), 코인 연속 배수(최대 ×5), seed 고정 길. **2인 분할 화면**: 물체 두 개 등록 시 왼쪽 물체 = 1P·오른쪽 = 2P, 물체 좌우 이동으로 조향(처음 보인 위치가 가운데, [가운데 다시 잡기]), 가속 자동, 같은 길에서 2500m 먼저 도착 승리. 키보드 A/D(1P)·←/→(2P).
- **좀비 서바이벌 단순화**: 충격파 삭제(`stepSurvival(g, dx, dy, dt, …)`), 조작 선택 창 삭제. 이동 우선순위 = 키보드 → 마우스 커서(맨손·물체 마우스가 켜져 있으면 커서 = 주인공) → 매핑한 스틱(조향·앞뒤 잭). 예시 프로필 '좀비'도 좌우·앞뒤 이동으로.
- **DJ 셋** (`DjDemo.tsx`, `djAudio.ts`): 음원 없이 WebAudio 로 만든 덱 A(드럼 루프)·덱 B(베이스+아르페지오), 크로스페이더(등전력), 필터(왼쪽 저역·오른쪽 고역), 에코, 템포, 볼륨, 에어혼, 스크래치, 회전하는 턴테이블·박자 LED. [소리 켜기] 후 사용(브라우저 정책). **DJ 패치 베이**: 크로스페이더(좌우 → 오른쪽 스틱 X), 필터(기울기 → 오른쪽 스틱 Y), 덱 A/B 재생·스크래치·에코·에어혼(손가락 터치 → X·Y·LB·RB·B 버튼, 누르는 순간 토글/발동). 연결된 컨트롤은 초록 점. 게임이 쓰는 출력(왼쪽 스틱·LT·RT·A)과 겹치지 않게 골랐다(그래서 일반 패치 베이의 '오른쪽 스틱 X(기울기)' 잭은 뺐다).

### 16.5 매핑 자유도 (`PatchBay.tsx`, `patch.ts`, `mappingDraft.ts`)
- 매핑 초안을 공유 저장소로 옮겼다(`useMappingDraft`/`editDraft`) → 매핑 패널과 DJ 데모가 같은 매핑을 편집한다.
- 패치 베이 공통 컴포넌트: **케이블을 누르면(또는 연결된 잭 이름을 누르면) 케이블 조정**: 입력 종류(좌우·위아래·크기·기울기·손가락 닿음·보이면 켜짐), 감도(×0.3~4, 범위를 좁히거나 넓힘), 방향 반대로, 사용 켜기/끄기, 케이블 빼기. (예전처럼 케이블을 누르자마자 빠지지 않는다.)
- **내 잭 만들기**: 이름 + 내보낼 것(키보드 키·게임패드 버튼·스틱/트리거·마우스) + 입력(물체 움직임 축 / 손가락 닿음). localStorage `anycontrol.customJacks`, × 로 삭제.
- 매핑 줄의 "세부 설정"(범위·데드존·곡선·놓쳤을 때)을 기본 모드에서도 연다. 데모가 자기 잭을 `registerFns(group, fns)` 로 등록하면 케이블 해석(`fnOf`)에 쓰인다.

### 16.6 검증
- 백엔드 484 passed, 프런트 154 passed(새 게임·로직 테스트 `grid.test.ts`, `racing.test.ts` 추가분, `Games.test.tsx` Space·새 게임·2인), `tsc` OK, 빌드 OK. 콘솔 오류 없음.
- 브라우저(test.mov): 영상 위 그리드·손바닥 십자, 두더지 실제 손으로 잡힘, DJ 소리 켜기·덱 재생, 레이싱 2인 분할 주행, 호버링 오른쪽 아래.
- **실측 못 한 것**: 물체 두 개로 하는 과일 받기·퐁 2인·레이싱 2인(test.mov 에 물체가 하나뿐), 물체 터치 → DJ 버튼(실카메라 필요), 종이 보정 원근 그리드. 부스 카메라로 확인 필요.
- 튜토리얼·anycontrol-chat 은 여전히 손대지 않음.

### 16.7 DJ 셋 디자인 개편 (같은 날 후속)
- 실제 DJ 컨트롤러 모양으로 다시 그렸다(`DjDemo.tsx`, CSS `.djc-*`): 검은 하드웨어 몸체(브러시드 결), 상단 브랜드·**호박색 LCD**(BPM·박자 LED·ECHO/LPF/HPF 표시)·전원 버튼, **실시간 파형 화면**(덱 A 시안·덱 B 마젠타, 캔버스로 매 프레임), 덱마다 **조그 휠**(돌아가는 비닐 판·라벨, 진행을 따라 도는 LED 링, 누르면 스크래치)과 **CUE/PLAY 둥근 버튼**(재생 중 초록 발광), 가운데 믹서: 채널마다 **HI·LOW EQ 노브**(위아래 끌기·휠·방향키, 두 번 클릭 = 가운데), **VU 미터**(초록·노랑·빨강 LED, 실제 소리 레벨), **세로 채널 페이더**, 가운데 **FILTER 큰 노브·TEMPO 노브·마스터 VU**, **고무 퍼포먼스 패드 4개**(SCRATCH·ECHO·AIR HORN·FX RESET, 누르면 색 발광), 하단 **크로스페이더**. 물체에 연결된 컨트롤은 노란 ⚡.
- 엔진(`djAudio.ts`): 채널 EQ(저음 셸프 220Hz·고음 셸프 3.2kHz, ±12dB) 추가, 채널·마스터 `AnalyserNode` 로 `level()`·`wave()`. 처음 재생·패드를 누르는 순간 자동으로 소리가 켜진다(따로 전원을 안 눌러도 됨).
- 좁은 폭에서는 덱 두 개가 위에 나란히, 믹서가 아래로(컨테이너 쿼리). 브라우저에서 두 덱 재생·파형·VU·LED 링 확인.

## 17. 패널 정리·매핑 잭 반응 (2026-10-18 같은 날)
- **매핑 패널 분리**: '매핑' 이 독립 패널(슬롯 `mapping`), 그 아래 **'데모' 패널**(슬롯 `demo`)에 나머지 데모. 기본 배치 메인 열 = 카메라 미리보기 → 매핑 → 데모. (배치 저장값은 슬롯 수가 바뀌어 기본 배치로 돌아간다.)
- **데모 패널**: 왼쪽에 아이콘+이름 목록 메뉴(세로 탭), 오른쪽에 게임 화면을 크게(게임 최대 폭 제한 해제). 패널 폭이 560px 보다 좁으면 목록이 위로 접힌다.
- **물체 정보**: 축 값(좌우·상하·깊이·기울기·형태·바닥선)·무늬/대비와 **튐 억제(실시간 EMA)** 체크를 기본 모드에서도 보인다. 재분할·손 가림·추적 상태 줄은 고급 모드.
- **고급 모드 전용 버튼은 초록(`dev-btn`/`dev-check`)**: Desk View 체크·설정·구도 적용, 합성 장면, 17sa 카메라, 종이 선택·수평 보정, 전체 입력 좌우 반전, 프로필 삭제, 재분할·손 가림 체크(기존 깊이 맵·기억·바닥 맵 버튼은 원래 초록).
- **고급/기본 버튼**을 '안내' 버튼과 같은 크기로.
- **N초 시연**: 고급 모드 헤더 체크 옆 숫자(기본 60, 5~3600초, localStorage `anycontrol.idleSeconds`).
- **케이블 반투명**: 꽂힌 케이블은 투명도 0.16(그림자 없음), 마우스를 올리면 진하게. 끄는 중인 선은 그대로.
- **잭 반응**: 연결된 기능 잭은 매핑 값만큼 배경이 밝아지고 옆 막대 미터가 차며, 값이 0.5 이상(버튼 눌림·터치)이면 초록으로 빛난다(`.patch-fn.firing`).
- **세부 조정 창 상시 표시**: 잭(행)·잭 이름·케이블 어느 것을 눌러도 그 연결의 조정 창으로 바뀐다. 고른 게 없으면 첫 케이블, 케이블이 없으면 안내 문구. '닫기' 버튼은 없앴다.
- 프런트 154 passed, 빌드 OK.

## 18. 바닥면 터치·마스크 기반 물체 터치·DJ 매핑·첫 화면·튜토리얼 (2026-10-18 같은 날)

### 18.1 바닥 3×3 = 카메라가 인식한 바닥면 + 손가락 끝 닿음 (§16.3 대체)
- 신규 `floor_surface.FloorSurface`: Depth Anything 상대 역깊이에 1초마다 평면을 RANSAC 으로 맞춘다(화면 아래 65%, 손·물체 박스는 제외). 평면에 맞는 픽셀 중 화면 아래에 닿은 가장 큰 덩어리를 바닥면으로 보고, 위·아래 띠의 좌우 끝으로 **사다리꼴 네 점**을 만든다(최근 4번 중앙값). 이 네 점이 3×3 판의 구역이다(원근대로 나뉨). 종이 4점 보정(또는 Desk View)이 있으면 그 면을 우선한다.
- **닿음 판정**: 손 인식의 검지·중지 끝 자리의 깊이(5×5 중앙값)와 그 자리 바닥 평면 깊이의 차이를 바닥 깊이 범위 대비로 잰다(`height`, 0 ≈ 바닥, + = 떠 있음). 문턱 `touch_on = 0.02 + 0.08·민감도`(기본 0.06) 아래로 새 깊이 2번 연속이면 닿음, 1.8배 넘게 2번이면 뗌. 바닥에 가장 가까운 손끝을 쓰고, 그 손끝의 칸이 입력. 깊이 모델이 없으면 손끝이 구역 안에서 0.15초 멈추는 것으로 대신(`method: dwell`). 바닥을 못 찾으면 `mode: none`(입력 없음, 영상에 "바닥면을 찾는 중…").
- 깊이는 그리드가 켜져 있는 동안 파이프라인이 직접 요청한다(약 10Hz, `DepthService.latest`).
- 상태 `state.grid`: `mode`(surface/floor/none), `method`, `quad`, `point`, `hover`, `pressed`, `height`, `touch_on`, `sensitivity`, `history`. 영상 오버레이는 `quad` 로 바닥면 위에 그리드를 그린다. 게임 피드백 그림에 '손끝 높이 막대'(초록 선 아래 = 닿음).
- 실영상(test.mov) 확인: 책상 면에 사다리꼴 그리드, mode floor·method depth, 지갑을 쥔 손끝 높이 0.16~0.27(문턱 0.06 → 닿음 아님).
- **한계**: 깊이 모델의 상대 깊이라 손끝이 바닥에서 1~2cm 떠 있는 것과 닿은 것은 구분이 어려울 수 있다(민감도로 조절). 실카메라로 문턱 확인 필요.

### 18.2 물체 터치 = 손끝 + 분할 마스크 가림 (§16.2 대체)
- `ObjectTouch`: 손끝이 물체 박스(8% 여유) 안에 있고, **손끝 둘레 원(손 크기의 35% 반지름) 안의 '쉬는 마스크' 중 지금 마스크에서 빠진 비율**이 문턱 이상일 때만 닿음. 쉬는 마스크 = 손이 물체 근처(박스 25% 여유)에 없을 때마다 새로 담은 마스크, 물체가 움직이면 박스 중심 이동만큼 옮겨 비교. 손이 물체 **뒤**에 있으면 마스크가 그대로라 닿지 않는다. 문턱 = 0.6 − 0.5·민감도(기본 0.35). 2번 연속 켬/3번 연속 끔. 상태 `state.touch[id].occluded`.
- **민감도 API** `GET/PUT /api/touch/settings {object_sensitivity, grid_sensitivity}`(0..1). UI `TouchSensitivity`: 매핑 패널(터치·바닥 입력을 쓰는 매핑이 있을 때), 두더지·틱택토 게임 아래.

### 18.3 매핑 출력 '데모 조작'(`target: "control"`)
- 스키마 `ControlOutput {target:"control", name, kind: bipolar|unipolar|digital}`. OS·게임패드로 나가지 않고 `computed.controls`/`controller.controls` 로 화면 데모가 읽는다. 게임패드 출력 개수 제한 없이 데모 요소마다 잭을 둘 수 있다. 매핑 줄에는 "데모 조작 이름"으로 보인다.

### 18.4 DJ 셋 단순화 + 모든 요소 매핑
- 남긴 것: 덱 A/B(조그 휠·재생 버튼 하나), 채널 볼륨 페이더+VU 2개, FILTER·TEMPO 노브, 패드 3개(SCRATCH·ECHO·AIR HORN), 크로스페이더, LCD·파형. 뺀 것: CUE, HI/LOW EQ 노브, 마스터 VU, FX RESET.
- **잭 10개**(전부 `dj.*` 데모 조작 출력): 덱 A·B 재생(손가락 터치), 볼륨 A·B(위아래, 들면 크게), 크로스페이더(좌우), 필터(기울기), 템포(가까이·멀리 → 90~150 BPM), 스크래치·에코·에어혼(손가락 터치). 한 물체에 케이블을 여러 개 이어 축마다 다른 요소를 움직일 수 있다(케이블을 눌러 축 변경). 연결된 요소는 ⚡.

### 18.5 첫 화면·튜토리얼
- **시작 3단계 줄**(`QuickStart.tsx`, 헤더 아래): ① 물체 등록 ② 쓰는 법 고르기(마우스 켜기 또는 매핑 연결) ③ 데모에서 놀기. 끝낸 단계는 초록 ✓, 누르면 해당 패널로 스크롤, × 로 숨김(localStorage).
- **튜토리얼 다시 씀**(`Tutorial.tsx`, 10단계, 한/영): 소개(3단계 흐름) · 주의(macOS·연속성 카메라·권한·앱 안·ESC) · 카메라 · ① 물체 등록 · ② 마우스 · ② 매핑(잭 끌기·케이블 조정·잭 반응·내 잭·손가락 닿음은 물체 앞에서) · ③ 데모(Space, 2인은 물체 2개, 바닥 게임은 손가락을 책상에, DJ) · 펜 Beta · 다른 앱 조작 · 끝내는 법(창 닫기, 고급 모드). 뺀 것: 한 손 하이브리드, 종이 원근 보정, 손 그림(handguide), 세부 손가락 설명. 저장 키 `anycontrol.tour.v2` 로 올려 기존 사용자에게도 한 번 다시 보인다. anycontrol-chat 은 손대지 않음.
- 두더지·틱택토 안내 문구를 "손가락으로 책상을 누르기"로.

### 18.6 검증
- 백엔드 485 passed(`test_touch_input.py` 4건: 마스크 가림 터치·민감도, 바닥면 찾기·손끝 높이, 손끝 닿음/뗌, 데모 조작 출력), 프런트 154 passed, 빌드 OK.
- 실측 필요: 실카메라에서 손가락으로 책상 누르기 문턱, 물체 앞 손가락 터치(마스크가 손가락을 빼는지 — 손 가림 처리를 켜면 더 확실), DJ 잭을 물체로 조작.

## 19. 물체 터치 재설계: 물체 모습 변화 감지 (2026-10-19, §18.2 대체)
- 문제: 손끝 위치 + 추적 마스크 가림만으로는 인식률이 너무 낮았다(손 인식이 손끝을 자주 놓치고, 추적 마스크가 손가락을 빼지 않을 때가 많음).
- 새 방식(`object_touch.py`): **물체를 계속 지켜보다가 물체 앞에 손이 나타나 모습이 바뀌면 닿음.**
  1. 기준 모습: 물체가 가만히 있고 손이 근처에 없을 때 물체 박스(6% 여유)를 긴 변 96px 로 잘라 Lab 색으로 저장. 조용할 때는 3%씩 섞어 조명 변화를 따라가고, 잡음 수준도 함께 추정.
  2. 변화: 매 프레임 같은 자리를 잘라 색 차이(밝기는 절반 반영 → 그림자 완화) > max(12, 3×잡음) 인 픽셀을 물체 마스크(조금 넓힘) 안에서 센다.
  3. 바뀐 면적이 문턱(민감도 0 → 12%, 1 → 1%, 기본 6.5%) 이상이고 **손 확인**이 되면 닿음: (a) 손 인식 손끝(엄지~새끼 끝 5개)이 영역 안, (b) 손 영역이 겹침, (c) 손 인식이 없어도 바뀐 픽셀의 30% 이상이 살색. 손이 아닌 변화(다른 물건·그림자)는 무시.
  4. 손 없이 거의 전부(85%↑) 바뀌면 조명 급변·카메라 이동으로 보고 기준을 다시 찍는다. 손 없이 물체가 다른 자리로 옮겨져 0.4초 머물면 다시 찍는다.
  5. **터치한 채 물체를 옮기면** 기준 모습은 유지하고 비교 영역만 물체를 따라 옮긴다(크기 15% 넘는 이동만, 손가락 가림으로 인한 작은 박스 흔들림은 무시) → 누른 채 이동해도 계속 닿음. (사용자 요청으로 '이동 중 제외' 규칙은 넣지 않음)
  6. 2번 연속 켬 / 3번 연속 끔.
- 손이 물체 **뒤**에 있으면 모습이 그대로라 닿지 않는다. 손이 물체 위 공중에서 가리는 것과 실제로 누른 것은 카메라 한 대로는 구분되지 않는다.
- 상태 `state.touch[id]`: `on`, `occluded`(바뀐 비율), `skin`, `reason`(fingertip/hand/skin/not-hand), `box`(지켜보는 영역), `min_change`.
- **영상 피드백**(`overlay.drawTouch`): 지켜보는 영역 점선, 아래에 바뀐 비율 막대(노란 선 = 문턱), 닿으면 초록 굵은 테두리 + "터치".
- 테스트 `test_touch_input.py`(합성 영상 8건: 손끝+가림, 손 인식 없이 살색, 손이 뒤·회색 물건·조명 급변 무시, 민감도, 누른 채 이동). 실영상(test.mov, 손이 지갑을 쥐고 있음)에서 손가락이 덮을 때 바뀐 비율 0.1~0.7 로 닿음, 손을 떼면 0 → 꺼짐 확인.
- 실카메라에서 가만히 놓인 버튼 물체로 민감도 확인 필요.

## 20. 종이 보정·바닥 3×3 그리드·틱택토·두더지 삭제, 남은 게임 대폭 개선 (2026-10-19)

### 20.1 삭제
- **바닥 3×3 그리드 전체**: 백엔드 `touch_input.py`(GridTouch), `floor_surface.py`, `PUT /api/touch/grid`, 매핑 입력 `grid`, 파이프라인의 바닥면 깊이 요청·그리드 상태, 영상의 그리드 그리기(`drawFloorGrid`·`homography`), 카메라 도구의 그리드 표시 체크, 터치 민감도의 '바닥' 항목. 물체 터치는 `object_touch.py` 그대로(테스트 파일 이름 `test_object_touch.py`).
- **틱택토·두더지 잡기** 게임과 `grid.ts`, `gridInput.ts`.
- **종이 보정(종이 선택)·수평 보정(기준선 2점)** UI: 카메라 미리보기의 두 버튼, 클릭 처리·안내 문구·점선, '책상 구역 표시' 체크, 마우스 패널의 종이 보정 그림·[종이 선택]·'커서에 종이 보정 쓰기'. 선택 모드는 `object | pen` 만. 마우스 패널의 '크기 기반 사선 보정'은 남김. '책상 터치패드' 손 이동 방식은 Desk View 일 때만 보인다(보정 면이 필요해서).
  - 백엔드의 책상 보정 코드(`/api/calibration`, `DeskCalibration`, `TouchSurface`)는 Desk View·자동 보정 내부에서 쓰여 남겨 두었다. UI 로는 더 이상 만들 수 없다.

### 20.2 공통 효과 `fx.ts`
- 파티클(`burst`), 떠오르는 점수 글자(`popup`), 화면 흔들림(`shake`), 번쩍임(`flash`), 가운데 배너(`banner`), 둥근 사각형, 결정적 난수(`rng`), **벡터 아이콘 `drawIcon`**(사과·오렌지·포도·수박·별·폭탄·자석·시계·넓은 그물·하트·전지·방패·폭발). 이모지 글꼴이 흑백으로 나오는 환경이 있어 과일·아이템은 모두 직접 그린다.

### 20.3 과일 받기 (`fruit.ts`, `FruitDemo.tsx`)
- 75초. **12초마다 이벤트**(1.5초 전에 화면에 예고 화살표·이름): 과일 폭포(한쪽 1/4 구역에서 쏟아짐), 폭탄 비(💣·⭐ 섞임), 돌풍(과일이 옆으로 날림, 바람 줄무늬), 황금 시간(⭐), 번개 속도(낙하 ×1.8).
- **아이템**: 자석(6초, 과일이 그물 가운데로 끌림), 슬로모션(5초, 과일만 느려짐), 넓은 그물(7초, 판정 여유 6→26px, 초록 빛), 하트(생명 +1, 최대 5).
- 과일: 사과 10·오렌지 15·포도 20·수박 40(빨리 떨어짐)·별 100. 연속 받기 배수 최대 ×5, 10콤보마다 알림. **마지막 10초 피버(×2)**. 놓치면 콤보만 끊김, 폭탄은 생명 −1 + 폭발·흔들림·빨간 번쩍.
- 그래픽: 시간이 갈수록 낮→노을로 바뀌는 하늘·해, 흘러가는 구름, 언덕·풀밭, 과일 그림자·회전, 과즙 파티클, 밧줄 그물, 남은 시간 막대·활성 아이템 표시.

### 20.4 네온 퐁 (`pong.ts`, `PongDemo.tsx`)
- 컴퓨터 **난이도 쉬움·보통·어려움**(속도·조준 오차), 패들을 **움직이며 치면 회전**(공이 휘어 나감), 랠리마다 빨라지고 5랠리마다 알림, **8랠리부터 불꽃 공**.
- **아이템**(9초마다 가운데, 공이 지나가면 마지막에 친 쪽): 큰 패들(+60%), 빠른 공(×1.4), 공 두 개(최대 3개), 상대 패들 작게(−40%).
- 서브 카운트다운, 네온 격자 코트·빛나는 패들·공 꼬리, 타격 불꽃, 득점 시 폭발·흔들림·번쩍.

### 20.5 레이싱 (`racing.ts`, `RacingDemo.tsx`)
- **차선을 바꾸는 느린 차**(깜빡이 표시), **기름**(1.1초 빙글 돌며 조향 불가), **코인 5개 = 니트로**(게이지), 부스터 발판, **600m마다 스테이지**(낮→노을→밤→폭풍, 최고 속도 상승, 장애물 증가, 스테이지 보너스 500점).
- 그래픽: 차 그림(바퀴·앞유리·라이트), 가로수·가로등(밤에는 불빛), 색조·밤 전조등·폭풍 비, 충돌 불꽃·길가 먼지·화면 흔들림, 속도·스테이지·니트로 HUD, 스테이지 배너. 2인 분할 화면은 그대로 동작.

### 20.6 좀비 서바이벌 (`survival.ts`, `SurvivalDemo.tsx`)
- **웨이브 8개**(웨이브마다 8+5n 마리, 클리어 후 3초 휴식·보너스), 좀비 종류: 일반·달리기·탱크(체력 막대)·**자폭**(가까이 오면 터져 주변 피해)·**보스**(웨이브 4·8, 체력 60).
- **아이템**: 전지(모으면 무기 한 발 → 두 발 → 산탄 → 연사), 하트(+2), 보호막(6초, 닿는 좀비 처치), 폭발(화면의 좀비 정리). 이전의 신호기·전지 운반 방식은 없앴다.
- 그래픽: 타일 바닥·얼룩 자국, 좀비 음영·바라보는 눈·피격 흰 번쩍·넉백, 총구 화염·빛나는 총알, 웨이브가 갈수록 어두워지는 손전등 효과, 웨이브/보스 배너, 진행 막대.

### 20.7 검증
- 백엔드 487 passed, 프런트 154 passed(새 `gameLogic.test.ts`: 과일 이벤트·폭포 방향·피버·아이템, 퐁 아이템·반사, 레이싱 기름·스테이지 / `survival.test.ts` 다시 씀), 빌드 OK.
- 브라우저에서 네 게임을 실제로 돌려 확인(과일 폭포 배너·벡터 과일, 네온 퐁, 레이싱 차·기름·부스터·가로수·HUD, 좀비 웨이브·아이템·손전등).


## 21. 매핑 연결 안정화·전체 초기화·DJ 패치 위치·차임 (2026-10-19)

### 21.1 이름을 바꿔도 물체 연결 유지
- 원인: 기존 입력의 `object`와 물체 카드 잭 DOM 키가 표시 이름을 사용했다. 이름 변경 API는 물체 이름만 바꾸므로 기존 이름을 참조하는 매핑이 입력과 잭을 찾지 못했다.
- 실행 중 매핑·물체 잭은 기존 엔진이 지원하는 `#<object id>`를 사용한다. 프런트의 `objectRefs.ts`가 이름/ID 해석과 표시 이름을 분리한다. 케이블·잭 접근성 이름·고급 물체 선택·움직임 학습은 현재 표시 이름을 보여주면서 ID로 연결한다.
- 백엔드 `bind_mapping_objects()`가 프로필 적용·물체 등록·이름 변경 시 기존 이름 기반 입력을 현재 ID에 연결한다. 이름 변경은 매핑 엔진의 runtime을 초기화하거나 출력을 놓지 않는다. 프런트의 이름 변경 직전에도 남아 있는 이름 기반 편집 초안을 ID로 바꾸어 대기 중 저장이 예전 이름을 다시 적용하지 않게 했다.
- 저장된 프로필은 다음 실행에서도 템플릿으로 쓸 수 있도록 `portable_profile()`로 현재 ID를 이름으로 변환해 저장하고, 적용할 때 다시 해당 물체 ID에 연결한다. 기존 이름 기반 프로필도 계속 읽는다. 이미 저장된 다른 프로필 파일까지 이름 변경에 맞춰 일괄 수정하지는 않는다. 동명 물체가 있는 이름 템플릿은 기존처럼 첫 일치 물체를 쓰며, 현재 세션의 ID 연결은 서로 구분한다.

### 21.2 잭·케이블 소실 경로 수정
- `useMappingDraft()`를 쓰는 매핑 패널과 DJ 화면이 각각 GET을 실행하고, 늦은 응답이 편집 초안을 덮어쓸 수 있었다. 공유 연결 세대·편집 revision으로 한 연결에서 중복 로드를 막고, 편집 뒤 도착하거나 이전 연결에서 도착한 GET을 무시한다. 화면 재진입에도 초안을 유지한다.
- PUT을 직렬화하고 대기 중 편집은 최신 값으로 합쳐, 오래된 저장이 나중에 완료되어 최신 연결을 서버에서 지우는 일을 막는다. 300ms 디바운스는 유지한다. 저장 실패 시 최신 초안과 오류를 남기며, 다음 편집이나 재연결에서 재시도한다. DJ에서도 저장 오류를 표시한다.
- `patchConnections.ts`에서 패널별 등록 토큰을 관리한다. 이전 패널 cleanup이 새 패널의 연결 콜백을 지우지 못하고, 마지막 소유자가 닫힐 때만 잭·끌기 상태를 해제한다. 기존에는 이 콜백이 null이면 모든 PatchJack이 렌더링되지 않았다.
- 출력 비교를 JSON 속성 순서에 무관하게 바꿨다. 서버 왕복으로 속성 순서가 달라져도 동일 출력의 기능 잭과 케이블을 인식한다.

### 21.3 매핑 전체 초기화
- 일반 패치 베이와 DJ 패치 베이에 `매핑 전체 초기화` 버튼을 추가했다.
- 첫 클릭은 확인 상태만 만들고, 4초 안에 두 번째 클릭 시 현재 프로필의 모든 매핑을 비워 바로 저장한다. 포커스를 잃거나 다른 편집을 하면 확인을 취소한다. 매핑이 없으면 비활성화한다.
- 등록 물체·사용자 정의 잭 정의·저장된 프로필 파일은 보존한다. 현재 프로필의 손 입력 및 다른 데모 매핑도 함께 초기화한다.

### 21.4 DJ
- DJ 패치 베이를 컨트롤러 위로 옮기고 안내 문구의 위/아래 설명도 수정했다.
- AIR HORN을 CHIME(차임)으로 교체했다. 기존 3중 톱니파·0.75초·음별 peak 0.18 대신 2개 사인파·총 0.32초·음별 peak 0.05로 짧고 부드럽게 생성한다. 실제 스피커 청취 비교는 수행하지 않았다.
- 기존 연결 호환을 위해 내부 잭 ID `dj-horn`과 제어 이름 `dj.horn`은 유지한다. 해당 입력은 이제 차임을 재생하므로 기존 매핑을 다시 연결할 필요가 없다.

### 21.5 검증·배포
- 백엔드 전체 491개 통과. 매핑 API 23개 통과: 축·보임·터치·펜 각각의 이름 기반 이전 프로필을 ID로 이행, 이름 변경 후 연결 및 runtime 보존, 프로필 저장/재적용을 확인했다.
- 프런트 30개 파일 / 158개 테스트 통과. 추가 회귀 테스트: 늦은 GET 무시, 공유 GET, 저장 직렬화, 패널 재진입, 이전 패널 해제 후 잭 유지, 출력 키 순서, 이름 변경 후 ID/표시 유지, 전체 초기화 2회 클릭·4초 만료·blur 취소.
- TypeScript 검사 통과, 프런트 Vite 빌드 검사 통과(기존 500kB 청크 안내 있음), 패키징 계약 검사 4개 통과. 이번 작업은 DOM/API 자동 테스트 중심이며 실제 카메라·브라우저에서 장시간 동작을 재현하거나 차임을 청취하지 않았다.
- 사용자 요청에 따라 배포 `.command` 패키지는 새로 만들지 않았고 기존 releases 파일도 변경하지 않았다.
- 수정 전 소스 백업: `/var/folders/p9/5_440v615gv65ht3hx5v9jb80000gn/T/anycontrol-mapping-20261019-dpgk1eqq` (frontend/src, backend/src, backend/tests, HANDOFF.md; 모델·캐시 제외).

## 22. 손 기반 터치 검증·맨손 입력 복원·겹침 보호·부스 초기화 (2026-10-19)

### 22.1 물체 터치 오인식 억제
- 이전에는 손 랜드마크가 없어도 바뀐 부분의 살색 비율만으로 눌림을 허용했다. 이 fallback을 제거했다. 이제 파이프라인에서 **0~150ms 이내 손 관측**, 감지기에서 **신뢰도 0.5 이상·유효한 좌표**, **물체 근처 손끝**, **그 손끝 주변 물체 마스크의 국소 외형 변화**를 모두 요구한다.
- 손 전체 박스가 겹친다는 이유만으로 누르지 않는다. 배경/조명이 바뀌어도 손이 없거나 멀면 눌리지 않고 기준 모습을 갱신한다. 비교 전 전반적인 색/밝기 이동을 중앙값으로 제거하고, 영역 대부분이 한꺼번에 바뀐 경우도 거부한다.
- 2프레임 연속으로 조건을 만족해야 켜진다. 손을 못 찾거나 손끝이 멀어지면 즉시 해제한다. 기존 마스크·작은 crop과 비동기 손 인식 경로를 사용하며 새 대형 모델이나 동기 추론을 추가하지 않았다.
- 터치 민감도 API에 남아 있던 삭제된 `grid_sensitivity` 참조도 수정했다.
- **한계**: 단일 RGB 영상에서는 물체 바로 앞 공중에서 손가락으로 가리는 것과 실제 접촉을 완전히 구분할 수 없다. 이번 변경은 배경·살색 변화에 의한 오검출을 우선 줄이는 보수적 판정이다. 실제 카메라·조명에서 손 인식 누락/과도한 가림에 따른 미검출은 추가 실측이 필요하다.

### 22.2 터치 진단 표시·입력 반전·성능
- 카메라의 터치 영역·변화 막대·접촉점 표시는 **고급(개발자) 모드 + ‘터치 감지 표시’ 토글**일 때만 그린다. 기본값은 꺼짐이며, 표시를 꺼도 터치 계산은 계속된다.
- ‘전체 입력 좌우 반전’을 기본 모드에서도 제공한다. 영상 표시 반전과 입력 반전은 계속 독립이다.
- 기본 성능 패널에 처리 ms(p50/p95), 캡처→처리 완료, 미리보기 fps, 캡처→화면(p50/p95), WS 왕복, 등록 물체 수, 맨손 입력 활성 상태를 추가했다. 이 숫자는 실측 텔레메트리이며 이번 작업의 합성 장면 수치를 실제 카메라 성능으로 해석하면 안 된다.

### 22.3 맨손 마우스 기본 복원
- 맨손 기본값을 `hand_control=air`, `hand_click_style=pinch`로 복원했다. 마우스 패널에서 맨손 모드를 선택할 때도 이 조합으로 시작한다. 영상 XY에 대응하는 손바닥 위치로 커서를 이동한다.
- 엄지+검지 집게 = 왼쪽 누름(유지하며 이동하면 드래그), 엄지+중지 집게 = 오른쪽 누름. 검지·중지만 펴고 엄지·약지·새끼를 접은 자세에서 위아래 이동 = 스크롤이다. 엄지를 접는 조건도 실제 판정에 추가했다.
- 고급 모드의 기존 대체 이동/클릭 옵션은 남겼고, 물체 마우스의 깊이 이동 기본값은 바꾸지 않았다. 공중 맨손 자동 보정의 위아래 안내도 영상 XY에 맞췄다.

### 22.4 기본 맨손 카드와 매핑 잭
- 등록 물체가 없어도 물체 패널에 `HandInputCard`를 표시한다. SVG 손 그림, 활성/비활성 스위치, `@hand` 잭이 있다. 물체 모두 삭제 대상에 맨손 카드는 포함되지 않는다.
- `PUT /api/tracking`의 `hand_input_enabled`로 맨손 마우스·손 제스처 매핑·손 그리기·물체 터치의 손 입력을 끌 수 있다. 비활성화 시 누르던 입력과 제스처를 해제한다. 별도 손 가림 보호 기능에 손 관측이 필요한 경우에는 그 목적의 워커가 계속 돌 수 있다.
- 맨손 잭을 기능 잭에 연결하면 기본 엄지+검지 집게 입력을 만든다. 케이블 편집기의 ‘집게 동작’에서 엄지+검지/엄지+중지를 고른다. 고급 매핑 행에서도 같은 HandInput을 편집한다.
- 맨손도 케이블·연결 이름·색상·삭제를 지원한다. 축 잭에 연결할 때는 집지 않은 상태를 중립 0, 집으면 1로 쓴다. 손을 놓치면 즉시 출력 중립으로 돌아간다. 실제 출력 여부는 기존 observe/send 및 OS 출력 설정을 따른다.

### 22.5 물체끼리 겹칠 때 보수적인 보호
- 기존 점 추적·칼만·물체 간 마스크 배타 처리·재획득 구조를 유지했다. 다른 물체의 기억한 전체 모양(amodal)과 **18% 넘게 겹치면** 겹침 보호를 켜고, 분리 후 **250ms**까지 유지한다.
- 보호 중에는 재분할 후보 요청/반영, Tier 1 외형 보정, 색 모델 갱신, 새 외형 기억 저장을 보류한다. 겹친 순간 상대 물체를 자기 외형으로 배우는 것을 줄이는 목적이며, 기본 이동 추적은 계속한다. 오래된 비동기 결과가 겹침 중 장면이면 뒤늦게 도착해도 외형 보정에 쓰지 않는다.
- 물체 카드와 경고에 ‘겹침’을 표시한다. 기존 동일 외형 두 물체의 겹침→분리 테스트는 ID 및 보이는 마스크 배타 조건을 유지한다. 실제 심한/완전 가림을 보장하는 새 추적기로 교체한 것은 아니다.

### 22.6 전체 초기화와 시연 영상
- 상단 ‘화면 초기화’를 **‘배치 초기화’**로 바꿨다. 옆에는 어두운 빨간색 **‘모든 세팅 초기화’**를 추가했다. 첫 클릭은 확인만, 4초 내 두 번째 클릭에 실행하며 포커스를 잃으면 확인을 취소한다.
- 사용자 확인 범위: **등록 물체·펜·현재 매핑·입력/추적/보정/표시 설정은 초기화**, **저장 프로필과 사용자 정의 잭은 보존**. **현재 카메라 연결·해상도·FPS도 유지**한다.
- `POST /api/settings/reset`을 엔진 스레드에서 실행한다. 실제 출력 끄기·누른 입력 해제, 추적 물체/외형 기억/기준점/깊이 기준/펜/그리기/자동 보정 정리, 마우스 끄기, 기본 손 백엔드/터치 감도/EMA/입력 반전/재분할 설정 복원, 빈 매핑(observe)을 적용한다. 선택한 캡처 소스 자체를 다시 열지는 않는다.
- 브라우저는 사용자 정의 잭을 제외한 `anycontrol.*` 저장값을 지우고 화면 배치·글씨 14px·기본 모드·게임/데모 상태를 복원한다. 예전 매핑 PUT이 초기화 뒤 다시 연결을 살리지 않도록 이미 보낸 저장은 완료를 기다리고, 대기 편집은 취소한다. 마우스 설정 큐도 취소하고 초기화 중 편집을 막는다.
- 시연 영상 placeholder 진입 때도 같은 초기화를 **진입당 한 번** 실행한다. 무입력 기본 대기 시간은 **120초**다. 사람이 다가오거나 포인터/키보드 입력을 하면 기존처럼 복귀한다. 저장 실패/초기화 실패는 오류로 표시한다.

### 22.7 DJ 음악
- 외부 음원 파일 대신 기존 WebAudio 합성기를 유지하면서 오리지널 **124 BPM 멜로딕 하우스 루프**로 편곡했다. 덱 A는 4박 킥·백비트·오프비트 하이햇, 덱 B는 Am–F–C–G 기반 8마디 코드·오프비트 베이스·부드러운 사인파 아르페지오다.
- 덱 B가 기존에 덱 A 경로로 드럼을 중복 생성하던 부분을 없애 덱별 소리가 분리된다. 날카로운 사각파 리드와 베이스 레벨은 줄였다. 덱 표시도 HOUSE BEAT / MELODIC HOUSE로 바꿨다. 기존 잭·크로스페이더·필터·템포·에코·차임 연결은 유지한다.
- 브라우저 AudioContext 실행 오류는 없었지만 자동 검증 브라우저는 음소거 상태였으므로 실제 스피커에서의 선호도/음량 청취 검증을 했다고 간주하지 않는다.

### 22.8 검증·작업 환경
- 별도 포트 8879 합성 카메라 서버와 별도 headless Chrome 프로필로 검증했다. 사용자의 실행 중인 카메라 서버/브라우저 세션은 변경하지 않았다.
- 브라우저에서 기본 맨손 카드·손 SVG·기본 입력 반전, 기본 모드 진단 토글 숨김/고급 모드 표시, 맨손 잭 연결→엄지+중지로 변경→서버 저장, DJ 패치 위치/차임 실행, 첫 초기화 클릭 시 물체 보존→둘째 클릭 시 삭제, 저장 프로필/사용자 잭 보존, placeholder 진입 시 자동 물체 삭제를 확인했다. 런타임 예외 없음. placeholder 대기는 테스트 브라우저의 시각을 앞당겨 검사했으며 그때의 지연 수치는 성능 측정값이 아니다.
- 수정 전 소스 백업: `/var/folders/p9/5_440v615gv65ht3hx5v9jb80000gn/T/anycontrol-input-reset-20261019-_3fjylp2`.
- 앞서 요청받은 대로 배포 `.command` 파일은 재생성하지 않았다. 개발용 프런트 번들만 현재 소스로 빌드했다.
- 최종 자동 검증: **백엔드 497개 통과**, **프런트 31개 파일/162개 통과**, TypeScript/Vite 빌드 통과(기존 500kB 청크 크기 안내만 있음), 패키징 계약 검사 4개 통과. 손 없는 살색/배경 변화 거부, 손끝 근접·손 소실 해제, 엄지 접힘 스크롤, 맨손 기본값, 맨손 카드 스위치, 집게 케이블, 매핑 저장과 전체 초기화의 순서, 저장 프로필 보존, 동일 물체 겹침 분리 및 외형 학습 보호를 회귀 검사했다.
- 적용 시 실행 중인 백엔드는 재시작하고 브라우저를 새로고침해야 새 API와 입력 기본값을 함께 사용한다. 실제 카메라의 터치 오인식률·손 인식 누락률·물체 완전 가림·스피커 음악 청취는 현장 확인이 남아 있다.


## 23. v1.8.0 · 보정 간소화와 설명/챗봇 동기화 (2026-10-19)

### 23.1 원위치 없는 기본 3단계 보정
- 일반 물체·맨손의 기본 과정을 **잠깐 정지 → 좌우 왕복 → 앞뒤/영상 위아래 왕복**으로 줄였다. 정지는 1.5초, 각 왕복은 유효 관측 7초를 모은다. 중앙으로 물체를 되돌리거나 원래 시작점을 통과할 필요가 없다.
- 왕복 측정은 초기 구간 대비 첫 유의한 이동과 방향 전환점을 찾고, 전환 전후에 각각 독립적인 시작점을 사용한다. 짧은/일방향 동작은 거부하며, 실제 물리적 이동 방향을 안내대로 수행해야 좌우 반전 추정이 맞는다.
- `movement_only` API 옵션을 추가했고 서버·UI 기본값은 true다. 직접 `AutoCalibration` 클래스를 사용하는 기존 상세 측정 호출은 이전 기본값(false)을 유지한다. UI의 **클릭·스크롤도 맞추기 (선택)**를 선택하면 상세 검사를 추가한다. 측정하지 않은 클릭/스크롤 설정은 보존한다.
- 물체 이동만 보정할 때 손 인식을 요구하지 않는다. 맨손 보정은 간편 측정에서도 손 워커를 요청한다. 펜은 접촉/들기 측정이 필요하므로 상세 과정을 유지한다.
- 취소·다시 측정·단계 건너뛰기·결과 확인 후 적용·측정 중 출력 억제는 유지했다. 한국어/영어 새 안내를 함께 갱신했다.

### 23.2 버전과 문서
- npm 루트/프런트 manifest·lock 루트, Python 프로젝트·모듈·egg-info 메타데이터, HTML 제목, 패키징 검증의 앱 버전을 **1.8.0**으로 통일했다. 의존 라이브러리 버전·프로토콜 형식 번호·이전 배포 바이너리는 변경하지 않았다.
- README 한국어/영어의 현재 사용 설명, INSTALL·DEVELOPMENT의 현재 버전, 상위 디렉토리 `AnyControl 소개서.md`를 갱신했다. 설치 문서의 v1.8.0 실행파일 이름은 향후 배포 예시이며 이번에 공개했다는 뜻이 아님을 명시했다.
- 현재 맨손 XY/집게, 기본 맨손 잭, 손을 요구하는 물체 터치, 이름 변경/프로필 구분, 겹침 보호, 패널 배치, 초기화 범위, 시연 대기 120초와 새 데모를 설명했다. 예전 하이브리드·그리드/종이 UI를 현재 기능으로 안내하지 않는다.

### 23.3 anycontrol-chat 동기화
- 이력 전체와 현재 코드·문서를 대조해 기존 답변 37개를 갱신하고 자세한 사용법 카드 24개를 추가했다(364 → **388개**, 한국어/영어). 전체 카드의 처리 내역은 챗봇 `kb/REVIEW_v1.8.0.md`에 기록한다.
- 챗봇 sources·35개 사실 점검·주제 지도·스냅샷을 현재 코드에 맞춘다. 김삼 개인정보 제한/고정 문구를 담은 policy 파일은 원본 바이트 그대로 유지하며 `log/`는 수정하지 않는다.
- 외부 휴대기기 가격을 AnyControl 가격으로 답하던 로컬 모델 오답을 막는 좁은 범위 확인을 추가했다. 카메라 호환 질문이나 AnyControl 자체 가격은 정상 검색한다. 검색 임계값은 변경하지 않았다.
- 챗봇 회귀 수치와 남은 모호한 질문은 챗봇 HANDOFF §33 및 검토 보고서에 별도 기록한다. 모든 질문에 정답을 보장하거나 최신 실환경 정확도를 새로 측정했다는 뜻은 아니다.

### 23.4 검증과 적용
- **백엔드 500개**, **프런트 164개/31개 파일**, 패키징 계약 검사 **4개** 통과. TypeScript/Vite 개발 번들 빌드 통과(500kB 청크 안내만 있음).
- 새로운 회귀 검사는 중앙을 통과하지 않는 왕복, 물체 간편 보정의 손 의존성 제거/클릭 설정 보존, 맨손 간편 보정의 손 워커 유지, UI 기본 옵션과 영어 안내를 확인한다.
- 별도 합성 서버(8879)·임시 Chrome 프로필에서 backend v1.8.0, 선택 옵션 기본 해제, 3단계 API 상태·현재 위치 안내·보정 대화상자와 런타임 예외 없음을 확인했다. 합성 서버는 실제 추적기가 없는 UI 검증용이므로 관측 수집/실사용 보정 성공률은 이 브라우저 검사로 주장하지 않는다.
- 실제 카메라에서의 사용자별 시간·성공률은 미측정이다. 초기 위치가 가장자리면 반대쪽 여유를 확보해 움직여야 한다. 원위치 필요는 없지만 양방향 유효 이동은 필요하다.
- 사용자 요청에 따라 배포 `.command`/zip은 새로 만들지 않았다. 개발용 프런트 번들만 갱신했다. 적용하려면 실행 중인 백엔드와 챗봇을 재시작하고 브라우저를 새로고침한다.
- 수정 전 백업: `/var/folders/p9/5_440v615gv65ht3hx5v9jb80000gn/T/anycontrol-v180-95lccpe4`.
