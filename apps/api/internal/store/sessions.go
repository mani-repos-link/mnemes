package store

import (
	"context"
	"database/sql"
	"errors"
	"strings"
)

func (s *Store) ListSessions(ctx context.Context) ([]Session, error) {
	rows, err := s.db.QueryContext(ctx, `
SELECT id, title, created_at, updated_at
FROM sessions
WHERE archived_at IS NULL
ORDER BY updated_at DESC
`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	sessions := []Session{}
	for rows.Next() {
		var session Session
		if err := rows.Scan(&session.ID, &session.Title, &session.CreatedAt, &session.UpdatedAt); err != nil {
			return nil, err
		}
		sessions = append(sessions, session)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}
	return sessions, nil
}

func (s *Store) CreateSession(ctx context.Context, title string) (Session, error) {
	now := timestamp()
	if strings.TrimSpace(title) == "" {
		title = "New chat"
	}

	session := Session{
		ID:        newID("ses"),
		Title:     strings.TrimSpace(title),
		CreatedAt: now,
		UpdatedAt: now,
	}

	_, err := s.db.ExecContext(ctx, `
INSERT INTO sessions (id, title, created_at, updated_at)
VALUES (?, ?, ?, ?)
`, session.ID, session.Title, session.CreatedAt, session.UpdatedAt)
	return session, err
}

func (s *Store) GetSession(ctx context.Context, sessionID string) (Session, error) {
	var session Session
	err := s.db.QueryRowContext(ctx, `
SELECT id, title, created_at, updated_at
FROM sessions
WHERE id = ? AND archived_at IS NULL
`, sessionID).Scan(&session.ID, &session.Title, &session.CreatedAt, &session.UpdatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return Session{}, ErrNotFound
	}
	return session, err
}

func (s *Store) DeleteSession(ctx context.Context, sessionID string) error {
	now := timestamp()
	result, err := s.db.ExecContext(ctx, `
UPDATE sessions
SET archived_at = ?, updated_at = ?
WHERE id = ? AND archived_at IS NULL
`, now, now, sessionID)
	if err != nil {
		return err
	}

	affected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if affected == 0 {
		return ErrNotFound
	}
	return nil
}
