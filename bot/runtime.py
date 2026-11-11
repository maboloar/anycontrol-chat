"""LLM 실행 환경: 내 컴퓨터 사양 확인, llama-server 찾기·실행, 속도 시험으로 켤지 말지 정하기.

폴더 구성 (휴대용):
  bin/<플랫폼>/llama-server(.exe)    플랫폼: macos-arm64, macos-x64, windows-x64, linux-x64
  models/*.gguf                       첫 번째 GGUF 파일을 쓴다 (또는 환경변수 ANYCONTROL_CHAT_MODEL)
llama-server 가 없거나 모델이 없거나 속도가 기준보다 느리면 LLM 없이(카드 답만) 동작한다 — 오류가 아니라 정상 모드다.
"""
from __future__ import annotations
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .llm import LLMClient

ROOT = Path(__file__).resolve().parents[1]


def platform_tag() -> str:
    s, m = platform.system().lower(), platform.machine().lower()
    arch = "arm64" if m in ("arm64", "aarch64") else "x64"
    return {"darwin": f"macos-{arch}", "windows": f"windows-{arch}", "linux": f"linux-{arch}"}.get(s, f"{s}-{arch}")


def total_ram_gb() -> float:
    try:
        if sys.platform == "darwin":
            return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()) / 2 ** 30
        if sys.platform.startswith("win"):
            import ctypes

            class MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEM()
            m.dwLength = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))  # type: ignore[attr-defined]
            return m.ullTotalPhys / 2 ** 30
        with open("/proc/meminfo") as f:
            return int(f.readline().split()[1]) / 2 ** 20
    except Exception:
        return 0.0


def find_server(root: Path = ROOT) -> Path | None:
    exe = "llama-server.exe" if sys.platform.startswith("win") else "llama-server"
    p = root / "bin" / platform_tag() / exe
    if p.exists():
        return p
    w = shutil.which("llama-server")
    return Path(w) if w else None


def find_model(root: Path = ROOT) -> Path | None:
    env = os.environ.get("ANYCONTROL_CHAT_MODEL")
    if env and Path(env).exists():
        return Path(env)
    pin = root / "models" / "MODEL.txt"                  # 한 줄에 쓴 파일명 (여러 모델이 있어도 이 모델을 쓴다)
    if pin.exists():
        name = pin.read_text(encoding="utf8").strip()
        if name and (root / "models" / name).exists():
            return root / "models" / name
    ggufs = sorted((root / "models").glob("*.gguf"), key=lambda p: p.name.lower())
    return ggufs[0] if ggufs else None


VC_DLLS = ("vcruntime140.dll", "msvcp140.dll")      # llama-server.exe(MSVC 로 빌드)가 필요로 하는 Visual C++ 런타임 (bin/windows-x64/ 에 같이 들어 있다)
VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"


def missing_windows_runtime(server: Path | None = None) -> list[str]:
    """Windows 에서 llama-server.exe 를 돌리는 데 필요한 Visual C++ 런타임 DLL 중 없는 것. (다른 OS 는 빈 목록)
    시스템 폴더나 llama-server.exe 옆에 있으면 된다. 없는 채로 실행하면 'VCRUNTIME140.dll 을 찾을 수 없습니다' 창이 DLL 마다 뜬다."""
    if not sys.platform.startswith("win"):
        return []
    sysdir = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    return [n for n in VC_DLLS if not (sysdir / n).exists() and not (server is not None and (server.parent / n).exists())]


