import { computed, onMounted, ref } from "vue";

import * as api from "../lib/api";
import type { Message, Session } from "../types/chat";
import { messageFromError } from "../utils/errors";

function createOptimisticUserMessage(sessionId: string, content: string): Message {
  return {
    id: `optimistic-${crypto.randomUUID()}`,
    sessionId,
    role: "user",
    content,
    createdAt: new Date().toISOString(),
  };
}

export function useChat() {
  const sessions = ref<Session[]>([]);
  const messages = ref<Message[]>([]);
  const selectedSessionId = ref<string | null>(null);
  const loading = ref(true);
  const loadingOlderMessages = ref(false);
  const messagesHasMore = ref(false);
  const messagesNextBefore = ref<string | null>(null);
  const sending = ref(false);
  const error = ref<string | null>(null);
  const status = ref<string | null>(null);

  const activeSession = computed(() =>
    sessions.value.find((session) => session.id === selectedSessionId.value),
  );

  onMounted(async () => {
    await loadSessions();
    if (sessions.value[0]) {
      await selectSession(sessions.value[0].id);
    }
  });

  async function loadSessions() {
    loading.value = true;
    error.value = null;
    status.value = null;
    try {
      const response = await api.listSessions();
      sessions.value = response.sessions;
    } catch (err) {
      error.value = messageFromError(err);
    } finally {
      loading.value = false;
    }
  }

  async function selectSession(sessionId: string) {
    selectedSessionId.value = sessionId;
    error.value = null;
    status.value = null;
    messagesHasMore.value = false;
    messagesNextBefore.value = null;
    try {
      const response = await api.listMessages(sessionId, { limit: 15 });
      messages.value = response.messages;
      messagesHasMore.value = response.page.hasMore;
      messagesNextBefore.value = response.page.nextBefore;
    } catch (err) {
      error.value = messageFromError(err);
    }
  }

  async function startSession() {
    error.value = null;
    status.value = null;
    const response = await api.createSession();
    sessions.value = [response.session, ...sessions.value];
    await selectSession(response.session.id);
  }

  async function deleteSession(sessionId: string) {
    error.value = null;
    status.value = null;
    try {
      await api.deleteSession(sessionId);
      const remainingSessions = sessions.value.filter((session) => session.id !== sessionId);
      sessions.value = remainingSessions;

      if (selectedSessionId.value !== sessionId) {
        return;
      }

      const nextSession = remainingSessions[0];
      if (nextSession) {
        await selectSession(nextSession.id);
      } else {
        selectedSessionId.value = null;
        messages.value = [];
        messagesHasMore.value = false;
        messagesNextBefore.value = null;
      }
    } catch (err) {
      error.value = messageFromError(err);
    }
  }

  async function loadOlderMessages() {
    const sessionId = selectedSessionId.value;
    if (
      !sessionId ||
      !messagesHasMore.value ||
      !messagesNextBefore.value ||
      loadingOlderMessages.value
    ) {
      return;
    }

    loadingOlderMessages.value = true;
    error.value = null;
    try {
      const response = await api.listMessages(sessionId, {
        limit: 15,
        before: messagesNextBefore.value,
      });
      messages.value = [...response.messages, ...messages.value];
      messagesHasMore.value = response.page.hasMore;
      messagesNextBefore.value = response.page.nextBefore;
    } catch (err) {
      error.value = messageFromError(err);
    } finally {
      loadingOlderMessages.value = false;
    }
  }

  function setStatus(message: string | null) {
    status.value = message;
  }

  async function sendMessage(content: string) {
    const trimmedContent = content.trim();
    if (!trimmedContent || sending.value) {
      return;
    }

    sending.value = true;
    error.value = null;

    try {
      if (!selectedSessionId.value) {
        await startSession();
      }

      const sessionId = selectedSessionId.value;
      if (!sessionId) {
        throw new Error("No active session");
      }

      const optimisticMessage = createOptimisticUserMessage(sessionId, trimmedContent);
      messages.value = [...messages.value, optimisticMessage];

      const response = await api.sendUserMessage(sessionId, trimmedContent);
      const responseMessages = response.messages ?? [response.message];
      messages.value = messages.value.flatMap((message) =>
        message.id === optimisticMessage.id ? responseMessages : [message],
      );
      await loadSessions();
      selectedSessionId.value = sessionId;
    } catch (err) {
      error.value = messageFromError(err);
      if (selectedSessionId.value) {
        await selectSession(selectedSessionId.value);
      }
    } finally {
      sending.value = false;
    }
  }

  return {
    activeSession,
    error,
    loading,
    loadingOlderMessages,
    messages,
    messagesHasMore,
    selectedSessionId,
    sending,
    sessions,
    status,
    loadSessions,
    loadOlderMessages,
    deleteSession,
    setStatus,
    selectSession,
    sendMessage,
    startSession,
  };
}
