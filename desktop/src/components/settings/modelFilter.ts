


















































export function filterDiscoveredModels(baseUrl: string, models: string[]): string[] {
  if (!/siliconflow/i.test(baseUrl)) return models
  const isFlash = (name: string) => /deepseek/i.test(name) && /flash/i.test(name)
  return [...models].sort((a, b) => Number(isFlash(b)) - Number(isFlash(a)))
}
