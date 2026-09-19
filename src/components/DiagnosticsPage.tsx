import { DialogButton, Focusable, Navigation } from "@decky/ui";
import { useEffect, useState } from "react";
import { getDiagnostics } from "../backend";
import { t } from "../strings";

export function DiagnosticsPage() {
  const [text, setText] = useState<string>("…");
  const load = () => {
    getDiagnostics().then((r) => setText(r.text)).catch((e) => setText(String(e)));
  };
  useEffect(load, []);
  return (
    <Focusable style={{ marginTop: "40px", padding: "0 28px 20px", color: "#fff" }} flow-children="vertical">
      <h2 style={{ marginBottom: "6px" }}>{t.diagnostics}</h2>
      <p style={{ opacity: 0.75, fontSize: "13px" }}>~/homebrew/logs/Ally DSP/diagnostics.txt</p>
      <Focusable style={{ display: "flex", gap: "12px", marginBottom: "10px" }} flow-children="horizontal">
        <DialogButton onClick={load}>{t.refresh}</DialogButton>
        <DialogButton onClick={() => Navigation.NavigateBack()}>{t.back}</DialogButton>
      </Focusable>
      <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: "12px", lineHeight: 1.35, background: "rgba(0,0,0,0.35)", padding: "10px", borderRadius: "6px" }}>
        {text}
      </pre>
    </Focusable>
  );
}
