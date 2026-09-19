import { addEventListener, removeEventListener } from "@decky/api";
import { useCallback, useEffect, useState } from "react";
import { getState } from "../backend";
import type { DspState, PluginState, SetupProgress, UpdateInfo } from "../types";

export function usePluginState() {
  const [state, setState] = useState<PluginState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setState(await getState());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onDsp = (dsp: DspState) => setState((s) => (s ? { ...s, dsp } : s));
    const onSetup = (p: SetupProgress) => {
      setState((s) => (s ? { ...s, setup: { ...s.setup, last: p, inProgress: p.status === "running" } } : s));
      if (p.step === "finished" || p.status === "error") void refresh();
    };
    const onConvert = (c: { percent: number; message: string; status: string }) => {
      setState((s) => (s ? { ...s, setup: { ...s.setup, convertLast: c, converting: c.status === "running" } } : s));
      if (c.status !== "running") void refresh();
    };
    const onUpdate = (u: UpdateInfo) => setState((s) => (s ? { ...s, update: u } : s));
    addEventListener<[DspState]>("dsp_state", onDsp);
    addEventListener<[SetupProgress]>("setup_progress", onSetup);
    addEventListener<[{ percent: number; message: string; status: string }]>("convert_progress", onConvert);
    addEventListener<[UpdateInfo]>("update_state", onUpdate);
    return () => {
      removeEventListener("dsp_state", onDsp);
      removeEventListener("setup_progress", onSetup);
      removeEventListener("convert_progress", onConvert);
      removeEventListener("update_state", onUpdate);
    };
  }, [refresh]);

  return { state, error, refresh, setState };
}
