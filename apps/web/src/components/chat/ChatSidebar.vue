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
  <aside class="chat-sidebar">
    <div class="chat-sidebar__header">
      <div>
        <p class="eyebrow">Local</p>
        <h1 class="sidebar-title">Mnemes</h1>
      </div>
      <Button size="icon" title="New chat" @click="$emit('newSession')">
        <Plus />
      </Button>
    </div>

    <div class="session-list" aria-label="Chat sessions" @scroll="handleSessionScroll">
      <div
        v-for="session in visibleSessions"
        :key="session.id"
        class="session-row"
        :class="{ 'session-button--active': session.id === selectedSessionId }"
      >
        <button class="session-button" type="button" @click="$emit('selectSession', session.id)">
          <span>{{ session.title }}</span>
          <small>{{ formatTime(session.updatedAt) }}</small>
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button
              class="session-menu"
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
        class="session-load-more"
        type="button"
        @click="loadMoreSessions"
      >
        Load more
      </button>

      <p v-if="!loading && sessions.length === 0" class="empty-copy">No sessions yet.</p>
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

<style scoped>
.chat-sidebar {
  display: flex;
  min-height: 0;
  flex-direction: column;
  background: var(--app-panel);
  border-bottom: 1px solid var(--app-line);
}

.chat-sidebar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.25rem;
  border-bottom: 1px solid var(--app-line);
}

.sidebar-title {
  font-size: 1.5rem;
  line-height: 1.25;
  font-weight: 600;
  color: var(--app-ink);
}

.session-list {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  padding: 0.5rem;
}

.session-row {
  display: grid;
  min-height: 2.75rem;
  min-width: 13rem;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  border: 1px solid transparent;
  border-radius: 0.375rem;
  transition:
    background-color 150ms ease,
    border-color 150ms ease;
}

.session-row:hover {
  background: var(--app-subtle);
  border-color: var(--app-line-strong);
}

.session-button--active {
  background: var(--app-raised);
  border-color: var(--app-line-strong);
}

.session-button {
  min-width: 0;
  padding: 0.5rem 0.625rem;
  background: transparent;
  text-align: left;
}

.session-button span {
  display: block;
  width: 100%;
  overflow: hidden;
  font-size: 0.875rem;
  line-height: 1.25rem;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-ink);
}

.session-button small {
  font-size: 0.75rem;
  line-height: 1rem;
  color: var(--app-muted);
}

.empty-copy {
  padding: 1rem 0.75rem;
  font-size: 0.875rem;
  line-height: 1.25rem;
  color: var(--app-muted);
}

.session-load-more {
  min-height: 2.25rem;
  min-width: 7rem;
  border: 1px solid var(--app-line);
  border-radius: 0.375rem;
  padding: 0.5rem 0.75rem;
  background: var(--app-panel);
  color: var(--app-muted);
  font-size: 0.8125rem;
  font-weight: 600;
}

.session-load-more:hover {
  background: var(--app-raised);
  color: var(--app-ink);
}

.session-menu {
  margin-right: 0.25rem;
  color: var(--app-muted);
}

.session-menu:hover {
  background: var(--app-raised);
  color: var(--app-ink);
}

@media (min-width: 48rem) {
  .chat-sidebar {
    min-height: 100svh;
    border-right: 1px solid var(--app-line);
    border-bottom: 0;
  }

  .session-list {
    min-height: 0;
    flex: 1;
    flex-direction: column;
    overflow-x: hidden;
    overflow-y: auto;
  }

  .session-row {
    width: 100%;
    min-width: 0;
  }
}
</style>
