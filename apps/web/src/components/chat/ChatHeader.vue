<script setup lang="ts">
import ThemeToggle from "./ThemeToggle.vue";
import type { Session } from "../../types/chat";

defineProps<{
  activeTheme: "light" | "dark";
  session?: Session;
}>();

defineEmits<{
  toggleTheme: [];
}>();
</script>

<template>
  <header class="chat-header">
    <div>
      <p class="eyebrow">Session</p>
      <h2 class="chat-title">{{ session?.title ?? "New chat" }}</h2>
    </div>
    <div class="chat-header__actions">
      <span class="status-pill">OpenRouter + SQLite</span>
      <ThemeToggle :active-theme="activeTheme" @toggle="$emit('toggleTheme')" />
    </div>
  </header>
</template>
