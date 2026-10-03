import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { DialogButton, Focusable, Navigation, ProgressBarWithInfo, ToggleField } from "@decky/ui";
import { useEffect, useState } from "react";
import { cancelSetup, getSetupProgress, getState, runSetup } from "../backend";
import { setupIntent } from "../setupIntent";
import { STEP_LABELS, t } from "../strings";
import type { PluginState, SetupProgress } from "../types";
import { Page, ScrollArea } from "./Page";

const STEPS = ["hardware", "resolve", "download", "extract", "venv", "convert", "activate"];

function stepMark(step: string, p: SetupProgress | null): string {
  if (!p) return "○";
  const idx = STEPS.indexOf(step);
  if (p.step === "finished") return p.status === "done" ? "✓" : "○";
  if (idx < p.index) return "✓";
  if (idx === p.index) return p.status === "error" ? "✗" : p.status === "done" || p.status === "skipped" ? "✓" : "▶";
  return "○";
}

export function SetupPage() {
  const [progress, setProgress] = useState<SetupProgress | null>(null);
  const [state, setState] = useState<PluginState | null>(null);
  const [force, setForce] = useState(setupIntent.force);
  const [allowUnsupported, setAllowUnsupported] = useState(false);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    void getState().then(setState).catch(() => undefined);
    void getSetupProgress().then((p) => p && setProgress(p)).catch(() => undefined);
    const onProgress = (p: SetupProgress) => {
      setProgress(p);
      if (p.step === "finished" && p.status === "done") toaster.toast({ title: t.title, body: p.message });
    };
    addEventListener<[SetupProgress]>("setup_progress", onProgress);
    return () => {
      removeEventListener("setup_progress", onProgress);
    };
  }, []);

  const running = !!progress && progress.status === "running" && progress.step !== "finished";
  const finished = !!progress && progress.step === "finished" && progress.status === "done";
  const failed = !!progress && progress.status === "error";
  const codec = state?.hardware.codec ?? null;
  const unsupported = !!codec && !codec.supported;

  const start = async () => {
    setStarting(true);
    try {
      const r = await runSetup(force, allowUnsupported);
      if (!r.started) toaster.toast({ title: t.title, body: r.reason ?? "" });
    } catch (e) {
      toaster.toast({ title: t.title, body: String(e) });
    } finally {
      setStarting(false);
    }
  };

  // Controls first: on the handheld the lower part of the page can sit behind Steam's footer.
  return (
    <Page>
      <h2 style={{ marginBottom: "6px" }}>{t.setupTitle}</h2>
      <p style={{ opacity: 0.85, lineHeight: 1.4 }}>{t.setupIntro}</p>
      {codec && (
        <p style={{ opacity: 0.85 }}>
          {codec.codec} · SSID {codec.ssid} · {codec.model ?? t.unsupported}
          {state?.hardware.sink ? ` · ${state.hardware.sink.name}` : ""}
        </p>
      )}
      {unsupported && (
        <ToggleField label={t.forceUnsupported} description={t.unsupported} checked={allowUnsupported} onChange={setAllowUnsupported} disabled={running} />
      )}
      {state?.setup.done && (
        <ToggleField label={t.rerunSetup} description="force" checked={force} onChange={setForce} disabled={running} />
      )}
      <Focusable style={{ display: "flex", gap: "12px", margin: "12px 0" }} flow-children="horizontal">
        <DialogButton onClick={() => void start()} disabled={running || starting || (unsupported && !allowUnsupported) || !codec}>
          {finished ? t.rerunSetup : t.start}
        </DialogButton>
        <DialogButton onClick={() => void cancelSetup()} disabled={!running}>{t.cancel}</DialogButton>
        <DialogButton onClick={() => Navigation.NavigateBack()}>{finished ? t.done : t.back}</DialogButton>
      </Focusable>
      <ProgressBarWithInfo nProgress={progress?.percent ?? 0} indeterminate={false} sOperationText={progress?.message ?? ""} layout="below" bottomSeparator="none" />
      {failed && <p style={{ color: "#ff8a80" }}>{progress?.message}</p>}
      {/* Two columns so the list fits above the footer; the progress bar shows the current message. */}
      <ScrollArea style={{ marginTop: "8px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gridTemplateRows: "repeat(4, auto)", gridAutoFlow: "column",
          columnGap: "24px", lineHeight: 1.25 }}>
          {STEPS.map((step) => (
            <div key={step} style={{ display: "flex", gap: "10px", padding: "1px 0", opacity: progress && STEPS.indexOf(step) > progress.index ? 0.55 : 1 }}>
              <span style={{ width: "18px", display: "inline-block" }}>{stepMark(step, progress)}</span>
              <span>{STEP_LABELS[step] ?? step}</span>
            </div>
          ))}
        </div>
      </ScrollArea>
    </Page>
  );
}
