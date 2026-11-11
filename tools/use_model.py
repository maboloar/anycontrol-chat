"""챗봇이 쓸 Qwen 모델을 두 가지 중에서 고른다 (models/MODEL.txt 를 바꾼다).

  python3 tools/use_model.py 4b      # Qwen3-4B  (더 크다·약 2.5GB, 느린 컴퓨터에서는 느릴 수 있음)
  python3 tools/use_model.py 1.5b    # Qwen2.5-1.5B-Instruct (작고 빠르다·약 1.1GB, GPU 없는 노트북에 권장)
  python3 tools/use_model.py         # 지금 고른 모델과 설치된 파일을 보여 준다
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
OPTIONS = {"4b": "Qwen3-4B-Q4_K_M.gguf", "1.5b": "qwen2.5-1.5b-instruct-q4_k_m.gguf"}


def main() -> int:
    pin = MODELS / "MODEL.txt"
    now = pin.read_text(encoding="utf8").strip() if pin.exists() else "(고정 안 함 → 이름순 첫 번째)"
    if len(sys.argv) < 2:
        print("지금 고른 모델:", now)
        for key, name in OPTIONS.items():
            p = MODELS / name
            print(f"  {key:5s} {name:38s} {'있음 %.1fGB' % (p.stat().st_size / 2**30) if p.exists() else '없음'}")
        return 0
    key = sys.argv[1].lower().replace("qwen", "").replace("3-", "").strip()
    key = {"1.5": "1.5b", "15b": "1.5b", "4": "4b"}.get(key, key)
    if key not in OPTIONS:
        print("고를 수 있는 것:", ", ".join(OPTIONS), "  (예: python3 tools/use_model.py 1.5b)")
        return 2
    if not (MODELS / OPTIONS[key]).exists():
        print(f"models/{OPTIONS[key]} 파일이 없습니다.")
        return 1
    pin.write_text(OPTIONS[key] + "\n", encoding="utf8")
    print("이제 이 모델을 씁니다:", OPTIONS[key], "(챗봇을 다시 시작하면 적용됩니다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
