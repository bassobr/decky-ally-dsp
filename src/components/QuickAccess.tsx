import {
  ButtonItem,
  DropdownItem,
  Field,
  Navigation,
  PanelSection,
  PanelSectionRow,
  ProgressBarWithInfo,
  SliderField,
  ToggleField,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useRef, useState } from "react";
import { appName } from "../appWatcher";
import {
  checkForUpdate,
  installViaDecky,
  prepareUpdate,
  setEnabled,
  setExtras,
  setGlobal,
  setPerApp,
} from "../backend";
import { usePluginState } from "../hooks/usePluginState";
import { setupIntent } from "../setupIntent";
import { t } from "../strings";
import type { PluginState } from "../types";

function goto(path: string) {
  Navigation.Navigate(path);
  Navigation.CloseSideMenus();
}

function statusText(s: PluginState): string {
  if (!s.setup.done) return t.notSetUp;
  if (s.dsp.jack?.paused || (s.hardware.headphones && !s.dsp.active)) return t.pausedHeadphones;
  if (!s.settings.enabled) return `${t.inactive} (Bypass)`;
  return s.dsp.active && s.dsp.verified ? t.active : t.inactive;
}

function labelOf(list: { id: string; label: string }[], id: string): string {
  return list.find((x) => x.id === id)?.label ?? id;
}

