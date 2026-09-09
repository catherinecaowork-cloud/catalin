"""定位修补任务与 AI 配置落盘自测。"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from autotest_control.heal import apply_locator_patches, build_locator_patches
from autotest_control.settings import Settings


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def main() -> int:
    steps = [
        {
            "id": "login.user",
            "action": "fill",
            "label": "登录账号",
            "target": {"candidates": [{"kind": "role", "value": "textbox"}]},
        },
        {
            "id": "s1",
            "action": "fill",
            "label": "填写成本",
            "target": {
                "candidates": [
                    {"kind": "label", "value": "成本"},
                    {"kind": "field", "value": "productCost"},
                ]
            },
        },
        {
            "id": "s2",
            "action": "fill",
            "label": "上传图片",
            "target": {
                "candidates": [
                    {"kind": "role", "value": "textbox"},
                    {"kind": "css", "value": '[data-name="imageUrls"]'},
                ]
            },
        },
        {"id": "s3", "action": "click", "label": "保存", "target": {"candidates": [{"kind": "text", "value": "保存"}]}},
    ]
    updates = [
        {
            "step_id": "login.user",
            "candidates": [{"kind": "css", "value": "#username"}, {"kind": "role", "value": "textbox"}],
        },
        {
            "step_id": "s1",
            "candidates": [
                {"kind": "field", "value": "productCost"},
                {"kind": "label", "value": "成本"},
            ],
        },
        {
            "step_id": "s2",
            "candidates": [
                {"kind": "css", "value": '[data-name="imageUrls"]'},
                {"kind": "role", "value": "textbox"},
            ],
        },
    ]
    # 脚本里没有登录步骤：监督者不应把它塞进任务
    flow_steps = [item for item in steps if item["id"] != "login.user"]
    patches = build_locator_patches(flow_steps, updates)
    _assert(len(patches) == 2, "只汇总脚本里存在的漂移步骤")
    _assert(patches[0]["step_id"] == "s1" and "productCost" in patches[0]["to_candidate"], "第一处改到实际命中的 field")
    _assert(patches[1]["step_id"] == "s2", "第二处改到实际命中的 css")

    new_steps, logs = apply_locator_patches(flow_steps, patches)
    _assert(len(new_steps) == 3, "步骤数量不变")
    _assert(new_steps[0]["target"]["candidates"][0]["kind"] == "field", "只改列出的步骤首选")
    _assert(new_steps[2]["target"]["candidates"][0]["value"] == "保存", "未列出的步骤原样保留")
    _assert(len(logs) == 2 and all("首选" in line for line in logs), "执行者日志覆盖每一处修改")

    unchanged = build_locator_patches(new_steps, updates[1:])
    _assert(unchanged == [], "首选已经是命中候选时不再生成任务")

    for name in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL"):
        os.environ.pop(name, None)
    with tempfile.TemporaryDirectory() as temp:
        os.environ["ATP_VAR_DIR"] = temp
        cfg = Settings()
        _assert(not cfg.ai_configured(), "未保存时 AI 未配置")
        cfg.save_ai_config(
            base_url="http://gateway.example/v1/messages",
            auth_token="secret-token",
            model="ark-code-latest",
            vision_enabled=False,
        )
        _assert(cfg.anthropic_base_url == "http://gateway.example", "保存时去掉 /v1/messages")
        cfg.save_ai_config(
            base_url="https://api.aicodewith.com/v1/chat/completions",
            auth_token="Bearer secret-token",
            model="glm-5.1",
            vision_enabled=False,
        )
        _assert(cfg.anthropic_base_url == "https://api.aicodewith.com", "保存时去掉 /v1/chat/completions")
        _assert(cfg.anthropic_auth_token == "secret-token", "保存时去掉 Bearer 前缀")
        _assert(cfg.ai_configured(), "保存三项后视为已配置")
        saved = json.loads(Path(temp, "ai.json").read_text(encoding="utf-8"))
        _assert(saved["auth_token"] == "secret-token", "token 写入 var/ai.json")
        cfg.save_ai_config(
            base_url="http://gateway.example",
            auth_token=None,
            model="other-model",
            vision_enabled=True,
        )
        _assert(cfg.anthropic_auth_token == "secret-token", "留空 token 不覆盖已保存值")
        _assert(cfg.anthropic_model == "other-model" and cfg.anthropic_vision_enabled, "可更新模型和视觉开关")
        os.environ["ANTHROPIC_AUTH_TOKEN"] = "env-should-not-win"
        cfg.save_ai_config(
            base_url="https://api.aicodewith.com",
            auth_token="file-should-win",
            model="glm-5.1",
            vision_enabled=False,
        )
        _assert(cfg.anthropic_auth_token == "file-should-win", "控制台保存后不再被环境变量盖掉")
        os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

    from autotest_control.settings import infer_api_format

    _assert(infer_api_format("glm-5.1") == "openai-completions", "glm-5.1 识别为 Chat Completions")
    _assert(infer_api_format("claude-sonnet-4-6") == "anthropic", "Claude 仍走 Anthropic Messages")

    from autotest_control.storage import prune_run_dirs

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for name in ("a", "b", "c"):
            folder = root / name
            folder.mkdir()
            (folder / "shot.png").write_bytes(b"x")
            time.sleep(0.05)
        prune_run_dirs(root, 2)
        left = sorted(p.name for p in root.iterdir() if p.is_dir())
        _assert(left == ["b", "c"], "产物目录只保留最近两次")

    print("\n定位修补与 AI 配置自测通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
