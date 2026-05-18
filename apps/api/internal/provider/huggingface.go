package provider

import "github.com/manpreet/chatbot/apps/api/internal/config"

func NewHuggingFaceClient(cfg config.ChatConfig) ChatCompleter {
	return newCompatibleClient(
		"huggingface",
		"huggingface",
		cfg.HuggingFaceBaseURL,
		cfg.HuggingFaceAPIKey,
		cfg.Model,
	)
}
