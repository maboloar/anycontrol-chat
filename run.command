#!/bin/bash
# macOS: 더블클릭하면 챗봇이 켜지고 브라우저가 열립니다. 끝내려면 이 창을 닫거나 Ctrl+C.
# 열리지 않으면: 터미널에서  bash run.command   (또는  python3 run_chat.py)
cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.9 이상이 필요합니다."
  echo "https://www.python.org/downloads/ 에서 macOS 설치 파일을 받아 설치한 뒤 이 파일을 다시 열어 주세요."
  echo "(Mac 이 '개발자 도구 설치'를 물어보면 취소하고 위 방법으로 설치해도 됩니다)"
  read -r -p "Enter 를 누르면 닫힙니다" _
  exit 1
fi
"$PY" run_chat.py "$@"
rc=$?
if [ $rc -ne 0 ]; then echo; echo "챗봇이 오류로 멈췄습니다 (코드 $rc). 위 메시지를 확인하세요."; read -r -p "Enter 를 누르면 닫힙니다" _; fi
exit $rc