export function QuickAccess() {
  const { state, error, refresh } = usePluginState();
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<number | null>(null);
  const gainTimer = useRef<number | null>(null);

  useEffect(() => () => {
    if (gainTimer.current) window.clearTimeout(gainTimer.current);
  }, []);

  if (error) {
    return (
      <PanelSection title={t.status}>
        <PanelSectionRow>
          <Field label="Backend" description={error} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => void refresh()}>{t.refresh}</ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }
  if (!state) {
    return (
      <PanelSection title={t.status}>
        <PanelSectionRow>
          <Field label="…" />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const s = state;
  const resolved = s.runningApp.resolved;
  const appId = s.runningApp.appId;
  const perApp = appId ? s.settings.perApp[appId] : undefined;
  const profileOptions = s.profiles.map((p) => ({ data: p.id, label: p.label }));
  const voicingOptions = s.voicings.map((v) => ({ data: v.id, label: v.label }));
  const activeLabel = s.dsp.active_preset?.profile
    ? `${labelOf(s.profiles, s.dsp.active_preset.profile)} · ${labelOf(s.voicings, s.dsp.active_preset.voicing ?? "")}`
    : "–";

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      toaster.toast({ title: t.title, body: String(e) });
    } finally {
      setBusy(false);
      void refresh();
    }
  };

  const onGain = (value: number) => {
    setPending(value);
    if (gainTimer.current) window.clearTimeout(gainTimer.current);
    gainTimer.current = window.setTimeout(() => {
      void run(() => setExtras({ preGainDb: value }));
      setPending(null);
    }, 700);
  };

  const onInstallUpdate = () =>
    run(async () => {
      const artifact = await prepareUpdate();
      await installViaDecky(artifact);
    });

  return (
    <>
      <PanelSection title={t.status}>
        <PanelSectionRow>
          <Field label={statusText(s)} description={`${activeLabel}${resolved.source === "app" ? ` · ${t.thisGame}` : ""}`} />
        </PanelSectionRow>
        {!s.setup.done && (
          <PanelSectionRow>
            <ButtonItem layout="below" description={t.setupNeeded} onClick={() => { setupIntent.force = false; goto("/ally-dsp/setup"); }}>
              {t.runSetup}
            </ButtonItem>
          </PanelSectionRow>
        )}
        {s.setup.inProgress && s.setup.last && (
          <PanelSectionRow>
            <ProgressBarWithInfo nProgress={s.setup.last.percent} sOperationText={s.setup.last.message} layout="below" bottomSeparator="none" />
          </PanelSectionRow>
        )}
      </PanelSection>

      {s.setup.done && (
        <>
          <PanelSection title={t.sound}>
            <PanelSectionRow>
              <ToggleField label={t.dspEnabled} description={t.dspEnabledDesc} checked={s.settings.enabled} disabled={busy}
                onChange={(v) => void run(() => setEnabled(v))} />
            </PanelSectionRow>
            <PanelSectionRow>
              <DropdownItem label={t.preset} rgOptions={profileOptions} selectedOption={s.settings.global.profile} disabled={busy}
                onChange={(o) => void run(() => setGlobal(o.data, s.settings.global.voicing))} />
            </PanelSectionRow>
            <PanelSectionRow>
              <DropdownItem label={t.voicing} rgOptions={voicingOptions} selectedOption={s.settings.global.voicing} disabled={busy}
                onChange={(o) => void run(() => setGlobal(s.settings.global.profile, o.data))} />
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title={appId ? `${t.thisGame}: ${appName(appId)}` : t.thisGame}>
            {appId ? (
              <>
                <PanelSectionRow>
                  <ToggleField label={t.perGameToggle} checked={!!perApp} disabled={busy}
                    onChange={(v) => void run(() => setPerApp(appId, v
                      ? { profile: resolved.profile, voicing: resolved.voicing, enabled: true, name: appName(appId) }
                      : null))} />
                </PanelSectionRow>
                {perApp && (
                  <>
                    <PanelSectionRow>
                      <DropdownItem label={t.perGamePreset} rgOptions={profileOptions} selectedOption={perApp.profile} disabled={busy}
                        onChange={(o) => void run(() => setPerApp(appId, { ...perApp, profile: o.data }))} />
                    </PanelSectionRow>
                    <PanelSectionRow>
                      <DropdownItem label={t.voicing} rgOptions={voicingOptions} selectedOption={perApp.voicing} disabled={busy}
                        onChange={(o) => void run(() => setPerApp(appId, { ...perApp, voicing: o.data }))} />
                    </PanelSectionRow>
                  </>
                )}
              </>
            ) : (
              <>
                <PanelSectionRow>
                  <Field description={t.noGame} />
                </PanelSectionRow>
                {Object.entries(s.settings.perApp).slice(0, 8).map(([id, entry]) => (
                  <PanelSectionRow key={id}>
                    <ButtonItem layout="below" label={`${entry.name || id}: ${labelOf(s.profiles, entry.profile)} · ${labelOf(s.voicings, entry.voicing)}`}
                      disabled={busy} onClick={() => void run(() => setPerApp(id, null))}>
                      {t.remove}
                    </ButtonItem>
                  </PanelSectionRow>
                ))}
              </>
            )}
          </PanelSection>

          <PanelSection title={t.extras}>
            {s.setup.converting && s.setup.convertLast && (
              <PanelSectionRow>
                <ProgressBarWithInfo nProgress={s.setup.convertLast.percent} sOperationText={`${t.reconverting} ${s.setup.convertLast.message}`} layout="below" bottomSeparator="none" />
              </PanelSectionRow>
            )}
            <PanelSectionRow>
              <ToggleField label={t.autogain} description={t.autogainDesc} checked={s.settings.extras.autogain} disabled={busy || s.setup.converting}
                onChange={(v) => void run(() => setExtras({ autogain: v }))} />
            </PanelSectionRow>
            <PanelSectionRow>
              <ToggleField label={t.dialog} checked={s.settings.extras.dialog} disabled={busy || s.setup.converting}
                onChange={(v) => void run(() => setExtras({ dialog: v }))} />
            </PanelSectionRow>
            <PanelSectionRow>
              <ToggleField label={t.regulator} description={t.regulatorDesc} checked={s.settings.extras.regulator} disabled={busy || s.setup.converting}
                onChange={(v) => void run(() => setExtras({ regulator: v }))} />
            </PanelSectionRow>
            {s.hardware.lv2?.calf && (
              <PanelSectionRow>
                <ToggleField label={t.virtualBass} checked={s.settings.extras.virtualBass} disabled={busy || s.setup.converting}
                  onChange={(v) => void run(() => setExtras({ virtualBass: v }))} />
              </PanelSectionRow>
            )}
            <PanelSectionRow>
              <SliderField label={t.preGain} value={pending ?? s.settings.extras.preGainDb} min={-6} max={6} step={1} showValue valueSuffix=" dB"
                notchCount={13} disabled={busy} onChange={onGain} />
            </PanelSectionRow>
          </PanelSection>
        </>
      )}

      <PanelSection title={t.maintenance}>
        {s.update.updateAvailable ? (
          <PanelSectionRow>
            <ButtonItem layout="below" description={`${t.updateAvailable}: v${s.update.latestVersion} (${t.version} ${s.version})`} disabled={busy}
              onClick={() => void onInstallUpdate()}>
              {t.installUpdate}
            </ButtonItem>
          </PanelSectionRow>
        ) : (
          <PanelSectionRow>
            <ButtonItem layout="below" description={s.update.error ? `${t.updateFailed}: ${s.update.error}` : `${t.upToDate} · ${t.version} ${s.version}`} disabled={busy}
              onClick={() => void run(() => checkForUpdate(true))}>
              {t.checkUpdate}
            </ButtonItem>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => goto("/ally-dsp/diagnostics")}>{t.diagnostics}</ButtonItem>
        </PanelSectionRow>
        {s.setup.done && (
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy || s.setup.inProgress} onClick={() => { setupIntent.force = true; goto("/ally-dsp/setup"); }}>
              {t.rerunSetup}
            </ButtonItem>
          </PanelSectionRow>
        )}
      </PanelSection>
    </>
  );
}
