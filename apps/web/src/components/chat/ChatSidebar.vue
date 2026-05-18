<script setup lang="ts">
import { MoreHorizontal, Plus, Trash2 } from "lucide-vue-next";
import { computed, ref, watch } from "vue";
import type { Session } from "../../types/chat";
import { formatTime } from "../../utils/date";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogBody,
  AlertDialogCancel,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const props = defineProps<{
  loading: boolean;
  selectedSessionId: string | null;
  sessions: Session[];
}>();

const emit = defineEmits<{
  deleteSession: [sessionId: string];
  newSession: [];
  selectSession: [sessionId: string];
}>();

const deleteDialogOpen = ref(false);
const deleteTarget = ref<Session | null>(null);
const visibleSessionCount = ref(60);

const visibleSessions = computed(() => props.sessions.slice(0, visibleSessionCount.value));
const hasMoreSessions = computed(() => visibleSessionCount.value < props.sessions.length);

watch(
  () => props.sessions.length,
  () => {
    visibleSessionCount.value = Math.min(
      Math.max(visibleSessionCount.value, 60),
      props.sessions.length || 60,
    );
  },
);

function requestDelete(session: Session) {
  deleteTarget.value = session;
  deleteDialogOpen.value = true;
}

function confirmDelete() {
  if (!deleteTarget.value) {
    return;
  }

  emit("deleteSession", deleteTarget.value.id);
  deleteDialogOpen.value = false;
  deleteTarget.value = null;
}

function loadMoreSessions() {
  visibleSessionCount.value = Math.min(visibleSessionCount.value + 40, props.sessions.length);
}

function handleSessionScroll(event: Event) {
  if (!hasMoreSessions.value) {
    return;
  }

  const element = event.currentTarget;
  if (!(element instanceof HTMLElement)) {
    return;
  }

  const nearVerticalEnd = element.scrollTop + element.clientHeight >= element.scrollHeight - 96;
  const nearHorizontalEnd = element.scrollLeft + element.clientWidth >= element.scrollWidth - 96;

  if (nearVerticalEnd || nearHorizontalEnd) {
    loadMoreSessions();
  }
}
</script>

<template>
  <aside
    class="flex min-h-0 flex-col border-b border-line bg-panel md:min-h-svh md:border-r md:border-b-0"
  >
    <div class="flex items-center justify-between gap-4 border-b border-line p-5">
      <div>
        <p class="mb-1 text-xs font-bold tracking-wide text-muted uppercase">Local</p>
        <h1 class="text-2xl leading-tight font-semibold text-ink">Mnemes</h1>
      </div>
      <Button size="icon" title="New chat" @click="$emit('newSession')">
        <Plus />
      </Button>
    </div>

    <div
      class="flex gap-2 overflow-x-auto p-2 md:min-h-0 md:flex-1 md:flex-col md:overflow-x-hidden md:overflow-y-auto"
      aria-label="Chat sessions"
      @scroll="handleSessionScroll"
    >
      <div
        v-for="session in visibleSessions"
        :key="session.id"
        class="grid min-h-11 min-w-52 grid-cols-[minmax(0,1fr)_auto] items-center rounded-md border transition md:w-full md:min-w-0"
        :class="
          session.id === selectedSessionId
            ? 'border-line-strong bg-raised'
            : 'border-transparent hover:border-line-strong hover:bg-subtle'
        "
      >
        <button
          class="min-w-0 bg-transparent px-2.5 py-2 text-left"
          type="button"
          @click="$emit('selectSession', session.id)"
        >
          <span class="block w-full truncate text-sm font-semibold text-ink">
            {{ session.title }}
          </span>
          <small class="text-xs text-muted">
            {{ formatTime(session.updatedAt) }}
          </small>
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button
              class="mr-1 text-muted hover:bg-raised hover:text-ink"
              variant="ghost"
              size="icon"
              :aria-label="`Open actions for ${session.title}`"
              title="Conversation actions"
              @click.stop
            >
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" @click.stop>
            <DropdownMenuItem class="text-destructive" @select="requestDelete(session)">
              <Trash2 />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <button
        v-if="hasMoreSessions"
        class="min-h-9 min-w-28 rounded-md border border-line bg-panel px-3 py-2 text-[0.8125rem] font-semibold text-muted hover:bg-raised hover:text-ink"
        type="button"
        @click="loadMoreSessions"
      >
        Load more
      </button>

      <p v-if="!loading && sessions.length === 0" class="px-3 py-4 text-sm text-muted">
        No sessions yet.
      </p>
    </div>

    <AlertDialog v-model:open="deleteDialogOpen">
      <AlertDialogBody>
        <AlertDialogHeader>
          <AlertDialogTitle class="text-lg font-semibold text-ink">
            Delete conversation?
          </AlertDialogTitle>
          <AlertDialogDescription class="text-sm leading-6 text-muted">
            This removes "{{ deleteTarget?.title }}" from your local history.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel as-child>
            <Button variant="outline" size="sm">Cancel</Button>
          </AlertDialogCancel>
          <AlertDialogAction as-child>
            <Button variant="destructive" size="sm" @click="confirmDelete">Delete</Button>
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogBody>
    </AlertDialog>
  </aside>
</template>
