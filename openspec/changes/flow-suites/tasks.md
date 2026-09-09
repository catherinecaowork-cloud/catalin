## 1. 数据模型

- [x] 1.1 新增 `Suite`、`Batch` 模型；`Run` 增加可空 `batch_id` / `batch_index`
- [x] 1.2 SQLite 启动补列 `run.batch_id`、`run.batch_index`

## 2. 批次与套件逻辑

- [x] 2.1 `suites.py`：已确认状态校验、成员属于同一站点、失败即停下一步决策
- [x] 2.2 套件 CRUD API：创建/列表/更新/删除；草稿或跨站点成员返回 409
- [x] 2.3 批次 API：按 `flow_ids` 或 `suite_id` 启动；只入队第一条
- [x] 2.4 `complete_run` 衔接下一条；非 `passed` 结束批次；删套件不删运行

## 3. 控制台

- [x] 3.1 已确认用例显示勾选；草稿不勾选
- [x] 3.2 「运行勾选」「存成套件」；套件列表可点运行、可删
- [x] 3.3 批次进行中跟随当前 `run_id` 打开直播

## 4. 自测

- [x] 4.1 `scripts/selftest_suites.py`：草稿拒入组、失败即停、通过后入队下一条
