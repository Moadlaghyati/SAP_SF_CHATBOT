import { startTransition, useEffect, useState } from "react";
import {
  fetchAudit,
  fetchDemoUsers,
  fetchHealth,
  fetchLocalModels,
  fetchRequest,
  fetchRequests,
  sendChat,
  switchLocalModel,
  switchDemoUser,
} from "./api/client";
import { AuditViewer } from "./components/AuditViewer";
import { ChatComposer } from "./components/ChatComposer";
import { DemoUserSwitcher } from "./components/DemoUserSwitcher";
import { MessageList } from "./components/MessageList";
import { RequestHistory } from "./components/RequestHistory";
import { SamplePrompts } from "./components/SamplePrompts";
import { StatusPill } from "./components/StatusPill";
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

const DEMO_PROMPTS = [
  "hello",
  "what can you do?",
  "How many absences did Sara Bennani have between 2026-01-01 and 2026-03-31?",
  "How many sick leaves did Sara Bennani have in Q1 2026?",
  "List Sara Bennani's absences in March 2026.",
  "How many absences did my direct report Ahmed have last month?",
  "Show the absence breakdown by type for Yasmine in February 2026.",
  "How many absences did Karim Ouali have in March 2026?",
  "How many absences did Yasmine have in February 2026?",
  "What is Sara Bennani's payroll amount?",
];

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

function pickInitialUserId(
  users: DemoUserSummary[],
  storedUserId: string | null,
  activeUserId: string | null,
): string {
  if (storedUserId && users.some((user) => user.user_id === storedUserId)) {
    return storedUserId;
  }

  if (activeUserId && users.some((user) => user.user_id === activeUserId)) {
    return activeUserId;
  }

  return users[0]?.user_id ?? "demo_manager_meryem";
}

function formatErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }

  return "The backend did not return a usable response.";
}

function buildBootstrapErrorMessage(
  failedAreas: string[],
  error: unknown,
  usingFallbackUsers: boolean,
): string {
  const resourceLabel = failedAreas.length > 0 ? failedAreas.join(", ") : "backend data";
  const fallbackCopy = usingFallbackUsers ? " Built-in demo personas are shown for now." : "";
  return `Could not load ${resourceLabel} from ${API_BASE_URL}.${fallbackCopy} Start the backend over http://, not https://, then retry. Example: http://127.0.0.1:8001/api/health. Details: ${formatErrorMessage(error)}`;
}

