package store

import (
	"crypto/rand"
	"encoding/hex"
	"time"
)

func timestamp() string {
	return time.Now().UTC().Format(time.RFC3339Nano)
}

func newID(prefix string) string {
	var bytes [12]byte
	if _, err := rand.Read(bytes[:]); err != nil {
		panic(err)
	}
	return prefix + "_" + hex.EncodeToString(bytes[:])
}
