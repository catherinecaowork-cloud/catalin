import { CircleDot, Square } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useRecordContext } from "../../context/RecordContext";
import {
  liveActionDescription,
  liveActionInput,
  liveActionItem,
  liveActionObject,
} from "../../utils/recordLiveDisplay";
import { Button } from "../ui";

type DisplayRow = {
  key: string;
  sequence: number;
  item: string;
  object: string;
  input: string;
  description: string;
  live?: boolean;
};

export function RecordLivePanel() {
  const ctx = useRecordContext();
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const rows = useMemo<DisplayRow[]>(() => {
    const setup: DisplayRow[] = [
      {
        key: "setup-open",
        sequence: 1,
        item: "1 - Open Browser",
        object: "Chrome",
        input: "—",
        description: "Headed 模式",
      },
      {
        key: "setup-goto",
        sequence: 2,
        item: "2 - Navigate To Url",
        object: "—",
        input: ctx.recordUrl || "—",
        description: ctx.intent || "—",
      },
    ];
    const actions = ctx.liveActions.map((action, offset) => {
      const sequence = setup.length + offset + 1;
      return {
        key: `live-${action.index}-${sequence}`,
        sequence,
        item: liveActionItem(action, sequence),
        object: liveActionObject(action),
        input: liveActionInput(action),
        description: liveActionDescription(action),
        live: true,
      };
    });
    return [...setup, ...actions];
  }, [ctx.intent, ctx.liveActions, ctx.recordUrl]);

  useEffect(() => {
    const node = listRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [rows.length]);

  useEffect(() => {
    if (!rows.length) return;
    const last = rows[rows.length - 1];
    setSelectedKey(last.key);
  }, [rows]);

  if (ctx.stage !== "busy") return null;

  return (
    <aside className="record-live-panel" aria-label="Web 录制面板">
      <header className="record-live-header">
        <div className="record-live-title">
          <CircleDot size={15} strokeWidth={2} aria-hidden />
          <span>Web 录制</span>
          <span className="record-live-badge">REC</span>
        </div>
        <div className="record-live-actions">
          <Button variant="ghost" onClick={() => void ctx.toggleRecordPause()}>
            {ctx.recordPaused ? "继续" : "暂停"}
          </Button>
          <Button variant="warn" className="record-live-stop" onClick={() => void ctx.stopRecord()}>
            <Square size={12} strokeWidth={2} aria-hidden />
            停止
          </Button>
        </div>
      </header>

      <div className="record-live-url-row">
        <span className="record-live-url-label">URL</span>
        <input
          className="record-live-url-input"
          type="text"
          readOnly
          value={ctx.recordUrl}
          aria-label="录制 URL"
        />
      </div>

      <p className="record-live-hint muted">
        在浏览器窗口中操作页面元素；此处实时显示录到的动作。右键元素可扩展验证类操作。
      </p>

      <div className="record-live-section-head">
        <span className="record-live-section-title">RECORDED ACTIONS</span>
        <span className="record-live-count">{ctx.liveActions.length} 个动作</span>
      </div>

      <div className="record-live-grid-wrap" ref={listRef}>
        <table className="record-live-grid">
          <thead>
            <tr>
              <th className="col-item">Item</th>
              <th className="col-object">Object</th>
              <th className="col-input">Input</th>
              <th className="col-desc">Description</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.key}
                className={`record-live-row${selectedKey === row.key ? " selected" : ""}${
                  row.live ? " live" : ""
                }`}
                onClick={() => setSelectedKey(row.key)}
              >
                <td className="col-item mono" title={row.item}>
                  {row.item}
                </td>
                <td className="col-object mono" title={row.object}>
                  {row.object}
                </td>
                <td className="col-input mono" title={row.input}>
                  {row.input}
                </td>
                <td className="col-desc" title={row.description}>
                  {row.description}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <footer className="record-live-foot muted">
        {ctx.waitingHint || "录制中…"}
        {ctx.observedEntries.length ? ` · 已识别 ${ctx.observedEntries.length} 个字段` : null}
      </footer>
    </aside>
  );
}
