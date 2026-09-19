// Decky's backend router; SteamClient, appStore and SteamUIStore come from @decky/ui.
interface Window {
  DeckyBackend?: { callable: <T extends any[] = any[], R = any>(route: string) => (...args: T) => Promise<R> };
}
