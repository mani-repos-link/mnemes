package httpapi

import (
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"net/url"
	"time"

	"github.com/manpreet/chatbot/apps/api/internal/config"
	"github.com/manpreet/chatbot/apps/api/internal/provider"
	"github.com/manpreet/chatbot/apps/api/internal/store"
)

type API struct {
	store      *store.Store
	chatClient provider.ChatCompleter
	context    config.ContextConfig
}

type createSessionRequest struct {
	Title string `json:"title"`
}

type createMessageRequest struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

func NewRouter(
	frontendOrigins []string,
	store *store.Store,
	chatClient provider.ChatCompleter,
	contextConfig config.ContextConfig,
) http.Handler {
	api := API{
		store:      store,
		chatClient: chatClient,
		context:    contextConfig,
	}
	mux := http.NewServeMux()

	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	mux.HandleFunc("GET /api/providers", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"chat":      []string{"openrouter"},
			"embedding": []string{"huggingface"},
		})
	})

	mux.HandleFunc("GET /api/sessions", api.listSessions)
	mux.HandleFunc("POST /api/sessions", api.createSession)
	mux.HandleFunc("DELETE /api/sessions/{sessionID}", api.deleteSession)
	mux.HandleFunc("GET /api/sessions/{sessionID}/messages", api.listMessages)
	mux.HandleFunc("POST /api/sessions/{sessionID}/messages", api.createMessage)

	return cors(frontendOrigins, mux)
}

func (a API) listSessions(w http.ResponseWriter, r *http.Request) {
	sessions, err := a.store.ListSessions(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"sessions": sessions})
}

func (a API) createSession(w http.ResponseWriter, r *http.Request) {
	var request createSessionRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	session, err := a.store.CreateSession(r.Context(), request.Title)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"session": session})
}

func (a API) deleteSession(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("sessionID")
	if err := a.store.DeleteSession(r.Context(), sessionID); errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "session not found")
		return
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	w.WriteHeader(http.StatusNoContent)
	log.Printf("session deleted session_id=%s", sessionID)
}

func (a API) listMessages(w http.ResponseWriter, r *http.Request) {
	messages, err := a.store.ListMessages(r.Context(), r.PathValue("sessionID"))
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "session not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"messages": messages})
}

func (a API) createMessage(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	var request createMessageRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	sessionID := r.PathValue("sessionID")
	log.Printf(
		"message create start session_id=%s role=%s content_chars=%d",
		sessionID,
		request.Role,
		len(request.Content),
	)
	message, err := a.store.CreateMessage(r.Context(), sessionID, request.Role, request.Content)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "session not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	messages := []store.Message{message}
	if request.Role == "user" {
		history, err := a.store.ListMessages(r.Context(), sessionID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}

		if limit := a.context.RecentMessageLimit; limit > 0 && len(history) > limit {
			history = history[len(history)-limit:]
		}
		log.Printf("message create invoking_chat session_id=%s history_messages=%d", sessionID, len(history))

		result, err := a.chatClient.Complete(r.Context(), history, a.context.MaxResponseTokens)
		if err != nil {
			log.Printf("message create chat_error session_id=%s duration=%s error=%v", sessionID, time.Since(start), err)
			writeError(w, http.StatusBadGateway, err.Error())
			return
		}
		log.Printf(
			"message create chat_success session_id=%s provider=%s model=%s content_chars=%d",
			sessionID,
			result.Provider,
			result.Model,
			len(result.Content),
		)

		assistantMessage, err := a.store.CreateMessageWithMeta(r.Context(), store.CreateMessageParams{
			SessionID: sessionID,
			Role:      "assistant",
			Content:   result.Content,
			Provider:  &result.Provider,
			Model:     &result.Model,
		})
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		messages = append(messages, assistantMessage)
	}

	writeJSON(w, http.StatusCreated, map[string]any{
		"message":  message,
		"messages": messages,
	})
	log.Printf("message create done session_id=%s returned_messages=%d duration=%s", sessionID, len(messages), time.Since(start))
}

func cors(allowedOrigins []string, next http.Handler) http.Handler {
	allowed := map[string]struct{}{}
	for _, origin := range allowedOrigins {
		allowed[origin] = struct{}{}
	}

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if origin := allowedOrigin(r.Header.Get("Origin"), allowed); origin != "" {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Vary", "Origin")
		}
		w.Header().Set("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type,Authorization")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}

		next.ServeHTTP(w, r)
	})
}

func allowedOrigin(origin string, allowed map[string]struct{}) string {
	if origin == "" {
		return ""
	}

	if _, ok := allowed[origin]; ok {
		return origin
	}

	parsed, err := url.Parse(origin)
	if err != nil {
		return ""
	}

	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return ""
	}

	switch parsed.Hostname() {
	case "localhost", "127.0.0.1", "::1":
		return origin
	default:
		return ""
	}
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(value); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
}

func readJSON(r *http.Request, value any) error {
	defer r.Body.Close()
	return json.NewDecoder(r.Body).Decode(value)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}
