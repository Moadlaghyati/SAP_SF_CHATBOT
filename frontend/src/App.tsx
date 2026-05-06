import { startTransition, useEffect, useRef, useState } from "react";
import {
  fetchAudit,
  fetchDemoUsers,
  fetchHealth,
  fetchLocalModels,
  fetchRequest,
  fetchRequests,
  sendChat,
  switchDemoUser,
  switchLocalModel,
} from "./api/client";
import { AuditViewer } from "./components/AuditViewer";
import { ChatComposer } from "./components/ChatComposer";
import { MessageList } from "./components/MessageList";
import { RequestHistory } from "./components/RequestHistory";
import { TracePanel } from "./components/TracePanel";
import type {
  AuditRecord,
  ChatMessage,
  ChatResponse,
  Conversation,
  DemoUserSummary,
  HealthResponse,
  LocalModelSummary,
  RequestDetail,
  RequestListItem,
} from "./types/api";

type ActiveTab = "chat" | "history" | "audit" | "trace";

const ACTIVE_USER_STORAGE_KEY = "hr-ai-assistant-active-user";
const CONVERSATIONS_STORAGE_KEY = "hr-ai-assistant-conversations";
const MAX_CONVERSATIONS = 30;

function generateId(): string {
  return `conv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function loadConversationsFromStorage(): Conversation[] {
  try {
    const raw = window.localStorage.getItem(CONVERSATIONS_STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as Conversation[];
  } catch {
    return [];
  }
}

function saveConversationsToStorage(conversations: Conversation[]): void {
  try {
    window.localStorage.setItem(CONVERSATIONS_STORAGE_KEY, JSON.stringify(conversations));
  } catch {
    // localStorage full or unavailable
  }
}

function formatConvDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;
  return d.toLocaleDateString();
}
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

const FALLBACK_DEMO_USERS: DemoUserSummary[] = [
  {
    user_id: "demo_fouzi_lekjaa",
    display_name: "Fouzi Lekjaa",
    role: "hr_admin",
    job_title: "Président, FRMF",
    employee_id: "90000638",
    description: "FRMF President — full access to all HR data and team absences.",
  },
  {
    user_id: "demo_walid_regragi",
    display_name: "Walid Regragi",
    role: "manager",
    job_title: "Sélectionneur National",
    employee_id: "90000712",
    description: "Head Coach Men's National Team — access to self and direct reports.",
  },
  {
    user_id: "demo_mouna_bennani",
    display_name: "Mouna Bennani",
    role: "hr_admin",
    job_title: "Responsable RH",
    employee_id: "90000726",
    description: "HR Operations Manager — full HR data access.",
  },
  {
    user_id: "demo_leila_haddad",
    display_name: "Leila Haddad",
    role: "employee",
    job_title: "Directrice Administrative",
    employee_id: "90000730",
    description: "Administrative Director — can view own absence data only.",
  },
  {
    user_id: "demo_assistant_coach",
    display_name: "Assistant Coach",
    role: "employee",
    job_title: "Entraîneur Adjoint",
    employee_id: "90000714",
    description: "Assistant Coach — can view own absence data only.",
  },
  {
    user_id: "demo_ilham_tbato",
    display_name: "Ilham Tbato",
    role: "employee",
    job_title: "Analyste Performance",
    employee_id: "90000718",
    description: "Performance Analyst — can view own absence data only.",
  },
  {
    user_id: "demo_eduardo_dominguez",
    display_name: "Eduardo Dominguez",
    role: "employee",
    job_title: "Préparateur Physique",
    employee_id: "90000722",
    description: "Physical Trainer — can view own absence data only.",
  },
  {
    user_id: "demo_visionage_video",
    display_name: "Visionage Video",
    role: "employee",
    job_title: "Analyste Vidéo",
    employee_id: "90000736",
    description: "Video Analyst — can view own absence data only.",
  },
];

const CATEGORIES = [
  {
    icon: "📅",
    title: "Absence Lookup",
    prompts: [
      "How many absences did Walid Regragi have this month?",
      "Show Ilham Tbato's absences in April 2026.",
      "List Eduardo Dominguez's absences this year.",
    ],
  },
  {
    icon: "👥",
    title: "Team Overview",
    prompts: [
      "Who on my team is absent this week?",
      "Show my team's absences this month.",
      "Is there anyone in Walid Regragi's department absent this month?",
    ],
  },
  {
    icon: "🏢",
    title: "Company Wide",
    prompts: [
      "Who is absent today?",
      "Who is absent this week?",
      "Show all absences in May 2026.",
    ],
  },
];

const TAB_LABELS: Record<ActiveTab, string> = {
  chat: "Chat AI",
  history: "Request History",
  audit: "Audit Trail",
  trace: "Trace & Debug",
};

function userInitials(name: string): string {
  return name
    .split(" ")
    .map((n) => n[0] ?? "")
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

function pickInitialUserId(
  users: DemoUserSummary[],
  storedUserId: string | null,
  activeUserId: string | null,
): string {
  if (storedUserId && users.some((u) => u.user_id === storedUserId)) return storedUserId;
  if (activeUserId && users.some((u) => u.user_id === activeUserId)) return activeUserId;
  return users[0]?.user_id ?? "demo_fouzi_lekjaa";
}

function formatErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message.trim();
  return "The backend did not return a usable response.";
}

function buildBootstrapErrorMessage(failedAreas: string[], error: unknown, usingFallbackUsers: boolean): string {
  const resourceLabel = failedAreas.length > 0 ? failedAreas.join(", ") : "backend data";
  const fallbackCopy = usingFallbackUsers ? " Built-in demo personas are shown for now." : "";
  return `Could not load ${resourceLabel} from ${API_BASE_URL}.${fallbackCopy} Start the backend over http://, not https://, then retry. Example: http://127.0.0.1:8001/api/health. Details: ${formatErrorMessage(error)}`;
}

