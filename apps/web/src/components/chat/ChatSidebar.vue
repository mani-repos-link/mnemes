<script setup lang="ts">
import type { Session } from "../../types/chat";
import { formatTime } from "../../utils/date";

defineProps<{
  loading: boolean;
  selectedSessionId: string | null;
  sessions: Session[];
}>();

defineEmits<{
  deleteSession: [sessionId: string];
  newSession: [];
  selectSession: [sessionId: string];
}>();
</script>

<template>
  <aside class="chat-sidebar">
    <div class="chat-sidebar__header">
      <div>
        <p class="eyebrow">Local</p>
        <h1 class="sidebar-title">Chatbot</h1>
      </div>
      <button class="icon-button" type="button" title="New chat" @click="$emit('newSession')">
        +
      </button>
    </div>

    <div class="session-list" aria-label="Chat sessions">
      <div
        v-for="session in sessions"
        :key="session.id"
        class="session-row"
        :class="{ 'session-button--active': session.id === selectedSessionId }"
      >
        <button class="session-button" type="button" @click="$emit('selectSession', session.id)">
          <span>{{ session.title }}</span>
          <small>{{ formatTime(session.updatedAt) }}</small>
        </button>
        <button
          class="session-delete"
          type="button"
          title="Delete chat"
          @click.stop="$emit('deleteSession', session.id)"
        >
          ×
        </button>
      </div>

      <p v-if="!loading && sessions.length === 0" class="empty-copy">No sessions yet.</p>
    </div>
  </aside>
</template>
