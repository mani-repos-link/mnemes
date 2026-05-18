<script setup lang="ts">
import type { Message } from "../../types/chat";
import { formatTime } from "../../utils/date";

defineProps<{
  messages: Message[];
}>();

function messageClass(message: Message) {
  if (message.role === "user") {
    return "message-card--user";
  }
  if (message.role === "assistant") {
    return "message-card--assistant";
  }
  return "message-card--system";
}
</script>

<template>
  <div class="message-list">
    <div v-if="messages.length === 0" class="empty-state">
      <h3>Start a local conversation</h3>
      <p>Messages are saved through the Go API into the local SQLite database.</p>
    </div>

    <article
      v-for="message in messages"
      :key="message.id"
      class="message-card"
      :class="messageClass(message)"
    >
      <div class="message-card__meta">
        <span>{{ message.role }}</span>
        <small v-if="message.model">{{ message.model }}</small>
      </div>
      <p>{{ message.content }}</p>
      <small>{{ formatTime(message.createdAt) }}</small>
    </article>
  </div>
</template>
