<script setup lang="ts">
defineProps<{
  activeTheme: "light" | "dark";
}>();

defineEmits<{
  toggle: [];
}>();
</script>

<template>
  <button
    class="theme-toggle"
    type="button"
    :title="activeTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
    @click="$emit('toggle')"
  >
    <span aria-hidden="true">{{ activeTheme === "dark" ? "☾" : "☼" }}</span>
    <span>{{ activeTheme === "dark" ? "Dark" : "Light" }}</span>
  </button>
</template>
