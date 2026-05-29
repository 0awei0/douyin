import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv

# 加载 .env 文件
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)


class Settings:
    def __init__(self):
        self.ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
        self.ARK_ENDPOINT = os.environ.get("ARK_ENDPOINT", "ep-20260508213828-7ntjl")
        self.ARK_MODEL = os.environ.get("ARK_MODEL", "doubao-seed-2.0-lite")
        self.UPLOAD_DIR = "uploads"
        self.OUTPUT_DIR = "outputs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
