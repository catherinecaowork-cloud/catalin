import { useState } from "react";

import { useRecordContext } from "../../context/RecordContext";
import { Alert, Button, Checkbox, Field, FootHint, Input, ModuleHint, Muted, Select } from "../ui";

export function RecordSidebar() {
  const ctx = useRecordContext();

  if (ctx.stage === "idle") {
    return (
      <>
        <ModuleHint>填写意图后开窗录制。结束后再 AI 编译或直接保存为草稿。</ModuleHint>
        <Field label="录制意图">
          <Input
            type="text"
            value={ctx.intent}
            placeholder="例如：新增一条款式并确认保存成功"
            onChange={(event) => ctx.setIntent(event.target.value)}
          />
        </Field>
        <Field label="登录凭证">
          <Select
            value={ctx.credentialId}
            onChange={(event) => ctx.setCredentialId(event.target.value)}
          >
            <option value="">不登录</option>
            {ctx.credentials.map((cred) => (
              <option key={cred.id} value={cred.id}>
                {cred.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="起始路径">
          <Input
            type="text"
            value={ctx.startPath}
            placeholder="/"
            onChange={(event) => ctx.setStartPath(event.target.value)}
          />
        </Field>
        <Checkbox
          label="结束录制后 AI 编译验证"
          checked={ctx.aiCompileEnabled}
          onChange={(event) => ctx.setAiCompileEnabled(event.target.checked)}
        />
      </>
    );
  }

  if (ctx.stage === "busy") {
    return (
      <>
        <ModuleHint>录制进行中。在浏览器里操作，完成后点「结束录制」。</ModuleHint>
        {ctx.observedEntries.length ? (
          <div className="observed-fields">
            <Muted>已认识 {ctx.observedEntries.length} 个字段/组件</Muted>
            <ul className="observed-fields-list">
              {ctx.observedEntries.map((entry) => (
                <li key={entry.id}>
                  <strong>{entry.display_name}</strong>
                  <span>
                    {entry.widget_kind} · {entry.value_strategy === "choose_any" ? "任选" : "参数化"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <Muted>观察者正在认识页面字段…</Muted>
        )}
      </>
    );
  }

  const canToggleScripts = ctx.sampleSteps.length > 0 && ctx.observerSteps.length > 0;

  return (
    <>
      <ModuleHint>
        当前路径：<strong>{ctx.compilePath}</strong>。默认展示观察者脚本，可切换查看样例轨迹。
      </ModuleHint>
      {canToggleScripts ? (
        <div className="script-source-toggle">
          <Button
            variant={ctx.scriptSource === "observer" ? "primary" : "ghost"}
            onClick={() => ctx.switchScriptSource("observer")}
          >
            观察者脚本 ({ctx.observerSteps.length})
          </Button>
          <Button
            variant={ctx.scriptSource === "sample" ? "primary" : "ghost"}
            onClick={() => ctx.switchScriptSource("sample")}
          >
            样例轨迹 ({ctx.sampleSteps.length})
          </Button>
        </div>
      ) : null}
    </>
  );
}

export function RecordSidebarFoot() {
  const ctx = useRecordContext();
  const [assertText, setAssertText] = useState("");

  if (ctx.stage === "idle") {
    return (
      <div className="run-foot">
        <Button variant="go" disabled={!ctx.intent.trim()} onClick={() => void ctx.startRecord()}>
          开始录制
        </Button>
        <FootHint>需要 headed 执行器在线。</FootHint>
      </div>
    );
  }

  if (ctx.stage === "busy") {
    return (
      <div className="run-foot">
        <Muted>{ctx.waitingHint}</Muted>
        <Muted>已采集 {ctx.eventCount} 个事件</Muted>
        <Button variant="warn" onClick={() => void ctx.stopRecord()}>
          结束录制
        </Button>
      </div>
    );
  }

  const showFallback =
    ctx.compilation &&
    ctx.compilation.status !== "passed" &&
    ctx.compilation.status !== "manual_validation";

  return (
    <div className="run-foot">
      {ctx.compileMessage ? (
        <Alert variant={ctx.compileError ? "error" : "info"}>{ctx.compileMessage}</Alert>
      ) : null}
      {ctx.notes.map((note, index) => (
        <Alert key={index}>{note}</Alert>
      ))}
      <Muted>编写路径：{ctx.compilePath}</Muted>
      <Button variant="ghost" onClick={() => void ctx.retryCompile()}>
        重新观察者编写
      </Button>
      <Button variant="ghost" style={{ marginTop: 8 }} onClick={() => void ctx.retryPolishCompile()}>
        走润色编译
      </Button>
      {showFallback ? (
        <Button variant="ghost" style={{ marginTop: 8 }} onClick={() => void ctx.useFallbackSteps()}>
          采用样例轨迹
        </Button>
      ) : null}
      <Field label="流程名称">
        <Input
          type="text"
          value={ctx.flowName}
          onChange={(event) => ctx.setFlowName(event.target.value)}
        />
      </Field>
      <Field label="添加断言（text_contains）">
        <Input
          type="text"
          value={assertText}
          placeholder="页面上应出现的文字"
          onChange={(event) => setAssertText(event.target.value)}
        />
      </Field>
      <Button
        variant="ghost"
        onClick={() => {
          ctx.addAssert(assertText);
          setAssertText("");
        }}
      >
        添加断言步骤
      </Button>
      <Button
        variant="primary"
        style={{ marginTop: 8 }}
        disabled={!ctx.draftSteps.length}
        onClick={() => void ctx.saveRecord()}
      >
        保存为流程
      </Button>
      <Button variant="ghost" style={{ marginTop: 8 }} onClick={ctx.cancelRecord}>
        丢弃并重置
      </Button>
      {ctx.saveHint ? <FootHint>{ctx.saveHint}</FootHint> : null}
    </div>
  );
}
