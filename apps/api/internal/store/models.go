package store

import "errors"

var ErrNotFound = errors.New("not found")

type Session struct {
	ID        string `json:"id"`
	Title     string `json:"title"`
	CreatedAt string `json:"createdAt"`
	UpdatedAt string `json:"updatedAt"`
}

type Message struct {
	ID        string  `json:"id"`
	SessionID string  `json:"sessionId"`
	Role      string  `json:"role"`
	Content   string  `json:"content"`
	Provider  *string `json:"provider,omitempty"`
	Model     *string `json:"model,omitempty"`
	CreatedAt string  `json:"createdAt"`
}

type CreateMessageParams struct {
	SessionID string
	Role      string
	Content   string
	Provider  *string
	Model     *string
}
