<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import type { Message } from "../../types/chat";
import { formatTime } from "../../utils/date";

const COLLAPSE_MESSAGE_LENGTH = 1000;
const COLLAPSE_MESSAGE_LINES = 20;

const props = defineProps<{
    hasOlderMessages: boolean;
    loadingOlderMessages: boolean;
    messages: Message[];
    sending: boolean;
    sessionId: string | null;
}>();

const emit = defineEmits<{
    loadOlderMessages: [];
}>();

const messageListElement = ref<HTMLElement | null>(null);
const expandedMessageIds = ref<Set<string>>(new Set());
const preserveScrollPosition = ref(false);

function messageClass(message: Message) {
    if (message.role === "user") {
        return "self-end border-mint-300 bg-mint-50";
    }
    if (message.role === "assistant") {
        return "self-start border-line bg-panel";
    }
    return "self-start border-line bg-subtle";
}

function isLongMessage(message: Message) {
    return message.content.length > COLLAPSE_MESSAGE_LENGTH;
}

function isExpanded(messageId: string) {
    return expandedMessageIds.value.has(messageId);
}

function toggleMessage(messageId: string) {
    const nextExpandedIds = new Set(expandedMessageIds.value);
    if (nextExpandedIds.has(messageId)) {
        nextExpandedIds.delete(messageId);
    } else {
        nextExpandedIds.add(messageId);
    }
    expandedMessageIds.value = nextExpandedIds;
}

function requestOlderMessages() {
    if (!props.hasOlderMessages || props.loadingOlderMessages) {
        return;
    }

    const element = messageListElement.value;
    preserveScrollPosition.value = true;
    previousScrollHeight = element?.scrollHeight ?? 0;
    emit("loadOlderMessages");
}

let previousScrollHeight = 0;

function handleScroll(event: Event) {
    const element = event.currentTarget;
    if (!(element instanceof HTMLElement)) {
        return;
    }

    if (element.scrollTop <= 96) {
        requestOlderMessages();
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
        preserveScrollPosition.value = false;
        await nextTick();
        scrollToLatest();
    },
);

watch(
    () => [props.messages.length, props.sending],
    async () => {
        await nextTick();
        if (preserveScrollPosition.value) {
            return;
        }
        scrollToLatest();
    },
);

watch(
    () => props.loadingOlderMessages,
    async (loading) => {
        if (loading || !preserveScrollPosition.value) {
            return;
        }

        await nextTick();
        const element = messageListElement.value;
        if (element) {
            element.scrollTop += element.scrollHeight - previousScrollHeight;
        }
        preserveScrollPosition.value = false;
        previousScrollHeight = 0;
    },
);
</script>

<template>
    <div
        ref="messageListElement"
        class="flex min-h-0 flex-col gap-3.5 overflow-y-auto p-4 md:p-6"
        @scroll="handleScroll"
    >
        <div
            v-if="messages.length === 0"
            class="m-auto max-w-xl text-center text-muted"
        >
            <h3 class="text-lg font-semibold text-ink">
                Start a local conversation
            </h3>
            <p class="mt-2 leading-6">
                Messages are saved through the Go API into the local SQLite
                database.
            </p>
        </div>

        <button
            v-if="hasOlderMessages"
            class="self-center rounded-full border border-line bg-panel px-3 py-1.5 text-[0.8125rem] font-bold text-muted hover:bg-raised hover:text-ink disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            :disabled="loadingOlderMessages"
            @click="requestOlderMessages"
        >
            {{
                loadingOlderMessages
                    ? "Loading earlier messages"
                    : "Load earlier messages"
            }}
        </button>

        <article
            v-for="message in messages"
            :key="message.id"
            class="grid w-full max-w-3xl gap-2 rounded-lg border px-4 py-3.5 leading-6 whitespace-pre-wrap shadow-sm"
            :class="messageClass(message)"
        >
            <div
                class="flex flex-wrap items-center gap-x-2 gap-y-1 whitespace-normal"
            >
                <span
                    class="text-xs font-extrabold tracking-wide text-meta uppercase"
                >
                    {{ message.role }}
                </span>
                <small v-if="message.model" class="truncate text-xs text-muted">
                    {{ message.model }}
                </small>
            </div>
            <p
                :class="
                    isLongMessage(message) && !isExpanded(message.id)
                        ? 'line-clamp-[var(--message-preview-lines)] overflow-hidden'
                        : ''
                "
                :style="{
                    '--message-preview-lines': String(COLLAPSE_MESSAGE_LINES),
                }"
            >
                {{ message.content }}
            </p>
            <div class="w-full flex items-center justify-between">
              <small class="text-xs text-muted">{{
                formatTime(message.createdAt)
            }}</small>

              <button
                  v-if="isLongMessage(message)"
                  class="w-fit text-md underline font-semibold text-brand hover:text-brand-strong"
                  type="button"
                  @click="toggleMessage(message.id)"
              >
                  {{ isExpanded(message.id) ? "Read less" : "Read more" }}
              </button>
            </div>
            
        </article>

        <article
            v-if="sending"
            class="grid min-w-32 max-w-3xl self-start rounded-lg border border-line bg-panel px-4 py-3.5 leading-6 shadow-sm"
        >
            <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span
                    class="text-xs font-extrabold tracking-wide text-meta uppercase"
                >
                    assistant
                </span>
            </div>
            <div
                class="inline-flex items-center gap-1"
                aria-label="Assistant is thinking"
            >
                <span
                    class="size-[0.45rem] animate-bounce rounded-full bg-muted"
                />
                <span
                    class="size-[0.45rem] animate-bounce rounded-full bg-muted [animation-delay:120ms]"
                />
                <span
                    class="size-[0.45rem] animate-bounce rounded-full bg-muted [animation-delay:240ms]"
                />
            </div>
        </article>
    </div>
</template>
