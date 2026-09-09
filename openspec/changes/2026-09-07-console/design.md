## Context

运行模块与本机执行器已能单条回放，但确认、删除、产物清理、AI 配置和漂移写回缺少控制台契约。套件能力见 `flow-suites`。见 `proposal.md`。

## Goals / Non-Goals

**Goals:**

- 把当天已实现行为写成可验收规格并进入主 specs
- 与 `flow-suites` 分工：本 change 不重复套件状态机

**Non-Goals:**

- 同会话连续回放、步骤间传变量
- 归档 `ai-compiler-p1-2` / `bootstrap-platform-p0`

## Decisions

1. **确认是控制台按钮，不是跑绿了就升级** — 与 P0 状态机一致，只补 UI 与删除门禁。
2. **执行器工作区 keep=0（清空目录）** — 截图以 `var/artifacts` 的 N=5 为准；`worker-ui` 里的 UUID 目录不是给用户翻的历史。
3. **漂移不静默写回** — 一条任务、一次确认、只改 N 处 candidates。
4. **AI 配置文件优先** — `var/ai.json` 保存后覆盖环境变量空值，避免换 Token 仍 401。

## Risks / Trade-offs

- [Windows 文件占用导致当时删不掉运行目录] → 任务结束与控制面清理都会再试；身份 json 不动
- [误点退回草稿会清基线] → 确认弹窗说明

## Migration Plan

无数据迁移。旧库 `run` 表缺列由启动补齐；工作区残留目录由清理扫掉。

## Open Questions

无。
