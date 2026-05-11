from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings
from scripts.google_auth import load_google_credentials


SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.send",
]


def main() -> int:
    settings = Settings()
    credentials, mode = load_google_credentials(
        credentials_path=settings.GOOGLE_DRIVE_CREDENTIALS_PATH,
        scopes=SCOPES,
        token_path=settings.GOOGLE_DRIVE_TOKEN_PATH,
        allow_interactive=True,
    )
    payload = {
        "success": True,
        "mode": mode,
        "credentials_path": str(settings.GOOGLE_DRIVE_CREDENTIALS_PATH),
        "token_path": str(settings.GOOGLE_DRIVE_TOKEN_PATH),
        "scopes": list(getattr(credentials, "scopes", []) or []),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())