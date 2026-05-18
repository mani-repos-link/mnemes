package config

import (
	"bufio"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type Config struct {
	Addr            string
	FrontendOrigins []string
	DatabaseURL     string
	Chat            ChatConfig
	Context         ContextConfig
}

type ChatConfig struct {
	Provider           string
	OpenRouterAPIKey   string
	OpenRouterBaseURL  string
	HuggingFaceAPIKey  string
	HuggingFaceBaseURL string
	Model              string
}

type ContextConfig struct {
	RecentMessageLimit int
	MaxResponseTokens  int
}

func Load() Config {
	loadDotEnvUpwards(".env")

	return Config{
		Addr:            env("APP_ADDR", ":8080"),
		FrontendOrigins: splitCSV(env("FRONTEND_ORIGINS", env("FRONTEND_ORIGIN", "http://localhost:5173"))),
		DatabaseURL:     env("DATABASE_URL", "file:../../data/chatbot.sqlite"),
		Chat:            loadChatConfig(),
		Context: ContextConfig{
			RecentMessageLimit: intEnv("RECENT_MESSAGE_LIMIT", 20),
			MaxResponseTokens:  intEnv("MAX_RESPONSE_TOKENS", 2000),
		},
	}
}

func loadChatConfig() ChatConfig {
	provider := strings.ToLower(env("DEFAULT_CHAT_PROVIDER", "openrouter"))
	return ChatConfig{
		Provider:           provider,
		OpenRouterAPIKey:   env("OPENROUTER_API_KEY", ""),
		OpenRouterBaseURL:  strings.TrimRight(env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"), "/"),
		HuggingFaceAPIKey:  env("HUGGINGFACE_API_KEY", env("HF_TOKEN", "")),
		HuggingFaceBaseURL: strings.TrimRight(env("HUGGINGFACE_BASE_URL", "https://router.huggingface.co/v1"), "/"),
		Model:              chatModel(provider),
	}
}

func chatModel(provider string) string {
	if value := env("CHAT_MODEL", ""); value != "" {
		return value
	}

	switch provider {
	case "huggingface":
		return env("HUGGINGFACE_CHAT_MODEL", "")
	default:
		return env("OPENROUTER_CHAT_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
	}
}

func splitCSV(value string) []string {
	parts := strings.Split(value, ",")
	values := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			values = append(values, part)
		}
	}
	return values
}

func env(key, fallback string) string {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	return value
}

func intEnv(key string, fallback int) int {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}

	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func loadDotEnvUpwards(filename string) {
	dir, err := os.Getwd()
	if err != nil {
		return
	}

	for {
		path := filepath.Join(dir, filename)
		if _, err := os.Stat(path); err == nil {
			loadDotEnv(path)
			return
		}

		parent := filepath.Dir(dir)
		if parent == dir {
			return
		}
		dir = parent
	}
}

func loadDotEnv(path string) {
	file, err := os.Open(path)
	if err != nil {
		return
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		key, value, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}

		key = strings.TrimSpace(key)
		value = strings.Trim(strings.TrimSpace(value), `"'`)
		if key != "" && os.Getenv(key) == "" {
			_ = os.Setenv(key, value)
		}
	}
}