function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("chat");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [demoUsers, setDemoUsers] = useState<DemoUserSummary[]>([]);
  const [activeUserId, setActiveUserId] = useState<string>("demo_fouzi_lekjaa");
  const [inputValue, setInputValue] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [requestHistory, setRequestHistory] = useState<RequestListItem[]>([]);
  const [selectedRequest, setSelectedRequest] = useState<RequestDetail | null>(null);
  const [auditRecords, setAuditRecords] = useState<AuditRecord[]>([]);
  const [localModels, setLocalModels] = useState<LocalModelSummary[]>([]);
  const [localModelBackend, setLocalModelBackend] = useState<string | null>(null);
  const [activeLocalModel, setActiveLocalModel] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [modelSwitching, setModelSwitching] = useState(false);
  const [pendingElapsedSeconds, setPendingElapsedSeconds] = useState(0);
  const [pendingRequestStartedAt, setPendingRequestStartedAt] = useState<number | null>(null);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [usingFallbackUsers, setUsingFallbackUsers] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>(() => loadConversationsFromStorage());
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  // Ref keeps the conversation ID synchronously up-to-date to avoid stale closure issues
  const activeConvIdRef = useRef<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!userMenuOpen) return;
    function handleClickOutside(e: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [userMenuOpen]);

  useEffect(() => {
    const stored = window.localStorage.getItem(ACTIVE_USER_STORAGE_KEY);
    if (stored) setActiveUserId(stored);
  }, []);

  useEffect(() => {
    void loadBootstrap();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Persist conversation to localStorage whenever messages settle (no pending messages)
  useEffect(() => {
    if (messages.length === 0 || messages.some((m) => m.pending)) return;
    const firstUser = messages.find((m) => m.role === "user");
    if (!firstUser) return;

    const title = firstUser.text.slice(0, 60) + (firstUser.text.length > 60 ? "…" : "");
    const now = new Date().toISOString();
    const convId = activeConvIdRef.current;
    const prev = loadConversationsFromStorage();
    const existingIdx = convId ? prev.findIndex((c) => c.id === convId) : -1;

    let updated: Conversation[];
    let resultId: string;

    if (existingIdx >= 0) {
      resultId = convId!;
      updated = prev.map((c, i) => i === existingIdx ? { ...c, messages, title, updatedAt: now } : c);
    } else {
      resultId = generateId();
      activeConvIdRef.current = resultId; // update ref immediately to prevent duplicate on StrictMode re-run
      const newConv: Conversation = { id: resultId, userId: activeUserId, title, messages, createdAt: now, updatedAt: now };
      updated = [newConv, ...prev].slice(0, MAX_CONVERSATIONS);
    }

    saveConversationsToStorage(updated);
    setConversations(updated);
    if (resultId !== activeConversationId) {
      setActiveConversationId(resultId);
      activeConvIdRef.current = resultId;
    }
  }, [messages, activeUserId]);

  useEffect(() => {
    if (!loading || pendingRequestStartedAt === null) {
      setPendingElapsedSeconds(0);
      return;
    }
    const updateElapsed = () =>
      setPendingElapsedSeconds(Math.max(0, Math.floor((Date.now() - pendingRequestStartedAt) / 1000)));
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [loading, pendingRequestStartedAt]);

  async function loadBootstrap() {
    const [healthResult, demoUsersResult, requestsResult, auditResult, localModelsResult] =
      await Promise.allSettled([fetchHealth(), fetchDemoUsers(), fetchRequests(), fetchAudit(), fetchLocalModels()]);

    const failedAreas: string[] = [];
    let firstFailure: unknown = null;

    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
    } else {
      setHealth(null);
      failedAreas.push("health status");
      firstFailure ??= healthResult.reason;
    }

    const nextDemoUsers =
      demoUsersResult.status === "fulfilled" && demoUsersResult.value.items.length > 0
        ? demoUsersResult.value.items
        : FALLBACK_DEMO_USERS;
    const nextUsingFallback = demoUsersResult.status !== "fulfilled" || demoUsersResult.value.items.length === 0;
    setDemoUsers(nextDemoUsers);
    setUsingFallbackUsers(nextUsingFallback);
    if (demoUsersResult.status !== "fulfilled") {
      failedAreas.push("demo users");
      firstFailure ??= demoUsersResult.reason;
    }

    const storedUserId = window.localStorage.getItem(ACTIVE_USER_STORAGE_KEY);
    const initialUserId = pickInitialUserId(
      nextDemoUsers,
      storedUserId,
      demoUsersResult.status === "fulfilled" ? demoUsersResult.value.active_user_id : null,
    );
    setActiveUserId(initialUserId);
    window.localStorage.setItem(ACTIVE_USER_STORAGE_KEY, initialUserId);

    if (requestsResult.status === "fulfilled") {
      startTransition(() => setRequestHistory(requestsResult.value.items));
    } else {
      setRequestHistory([]);
      failedAreas.push("request history");
      firstFailure ??= requestsResult.reason;
    }

    if (auditResult.status === "fulfilled") {
      startTransition(() => setAuditRecords(auditResult.value.items));
    } else {
      setAuditRecords([]);
      failedAreas.push("audit trail");
      firstFailure ??= auditResult.reason;
    }

    if (localModelsResult.status === "fulfilled") {
      setLocalModels(localModelsResult.value.items);
      setLocalModelBackend(localModelsResult.value.backend);
      setActiveLocalModel(localModelsResult.value.active_model ?? localModelsResult.value.items[0]?.name ?? "");
    } else {
      setLocalModels([]);
      setLocalModelBackend(null);
      setActiveLocalModel("");
      failedAreas.push("local model metadata");
      firstFailure ??= localModelsResult.reason;
    }

    if (requestsResult.status === "fulfilled" && requestsResult.value.items[0]) {
      try {
        const detail = await fetchRequest(requestsResult.value.items[0].request_id);
        setSelectedRequest(detail);
      } catch (error) {
        setSelectedRequest(null);
        failedAreas.push("selected request details");
        firstFailure ??= error;
      }
    } else {
      setSelectedRequest(null);
    }

    if (failedAreas.length > 0) {
      setBootstrapError(buildBootstrapErrorMessage(failedAreas, firstFailure, nextUsingFallback));
      return;
    }
    setBootstrapError(null);
  }

  async function refreshData(selectedRequestId?: string) {
    const [requestsResult, auditResult, healthResult, localModelsResult] = await Promise.allSettled([
      fetchRequests(),
      fetchAudit(),
      fetchHealth(),
      fetchLocalModels(),
    ]);

    const failedAreas: string[] = [];
    let firstFailure: unknown = null;
    let requestIdToLoad = selectedRequestId;

    if (requestsResult.status === "fulfilled") {
      startTransition(() => setRequestHistory(requestsResult.value.items));
      requestIdToLoad ??= requestsResult.value.items[0]?.request_id;
    } else {
      failedAreas.push("request history");
      firstFailure ??= requestsResult.reason;
    }

    if (auditResult.status === "fulfilled") {
      startTransition(() => setAuditRecords(auditResult.value.items));
    } else {
      failedAreas.push("audit trail");
      firstFailure ??= auditResult.reason;
    }

    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
    } else {
      failedAreas.push("health status");
      firstFailure ??= healthResult.reason;
    }

    if (localModelsResult.status === "fulfilled") {
      setLocalModels(localModelsResult.value.items);
      setLocalModelBackend(localModelsResult.value.backend);
      setActiveLocalModel(
        (current) =>
          localModelsResult.value.active_model ?? localModelsResult.value.items[0]?.name ?? current,
      );
    } else {
      failedAreas.push("local model metadata");
      firstFailure ??= localModelsResult.reason;
    }

    if (requestIdToLoad) {
      try {
        const detail = await fetchRequest(requestIdToLoad);
        setSelectedRequest(detail);
      } catch (error) {
        failedAreas.push("selected request details");
        firstFailure ??= error;
      }
    }

    if (failedAreas.length > 0) {
      setBootstrapError(buildBootstrapErrorMessage(failedAreas, firstFailure, usingFallbackUsers));
      return;
    }
    setBootstrapError(null);
  }

  async function handleUserChange(userId: string) {
    setActiveUserId(userId);
    window.localStorage.setItem(ACTIVE_USER_STORAGE_KEY, userId);
    try {
      const activeUser = await switchDemoUser(userId);
      setActiveUserId(activeUser.user_id);
      window.localStorage.setItem(ACTIVE_USER_STORAGE_KEY, activeUser.user_id);
      setBootstrapError(null);
    } catch (error) {
      setBootstrapError(
        `Using the selected persona locally. Start the backend at ${API_BASE_URL} over http:// to sync the demo user switch. Details: ${formatErrorMessage(error)}`,
      );
    }
  }

  async function handleSubmit() {
    const trimmed = inputValue.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    const pendingMessageId = `assistant-pending-${Date.now()}`;
    setPendingRequestStartedAt(Date.now());
    setBootstrapError(null);

    const userMessage: ChatMessage = { id: `user-${Date.now()}`, role: "user", text: trimmed };
    const pendingAssistantMessage: ChatMessage = {
      id: pendingMessageId,
      role: "assistant",
      text: `Thinking with ${activeLocalModel || "Ollama"}...`,
      pending: true,
    };
    setMessages((current) => [...current, userMessage, pendingAssistantMessage]);

    try {
      const response = await sendChat(trimmed, activeUserId);
      applyChatResponse(response, pendingMessageId);
      setInputValue("");
      await refreshData(response.request_id);
    } catch (error) {
      const failureMessage =
        error instanceof Error ? error.message : "The request failed before a response was returned.";
      setMessages((current) =>
        current.map((m) =>
          m.id === pendingMessageId ? { ...m, text: failureMessage, status: "error", pending: false } : m,
        ),
      );
      setBootstrapError(failureMessage);
    } finally {
      setLoading(false);
      setPendingRequestStartedAt(null);
    }
  }

  async function handleModelSwitch() {
    if (!activeLocalModel || modelSwitching) return;
    setModelSwitching(true);
    try {
      const response = await switchLocalModel(activeLocalModel);
      setLocalModelBackend(response.backend);
      setActiveLocalModel(response.active_model);
      await refreshData(selectedRequest?.request_id);
      setBootstrapError(null);
    } catch (error) {
      setBootstrapError(error instanceof Error ? error.message : "Failed to switch the local model.");
    } finally {
      setModelSwitching(false);
    }
  }

  function startNewChat() {
    setMessages([]);
    setActiveConversationId(null);
    activeConvIdRef.current = null;
    setActiveTab("chat");
  }

  function loadConversation(conv: Conversation) {
    setMessages(conv.messages);
    setActiveConversationId(conv.id);
    activeConvIdRef.current = conv.id;
    setActiveTab("chat");
  }

  function deleteConversation(convId: string, e: React.MouseEvent) {
    e.stopPropagation();
    const updated = conversations.filter((c) => c.id !== convId);
    setConversations(updated);
    saveConversationsToStorage(updated);
    if (activeConversationId === convId) {
      setMessages([]);
      setActiveConversationId(null);
    }
  }

function applyChatResponse(response: ChatResponse, pendingMessageId?: string) {
    const nextMessage: ChatMessage = {
      id: `assistant-${response.request_id}`,
      role: "assistant",
      text: response.answer,
      status: response.status,
      requestId: response.request_id,
      pending: false,
      minimizedResult: response.trace.minimized_result,
    };

    // Use functional updater so we always get the latest messages (avoids stale closure)
    setMessages((current) => {
      if (!pendingMessageId) return [...current, nextMessage];
      const replaced = current.some((m) => m.id === pendingMessageId);
      return replaced
        ? current.map((m) => (m.id === pendingMessageId ? nextMessage : m))
        : [...current, nextMessage];
    });
    setSelectedRequest({
      request_id: response.request_id,
      created_at: new Date().toISOString(),
      acting_user: demoUsers.find((u) => u.user_id === activeUserId)?.display_name ?? activeUserId,
      user_role: demoUsers.find((u) => u.user_id === activeUserId)?.role ?? "manager",
      question: response.trace.request_message,
      parsed_intent: response.trace.detected_intent,
      tool_name: response.trace.tool_name,
      target_employee_id: response.trace.target_employee_id,
      authorization_outcome: response.trace.authorization_outcome,
      status: response.status,
      duration_ms: response.trace.duration_ms,
      answer: response.answer,
      trace: response.trace,
    });
  }

  async function handleSelectRequest(requestId: string) {
    const detail = await fetchRequest(requestId);
    setSelectedRequest(detail);
  }

  const activeUser = demoUsers.find((u) => u.user_id === activeUserId) ?? null;
  const showWelcome = activeTab === "chat" && messages.length === 0;
  const effectiveLlmBackend = health?.llm_backend ?? localModelBackend ?? "unknown";
  const showOllamaModelControls = effectiveLlmBackend === "ollama";

  return (
    <div className="app-shell">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <button
          type="button"
          className="sidebar__brand"
          onClick={() => { setActiveTab("chat"); setMessages([]); }}
          style={{ background: "none", border: "none", cursor: "pointer", textAlign: "left", width: "100%", padding: 0 }}
        >
          <div className="brand-icon">🤖</div>
          <span className="brand-name">HR Assistant</span>
        </button>

        <nav className="sidebar__nav">
          <span className="sidebar__section-label">AI Tools</span>
          <button
            type="button"
            className={`nav-item ${activeTab === "chat" && activeConversationId === null && messages.length === 0 ? "nav-item--active" : ""}`}
            onClick={startNewChat}
          >
            <span className="nav-item__icon">✏️</span>
            New Chat
          </button>
          <button
            type="button"
            className={`nav-item ${activeTab === "chat" ? "nav-item--active" : ""}`}
            onClick={() => setActiveTab("chat")}
          >
            <span className="nav-item__icon">💬</span>
            Chat AI
          </button>

          {conversations.filter((c) => c.userId === activeUserId).length > 0 && (
            <>
              <span className="sidebar__section-label sidebar__section-label--recents">Recents</span>
              {conversations
                .filter((c) => c.userId === activeUserId)
                .slice(0, 15)
                .map((conv) => (
                  <button
                    key={conv.id}
                    type="button"
                    className={`conv-item ${activeConversationId === conv.id ? "conv-item--active" : ""}`}
                    onClick={() => loadConversation(conv)}
                  >
                    <span className="conv-item__title">{conv.title}</span>
                    <span className="conv-item__meta">{formatConvDate(conv.updatedAt)}</span>
                    <span
                      className="conv-item__delete"
                      role="button"
                      tabIndex={0}
                      onClick={(e) => deleteConversation(conv.id, e)}
                      onKeyDown={(e) => e.key === "Enter" && deleteConversation(conv.id, e as unknown as React.MouseEvent)}
                    >×</span>
                  </button>
                ))}
            </>
          )}

          <span className="sidebar__section-label">Data & Logs</span>
          <button
            type="button"
            className={`nav-item ${activeTab === "history" ? "nav-item--active" : ""}`}
            onClick={() => setActiveTab("history")}
          >
            <span className="nav-item__icon">📋</span>
            Request History
            {requestHistory.length > 0 && (
              <span className="nav-item__badge">{requestHistory.length}</span>
            )}
          </button>
          <button
            type="button"
            className={`nav-item ${activeTab === "audit" ? "nav-item--active" : ""}`}
            onClick={() => setActiveTab("audit")}
          >
            <span className="nav-item__icon">🔍</span>
            Audit Trail
            {auditRecords.length > 0 && (
              <span className="nav-item__badge">{auditRecords.length}</span>
            )}
          </button>
          <button
            type="button"
            className={`nav-item ${activeTab === "trace" ? "nav-item--active" : ""}`}
            onClick={() => setActiveTab("trace")}
          >
            <span className="nav-item__icon">⚙️</span>
            Trace & Debug
          </button>
        </nav>

        <div className="sidebar__bottom" ref={userMenuRef}>
          {userMenuOpen && (
            <div className="user-menu">
              {demoUsers.map((user) => (
                <button
                  key={user.user_id}
                  type="button"
                  className={`user-menu-item${user.user_id === activeUserId ? " user-menu-item--active" : ""}`}
                  onClick={() => { void handleUserChange(user.user_id); setUserMenuOpen(false); }}
                >
                  <div className="user-menu-item__avatar">{userInitials(user.display_name)}</div>
                  <div className="user-menu-item__info">
                    <div className="user-menu-item__name">{user.display_name}</div>
                    <div className="user-menu-item__title">{user.job_title || user.role}</div>
                  </div>
                  {user.user_id === activeUserId && <span className="user-menu-item__check">✓</span>}
                </button>
              ))}
            </div>
          )}
          <button
            type="button"
            className="sidebar__user sidebar__user--toggle"
            onClick={() => setUserMenuOpen((o) => !o)}
            disabled={demoUsers.length === 0}
          >
            <div className="user-avatar">
              {activeUser ? userInitials(activeUser.display_name) : "?"}
            </div>
            <div className="user-info">
              <div className="user-name">{activeUser?.display_name ?? "Loading..."}</div>
              <div className="user-role">{activeUser?.job_title || activeUser?.role || ""}</div>
            </div>
            <span className="user-chevron">{userMenuOpen ? "▲" : "▼"}</span>
          </button>
        </div>
      </aside>

      {/* ── Main area ── */}
      <div className="main-area">
        <header className="topbar">
          <div className="topbar__left">
            <span className="topbar__page">SuccessFactors HR</span>
            <span className="topbar__separator">/</span>
            <span className="topbar__breadcrumb">{TAB_LABELS[activeTab]}</span>
          </div>
          <div className="topbar__right">
            <div className="topbar__status-dots">
              <span className="status-dot">{health?.model_inference ?? "local"}</span>
              <span className="status-dot">{health?.connector_backend ?? "mock"}</span>
            </div>
            <div className="topbar-avatar">
              {activeUser ? userInitials(activeUser.display_name) : "?"}
            </div>
          </div>
        </header>

        {bootstrapError ? (
          <div className="banner banner--error">{bootstrapError}</div>
        ) : null}

        {/* Welcome screen */}
        {showWelcome && (
          <div className="welcome-screen">
            <div className="welcome-icon-wrap">🤖</div>
            <h1 className="welcome-heading">What HR data can I help you with?</h1>
            <p className="welcome-sub">
              Ask about absences, time off, and employee records — all processed locally with approved SAP tools only.
            </p>
            <div className="welcome-composer">
              <ChatComposer
                value={inputValue}
                onChange={setInputValue}
                onSubmit={() => void handleSubmit()}
                loading={loading}
              />
              <p className="inline-composer__hint">Press Enter to send · Shift+Enter for new line</p>
            </div>
            <div className="category-grid">
              {CATEGORIES.map((cat) => (
                <div key={cat.title} className="category-card">
                  <span className="category-card__icon">{cat.icon}</span>
                  <p className="category-card__title">{cat.title}</p>
                  <ul className="category-card__prompts">
                    {cat.prompts.map((prompt) => (
                      <li
                        key={prompt}
                        className="category-card__prompt"
                        onClick={() => setInputValue(prompt)}
                      >
                        {prompt}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Chat view with messages */}
        {activeTab === "chat" && !showWelcome && (
          <div className="chat-view">
            <div className="chat-view__messages">
              <MessageList messages={messages} pendingElapsedSeconds={pendingElapsedSeconds} />
              <div ref={messagesEndRef} />
            </div>
            <div className="chat-view__input">
              <ChatComposer
                value={inputValue}
                onChange={setInputValue}
                onSubmit={() => void handleSubmit()}
                loading={loading}
              />
              <p className="inline-composer__hint">Press Enter to send · Shift+Enter for new line</p>
            </div>
          </div>
        )}

        {/* Request History tab */}
        {activeTab === "history" && (
          <div className="tab-content">
            <div className="tab-content-header">
              <h2>Request History</h2>
              <p>{requestHistory.length} stored request(s)</p>
            </div>
            <RequestHistory
              items={requestHistory}
              selectedRequestId={selectedRequest?.request_id ?? null}
              onSelect={(requestId) => void handleSelectRequest(requestId)}
            />
          </div>
        )}

        {/* Audit Trail tab */}
        {activeTab === "audit" && (
          <div className="tab-content">
            <div className="tab-content-header">
              <h2>Audit Trail</h2>
              <p>{auditRecords.length} audit record(s)</p>
            </div>
            <AuditViewer records={auditRecords} />
          </div>
        )}

        {/* Trace & Debug tab */}
        {activeTab === "trace" && (
          <div className="tab-content">
            <div className="tab-content-header">
              <h2>Trace & Debug</h2>
              <p>Inspect the last request's tool path and authorization outcome.</p>
            </div>
            <TracePanel trace={selectedRequest?.trace ?? null} request={selectedRequest} health={health} />
            {showOllamaModelControls && (
              <div className="panel" style={{ marginTop: 20 }}>
                <div className="panel__header">
                  <h2>Local Model</h2>
                  <span className="panel__eyebrow">Ollama</span>
                </div>
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <select
                    className="select-input"
                    style={{ flex: 1, minWidth: 180 }}
                    value={activeLocalModel}
                    onChange={(e) => setActiveLocalModel(e.target.value)}
                    disabled={localModels.length === 0 || modelSwitching}
                  >
                    {localModels.map((model) => (
                      <option key={model.name} value={model.name}>
                        {model.name}
                        {model.parameter_size ? ` — ${model.parameter_size}` : ""}
                      </option>
                    ))}
                  </select>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void handleModelSwitch()}
                    disabled={!activeLocalModel || modelSwitching}
                  >
                    {modelSwitching ? "Switching..." : "Use model"}
                  </button>
                </div>
                <p className="muted-text" style={{ marginTop: 8 }}>
                  Switching updates the active Ollama model for future requests without changing the approved tool flow.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
