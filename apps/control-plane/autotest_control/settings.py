from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

_OPENAI_COMPLETIONS_PREFIXES = (
    "glm-",
    "deepseek-",
    "kimi-",
    "qwen-",
    "qwq-",
    "grok-",
    "minimax-",
    "mimo-",
    "longcat-",
    "seed-",
)


def infer_api_format(model: str, explicit: str = "") -> str:
    """Claude Code 的 ANTHROPIC_* 可以指向任意模型，但网关协议并不都是 Anthropic。"""
    lower = (model or "").strip().lower()
    if lower.startswith("gpt-"):
        return "openai-responses"
    if lower.startswith("gemini-"):
        return "gemini"
    if any(lower.startswith(prefix) for prefix in _OPENAI_COMPLETIONS_PREFIXES):
        return "openai-completions"
    if explicit:
        return explicit
    return "anthropic"


def _repo_root() -> Path:
    # apps/control-plane/autotest_control/settings.py -> 仓库根
    return Path(__file__).resolve().parents[3]


class Settings:
    """P0 切片配置。

    数据库默认 SQLite、产物默认落本地磁盘，为的是零基础设施就能跑起来。
    正式部署换成 Postgres + MinIO 时只需改这两个 URL/路径。
    """

    def __init__(self) -> None:
        root = _repo_root()
        self.var_dir = Path(os.getenv("ATP_VAR_DIR", root / "var"))
        self.artifacts_dir = self.var_dir / "artifacts"
        self.database_url = os.getenv(
            "ATP_DATABASE_URL", f"sqlite:///{(self.var_dir / 'control.db').as_posix()}"
        )
        self.host = os.getenv("ATP_HOST", "127.0.0.1")
        self.port = int(os.getenv("ATP_PORT", "8910"))
        # 凭证加密密钥。未设置时首次启动生成并落盘，避免明文存储凭证。
        self.secret_key_path = Path(os.getenv("ATP_SECRET_KEY_PATH", root / ".secret.key"))
        # Worker 领任务的长轮询上限
        self.lease_wait_seconds = float(os.getenv("ATP_LEASE_WAIT_SECONDS", "25"))
        # 领取后多久未完成视为失联并回收
        self.lease_ttl_seconds = float(os.getenv("ATP_LEASE_TTL_SECONDS", "900"))
        self.heartbeat_offline_seconds = float(os.getenv("ATP_HEARTBEAT_OFFLINE_SECONDS", "60"))
        # 截图 / 录像只留最近 N 次运行；0 表示不自动删。
        self.artifact_keep_runs = int(os.getenv("ATP_ARTIFACT_KEEP_RUNS", "5"))
        # 控制面写接口共享密钥；未设环境变量时首次启动生成并落盘。
        self.api_token_path = Path(os.getenv("ATP_API_TOKEN_PATH", self.var_dir / "api.token"))
        self.api_token = (os.getenv("ATP_API_TOKEN") or "").strip()
        # Worker 注册码：没有它不能 register，避免任意机器领到身份后换凭证。
        self.worker_register_code_path = Path(
            os.getenv("ATP_WORKER_REGISTER_CODE_PATH", self.var_dir / "worker.register_code")
        )
        self.worker_register_code = (os.getenv("ATP_WORKER_REGISTER_CODE") or "").strip()
        self._bind_ai()
        self.ensure_access_secrets()

    def ensure_access_secrets(self) -> None:
        """保证 API Token 与 Worker 注册码可用：环境变量优先，否则落盘生成。"""
        self.ensure_dirs()
        if not self.api_token:
            self.api_token = self._load_or_create_secret(self.api_token_path)
        if not self.worker_register_code:
            self.worker_register_code = self._load_or_create_secret(self.worker_register_code_path)

    @staticmethod
    def _load_or_create_secret(path: Path) -> str:
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = secrets.token_urlsafe(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return value

    def ai_config_path(self) -> Path:
        return self.var_dir / "ai.json"

    def _read_ai_file(self) -> dict:
        path = self.ai_config_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _bind_ai(self, file: dict | None = None) -> None:
        saved = file if file is not None else self._read_ai_file()
        prefer_saved = file is not None

        def pick(env_name: str, saved_key: str) -> str:
            env_val = os.getenv(env_name) or ""
            file_val = str(saved.get(saved_key) or "")
            if prefer_saved:
                return file_val or env_val
            return env_val or file_val

        self.anthropic_base_url = self.normalize_base_url(pick("ANTHROPIC_BASE_URL", "base_url"))
        self.anthropic_auth_token = self.normalize_auth_token(pick("ANTHROPIC_AUTH_TOKEN", "auth_token"))
        self.anthropic_model = pick("ANTHROPIC_MODEL", "model")
        self.anthropic_api_format = infer_api_format(
            self.anthropic_model, str(saved.get("api_format") or "")
        )
        self.anthropic_timeout_seconds = float(os.getenv("ANTHROPIC_TIMEOUT_SECONDS", saved.get("timeout_seconds") or 60))
        self.anthropic_max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", saved.get("max_tokens") or 4096))
        vision = os.getenv("ATP_AI_VISION_ENABLED") or os.getenv("ANTHROPIC_VISION_ENABLED")
        if vision is None:
            vision = "true" if saved.get("vision_enabled") else "false"
        self.anthropic_vision_enabled = str(vision).strip().lower() in {"1", "true", "yes", "on"}
        self.anthropic_max_retries = int(os.getenv("ANTHROPIC_MAX_RETRIES", saved.get("max_retries") or 2))

    def save_ai_config(
        self,
        *,
        base_url: str,
        auth_token: str | None,
        model: str,
        vision_enabled: bool = False,
    ) -> None:
        self.ensure_dirs()
        saved = self._read_ai_file()
        saved["base_url"] = self.normalize_base_url(base_url)
        if auth_token:
            saved["auth_token"] = self.normalize_auth_token(auth_token)
        saved["model"] = model
        saved["vision_enabled"] = vision_enabled
        saved["api_format"] = infer_api_format(model)
        self.ai_config_path().write_text(
            json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._bind_ai(saved)

    def reload_ai(self, *, prefer_file: bool = False) -> None:
        self._bind_ai(self._read_ai_file() if prefer_file else None)

    def token_hint(self) -> str:
        token = self.anthropic_auth_token or ""
        return token[-4:] if len(token) >= 4 else ""

    def ai_configured(self) -> bool:
        return bool(self.anthropic_base_url and self.anthropic_auth_token and self.anthropic_model)

    def ai_env_overrides(self) -> list[str]:
        names = []
        for name in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL"):
            if os.getenv(name):
                names.append(name)
        return names

    @staticmethod
    def normalize_base_url(url: str) -> str:
        value = (url or "").strip().rstrip("/")
        for suffix in (
            "/v1/chat/completions",
            "/v1/messages",
            "/v1/responses",
            "/v1",
        ):
            if value.endswith(suffix):
                value = value[: -len(suffix)].rstrip("/")
        return value

    @staticmethod
    def normalize_auth_token(token: str) -> str:
        value = (token or "").strip().strip('"').strip("'")
        for prefix in ("Bearer ", "bearer ", "BEARER "):
            if value.startswith(prefix):
                value = value[len(prefix) :].strip()
        return value

    def ensure_dirs(self) -> None:
        self.var_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
