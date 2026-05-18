package store

import (
	"context"
	"fmt"
	"strings"
)

func (s *Store) ListMessages(ctx context.Context, sessionID string) ([]Message, error) {
	if _, err := s.GetSession(ctx, sessionID); err != nil {
		return nil, err
	}

	rows, err := s.db.QueryContext(ctx, `
SELECT id, session_id, role, content, provider, model, created_at
FROM messages
WHERE session_id = ?
ORDER BY created_at ASC
`, sessionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	messages := []Message{}
	for rows.Next() {
		var message Message
		if err := rows.Scan(
			&message.ID,
			&message.SessionID,
			&message.Role,
			&message.Content,
			&message.Provider,
			&message.Model,
			&message.CreatedAt,
		); err != nil {
			return nil, err
		}
		messages = append(messages, message)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}
	return messages, nil
}

func (s *Store) CreateMessage(ctx context.Context, sessionID, role, content string) (Message, error) {
	return s.CreateMessageWithMeta(ctx, CreateMessageParams{
		SessionID: sessionID,
		Role:      role,
		Content:   content,
	})
}

func (s *Store) CreateMessageWithMeta(ctx context.Context, params CreateMessageParams) (Message, error) {
	role := strings.TrimSpace(params.Role)
	content := strings.TrimSpace(params.Content)
	if !validRole(role) {
		return Message{}, fmt.Errorf("invalid role")
	}
	if content == "" {
		return Message{}, fmt.Errorf("content is required")
	}

	if _, err := s.GetSession(ctx, params.SessionID); err != nil {
		return Message{}, err
	}

	now := timestamp()
	message := Message{
		ID:        newID("msg"),
		SessionID: params.SessionID,
		Role:      role,
		Content:   content,
		Provider:  params.Provider,
		Model:     params.Model,
		CreatedAt: now,
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return Message{}, err
	}
	defer tx.Rollback()

	_, err = tx.ExecContext(ctx, `
INSERT INTO messages (id, session_id, role, content, provider, model, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
`, message.ID, message.SessionID, message.Role, message.Content, message.Provider, message.Model, message.CreatedAt)
	if err != nil {
		return Message{}, err
	}

	_, err = tx.ExecContext(ctx, `
UPDATE sessions
SET updated_at = ?
WHERE id = ?
`, now, params.SessionID)
	if err != nil {
		return Message{}, err
	}

	if err := tx.Commit(); err != nil {
		return Message{}, err
	}
	return message, nil
}

func validRole(role string) bool {
	switch role {
	case "user", "assistant", "system", "tool":
		return true
	default:
		return false
	}
}
