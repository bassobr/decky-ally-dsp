import { Focusable } from "@decky/ui";
import { type CSSProperties, type ReactNode, useRef } from "react";

/** Route page between Steam's top bar and footer legend (about 40 px each); a ScrollArea takes the rest. */
export function Page({ children }: { children: ReactNode }) {
  return (
    <Focusable style={{ marginTop: "40px", height: "calc(100vh - 84px)", padding: "0 28px", maxWidth: "900px", color: "#fff",
      display: "flex", flexDirection: "column" }} flow-children="vertical">
      {children}
    </Focusable>
  );
}

/** Scrolls when its content is taller than the rest of the page; the D-pad reaches it through FocusStops. */
export function ScrollArea({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div style={{ flex: 1, minHeight: 0, overflowY: "auto", ...style }}>{children}</div>;
}

/** A focus stop for content that is not a control; it scrolls into view when it gets focus. */
export function FocusStop({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <Focusable ref={ref} style={style} onActivate={() => {}}
      onGamepadFocus={() => ref.current?.scrollIntoView({ block: "nearest" })}>
      {children}
    </Focusable>
  );
}
