package main

import (
	"context"
	"log"
	"net/http"
	"strconv"
	"strings"

	"github.com/manpreet/chatbot/apps/api/internal/config"
	"github.com/manpreet/chatbot/apps/api/internal/httpapi"
	"github.com/manpreet/chatbot/apps/api/internal/provider"
	"github.com/manpreet/chatbot/apps/api/internal/store"
)

func main() {
	cfg := config.Load()
	log.Printf(
		"config loaded addr=%s database=%s chat_provider=%s chat_model=%s openrouter_base_url=%s openrouter_key=%s huggingface_base_url=%s huggingface_key=%s frontend_origins=%s recent_limit=%d max_response_tokens=%d",
		cfg.Addr,
		cfg.DatabaseURL,
		cfg.Chat.Provider,
		cfg.Chat.Model,
		cfg.Chat.OpenRouterBaseURL,
		redactedKey(cfg.Chat.OpenRouterAPIKey),
		cfg.Chat.HuggingFaceBaseURL,
		redactedKey(cfg.Chat.HuggingFaceAPIKey),
		strings.Join(cfg.FrontendOrigins, ","),
		cfg.Context.RecentMessageLimit,
		cfg.Context.MaxResponseTokens,
	)

	store, err := store.Open(context.Background(), cfg.DatabaseURL)
	if err != nil {
		log.Fatal(err)
	}
	defer store.Close()

	chatClient := provider.NewChatClient(cfg.Chat)

	server := &http.Server{
		Addr:    cfg.Addr,
		Handler: httpapi.NewRouter(cfg.FrontendOrigins, store, chatClient, cfg.Context),
	}

	log.Printf("api listening on %s", cfg.Addr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}

func redactedKey(value string) string {
	if value == "" {
		return "missing"
	}
	if len(value) <= 10 {
		return "present-too-short"
	}
	return value[:7] + "..." + value[len(value)-4:] + " len=" + strconv.Itoa(len(value))
}
