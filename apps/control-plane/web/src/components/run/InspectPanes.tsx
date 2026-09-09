import { Alert, EmptyState } from "../ui";

function alertText(item: Record<string, unknown>): string {
  const kind = String(item.kind ?? "");
  if (kind === "page_error") {
    const counts = (item.counts ?? {}) as Record<string, unknown>;
    return `页面底层异常 脚本 ${counts.jsErrors ?? 0} · 请求 ${counts.requestErrors ?? 0}`;
  }
  if (kind === "ui_error") {
    return `页面报错 ${String(item.message ?? "")}`;
  }
  if (item.message) return String(item.message);
  return JSON.stringify(item);
}

function alertVariant(item: Record<string, unknown>): "error" | "info" {
  return item.kind === "locator_drift" ? "info" : "error";
}

export function AlertPane({ alerts }: { alerts: Record<string, unknown>[] }) {
  if (!alerts.length) return <EmptyState>没有告警。</EmptyState>;
  return (
    <div className="alert-list">
      {alerts.map((item, index) => (
        <Alert key={index} variant={alertVariant(item)}>
          {alertText(item)}
        </Alert>
      ))}
    </div>
  );
}

export function AssertPane({ asserts }: { asserts: Record<string, unknown>[] }) {
  if (!asserts.length) return <EmptyState>还没有断言。</EmptyState>;
  return (
    <div className="assert-list">
      {asserts.map((item, index) => (
        <div key={index} className="card">
          <div className={`result ${item.status}`}>
            {item.status === "passed" ? "通过" : "失败"} · {String(item.kind ?? "")}
          </div>
          {item.message ? <div className="muted">{String(item.message)}</div> : null}
        </div>
      ))}
    </div>
  );
}
