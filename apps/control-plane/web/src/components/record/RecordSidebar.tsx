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
    return <ModuleHint>录制进行中。在浏览器里操作，完成后点「结束录制」。</ModuleHint>;
  }

  return <ModuleHint>核对步骤后保存为流程草稿。可在主区域编辑每一步。</ModuleHint>;
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
      <Button variant="ghost" onClick={() => void ctx.retryCompile()}>
        重新编译
      </Button>
      {showFallback ? (
        <Button variant="ghost" style={{ marginTop: 8 }} onClick={() => void ctx.useFallbackSteps()}>
          采用确定性步骤
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
