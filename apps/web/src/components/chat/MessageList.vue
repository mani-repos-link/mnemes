<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { Message } from "../../types/chat";
import { formatTime } from "../../utils/date";

const props = defineProps<{
  messages: Message[];
  sending: boolean;
  sessionId: string | null;
}>();

const INITIAL_MESSAGE_COUNT = 80;
const MESSAGE_BATCH_SIZE = 40;

const messageListElement = ref<HTMLElement | null>(null);
const visibleMessageCount = ref(INITIAL_MESSAGE_COUNT);

const hiddenMessageCount = computed(() =>
  Math.max(props.messages.length - visibleMessageCount.value, 0),
);

const visibleMessages = computed(() => props.messages.slice(-visibleMessageCount.value));

function messageClass(message: Message) {
  if (message.role === "user") {
    return "message-card--user";
  }
  if (message.role === "assistant") {
    return "message-card--assistant";
  }
  return "message-card--system";
}

async function loadEarlierMessages() {
  const element = messageListElement.value;
  const previousScrollHeight = element?.scrollHeight ?? 0;

  visibleMessageCount.value = Math.min(
    visibleMessageCount.value + MESSAGE_BATCH_SIZE,
    props.messages.length,
  );

  await nextTick();
  if (element) {
    element.scrollTop += element.scrollHeight - previousScrollHeight;
  }
}

function scrollToLatest() {
  const element = messageListElement.value;
  if (!element) {
    return;
  }

  element.scrollTop = element.scrollHeight;
}

watch(
  () => props.sessionId,
  async () => {
    visibleMessageCount.value = INITIAL_MESSAGE_COUNT;
    await nextTick();
    scrollToLatest();
  },
);

watch(
  () => [props.messages.length, props.sending],
  async () => {
    await nextTick();
    scrollToLatest();
  },
);
</script>

<template>
  <div ref="messageListElement" class="message-list">
    <div v-if="messages.length === 0" class="empty-state">
      <h3>Start a local conversation</h3>
      <p>Messages are saved through the Go API into the local SQLite database.</p>
    </div>

    <button
      v-if="hiddenMessageCount > 0"
      class="message-history-button"
      type="button"
      @click="loadEarlierMessages"
    >
      Load {{ Math.min(hiddenMessageCount, MESSAGE_BATCH_SIZE) }} earlier messages
    </button>

    <article
      v-for="message in visibleMessages"
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

    <article v-if="sending" class="message-card message-card--assistant message-card--pending">
      <div class="message-card__meta">
        <span>assistant</span>
      </div>
      <div class="typing-indicator" aria-label="Assistant is thinking">
        <span />
        <span />
        <span />
      </div>
    </article>
  </div>
</template>

<style scoped>
.message-list {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: 0.875rem;
  overflow-y: auto;
  padding: 1rem;
}

.empty-state {
  margin: auto;
  max-width: 36rem;
  text-align: center;
  color: var(--app-muted);
}

.empty-state h3 {
  font-size: 1.125rem;
  line-height: 1.75rem;
  font-weight: 600;
  color: var(--app-ink);
}

.empty-state p {
  margin-top: 0.5rem;
  line-height: 1.5rem;
}

.message-history-button {
  align-self: center;
  border: 1px solid var(--app-line);
  border-radius: 999px;
  padding: 0.375rem 0.75rem;
  background: var(--app-panel);
  color: var(--app-muted);
  font-size: 0.8125rem;
  font-weight: 700;
}

.message-history-button:hover {
  background: var(--app-raised);
  color: var(--app-ink);
}

.message-card {
  display: grid;
  width: 100%;
  max-width: 48rem;
  gap: 0.5rem;
  border: 1px solid;
  border-radius: 0.5rem;
  padding: 0.875rem 1rem;
  line-height: 1.5rem;
  white-space: pre-wrap;
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.06);
}

.message-card--user {
  align-self: flex-end;
  background: var(--app-mint-50);
  border-color: var(--app-mint-300);
}

.message-card--assistant {
  align-self: flex-start;
  background: var(--app-panel);
  border-color: var(--app-line);
}

.message-card--system {
  align-self: flex-start;
  background: var(--app-subtle);
  border-color: var(--app-line);
}

.message-card--pending {
  min-width: 8rem;
}

.message-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  column-gap: 0.5rem;
  row-gap: 0.25rem;
  white-space: normal;
}

.message-card__meta span {
  color: var(--app-meta);
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.025em;
  text-transform: uppercase;
}

.message-card__meta small,
.message-card small {
  overflow: hidden;
  color: var(--app-muted);
  font-size: 0.75rem;
  line-height: 1rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.typing-indicator {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.typing-indicator span {
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 999px;
  background: var(--app-muted);
  animation: typing-pulse 1s infinite ease-in-out;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 120ms;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 240ms;
}

@keyframes typing-pulse {
  0%,
  80%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }

  40% {
    opacity: 1;
    transform: translateY(-0.125rem);
  }
}

@media (min-width: 48rem) {
  .message-list {
    padding: 1.5rem;
  }
}
</style>
