package provider

import (
	"context"

	"github.com/manpreet/chatbot/apps/api/internal/store"
)

type ChatCompleter interface {
	Complete(ctx context.Context, history []store.Message, maxResponseTokens int) (ChatResult, error)
}

type ChatResult struct {
	Content  string
	Provider string
	Model    string
}
