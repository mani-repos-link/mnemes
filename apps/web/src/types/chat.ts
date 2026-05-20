export type Session = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
};

export type Message = {
  id: string;
  sessionId: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  provider?: string;
  model?: string;
  parentMessageId?: string | null;
  activeResponseId?: string | null;
  createdAt: string;
};

export type ChatKeyword = {
  term: string;
  count: number;
};

export type ChatMetricsMessage = Message & {
  preview: string;
  memoryStatus:
    | "indexed-vector"
    | "indexed-text"
    | "indexed"
    | "inactive-vector"
    | "inactive-text"
    | "pending-index"
    | "pending-summary"
    | "summarized"
    | "raw";
};

export type ChatMetrics = {
  session: Session;
  config: {
    memoryMode: string;
    triggerMessageLimit: number;
    bufferMessageLimit: number;
  };
  stats: {
    totalMessages: number;
    userMessages: number;
    assistantMessages: number;
    rawMessageWindow: number;
    compactedMessageEstimate: number;
    indexedTextMemories: number;
    indexedVectorMemories: number;
    totalEmbeddings: number;
    summaries: number;
    pendingMemoryMessages: number;
    pendingSummaryMessages: number;
    activeMemoryMessages: number;
    inactiveVectorMemories: number;
    inactiveSummaries: number;
  };
  summary: {
    id: string;
    content: string;
    preview: string;
    coveredMessageId: string | null;
    createdAt: string;
    updatedAt: string;
    active: boolean;
  } | null;
  keywords: ChatKeyword[];
  messages: ChatMetricsMessage[];
};