def suppress_error_dialogs() -> None:
    """Windows: 자식 프로세스(llama-server)가 DLL 을 못 찾아도 '시스템 오류' 창을 띄우지 않고 조용히 실패하게 한다."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x8000)        # SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX (자식에게 상속됨)
        except Exception:
            pass


class LLMRuntime:
    """llama-server 를 자식 프로세스로 띄우고 속도 시험을 통과하면 LLM 을 켠다."""

    def __init__(self, root: Path = ROOT, port: int = 8081, min_tok_s: float = 3.0, min_ram_gb: float = 5.5, ctx: int = 8192, max_pair_s: float = 2.5, max_rag_s: float = 7.0, max_chat_s: float = 7.0) -> None:
        self.max_chat_s = max_chat_s
        self.persona: "str | dict" = ""            # 잡담 안내문(정체성). 속도를 잴 때 실제 대화와 같은 앞부분을 써야 캐시가 맞는다 (bot serve 가 채운다)
        self.root, self.port, self.min_tok_s, self.min_ram_gb, self.ctx = root, port, min_tok_s, min_ram_gb, ctx
        self.max_pair_s = max_pair_s
        self.max_rag_s = max_rag_s
        self.proc: subprocess.Popen | None = None
        self.client: LLMClient | None = None
        self.status = "off"          # off | no-binary | no-model | low-ram | failed | slow | on
        self.detail = ""

    def start(self, wait_s: float = 120.0) -> LLMClient | None:
        server, model = find_server(self.root), find_model(self.root)
        if not server:
            self.status, self.detail = "no-binary", f"bin/{platform_tag()}/llama-server 없음"
            return None
        if not model:
            self.status, self.detail = "no-model", "models/*.gguf 없음"
            return None
        suppress_error_dialogs()
        miss = missing_windows_runtime(server)
        if miss:                                          # 오류 창을 3개씩 띄우지 말고, 이유를 알려 주고 카드 검색만으로 계속한다
            self.status, self.detail = "no-runtime", f"Windows 에 Visual C++ 런타임({', '.join(miss)})이 없음 — {VC_REDIST_URL} 설치"
            return None
        ram = total_ram_gb()
        if ram and ram < self.min_ram_gb:
            self.status, self.detail = "low-ram", f"RAM {ram:.1f}GB < {self.min_ram_gb}GB"
            return None
        existing = LLMClient(f"http://127.0.0.1:{self.port}")
        if existing.ping():                              # 이전 실행에서 남은 llama-server 가 살아 있으면 새로 띄우지 않고 쓴다
            self.proc = None
            return self._finish(existing, model, adopted=True)
        threads = max(1, (os.cpu_count() or 2) - (0 if (os.cpu_count() or 2) <= 2 else 1))
        gpu = "99" if sys.platform == "darwin" else "0"
        cmd = [str(server), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port), "-c", str(self.ctx),
               "-np", "6",                       # 작업 칸을 넉넉히: 잡담·질문 이해·오타 교정이 각자 앞부분(캐시)을 오래 유지해야 느린 컴퓨터에서 안내문을 다시 읽지 않는다
               "-t", str(threads), "-ngl", gpu]
        try:
            flags = 0x08000000 if sys.platform.startswith("win") else 0     # Windows: llama-server 가 검은 창을 따로 띄우지 않게 (CREATE_NO_WINDOW)
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        except OSError as exc:
            self.status, self.detail = "failed", str(exc)
            return None
        client = LLMClient(f"http://127.0.0.1:{self.port}")
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if self.proc.poll() is not None:
                self.status, self.detail = "failed", f"llama-server 가 종료됨 (코드 {self.proc.returncode})"
                return None
            if client.ping():
                break
            time.sleep(0.5)
        else:
            self.stop()
            self.status, self.detail = "failed", "llama-server 시작 시간 초과"
            return None
        return self._finish(client, model)

    def _finish(self, client: LLMClient, model: Path, adopted: bool = False) -> LLMClient | None:
        try:
            speed = client.speed_test()
        except Exception as exc:
            self.stop()
            self.status, self.detail = "failed", f"속도 시험 실패: {exc}"
            return None
        client.info = {"model": model.name, **speed}
        if speed["tok_per_s"] < self.min_tok_s:
            self.stop()
            self.status, self.detail = "slow", f"{speed['tok_per_s']} tok/s < {self.min_tok_s}"
            return None
        try:
            pair_s = client.calibrate()
        except Exception as exc:
            self.stop()
            self.status, self.detail = "failed", f"질문 이해 시험 실패: {exc}"
            return None
        client.info["pair_s"] = round(pair_s, 3)
        if pair_s > self.max_pair_s:
            self.stop()
            self.status, self.detail = "slow", f"질문 이해 1회 {pair_s:.1f}초 > {self.max_pair_s}초"
            return None
        try:                                            # RAG(답 정리) 속도: 너무 느리면 그 기능만 끄고 질문 이해(순위)는 그대로 쓴다
            rag_s = client.calibrate_rag()
            client.rag_ok = rag_s <= self.max_rag_s
            client.info["rag_s"] = round(rag_s, 2)
        except Exception:
            client.rag_ok = False
        try:                                            # 잡담 속도: 답 정리와 따로 잰다 (답 정리가 느려도 짧은 잡담은 될 수 있다)
            chat_s = client.calibrate_chat(self.persona)
            client.chat_ok = chat_s <= self.max_chat_s
            client.info["chat_s"] = round(chat_s, 2)
        except Exception:
            client.chat_ok = False
        client.enabled = True
        self.client = client
        self.status, self.detail = "on", f"{model.name} · {speed['tok_per_s']} tok/s · 질문 이해 1회 {pair_s * 1000:.0f}ms · 답 정리 {'켜짐' if client.rag_ok else '꺼짐(느림)'} {client.info.get('rag_s', 0)}초 · 잡담 {'켜짐' if client.chat_ok else '꺼짐(느림)'} {client.info.get('chat_s', 0)}초"
        return client

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
