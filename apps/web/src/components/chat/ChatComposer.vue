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
        <button
            class="composer__submit"
            type="submit"
            :disabled="sending || !draft.trim()"
        >
            <span v-if="sending" class="composer__spinner" aria-hidden="true" />
            {{ sending ? "Thinking" : "Send" }}
        </button>
    </form>
</template>

<style scoped>
.composer {
    display: grid;
    gap: 0.75rem;
    border-top: 1px solid var(--app-line);
    padding: 1rem;
    background: var(--app-panel);
}

.composer__input {
    min-height: 5rem;
    width: 100%;
    resize: vertical;
    border: 1px solid var(--app-line-strong);
    border-radius: 0.5rem;
    padding: 0.75rem;
    background: var(--app-panel);
    color: var(--app-ink);
    outline: none;
    transition:
        border-color 150ms ease,
        box-shadow 150ms ease;
}

.composer__input::placeholder {
    color: var(--app-muted);
}

.composer__input:focus {
    border-color: var(--app-brand);
    box-shadow: 0 0 0 3px color-mix(in oklab, var(--app-brand) 20%, transparent);
}

.composer__submit {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    align-self: end;
    border: 1px solid var(--app-brand-strong);
    border-radius: 0.5rem;
    padding: 0.75rem 1.25rem;
    background: var(--app-brand);
    color: #ffffff;
    font-weight: 700;
    transition: background-color 150ms ease;
}

.composer__submit:hover {
    background: var(--app-brand-strong);
}

.composer__submit:disabled {
    cursor: not-allowed;
    opacity: 0.55;
}

.composer__spinner {
    width: 1rem;
    height: 1rem;
    border: 2px solid rgb(255 255 255 / 0.45);
    border-top-color: #ffffff;
    border-radius: 999px;
    animation: composer-spin 700ms linear infinite;
}

@keyframes composer-spin {
    to {
        transform: rotate(360deg);
    }
}

@media (min-width: 48rem) {
    .composer {
        grid-template-columns: minmax(0, 1fr) auto;
        padding: 1rem 1.25rem 1.25rem;
    }
}

@media (max-width: 47.999rem) {
    .composer__submit {
        width: 100%;
    }
}
</style>
