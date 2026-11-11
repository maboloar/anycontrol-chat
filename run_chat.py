#!/usr/bin/env python3
"""더블클릭 실행기(run.command / run.bat)가 부르는 공통 진입점.

- Python 3.9 이상이면 어떤 Python 이든(설치판, Windows embeddable 포함) 이 폴더의 bot 패키지를 찾게 한다.
- 카드 검증 -> 서버 시작 -> 브라우저 열기. 인자는 `python -m bot serve` 에 그대로 넘어간다 (예: --port 9000).
- 문제가 생기면 이유를 한국어로 알려 주고 창이 바로 닫히지 않게 한다.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

if sys.version_info < (3, 9):
    print("Python 3.9 이상이 필요합니다. (지금: %s)  https://www.python.org/downloads/" % sys.version.split()[0])
    sys.exit(2)

from bot.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main(["serve", "--open"] + sys.argv[1:])
