"""AI 监督者：把一次回放里的定位漂移汇总成脚本修补任务。"""

from __future__ import annotations

from typing import Any


def describe_candidate(candidate: Any) -> str:
    if not isinstance(candidate, dict):
        return str(candidate or "")
    kind = candidate.get("kind") or ""
    value = candidate.get("value") or ""
    name = candidate.get("name")
    if name:
        return f"{kind}={value!r} name={name!r}"
    return f"{kind}={value!r}"


def candidates_equal(left: Any, right: Any) -> bool:
    if not isinstance(left, list) or not isinstance(right, list):
        return False
    if len(left) != len(right):
        return False
    return [describe_candidate(item) for item in left] == [describe_candidate(item) for item in right]


def build_locator_patches(flow_steps: list[Any], updates: list[Any]) -> list[dict[str, Any]]:
    """只保留已保存脚本里存在、且首选确实变了的步骤。登录步骤等不在脚本里的一律跳过。"""
    steps_by_id: dict[str, dict[str, Any]] = {}
    for step in flow_steps or []:
        if isinstance(step, dict) and step.get("id"):
            steps_by_id[str(step["id"])] = step

    patches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in updates or []:
        if not isinstance(item, dict):
            continue
        step_id = item.get("step_id")
        candidates = item.get("candidates")
        if not isinstance(step_id, str) or step_id in seen:
            continue
        if not isinstance(candidates, list) or not candidates:
            continue
        step = steps_by_id.get(step_id)
        if step is None:
            continue
        target = step.get("target")
        if not isinstance(target, dict):
            continue
        old = target.get("candidates") if isinstance(target.get("candidates"), list) else []
        if candidates_equal(old, candidates):
            continue
        seen.add(step_id)
        patches.append(
            {
                "step_id": step_id,
                "label": str(step.get("label") or step.get("action") or step_id),
                "from_candidate": describe_candidate(old[0]) if old else "(空)",
                "to_candidate": describe_candidate(candidates[0]),
                "candidates": candidates,
            }
        )
    return patches


def supervisor_instruction(patches: list[dict[str, Any]]) -> str:
    n = len(patches)
    return (
        f"本轮回放出现 {n} 处定位漂移（首选候选失效，实际命中后顺位）。"
        f"请把这 {n} 步的首选定位改成实际命中的候选，其余步骤一律不要改。"
    )


def apply_locator_patches(flow_steps: list[Any], patches: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """只改 patches 里那些步骤的 target.candidates，其它字段和步骤不动。"""
    by_id: dict[str, dict[str, Any]] = {}
    for patch in patches or []:
        if not isinstance(patch, dict):
            continue
        step_id = patch.get("step_id")
        candidates = patch.get("candidates")
        if isinstance(step_id, str) and isinstance(candidates, list) and candidates:
            by_id[step_id] = patch

    steps = list(flow_steps or [])
    logs: list[str] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id") or "")
        patch = by_id.pop(step_id, None)
        if patch is None:
            continue
        target = step.get("target")
        if not isinstance(target, dict):
            logs.append(f"跳过「{patch.get('label') or step_id}」：步骤没有 target")
            continue
        new_step = dict(step)
        new_target = dict(target)
        new_target["candidates"] = patch["candidates"]
        new_step["target"] = new_target
        steps[index] = new_step
        logs.append(
            f"步骤「{patch.get('label') or step_id}」首选 "
            f"{patch.get('from_candidate') or describe_candidate((target.get('candidates') or [None])[0])} → "
            f"{patch.get('to_candidate') or describe_candidate(patch['candidates'][0])}"
        )
    for leftover in by_id.values():
        logs.append(f"跳过「{leftover.get('label') or leftover.get('step_id')}」：脚本里已找不到该步骤")
    return steps, logs
