import { useState } from "react";

import { useRecordContext } from "../../context/RecordContext";
import { Alert, Button, Field, FootHint, Input, ModuleHint, Muted } from "../ui";

export function RecordSidebar() {
  const ctx = useRecordContext();

  if (ctx.stage === "busy") {
    return (
      <>
        <ModuleHint>
          {ctx.recordPaused
            ? "录制已暂停。调整页面后点「继续录制」，或点「结束录制」收工。"
            : "录制进行中。在浏览器里操作，可暂停或结束录制。"}
        </ModuleHint>
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

  if (ctx.stage === "busy") {
    return (
      <div className="run-foot">
        <Muted>{ctx.waitingHint}</Muted>
        <Muted>
          {ctx.recordPaused ? "已暂停 · " : ""}已采集 {ctx.eventCount} 个事件
        </Muted>
        <div className="run-foot-actions">
          <Button variant="ghost" onClick={() => void ctx.toggleRecordPause()}>
            {ctx.recordPaused ? "继续录制" : "暂停录制"}
          </Button>
          <Button variant="warn" onClick={() => void ctx.stopRecord()}>
            结束录制
          </Button>
        </div>
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

      <div className="run-foot-section">
        <div className="run-foot-section-title">保存</div>
        <Muted>编写路径：{ctx.compilePath}</Muted>
        <Field label="流程名称">
          <Input
            type="text"
            value={ctx.flowName}
            onChange={(event) => ctx.setFlowName(event.target.value)}
          />
        </Field>
        <div className="run-foot-actions">
          <Button
            variant="primary"
            disabled={!ctx.draftSteps.length}
            onClick={() => void ctx.saveRecord()}
          >
            保存为流程
          </Button>
          <Button variant="ghost" onClick={ctx.cancelRecord}>
            丢弃并重置
          </Button>
        </div>
        {ctx.saveHint ? <FootHint>{ctx.saveHint}</FootHint> : null}
      </div>

      <div className="run-foot-section">
        <div className="run-foot-section-title">断言</div>
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
      </div>

      <div className="run-foot-section">
        <div className="run-foot-section-title">重新编写</div>
        <div className="run-foot-actions stacked">
          <Button variant="ghost" onClick={() => void ctx.retryCompile()}>
            重新观察者编写
          </Button>
          <Button variant="ghost" onClick={() => void ctx.retryPolishCompile()}>
            走润色编译
          </Button>
          {showFallback ? (
            <Button variant="ghost" onClick={() => void ctx.useFallbackSteps()}>
              采用样例轨迹
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
