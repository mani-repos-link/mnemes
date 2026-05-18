package provider

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/manpreet/chatbot/apps/api/internal/store"
)

type openAICompatibleClient struct {
	apiKey     string
	baseURL    string
	logPrefix  string
	model      string
	provider   string
	httpClient *http.Client
}

type chatRequest struct {
	Model               string        `json:"model"`
	Messages            []chatMessage `json:"messages"`
	MaxCompletionTokens int           `json:"max_completion_tokens,omitempty"`
	Temperature         float64       `json:"temperature"`
	Stream              bool          `json:"stream"`
}

type chatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type chatResponse struct {
	Model   string `json:"model"`
	Choices []struct {
		Message struct {
			Role    string `json:"role"`
			Content string `json:"content"`
		} `json:"message"`
	} `json:"choices"`
	Error *struct {
		Message string `json:"message"`
		Code    any    `json:"code"`
	} `json:"error"`
}

func newCompatibleClient(providerName, logPrefix, baseURL, apiKey, model string) *openAICompatibleClient {
	return &openAICompatibleClient{
		apiKey:    apiKey,
		baseURL:   strings.TrimRight(baseURL, "/"),
		logPrefix: logPrefix,
		model:     model,
		provider:  providerName,
		httpClient: &http.Client{
			Timeout: 120 * time.Second,
		},
	}
}

func (c *openAICompatibleClient) Complete(ctx context.Context, history []store.Message, maxResponseTokens int) (ChatResult, error) {
	start := time.Now()
	if c.apiKey == "" {
		return ChatResult{}, fmt.Errorf("%s API key is required", c.provider)
	}
	if c.model == "" {
		return ChatResult{}, fmt.Errorf("%s chat model is required", c.provider)
	}

	messages := buildMessages(history)
	body, err := json.Marshal(chatRequest{
		Model:               c.model,
		Messages:            messages,
		MaxCompletionTokens: maxResponseTokens,
		Temperature:         0.7,
		Stream:              false,
	})
	if err != nil {
		return ChatResult{}, err
	}

	endpoint := c.baseURL + "/chat/completions"
	log.Printf(
		"%s request endpoint=%s model=%s messages=%d max_completion_tokens=%d body_bytes=%d",
		c.logPrefix,
		endpoint,
		c.model,
		len(messages),
		maxResponseTokens,
		len(body),
	)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return ChatResult{}, err
	}
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("HTTP-Referer", "http://localhost:5173")
	req.Header.Set("X-Title", "Local Self-Hosted Chatbot")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		log.Printf("%s transport_error duration=%s error=%v", c.logPrefix, time.Since(start), err)
		return ChatResult{}, err
	}
	defer resp.Body.Close()

	responseBody, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return ChatResult{}, err
	}
	log.Printf(
		"%s response status=%d duration=%s response_bytes=%d",
		c.logPrefix,
		resp.StatusCode,
		time.Since(start),
		len(responseBody),
	)

	var parsed chatResponse
	if err := json.Unmarshal(responseBody, &parsed); err != nil {
		log.Printf("%s invalid_json body_preview=%q", c.logPrefix, preview(responseBody, 400))
		return ChatResult{}, fmt.Errorf("%s returned invalid JSON: %w", c.provider, err)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		if parsed.Error != nil && parsed.Error.Message != "" {
			log.Printf("%s error status=%d message=%q code=%v", c.logPrefix, resp.StatusCode, parsed.Error.Message, parsed.Error.Code)
			return ChatResult{}, fmt.Errorf("%s error: %s", c.provider, parsed.Error.Message)
		}
		log.Printf("%s error status=%d body_preview=%q", c.logPrefix, resp.StatusCode, preview(responseBody, 400))
		return ChatResult{}, fmt.Errorf("%s error: %s", c.provider, resp.Status)
	}

	if len(parsed.Choices) == 0 {
		return ChatResult{}, fmt.Errorf("%s returned no choices", c.provider)
	}

	content := strings.TrimSpace(parsed.Choices[0].Message.Content)
	if content == "" {
		log.Printf("%s empty_message model=%s choices=%d", c.logPrefix, parsed.Model, len(parsed.Choices))
		return ChatResult{}, fmt.Errorf("%s returned an empty message", c.provider)
	}

	model := parsed.Model
	if model == "" {
		model = c.model
	}

	return ChatResult{
		Content:  content,
		Provider: c.provider,
		Model:    model,
	}, nil
}

func buildMessages(history []store.Message) []chatMessage {
	messages := []chatMessage{
		{
			Role:    "system",
			Content: "You are a helpful assistant in a local, self-hosted chatbot. Answer clearly and concisely.",
		},
	}

	for _, message := range history {
		if message.Role == "user" || message.Role == "assistant" || message.Role == "system" {
			messages = append(messages, chatMessage{
				Role:    message.Role,
				Content: message.Content,
			})
		}
	}
	return messages
}

func preview(value []byte, limit int) string {
	if len(value) <= limit {
		return string(value)
	}
	return string(value[:limit]) + "...(truncated)"
}
