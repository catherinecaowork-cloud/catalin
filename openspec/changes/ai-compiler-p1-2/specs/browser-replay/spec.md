## MODIFIED Requirements

### Requirement: 统一动作原语

回放引擎 SHALL 提供一套固定的动作原语：打开地址、点击、填值、选择、等待条件、读取表格、读取页面体检、断言、截图；流程步骤 SHALL 只能由这些原语构成。步骤 MAY 携带可选阶段元数据 `phase`（setup、main、verify）用于分组展示，SHALL NOT 改变执行顺序语义。

#### Scenario: 手写流程可回放

- **WHEN** 使用者用动作原语定义一条流程并执行
- **THEN** 执行器按步骤在真浏览器中依次操作，并逐步返回每步结果

#### Scenario: 不支持的动作被拒绝

- **WHEN** 流程中出现动作原语之外的自定义指令
- **THEN** 平台在保存或执行前校验失败，并指出不被支持的步骤

#### Scenario: phase 仅作元数据

- **WHEN** 步骤设置了 phase 为 setup、main 或 verify
- **THEN** 回放仍按步骤列表顺序执行，phase 不改变执行次序

### Requirement: 真实执行与可见性解耦

所有页面操作（打开、等待加载、点击、填表）SHALL 在真实浏览器中发生；开窗与无头 SHALL 仅影响是否绘制窗口，SHALL NOT 改变执行路径与判定结果。执行前 SHALL 解析步骤 value 与 expected 中的变量模板（见 step-variables 能力）。

#### Scenario: 两种模式结果一致

- **WHEN** 同一条流程分别以开窗与无头模式执行且被测环境未变化
- **THEN** 两次运行的步骤序列与断言结论一致

#### Scenario: 开窗需要真实桌面

- **WHEN** 在无桌面会话的环境中请求开窗执行
- **THEN** 任务以明确的「该执行器不支持开窗」原因失败，而不是静默降级为无头

#### Scenario: 变量模板在两种模式下一致展开

- **WHEN** 同一条含 `{{unique:key}}` 的流程分别以开窗与无头模式各执行一次
- **THEN** 每种模式内部 unique 值自洽，且两种模式的步骤序列与断言判定规则一致
