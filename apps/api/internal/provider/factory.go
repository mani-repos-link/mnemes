package provider

import (
	"context"
	"fmt"

	"github.com/manpreet/chatbot/apps/api/internal/config"
	"github.com/manpreet/chatbot/apps/api/internal/store"
)

func NewChatClient(cfg config.ChatConfig) ChatCompleter {
	switch cfg.Provider {
	case "openrouter":
		return NewOpenRouterClient(cfg)
	case "huggingface":
		return NewHuggingFaceClient(cfg)
	default:
		return unsupportedClient{provider: cfg.Provider}
	}
}

type unsupportedClient struct {
	provider string
}

func (c unsupportedClient) Complete(_ context.Context, _ []store.Message, _ int) (ChatResult, error) {
	return ChatResult{}, fmt.Errorf("unsupported chat provider %q", c.provider)
}
