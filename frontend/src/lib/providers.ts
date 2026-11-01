/** Provider presets: base URLs and key pages checked against each provider's official documentation. */
export interface Provider {
  id: string
  label: string
  baseUrl: string // '' = the visitor types it (Custom)
  keyUrl: string
  keyLabel: string
  tier: string
  /** Short honest label shown on the provider chip */
  note: string
  noteTone: 'free' | 'plain'
}

export const PROVIDERS: Provider[] = [
  {
    id: 'groq',
    note: 'free tier, tested here',
    noteTone: 'free',
    label: 'Groq',
    baseUrl: 'https://api.groq.com/openai/v1',
    keyUrl: 'https://console.groq.com/keys',
    keyLabel: 'console.groq.com/keys',
    tier: 'Has a free plan (a payment method is only needed to upgrade to the paid plan). Limits apply.',
  },
  {
    id: 'gemini',
    note: 'free tier, strict rate limits',
    noteTone: 'free',
    label: 'Google Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    keyUrl: 'https://aistudio.google.com/apikey',
    keyLabel: 'aistudio.google.com/apikey',
    tier: 'Has a free tier with limited models and limits. Free-tier data may be used to improve Google products.',
  },
  {
    id: 'openrouter',
    note: 'free models are often rate-limited',
    noteTone: 'free',
    label: 'OpenRouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    keyUrl: 'https://openrouter.ai/keys',
    keyLabel: 'openrouter.ai/keys',
    tier: 'Models whose name ends in ":free" cost nothing but have low daily limits.',
  },
  {
    id: 'openai',
    note: 'paid, bring your own key',
    noteTone: 'plain',
    label: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    keyUrl: 'https://platform.openai.com/api-keys',
    keyLabel: 'platform.openai.com/api-keys',
    tier: 'Paid usage. Check OpenAI’s pricing page for current credit rules.',
  },
  {
    id: 'custom',
    note: 'any OpenAI-compatible endpoint',
    noteTone: 'plain',
    label: 'Custom',
    baseUrl: '',
    keyUrl: '',
    keyLabel: '',
    tier: 'Any OpenAI-compatible service. The address must start with https://.',
  },
]

export const GNANI_KEY_URL = 'https://app.gnani.ai/voice'
