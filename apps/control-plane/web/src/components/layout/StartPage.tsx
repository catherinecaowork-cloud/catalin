import { CircleDot, Clock, Play } from "lucide-react";

import { useHistoryContext } from "../../context/HistoryContext";
import { useRunContext } from "../../context/RunContext";

type Props = {
  onOpenRecord: () => void;
  onOpenRun: () => void;
  onOpenHistory: () => void;
  onOpenRunRecord: (runId: string, title: string) => void;
};

export function StartPage({ onOpenRecord, onOpenRun, onOpenHistory, onOpenRunRecord }: Props) {
  const history = useHistoryContext();
  const run = useRunContext();
  const recent = history.runs.slice(0, 8);
  const hasSite = Boolean(run.siteId);
  const flowCount = run.flows.length;

  const nextStep = !hasSite
    ? {
        title: "先选环境",
        desc: "在顶栏左侧选择或添加站点，资源树才会加载用例。",
        primary: { label: "管理环境", onClick: onOpenRecord },
        secondary: null as { label: string; onClick: () => void } | null,
      }
    : flowCount === 0
      ? {
          title: "录一条用例",
          desc: "当前环境还没有脚本。用顶栏「录制」抓取步骤，保存后会出现在左侧。",
          primary: { label: "开始录制", onClick: onOpenRecord },
          secondary: { label: "查看运行记录", onClick: onOpenHistory },
        }
      : {
          title: "运行或继续录制",
          desc: `已有 ${flowCount} 条流程。在左侧选中用例后点「运行所选」，或继续录新脚本。`,
          primary: { label: "打开运行", onClick: onOpenRun },
          secondary: { label: "录制", onClick: onOpenRecord },
        };

  return (
    <div className="editor-empty start-page">
      <div className="start-page-hero">
        <div className="start-page-brand">
          <img className="start-page-brand-mark" src="/favicon.svg" width={28} height={28} alt="" />
          <div>
            <h2>Catalin</h2>
            <p className="muted">自动化测试工作台</p>
          </div>
        </div>
      </div>

      <section className="start-next" aria-label="下一步">
        <div className="start-next-copy">
          <h3>{nextStep.title}</h3>
          <p>{nextStep.desc}</p>
        </div>
        <div className="start-next-actions">
          <button type="button" className="start-cta primary" onClick={nextStep.primary.onClick}>
            {nextStep.primary.label === "开始录制" || nextStep.primary.label === "管理环境" ? (
              <CircleDot size={14} strokeWidth={2} aria-hidden />
            ) : (
              <Play size={14} strokeWidth={2} aria-hidden />
            )}
            {nextStep.primary.label}
          </button>
          {nextStep.secondary ? (
            <button type="button" className="start-cta ghost" onClick={nextStep.secondary.onClick}>
              {nextStep.secondary.label === "录制" ? (
                <CircleDot size={14} strokeWidth={2} aria-hidden />
              ) : (
                <Clock size={14} strokeWidth={2} aria-hidden />
              )}
              {nextStep.secondary.label}
            </button>
          ) : null}
        </div>
      </section>

      <section className="start-recent" aria-label="最近运行">
        <div className="start-recent-head">
          <h4>最近运行</h4>
          <button type="button" className="start-recent-more" onClick={onOpenHistory}>
            全部记录
          </button>
        </div>

        {!hasSite ? (
          <p className="start-recent-empty">选择环境后显示本站点最近运行。</p>
        ) : history.loading && recent.length === 0 ? (
          <p className="start-recent-empty">加载中…</p>
        ) : recent.length === 0 ? (
          <p className="start-recent-empty">还没有运行记录。选中用例后从左侧执行区启动回放。</p>
        ) : (
          <ul className="start-recent-list">
            {recent.map((item) => {
              const time = new Date(item.created_at).toLocaleString("zh-CN", { hour12: false });
              const dur = item.duration_seconds ? `${item.duration_seconds.toFixed(1)}s` : "—";
              const busy = history.isBusy(item);
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className="start-recent-row"
                    disabled={busy}
                    onClick={() => onOpenRunRecord(item.id, `运行 ${item.id.slice(0, 8)}`)}
                  >
                    <span className={`start-recent-status status-${item.status}`}>
                      {history.statusText(item.status)}
                    </span>
                    <span className="start-recent-kind">{history.kindText(item.kind)}</span>
                    <span className="start-recent-meta">
                      <span>{time}</span>
                      <span>{dur}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
