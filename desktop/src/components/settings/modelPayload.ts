import type { ModelInfo } from '@/types'








export interface Draft extends ModelInfo {
  
  testState?: { status: 'idle' | 'testing' | 'ok' | 'fail'; message?: string }
  
  availableModels?: string[]
  







  apiKeyInput: string
  
  apiKeyMask: string
  
  apiKeyDirty: boolean
  
  apiKeyCleared: boolean
  
  apiKeyRevealed: boolean
}


export interface ModelsPayload {
  default_model: string
  models: Array<Record<string, unknown>>
}













export function modelPayload(list: Draft[], defaultModel: string): ModelsPayload {
  return {
    default_model: defaultModel,
    models: list.map((model) => ({
      id: model.id,
      name: model.name,
      provider: model.provider,
      adapter: model.adapter,
      base_url: model.base_url,
      
      
      
      
      
      
      
      
      
      
      
      
      
      api_key: model.apiKeyCleared ? '' : model.apiKeyInput,
      api_key_unchanged: !model.apiKeyCleared && !model.apiKeyInput,
      clear_api_key: model.apiKeyCleared,
      
      inherit_key_from: model.inherit_key_from ?? '',
      model_name: model.model_name,
      token_limit: model.token_limit,
      supports_tools: model.supports_tools,
      supports_stream: model.supports_stream,
      supports_vision: model.supports_vision,
      supports_reasoning: model.supports_reasoning,
      use_system_proxy: model.use_system_proxy ?? false,
      timeout: model.timeout,
      temperature: model.temperature,
      max_tokens: model.max_tokens,
      enabled: model.enabled,
      is_default: model.is_default,
      tier: model.tier,
      fallback_models: model.fallback_models,
      price_input_per_1m: model.price_input_per_1m,
      price_cached_input_per_1m: model.price_cached_input_per_1m,
      price_output_per_1m: model.price_output_per_1m,
      price_input_per_1m_peak: model.price_input_per_1m_peak ?? null,
      price_output_per_1m_peak: model.price_output_per_1m_peak ?? null,
      price_cached_input_per_1m_peak: model.price_cached_input_per_1m_peak ?? null,
      peak_windows: model.peak_windows ?? [],
    })),
  }
}













export function emptyDraft(overrides: Partial<Draft> = {}): Draft {
  return {
    id: '',
    name: '',
    display_name: '',
    provider: '',
    adapter: 'openai_compat',
    base_url: '',
    api_key: '',
    has_api_key: false,
    model_name: '',
    token_limit: 131072,
    supports_tools: true,
    supports_stream: true,
    supports_vision: false,
    supports_reasoning: true,
    use_system_proxy: false,
    timeout: 120,
    temperature: 0.7,
    max_tokens: null,
    tier: 'standard',
    fallback_models: [],
    enabled: true,
    is_default: false,
    price_input_per_1m: null,
    price_cached_input_per_1m: null,
    price_output_per_1m: null,
    price_input_per_1m_peak: null,
    price_output_per_1m_peak: null,
    price_cached_input_per_1m_peak: null,
    peak_windows: [],
    
    apiKeyInput: '',
    apiKeyMask: '',
    apiKeyDirty: false,
    apiKeyCleared: false,
    apiKeyRevealed: false,
    ...overrides,
  }
}
