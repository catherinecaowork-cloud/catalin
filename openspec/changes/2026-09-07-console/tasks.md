## 1. 流程确认与删除

- [x] 1.1 运行模块「确认为用例」：`draft → reviewed`
- [x] 1.2 用例显示「退回草稿」；非草稿隐藏删除；`DELETE` 返回 409

## 2. 产物与工作区

- [x] 2.1 控制面 `var/artifacts` 默认只留最近 5 次
- [x] 2.2 清空 `worker` / `worker-ui` / `worker-headless` 运行目录，保留身份文件

## 3. 定位修补与 AI 配置

- [x] 3.1 运行结束生成 heal 任务；确认后只改列出的 candidates
- [x] 3.2 顶栏 AI 配置落盘 `var/ai.json`；GLM 走 Chat Completions

## 4. 套件（并行 change）

- [x] 4.1 勾选运行、存成套件、失败即停 — 见 `openspec/changes/flow-suites`
