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
      <MessageList :messages="chat.messages.value" />

      <p v-if="chat.error.value" class="error-banner">
        {{ chat.error.value }}
      </p>

      <ChatComposer :sending="chat.sending.value" @send="chat.sendMessage" />
    </section>
  </main>
</template>
