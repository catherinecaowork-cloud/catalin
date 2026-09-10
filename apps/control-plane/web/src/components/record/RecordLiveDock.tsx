import { useRecordContext } from "../../context/RecordContext";
import { RecordLivePanel } from "./RecordLivePanel";

export function RecordLiveDock() {
  const ctx = useRecordContext();
  if (ctx.stage !== "busy") return null;
  return <RecordLivePanel />;
}
