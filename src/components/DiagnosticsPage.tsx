import { DialogButton, Focusable, Navigation } from "@decky/ui";
import { useEffect, useState } from "react";
import { getDiagnostics } from "../backend";
import { t } from "../strings";
import { FocusStop, Page, ScrollArea } from "./Page";

const LINES_PER_STOP = 6;

function chunks(text: string): string[] {
  const lines = text.split("\n");
  const out: string[] = [];
  for (let i = 0; i < lines.length; i += LINES_PER_STOP) out.push(lines.slice(i, i + LINES_PER_STOP).join("\n"));
  return out;
}

export function DiagnosticsPage() {
  const [text, setText] = useState<string>("…");
  const load = () => {
    getDiagnostics().then((r) => setText(r.text)).catch((e) => setText(String(e)));
  };
  useEffect(load, []);
  return (
    <Page>
      <h2 style={{ marginBottom: "6px" }}>{t.diagnostics}</h2>
      <p style={{ opacity: 0.75, fontSize: "13px" }}>~/homebrew/logs/Ally DSP/diagnostics.txt</p>
      <Focusable style={{ display: "flex", gap: "12px", marginBottom: "10px" }} flow-children="horizontal">
        <DialogButton onClick={load}>{t.refresh}</DialogButton>
        <DialogButton onClick={() => Navigation.NavigateBack()}>{t.back}</DialogButton>
      </Focusable>
      <ScrollArea style={{ background: "rgba(0,0,0,0.35)", padding: "6px 10px", borderRadius: "6px" }}>
        {chunks(text).map((c, i) => (
          <FocusStop key={i}>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: "12px", lineHeight: 1.35 }}>{c}</pre>
          </FocusStop>
        ))}
      </ScrollArea>
    </Page>
  );
}
