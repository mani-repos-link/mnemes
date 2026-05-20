<script setup lang="ts">
import { ArrowLeft, GitBranch, Loader2, RefreshCw } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { generateSessionMemory, getSessionMetrics } from "../../lib/api";
import type { ChatMetrics, ChatMetricsMessage } from "../../types/chat";
import { formatTime } from "../../utils/date";
import { messageFromError } from "../../utils/errors";
import { Button } from "@/components/ui/button";

const props = defineProps<{
  sessionId: string;
}>();

const metrics = ref<ChatMetrics | null>(null);
const loading = ref(true);
const generating = ref(false);
const error = ref<string | null>(null);

const compactedMessages = computed(
  () =>
    metrics.value?.messages.filter(
      (message) =>
        message.memoryStatus.startsWith("indexed") || message.memoryStatus === "summarized",
    ) ?? [],
);
const pendingMessages = computed(
  () =>
    metrics.value?.messages.filter((message) =>
      ["pending-index", "pending-summary"].includes(message.memoryStatus),
    ) ?? [],
);
const rawMessages = computed(
  () =>
    metrics.value?.messages.filter(
      (message) => message.memoryStatus === "raw" || message.memoryStatus.startsWith("inactive"),
    ) ?? [],
);
const graphNodes = computed(
  () =>
    metrics.value?.messages.map((message, index) => ({
      message,
      x: graphLaneX(message.memoryStatus),
      y: 42 + index * 58,
      label: `${index + 1}. ${message.role}`,
      preview: message.preview.length > 54 ? `${message.preview.slice(0, 54)}...` : message.preview,
    })) ?? [],
);
const graphEdges = computed(() =>
  graphNodes.value.slice(1).map((node, index) => ({
    from: graphNodes.value[index],
    to: node,
  })),
);
const graphHeight = computed(() => Math.max(180, 72 + graphNodes.value.length * 58));

onMounted(loadMetrics);

async function loadMetrics() {
  loading.value = true;
  error.value = null;
  try {
    metrics.value = await getSessionMetrics(props.sessionId);
  } catch (err) {
    error.value = messageFromError(err);
  } finally {
    loading.value = false;
  }
}

async function generateMemory() {
  generating.value = true;
  error.value = null;
  try {
    metrics.value = await generateSessionMemory(props.sessionId);
  } catch (err) {
    error.value = messageFromError(err);
  } finally {
    generating.value = false;
  }
}

function statusClasses(status: ChatMetricsMessage["memoryStatus"]) {
  if (status.startsWith("indexed")) {
    return "border-success-200 bg-success-50 text-success-700";
  }
  if (status === "summarized") {
    return "border-primary/30 bg-primary/10 text-primary";
  }
  if (status.startsWith("inactive")) {
    return "border-line bg-subtle text-muted";
  }
  if (status.startsWith("pending")) {
    return "border-warning-200 bg-warning-50 text-warning-800";
  }
  return "border-line bg-raised text-muted";
}

function graphLaneX(status: ChatMetricsMessage["memoryStatus"]) {
  if (status.startsWith("indexed") || status === "summarized") {
    return 150;
  }
  if (status.startsWith("pending")) {
    return 390;
  }
  return 630;
}

function graphColor(status: ChatMetricsMessage["memoryStatus"]) {
  if (status.startsWith("indexed")) {
    return "#16a34a";
  }
  if (status === "summarized") {
    return "#2563eb";
  }
  if (status.startsWith("pending")) {
    return "#d97706";
  }
  if (status.startsWith("inactive")) {
    return "#94a3b8";
  }
  return "#64748b";
}
</script>

