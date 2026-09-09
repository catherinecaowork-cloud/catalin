import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { RunAlert, RunStep } from "../types";

export type BottomPanelFeed = {
  steps: RunStep[];
  alerts: RunAlert[];
};

type BottomPanelContextValue = {
  feed: BottomPanelFeed;
  setFeed: (patch: Partial<BottomPanelFeed>) => void;
  clearFeed: () => void;
};

const emptyFeed: BottomPanelFeed = { steps: [], alerts: [] };

const BottomPanelContext = createContext<BottomPanelContextValue | null>(null);

export function BottomPanelProvider({ children }: { children: ReactNode }) {
  const [feed, setFeedState] = useState<BottomPanelFeed>(emptyFeed);

  const setFeed = useCallback((patch: Partial<BottomPanelFeed>) => {
    setFeedState((prev) => ({ ...prev, ...patch }));
  }, []);

  const clearFeed = useCallback(() => setFeedState(emptyFeed), []);

  const value = useMemo(
    () => ({ feed, setFeed, clearFeed }),
    [feed, setFeed, clearFeed],
  );

  return <BottomPanelContext.Provider value={value}>{children}</BottomPanelContext.Provider>;
}

export function useBottomPanel() {
  const ctx = useContext(BottomPanelContext);
  if (!ctx) throw new Error("useBottomPanel must be used within BottomPanelProvider");
  return ctx;
}

export function useBottomPanelPublisher(steps: RunStep[], alerts: RunAlert[]) {
  const { setFeed, clearFeed } = useBottomPanel();

  useEffect(() => {
    setFeed({ steps, alerts });
  }, [steps, alerts, setFeed]);

  useEffect(() => () => clearFeed(), [clearFeed]);
}
