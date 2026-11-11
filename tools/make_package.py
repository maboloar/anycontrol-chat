"""부스 노트북에 옮길 휴대용 폴더(zip)를 만든다. 실행: python3 tools/make_package.py [--with-llm] [--out dist/anycontrol-chat.zip]

기본(카드 답변만)은 몇 MB. --with-llm 이면 bin/ 과 models/ 도 넣는다 (GGUF 때문에 1GB 이상).
포함하지 않는 것: log/(방문객 질문 기록), sources/(원문 — 챗봇 실행에 필요 없음, --with-sources 로 포함 가능), kb/cards_archive 는 포함(작아서), __pycache__, .DS_Store.
Windows 용 embeddable Python 은 라이선스·크기 때문에 자동으로 넣지 않는다 → README.md 의 Windows 준비 참고.
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ALWAYS = ["bot", "kb", "kb_src", "web", "tools", "eval", "tests", "run.bat", "run.command", "run_chat.py", "README.md", "START_HERE.txt",
          "UPDATE_GUIDE.md", "HANDOFF.md", "CLAUDE.md"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist" / "anycontrol-chat.zip"))
    ap.add_argument("--with-llm", action="store_true", help="Qwen 모델과 llama.cpp 를 포함 (질문 이해 보조, 약 1.2GB)")
    ap.add_argument("--platform", default="all", help="--with-llm 일 때 넣을 실행 파일: all | windows-x64 | macos-arm64 | macos-x64")
    ap.add_argument("--with-sources", action="store_true")
    a = ap.parse_args()
    if subprocess.call([sys.executable, "-m", "bot", "validate"], cwd=ROOT) != 0:
        print("카드 검증 실패 — 패키지를 만들지 않습니다.")
        return 1
    bins = []
    if a.with_llm:
        d = ROOT / "bin"
        bins = ["bin/" + x.name for x in sorted(d.iterdir()) if x.is_dir() and a.platform in ("all", x.name)] if d.exists() else []
    models = []
    if a.with_llm:
        from bot.runtime import find_model
        m = find_model(ROOT)                              # models/MODEL.txt 로 고정한 모델(없으면 첫 gguf) 하나만 넣는다
        models = ["models/" + m.name] + (["models/MODEL.txt"] if (ROOT / "models" / "MODEL.txt").exists() else []) if m else []
    items = ALWAYS + bins + models + (["sources"] if a.with_sources else [])
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for item in items:
            p = ROOT / item
            if not p.exists():
                continue
            for f in ([p] if p.is_file() else sorted(p.rglob("*"))):
                if not f.is_file() or "__pycache__" in f.parts or "__MACOSX" in f.parts or f.name == ".DS_Store" or f.name.startswith("._") or f.suffix == ".pyc":
                    continue
                if "snapshot" in f.relative_to(ROOT).parts[:2]:      # kb/snapshot 은 업데이트 점검용(개발 컴퓨터에서만 필요)
                    continue
                info = zipfile.ZipInfo.from_file(f, "anycontrol-chat/" + str(f.relative_to(ROOT)))
                if f.suffix in (".command", "") and f.parent.name in ("macos-arm64", "macos-x64") or f.name in ("run.command", "run_chat.py"):
                    info.external_attr = 0o755 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, f.read_bytes())
                n += 1
        (ROOT / "log").mkdir(exist_ok=True)
    print(f"{out}  파일 {n}개  {out.stat().st_size / 2**20:.1f}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
