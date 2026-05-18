import { computed, onMounted, ref } from "vue";

import * as api from "../lib/api";
import type { Message, Session } from "../types/chat";
import { messageFromError } from "../utils/errors";

export function useChat() {
  const sessions = ref<Session[]>([]);
  const messages = ref<Message[]>([]);
  const selectedSessionId = ref<string | null>(null);
  const loading = ref(true);
  const sending = ref(false);
  const error = ref<string | null>(null);

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
    try {
      const response = await api.listMessages(sessionId);
      messages.value = response.messages;
    } catch (err) {
      error.value = messageFromError(err);
    }
  }

  async function startSession() {
    error.value = null;
    const response = await api.createSession();
    sessions.value = [response.session, ...sessions.value];
    await selectSession(response.session.id);
  }

  async function deleteSession(sessionId: string) {
    error.value = null;
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
      }
    } catch (err) {
      error.value = messageFromError(err);
    }
  }

  async function sendMessage(content: string) {
    if (!content.trim() || sending.value) {
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

      const response = await api.sendUserMessage(sessionId, content.trim());
      messages.value = [...messages.value, ...(response.messages ?? [response.message])];
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
    messages,
    selectedSessionId,
    sending,
    sessions,
    loadSessions,
    deleteSession,
    selectSession,
    sendMessage,
    startSession,
  };
}
