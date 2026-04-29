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
  DemoUserSummary,
  HealthResponse,
  LocalModelSummary,
  RequestDetail,
  RequestListItem,
} from "./types/api";

type ActiveTab = "chat" | "history" | "audit" | "trace";

const ACTIVE_USER_STORAGE_KEY = "hr-ai-assistant-active-user";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

const FALLBACK_DEMO_USERS: DemoUserSummary[] = [
  {
    user_id: "demo_employee_sara",
    display_name: "Sara Bennani",
    role: "employee",
    employee_id: "E1001",
    description: "Employee demo user who can view only Sara's own data.",
  },
  {
    user_id: "demo_manager_meryem",
    display_name: "Meryem Ait Said",
    role: "manager",
    employee_id: "E1000",
    description: "Manager demo user with access to self and direct reports Sara, Ahmed, and Yasmine Alami.",
  },
  {
    user_id: "demo_manager_omar",
    display_name: "Omar Kabbaj",
    role: "manager",
    employee_id: "E1004",
    description: "Manager demo user with access to self, Karim Ouali, and Yasmine Amrani.",
  },
  {
    user_id: "demo_hr_admin_nadia",
    display_name: "Nadia El Fassi",
    role: "hr_admin",
    employee_id: "E9000",
    description: "HR admin demo user with access to all seeded employees.",
  },
];

const CATEGORIES = [
  {
    icon: "📅",
    title: "Absence Lookup",
    prompts: [
      "How many absences did Sara Bennani have between 2026-01-01 and 2026-03-31?",
      "List Sara Bennani's absences in March 2026.",
      "How many sick leaves did Sara Bennani have in Q1 2026?",
    ],
  },
  {
    icon: "👥",
    title: "Team Overview",
    prompts: [
      "How many absences did my direct report Ahmed have last month?",
      "Show the absence breakdown by type for Yasmine in February 2026.",
      "How many absences did Karim Ouali have in March 2026?",
    ],
  },
  {
    icon: "💡",
    title: "Help & Capabilities",
    prompts: [
      "hello",
      "what can you do?",
      "What is Sara Bennani's payroll amount?",
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
  return users[0]?.user_id ?? "demo_manager_meryem";
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
  const [activeUserId, setActiveUserId] = useState<string>("demo_manager_meryem");
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

  const messagesEndRef = useRef<HTMLDivElement>(null);

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
      text: "Thinking locally with Ollama...",
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

  function applyChatResponse(response: ChatResponse, pendingMessageId?: string) {
    setMessages((current) => {
      const nextMessage: ChatMessage = {
        id: `assistant-${response.request_id}`,
        role: "assistant",
        text: response.answer,
        status: response.status,
        requestId: response.request_id,
        pending: false,
        minimizedResult: response.trace.minimized_result,
      };
      if (!pendingMessageId) return [...current, nextMessage];
      const replaced = current.some((m) => m.id === pendingMessageId);
      if (!replaced) return [...current, nextMessage];
      return current.map((m) => (m.id === pendingMessageId ? nextMessage : m));
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
        <div className="sidebar__brand">
          <div className="brand-icon">🤖</div>
          <span className="brand-name">HR Assistant</span>
        </div>

        <nav className="sidebar__nav">
          <span className="sidebar__section-label">AI Tools</span>
          <button
            type="button"
            className={`nav-item ${activeTab === "chat" ? "nav-item--active" : ""}`}
            onClick={() => setActiveTab("chat")}
          >
            <span className="nav-item__icon">💬</span>
            Chat AI
          </button>

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

        <div className="sidebar__bottom">
          <div className="sidebar__user">
            <div className="user-avatar">
              {activeUser ? userInitials(activeUser.display_name) : "?"}
            </div>
            <div className="user-info">
              <div className="user-name">{activeUser?.display_name ?? "Loading..."}</div>
              <div className="user-role">{activeUser?.role ?? ""}</div>
            </div>
          </div>
          <select
            style={{
              width: "100%",
              background: "rgba(255,255,255,0.07)",
              color: "rgba(255,255,255,0.75)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: "8px",
              fontSize: "0.78rem",
              padding: "6px 8px",
              cursor: "pointer",
            }}
            value={activeUserId}
            onChange={(e) => void handleUserChange(e.target.value)}
            disabled={demoUsers.length === 0}
          >
            {demoUsers.map((user) => (
              <option key={user.user_id} value={user.user_id}>
                {user.display_name} ({user.role})
              </option>
            ))}
          </select>
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