function App() {
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

  useEffect(() => {
    const stored = window.localStorage.getItem(ACTIVE_USER_STORAGE_KEY);
    if (stored) {
      setActiveUserId(stored);
    }
  }, []);

  useEffect(() => {
    void loadBootstrap();
  }, []);

  useEffect(() => {
    if (!loading || pendingRequestStartedAt === null) {
      setPendingElapsedSeconds(0);
      return;
    }

    const updateElapsed = () => {
      setPendingElapsedSeconds(Math.max(0, Math.floor((Date.now() - pendingRequestStartedAt) / 1000)));
    };

    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [loading, pendingRequestStartedAt]);

  async function loadBootstrap() {
    const [healthResult, demoUsersResult, requestsResult, auditResult, localModelsResult] = await Promise.allSettled([
      fetchHealth(),
      fetchDemoUsers(),
      fetchRequests(),
      fetchAudit(),
      fetchLocalModels(),
    ]);

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
    const nextUsingFallbackUsers = demoUsersResult.status !== "fulfilled" || demoUsersResult.value.items.length === 0;
    setDemoUsers(nextDemoUsers);
    setUsingFallbackUsers(nextUsingFallbackUsers);

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
      startTransition(() => {
        setRequestHistory(requestsResult.value.items);
      });
    } else {
      setRequestHistory([]);
      failedAreas.push("request history");
      firstFailure ??= requestsResult.reason;
    }

    if (auditResult.status === "fulfilled") {
      startTransition(() => {
        setAuditRecords(auditResult.value.items);
      });
    } else {
      setAuditRecords([]);
      failedAreas.push("audit trail");
      firstFailure ??= auditResult.reason;
    }

    if (localModelsResult.status === "fulfilled") {
      setLocalModels(localModelsResult.value.items);
      setLocalModelBackend(localModelsResult.value.backend);
      setActiveLocalModel(
        localModelsResult.value.active_model ?? localModelsResult.value.items[0]?.name ?? "",
      );
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
      setBootstrapError(buildBootstrapErrorMessage(failedAreas, firstFailure, nextUsingFallbackUsers));
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
      startTransition(() => {
        setRequestHistory(requestsResult.value.items);
      });
      requestIdToLoad ??= requestsResult.value.items[0]?.request_id;
    } else {
      failedAreas.push("request history");
      firstFailure ??= requestsResult.reason;
    }

    if (auditResult.status === "fulfilled") {
      startTransition(() => {
        setAuditRecords(auditResult.value.items);
      });
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
          localModelsResult.value.active_model ??
          localModelsResult.value.items[0]?.name ??
          current,
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
        `Using the selected persona locally. Start the backend at ${API_BASE_URL} over http:// to sync the demo user switch and send chat requests. Details: ${formatErrorMessage(error)}`,
      );
    }
  }

  async function handleSubmit() {
    const trimmed = inputValue.trim();
    if (!trimmed || loading) {
      return;
    }

    setLoading(true);
    const pendingMessageId = `assistant-pending-${Date.now()}`;
    setPendingRequestStartedAt(Date.now());
    setBootstrapError(null);
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      text: trimmed,
    };
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
        current.map((message) =>
          message.id === pendingMessageId
            ? {
                ...message,
                text: failureMessage,
                status: "error",
                pending: false,
              }
            : message,
        ),
      );
      setBootstrapError(failureMessage);
    } finally {
      setLoading(false);
      setPendingRequestStartedAt(null);
    }
  }

  async function handleModelSwitch() {
    if (!activeLocalModel || modelSwitching) {
      return;
    }

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
      };

      if (!pendingMessageId) {
        return [...current, nextMessage];
      }

      const replaced = current.some((message) => message.id === pendingMessageId);
      if (!replaced) {
        return [...current, nextMessage];
      }

      return current.map((message) => (message.id === pendingMessageId ? nextMessage : message));
    });
    setSelectedRequest({
      request_id: response.request_id,
      created_at: new Date().toISOString(),
      acting_user: demoUsers.find((user) => user.user_id === activeUserId)?.display_name ?? activeUserId,
      user_role: demoUsers.find((user) => user.user_id === activeUserId)?.role ?? "manager",
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

  const activeUser = demoUsers.find((user) => user.user_id === activeUserId) ?? null;
  const effectiveLlmBackend = health?.llm_backend ?? localModelBackend ?? "unknown";
  const showOllamaModelControls = effectiveLlmBackend === "ollama";

  return (
    <div className="app-shell">
      <div className="background-orb background-orb--left" />
      <div className="background-orb background-orb--right" />

      <header className="hero">
        <div>
          <p className="hero__eyebrow">Local-only HR AI demo</p>
          <h1>SuccessFactors HR Assistant MVP</h1>
          <p className="hero__copy">
            Deterministic orchestration, approved tools only, and no external AI inference.
          </p>
        </div>
        <div className="hero__signals">
          <StatusPill label={`Model inference: ${health?.model_inference ?? "local"}`} />
          <StatusPill label={`External AI calls: ${health?.external_ai_calls ?? "none"}`} />
          <StatusPill label={`Connector: ${health?.connector_backend ?? "mock"}`} />
        </div>
      </header>

      {bootstrapError ? <div className="banner banner--error">{bootstrapError}</div> : null}

      <main className="main-column">
        <div className="top-row">
          <DemoUserSwitcher
            users={demoUsers}
            activeUserId={activeUserId}
            onChange={(userId) => void handleUserChange(userId)}
            usingFallbackUsers={usingFallbackUsers}
          />
          <section className="panel panel--compact trust-panel">
            <div className="panel__header">
              <h2>Current Access</h2>
              <span className="panel__eyebrow">{activeUser?.role ?? "loading"}</span>
            </div>
            <p className="trust-panel__headline">{activeUser?.display_name ?? "Loading user..."}</p>
            <p className="muted-text">
              Authorization is enforced in backend code before connector access. The model never sees SAP credentials.
            </p>
              <ul className="trust-list">
                <li>Local model backend: {health?.llm_backend ?? "unknown"}</li>
                <li>Configured local model: {health?.llm_model ?? "unknown"}</li>
                <li>Selected connector: {health?.connector_backend ?? "mock"}</li>
                <li>{usingFallbackUsers ? "Showing built-in demo personas until the backend responds." : "Live demo users are loaded from the backend."}</li>
              </ul>
              {showOllamaModelControls ? (
                <div className="model-switcher">
                  <label className="model-switcher__label" htmlFor="local-model-select">
                    Installed local models
                  </label>
                  <div className="model-switcher__controls">
                    <select
                      id="local-model-select"
                      className="select-input"
                      value={activeLocalModel}
                      onChange={(event) => setActiveLocalModel(event.target.value)}
                      disabled={localModels.length === 0 || modelSwitching}
                    >
                      {localModels.map((model) => (
                        <option key={model.name} value={model.name}>
                          {model.name}
                          {model.parameter_size ? ` - ${model.parameter_size}` : ""}
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
                  <p className="muted-text">
                    Switching updates the active Ollama model for future requests without changing the approved tool flow.
                  </p>
                </div>
              ) : (
                <p className="muted-text">
                  Start the backend with <code>LLM_BACKEND=ollama</code> to enable runtime local model switching.
                </p>
              )}
            </section>
        </div>

        <SamplePrompts prompts={DEMO_PROMPTS} onPick={setInputValue} />
        <ChatComposer
          value={inputValue}
          onChange={setInputValue}
          onSubmit={() => void handleSubmit()}
          loading={loading}
        />
        <MessageList messages={messages} pendingElapsedSeconds={pendingElapsedSeconds} />

        <section className="advanced-stack">
          <details className="details-panel">
            <summary className="details-panel__summary">
              <span>Request History</span>
              <span className="panel__eyebrow">{requestHistory.length} stored request(s)</span>
            </summary>
            <div className="details-panel__body">
              <RequestHistory
                items={requestHistory}
                selectedRequestId={selectedRequest?.request_id ?? null}
                onSelect={(requestId) => void handleSelectRequest(requestId)}
              />
            </div>
          </details>

          <details className="details-panel">
            <summary className="details-panel__summary">
              <span>Trace & Debug</span>
              <span className="panel__eyebrow">Expand when you want internals</span>
            </summary>
            <div className="details-panel__body">
              <TracePanel trace={selectedRequest?.trace ?? null} request={selectedRequest} health={health} />
            </div>
          </details>

          <details className="details-panel">
            <summary className="details-panel__summary">
              <span>Audit Trail</span>
              <span className="panel__eyebrow">{auditRecords.length} audit record(s)</span>
            </summary>
            <div className="details-panel__body">
              <AuditViewer records={auditRecords} />
            </div>
          </details>
        </section>
      </main>
    </div>
  );
}

export default App;
