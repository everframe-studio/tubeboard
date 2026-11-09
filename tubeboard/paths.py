"""설정(.env)과 캐시를 두는 폴더. 소스로 실행하면 저장소 폴더, 설치형 실행 파일이면 사용자 폴더."""
import os
import sys
from pathlib import Path


def data_dir():
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    d = base / "TubeBoard"
    d.mkdir(parents=True, exist_ok=True)
    return d
