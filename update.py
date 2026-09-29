"""起動時に GitHub から最新版を取り込む (手動でダウンロードして上書きする手間をなくす)。

API キーや覚えた単語など、自分で作ったファイルは上書きしない。
ネットにつながらないときなどは何もせずに終わる。
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
REPO = "ivar0521/esolve-auto-subtitle"
URL = f"https://codeload.github.com/{REPO}/zip/refs/heads/main"
KEEP = {"APIキー.txt", "覚えた単語.txt"}
REQUIRED_MODULES = ("faster_whisper", "anthropic")


def update_files() -> list[str]:
    try:
        data = urlopen(URL, timeout=20).read()
    except Exception as e:  # ネット不通・非公開リポジトリなど
        print(f"(最新版の確認をスキップしました: {e})")
        return []
    changed = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            rel = info.filename.split("/", 1)[-1]
            if info.is_dir() or not rel or rel in KEEP or rel.startswith(".venv"):
                continue
            dest = HERE / rel
            new = zf.read(info)
            if dest.is_file() and dest.read_bytes() == new:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(new)
            if rel.endswith(".command"):
                dest.chmod(0o755)
            changed.append(rel)
    return changed


def main() -> int:
    changed = update_files()
    if changed:
        print("🔄 最新版に更新しました: " + "、".join(changed))
    missing = [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]
    if "requirements.txt" in changed or missing:
        print("必要な部品をインストール中… (数分かかることがあります)")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(HERE / "requirements.txt")],
            check=False,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
