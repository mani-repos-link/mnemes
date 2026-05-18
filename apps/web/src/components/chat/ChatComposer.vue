<script setup lang="ts">
import { ref } from "vue";

defineProps<{
  sending: boolean;
}>();

const emit = defineEmits<{
  send: [content: string];
}>();

const draft = ref("");

function submit() {
  const content = draft.value.trim();
  if (!content) {
    return;
  }

  emit("send", content);
  draft.value = "";
}
</script>

<template>
  <form class="composer" @submit.prevent="submit">
    <textarea
      v-model="draft"
      class="composer__input"
      rows="3"
      placeholder="Send a message"
      @keydown.enter.exact.prevent="submit"
    />
    <button class="composer__submit" type="submit" :disabled="sending || !draft.trim()">
      {{ sending ? "Thinking" : "Send" }}
    </button>
  </form>
</template>
