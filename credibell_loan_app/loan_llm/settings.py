from dataclasses import dataclass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_env_file(path):
    """Read a deliberately small literal .env format; never execute/interpolate it."""
    permitted = {"GRAFILAB_API_KEY", "GRAFILAB_MODEL", "GRAFILAB_BASE_URL", "LOAN_DASHBOARD_TOKEN", "LOAN_CORS_ORIGINS"}
    values = {}
    if Path(path).is_file():
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if separator and key in permitted:
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                values[key] = value
    return values


@dataclass(repr=False, frozen=True)
class Settings:
    api_key: str = ""
    model: str = ""  # Set a model from your account's /models catalogue; no guessed default.
    base_url: str = "https://llm.grafilab.ai/v1"
    dashboard_token: str = ""
    cors_origins: tuple = ("http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000")
    knowledge_path: Path = ROOT / "loan_llm/bank_knowledge.json"
    cache_dir: Path = ROOT / "cache/public_sources"

    @classmethod
    def load(cls, env_path=None):
        local = read_env_file(env_path or ROOT / ".env")
        def get(key, default=""):
            return os.environ.get(key, local.get(key, default)).strip()
        return cls(api_key=get("GRAFILAB_API_KEY"), model=get("GRAFILAB_MODEL"),
            base_url=get("GRAFILAB_BASE_URL", "https://llm.grafilab.ai/v1").rstrip("/"),
            dashboard_token=get("LOAN_DASHBOARD_TOKEN"),
            cors_origins=tuple(x.strip() for x in get("LOAN_CORS_ORIGINS", ",".join(cls.cors_origins)).split(",") if x.strip()))

    def public_status(self):
        return {"provider": "Grafilab", "base_url": self.base_url,
            "api_key_configured": bool(self.api_key), "model_configured": bool(self.model),
            "model": self.model or None, "dashboard_auth_enabled": bool(self.dashboard_token)}
