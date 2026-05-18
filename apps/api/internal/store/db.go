package store

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"strings"

	_ "github.com/mattn/go-sqlite3"
)

type Store struct {
	db *sql.DB
}

func Open(ctx context.Context, databaseURL string) (*Store, error) {
	if err := ensureSQLiteDir(databaseURL); err != nil {
		return nil, err
	}

	db, err := sql.Open("sqlite3", normalizeSQLiteDSN(databaseURL))
	if err != nil {
		return nil, err
	}

	db.SetMaxOpenConns(1)

	if err := db.PingContext(ctx); err != nil {
		db.Close()
		return nil, err
	}

	store := &Store{db: db}
	if err := store.Migrate(ctx); err != nil {
		db.Close()
		return nil, err
	}

	return store, nil
}

func (s *Store) Close() error {
	return s.db.Close()
}

func normalizeSQLiteDSN(databaseURL string) string {
	if strings.HasPrefix(databaseURL, "file:") {
		return databaseURL + "?_foreign_keys=on"
	}
	return databaseURL
}

func ensureSQLiteDir(databaseURL string) error {
	path := strings.TrimPrefix(databaseURL, "file:")
	if path == databaseURL || path == "" || path == ":memory:" {
		return nil
	}

	if index := strings.Index(path, "?"); index >= 0 {
		path = path[:index]
	}

	dir := filepath.Dir(path)
	if dir == "." || dir == "" {
		return nil
	}
	return os.MkdirAll(dir, 0o755)
}
