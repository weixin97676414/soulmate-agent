






































export function filterDiscoveredModels(baseUrl: string, models: string[]): string[] {
  if (!/siliconflow/i.test(baseUrl)) return models
  
  
  
  
  const only = models.filter((name) => /deepseek/i.test(name) && /flash/i.test(name))
  return only.length > 0 ? only : models
}