<template>
  <main class="min-h-svh bg-shell text-ink">
    <header class="border-b border-line bg-panel px-5 py-4">
      <div class="mx-auto flex max-w-6xl items-center justify-between gap-3">
        <div class="min-w-0">
          <a
            class="mb-2 inline-flex items-center gap-1 text-sm font-semibold text-muted hover:text-ink"
            :href="`/s/${encodeURIComponent(sessionId)}`"
          >
            <ArrowLeft class="size-4" />
            Back to chat
          </a>
          <h1 class="truncate text-xl font-semibold">
            {{ metrics?.session.title ?? "Chat diagnostics" }}
          </h1>
        </div>
        <Button :disabled="loading || generating" size="sm" @click="generateMemory">
          <Loader2 v-if="generating" class="animate-spin" />
          <RefreshCw v-else />
          Generate memory
        </Button>
      </div>
    </header>

    <section class="mx-auto grid max-w-6xl gap-4 px-5 py-5">
      <p
        v-if="error"
        class="rounded-md border border-danger-300 bg-danger-50 px-3 py-2 text-sm text-danger-700"
      >
        {{ error }}
      </p>

      <div v-if="loading" class="flex min-h-64 items-center justify-center text-muted">
        <Loader2 class="mr-2 size-5 animate-spin" />
        Loading diagnostics
      </div>

      <template v-else-if="metrics">
        <div class="grid gap-3 md:grid-cols-4">
          <div
            v-for="item in [
              ['Messages', metrics.stats.totalMessages],
              ['Text memories', metrics.stats.indexedTextMemories],
              ['Embeddings', metrics.stats.totalEmbeddings],
              ['Summaries', metrics.stats.summaries],
            ]"
            :key="item[0]"
            class="rounded-lg border border-line bg-panel p-4"
          >
            <p class="text-xs font-semibold tracking-wide text-muted uppercase">{{ item[0] }}</p>
            <p class="mt-2 text-2xl font-semibold">{{ item[1] }}</p>
          </div>
        </div>

        <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <section class="rounded-lg border border-line bg-panel p-4">
            <div class="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 class="text-base font-semibold">Conversation Tree</h2>
                <p class="text-sm text-muted">
                  {{ metrics.config.memoryMode }} · raw {{ metrics.config.triggerMessageLimit }} ·
                  buffer {{ metrics.config.bufferMessageLimit }}
                </p>
              </div>
              <GitBranch class="size-5 text-muted" />
            </div>

            <div class="mb-5 overflow-x-auto rounded-lg border border-line bg-shell p-3">
              <svg
                class="min-w-[760px]"
                :height="graphHeight"
                :viewBox="`0 0 760 ${graphHeight}`"
                :style="{ height: `${graphHeight}px` }"
                role="img"
                aria-label="Conversation memory graph"
              >
                <line
                  x1="150"
                  y1="26"
                  x2="150"
                  :y2="graphHeight - 20"
                  stroke="#cbd5e1"
                  stroke-width="2"
                />
                <line
                  x1="390"
                  y1="26"
                  x2="390"
                  :y2="graphHeight - 20"
                  stroke="#cbd5e1"
                  stroke-width="2"
                />
                <line
                  x1="630"
                  y1="26"
                  x2="630"
                  :y2="graphHeight - 20"
                  stroke="#cbd5e1"
                  stroke-width="2"
                />
                <text
                  x="150"
                  y="16"
                  text-anchor="middle"
                  class="fill-muted text-[12px] font-semibold"
                >
                  active memory
                </text>
                <text
                  x="390"
                  y="16"
                  text-anchor="middle"
                  class="fill-muted text-[12px] font-semibold"
                >
                  pending / inactive
                </text>
                <text
                  x="630"
                  y="16"
                  text-anchor="middle"
                  class="fill-muted text-[12px] font-semibold"
                >
                  raw context
                </text>

                <path
                  v-for="edge in graphEdges"
                  :key="`${edge.from.message.id}-${edge.to.message.id}`"
                  :d="`M ${edge.from.x} ${edge.from.y} C ${edge.from.x} ${edge.from.y + 26}, ${edge.to.x} ${edge.to.y - 26}, ${edge.to.x} ${edge.to.y}`"
                  fill="none"
                  stroke="#cbd5e1"
                  stroke-width="1.5"
                />

                <g v-for="node in graphNodes" :key="node.message.id">
                  <circle
                    :cx="node.x"
                    :cy="node.y"
                    r="10"
                    :fill="graphColor(node.message.memoryStatus)"
                    stroke="white"
                    stroke-width="2"
                  />
                  <text :x="node.x + 16" :y="node.y - 4" class="fill-ink text-[12px] font-semibold">
                    {{ node.label }}
                  </text>
                  <text :x="node.x + 16" :y="node.y + 13" class="fill-muted text-[11px]">
                    {{ node.preview }}
                  </text>
                </g>
              </svg>
            </div>

            <div class="grid gap-5">
              <div>
                <h3 class="mb-2 text-sm font-semibold text-muted">Indexed / compacted</h3>
                <div class="grid gap-2">
                  <p v-if="compactedMessages.length === 0" class="text-sm text-muted">
                    No indexed messages yet.
                  </p>
                  <div
                    v-for="message in compactedMessages"
                    :key="message.id"
                    class="rounded-md border px-3 py-2 text-sm"
                    :class="statusClasses(message.memoryStatus)"
                  >
                    <div class="mb-1 flex items-center justify-between gap-2">
                      <span class="font-semibold">{{ message.role }}</span>
                      <span>{{ formatTime(message.createdAt) }}</span>
                    </div>
                    <p class="line-clamp-2 text-ink">{{ message.preview }}</p>
                  </div>
                </div>
              </div>

              <div>
                <h3 class="mb-2 text-sm font-semibold text-muted">Buffer / pending</h3>
                <div class="grid gap-2">
                  <p v-if="pendingMessages.length === 0" class="text-sm text-muted">
                    No pending memory batch.
                  </p>
                  <div
                    v-for="message in pendingMessages"
                    :key="message.id"
                    class="rounded-md border px-3 py-2 text-sm"
                    :class="statusClasses(message.memoryStatus)"
                  >
                    <div class="mb-1 flex items-center justify-between gap-2">
                      <span class="font-semibold">{{ message.role }}</span>
                      <span>{{ formatTime(message.createdAt) }}</span>
                    </div>
                    <p class="line-clamp-2 text-ink">{{ message.preview }}</p>
                  </div>
                </div>
              </div>

              <div>
                <h3 class="mb-2 text-sm font-semibold text-muted">Raw context tail</h3>
                <div class="grid gap-2">
                  <div
                    v-for="message in rawMessages"
                    :key="message.id"
                    class="rounded-md border px-3 py-2 text-sm"
                    :class="statusClasses(message.memoryStatus)"
                  >
                    <div class="mb-1 flex items-center justify-between gap-2">
                      <span class="font-semibold">{{ message.role }}</span>
                      <span>{{ formatTime(message.createdAt) }}</span>
                    </div>
                    <p class="line-clamp-2 text-ink">{{ message.preview }}</p>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <aside class="grid gap-4">
            <section class="rounded-lg border border-line bg-panel p-4">
              <h2 class="mb-3 text-base font-semibold">Memory Data</h2>
              <dl class="grid gap-2 text-sm">
                <div class="flex justify-between gap-3">
                  <dt class="text-muted">User</dt>
                  <dd class="font-semibold">{{ metrics.stats.userMessages }}</dd>
                </div>
                <div class="flex justify-between gap-3">
                  <dt class="text-muted">Assistant</dt>
                  <dd class="font-semibold">{{ metrics.stats.assistantMessages }}</dd>
                </div>
                <div class="flex justify-between gap-3">
                  <dt class="text-muted">Pending memory</dt>
                  <dd class="font-semibold">{{ metrics.stats.pendingMemoryMessages }}</dd>
                </div>
                <div class="flex justify-between gap-3">
                  <dt class="text-muted">Pending summary</dt>
                  <dd class="font-semibold">{{ metrics.stats.pendingSummaryMessages }}</dd>
                </div>
                <div class="flex justify-between gap-3">
                  <dt class="text-muted">Inactive vectors</dt>
                  <dd class="font-semibold">{{ metrics.stats.inactiveVectorMemories }}</dd>
                </div>
                <div class="flex justify-between gap-3">
                  <dt class="text-muted">Inactive summaries</dt>
                  <dd class="font-semibold">{{ metrics.stats.inactiveSummaries }}</dd>
                </div>
              </dl>
            </section>

            <section class="rounded-lg border border-line bg-panel p-4">
              <h2 class="mb-3 text-base font-semibold">Summary</h2>
              <p v-if="!metrics.summary" class="text-sm text-muted">No summary exists.</p>
              <div v-else class="grid gap-2">
                <span
                  class="w-fit rounded-md border px-2 py-1 text-xs font-semibold"
                  :class="
                    metrics.summary.active
                      ? 'border-primary/30 bg-primary/10 text-primary'
                      : 'border-line bg-subtle text-muted'
                  "
                >
                  {{ metrics.summary.active ? "active" : "stored but inactive" }}
                </span>
                <p class="text-sm leading-6 text-ink">{{ metrics.summary.preview }}</p>
              </div>
            </section>

            <section class="rounded-lg border border-line bg-panel p-4">
              <h2 class="mb-3 text-base font-semibold">Main Keywords</h2>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="keyword in metrics.keywords"
                  :key="keyword.term"
                  class="rounded-md border border-line bg-raised px-2 py-1 text-xs font-semibold text-muted"
                >
                  {{ keyword.term }} · {{ keyword.count }}
                </span>
              </div>
            </section>
          </aside>
        </div>
      </template>
    </section>
  </main>
</template>
