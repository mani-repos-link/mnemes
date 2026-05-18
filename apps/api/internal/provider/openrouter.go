package provider

import "github.com/manpreet/chatbot/apps/api/internal/config"

func NewOpenRouterClient(cfg config.ChatConfig) ChatCompleter {
	return newCompatibleClient(
		"openrouter",
		"openrouter",
		cfg.OpenRouterBaseURL,
		cfg.OpenRouterAPIKey,
		cfg.Model,
	)
}
