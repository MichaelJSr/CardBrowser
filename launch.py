"""Linux entry (run.sh): the app folder and its vendor/ packages first on sys.path, then CardBrowser."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "vendor")]

import cardbrowser  # noqa: E402

sys.exit(cardbrowser.main())
