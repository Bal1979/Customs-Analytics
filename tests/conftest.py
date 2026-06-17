import sys
from pathlib import Path

# Gør projektroden importbar, så `import customs` virker uden installation.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
