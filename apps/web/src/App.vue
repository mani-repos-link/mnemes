<script setup lang="ts">
import ChatComposer from "./components/chat/ChatComposer.vue";
import ChatHeader from "./components/chat/ChatHeader.vue";
import ChatSidebar from "./components/chat/ChatSidebar.vue";
import MessageList from "./components/chat/MessageList.vue";
import { useChat } from "./composables/useChat";
import { useTheme } from "./composables/useTheme";

const chat = useChat();
const theme = useTheme();
</script>

<template>
  <main class="app-shell">
    <ChatSidebar
      :loading="chat.loading.value"
      :selected-session-id="chat.selectedSessionId.value"
      :sessions="chat.sessions.value"
      @delete-session="chat.deleteSession"
      @new-session="chat.startSession"
      @select-session="chat.selectSession"
    />

    <section class="chat-pane" aria-label="Active chat">
      <ChatHeader
        :active-theme="theme.appliedTheme.value"
        :session="chat.activeSession.value"
        @toggle-theme="theme.toggleTheme"
      />
      <MessageList
        :messages="chat.messages.value"
        :sending="chat.sending.value"
        :session-id="chat.selectedSessionId.value"
      />

      <p v-if="chat.error.value" class="error-banner">
        {{ chat.error.value }}
      </p>

      <ChatComposer :sending="chat.sending.value" @send="chat.sendMessage" />
    </section>
  </main>
</template>

<style scoped>
.app-shell {
  display: grid;
  min-height: 100svh;
  background: var(--app-shell);
  color: var(--app-ink);
}

.chat-pane {
  display: grid;
  min-width: 0;
  min-height: 0;
  grid-template-rows: auto minmax(0, 1fr) auto auto;
  overflow: hidden;
}

.error-banner {
  margin: 0 1rem 0.75rem;
  border: 1px solid var(--app-danger-300);
  border-radius: 0.5rem;
  padding: 0.625rem 0.75rem;
  background: var(--app-danger-50);
  color: var(--app-danger-700);
  font-size: 0.875rem;
  line-height: 1.25rem;
}

@media (min-width: 48rem) {
  .app-shell {
    height: 100svh;
    grid-template-columns: 300px minmax(0, 1fr);
    overflow: hidden;
  }

  .error-banner {
    margin-right: 1.5rem;
    margin-left: 1.5rem;
  }
}
</style>
