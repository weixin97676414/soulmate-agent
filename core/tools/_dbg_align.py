
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from my_agent.assistants import persona
from my_agent.assistants.persona import SOUL_FILE
from my_agent.config.loader import ConfigStore
from my_agent.config.paths import AppPaths

tmp = Path(tempfile.mkdtemp())
paths = AppPaths(tmp / "data").ensure()
ConfigStore(paths).load()

directory = persona.assistant_dir(paths, "soulmate")
marker = paths.data_dir / ".persona-pack-aligned"
print("marker exists after load1:", marker.exists())

(directory / SOUL_FILE).write_text("# 用户自己改的人设\n", encoding="utf-8")
print("before load2 SOUL:", (directory / SOUL_FILE).read_text(encoding="utf-8")[:20])

store = ConfigStore(paths)
cfg = store.load()
print("after load2 SOUL:", (directory / SOUL_FILE).read_text(encoding="utf-8")[:20])
print("marker exists after load2:", marker.exists())
