// SteamClient, appStore and SteamUIStore are declared by @decky/ui; we only add Decky's backend router.
interface Window {
  DeckyBackend?: { callable: <T extends any[] = any[], R = any>(route: string) => (...args: T) => Promise<R> };
}
