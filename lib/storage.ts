// Centralized localStorage keys for openBIMForge quota tracking and settings.

export const STORAGE_KEYS = {
    // Quota tracking
    requestCount: "openbimforge-request-count",
    requestDate: "openbimforge-request-date",
    tokenCount: "openbimforge-token-count",
    tokenDate: "openbimforge-token-date",
    tpmCount: "openbimforge-tpm-count",
    tpmMinute: "openbimforge-tpm-minute",

    // Settings
    accessCode: "openbimforge-access-code",
    accessCodeRequired: "openbimforge-access-code-required",
    aiProvider: "openbimforge-ai-provider",
    aiBaseUrl: "openbimforge-ai-base-url",
    aiApiKey: "openbimforge-ai-api-key",
    aiModel: "openbimforge-ai-model",

    // Multi-model configuration
    modelConfigs: "openbimforge-model-configs",
    selectedModelId: "openbimforge-selected-model-id",
    showUnvalidatedModels: "openbimforge-show-unvalidated-models",

    // Chat input preferences
    sendShortcut: "openbimforge-send-shortcut",

    // Custom system message
    customSystemMessage: "openbimforge-custom-system-message",

    // BIM clarification loop
    bimModeEnabled: "openbimforge-bim-mode-enabled",
    mepModeEnabled: "openbimforge-mep-mode-enabled",
    // Per-agent model specialisation (optional). Each value is a JSON blob
    // {provider, modelId, baseUrl, apiKey}. When empty the agent falls back
    // to the main model.
    architectAgentOverride: "openbimforge-agent-architect",
    constructorAgentOverride: "openbimforge-agent-constructor",
    checkerAgentOverride: "openbimforge-agent-checker",
    clarifyUseSeparateModel: "openbimforge-clarify-use-separate-model",
    clarifyProvider: "openbimforge-clarify-provider",
    clarifyBaseUrl: "openbimforge-clarify-base-url",
    clarifyApiKey: "openbimforge-clarify-api-key",
    clarifyModel: "openbimforge-clarify-model",
    clarifyProfiles: "openbimforge-clarify-profiles",
    clarifyActiveProfileId: "openbimforge-clarify-active-profile-id",
    clarifyLanguage: "openbimforge-clarify-language",
} as const
