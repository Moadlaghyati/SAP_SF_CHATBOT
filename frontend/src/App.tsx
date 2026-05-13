import { startTransition, useEffect, useRef, useState } from "react";
import logo from "./assets/logo.png";
import {
  fetchAudit,
  fetchDemoUsers,
  fetchHealth,
  fetchLocalModels,
  fetchRequest,
  fetchRequests,
  sapLogin,
  sendChat,
  switchDemoUser,
  switchLocalModel,
  uploadAttachment,
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

interface WeatherInfo {
  temp: string;
  desc: string;
  city: string;
  emoji: string;
}

function getWeatherEmoji(code: number): string {
  if (code === 113) return "☀️";
  if (code === 116) return "⛅";
  if (code <= 122) return "☁️";
  if (code <= 260) return "🌫️";
  if (code <= 314) return "🌧️";
  if (code <= 377) return "❄️";
  return "⛈️";
}

function ChatBubbleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>
  );
}

function HistoryIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/>
      <line x1="16" y1="17" x2="8" y2="17"/>
      <polyline points="10 9 9 9 8 9"/>
    </svg>
  );
}

function AuditIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/>
      <line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2"/>
      <line x1="16" y1="2" x2="16" y2="6"/>
      <line x1="8" y1="2" x2="8" y2="6"/>
      <line x1="3" y1="10" x2="21" y2="10"/>
      <rect x="7" y="14" width="3" height="3" rx="0.5" fill="currentColor" stroke="none"/>
    </svg>
  );
}

function TeamIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
      <circle cx="9" cy="7" r="4"/>
      <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
      <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
    </svg>
  );
}

function BuildingIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="2" width="18" height="20" rx="1"/>
      <line x1="3" y1="9" x2="21" y2="9"/>
      <line x1="3" y1="16" x2="21" y2="16"/>
      <line x1="9" y1="2" x2="9" y2="22"/>
      <line x1="15" y1="2" x2="15" y2="22"/>
    </svg>
  );
}

const FAQ_ITEMS = [
  { q: "What can PeoplePilot help me with?", a: "PeoplePilot queries absence records, time off, sick leaves, and vacation data directly from SAP SuccessFactors using plain language." },
  { q: "How do I check my own absences?", a: "Ask \"Show my absences this year\" or \"How many sick days did I take this month?\" — no need for exact field names." },
  { q: "Who can see other employees' data?", a: "HR Admins see everyone. Managers see their team. Employees see only their own data." },
  { q: "What date formats are supported?", a: "Natural language works: \"this week\", \"last month\", \"April 2026\", or specific dates like \"04-05-2026\" (day-month-year)." },
  { q: "Can I export the results?", a: "Yes — every absence table has an Excel export button and an Add to Calendar button directly in the response." },
];

const CATEGORIES = [
  {
    Icon: CalendarIcon,
    colorClass: "category-card__icon-wrap--purple",
    title: "Absence Lookup",
    description: "Get absence details by employee, date range, or absence type.",
    badge: "Popular",
    prompts: [
      "How many absences did Walid Regragi have this month?",
      "Show Ilham Tbato's absences in April 2026.",
      "List Eduardo Dominguez's absences this year.",
    ],
  },
  {
    Icon: TeamIcon,
    colorClass: "category-card__icon-wrap--purple",
    title: "Team Overview",
    description: "View your team's absence summary and trends.",
    badge: "Team Insights",
    prompts: [
      "Who on my team is absent this week?",
      "Show my team's absences this month.",
      "Is there anyone in Walid Regragi's department absent this month?",
    ],
  },
  {
    Icon: BuildingIcon,
    colorClass: "category-card__icon-wrap--purple",
    title: "Company Wide",
    description: "Get company-wide absence insights and reports.",
    badge: "Reports",
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
  const [weather, setWeather] = useState<WeatherInfo | null>(null);
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [sapLoginInput, setSapLoginInput] = useState("");
  const [sapLoginLoading, setSapLoginLoading] = useState(false);
  const [sapLoginError, setSapLoginError] = useState<string | null>(null);
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
    fetch("https://wttr.in/?format=j1")
      .then((r) => r.json())
      .then((data) => {
        const cond = data.current_condition?.[0];
        const area = data.nearest_area?.[0];
        if (cond && area) {
          setWeather({
            temp: cond.temp_C ?? "?",
            desc: cond.weatherDesc?.[0]?.value ?? "",
            city: area.areaName?.[0]?.value ?? "",
            emoji: getWeatherEmoji(Number(cond.weatherCode ?? 113)),
          });
        }
      })
      .catch(() => {});
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
    const apiActiveUserId = demoUsersResult.status === "fulfilled" ? demoUsersResult.value.active_user_id : null;
    const isSapModeLocal = healthResult.status === "fulfilled" && healthResult.value.connector_backend === "successfactors";
    // In SAP mode always use the server-designated active user (auto-registered at startup) so the right org permissions apply.
    const initialUserId =
      isSapModeLocal && apiActiveUserId && nextDemoUsers.some((u) => u.user_id === apiActiveUserId)
        ? apiActiveUserId
        : pickInitialUserId(nextDemoUsers, storedUserId, apiActiveUserId);
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

  async function handleUploadAndResubmit(triggerMessage: ChatMessage, file: File) {
    if (loading) return;
    // The original request text is the last user message before this assistant message
    const msgIndex = messages.findIndex((m) => m.id === triggerMessage.id);
    const rawText = msgIndex > 0
      ? [...messages].slice(0, msgIndex).reverse().find((m) => m.role === "user")?.text ?? ""
      : "";
    // Strip any previously prepended "[Attachment: ...]" prefix so re-attempts send a clean message
    const originalText = rawText.replace(/^\[Attachment:[^\]]+\]\s*/, "");
    if (!originalText) return;

    setLoading(true);
    const pendingMessageId = `assistant-pending-${Date.now()}`;
    setPendingRequestStartedAt(Date.now());
    setBootstrapError(null);

    const userMessage: ChatMessage = { id: `user-${Date.now()}`, role: "user", text: `[Attachment: ${file.name}] ${originalText}` };
    const pendingAssistantMessage: ChatMessage = {
      id: pendingMessageId,
      role: "assistant",
      text: `Uploading ${file.name} and re-submitting request...`,
      pending: true,
    };
    setMessages((current) => [...current, userMessage, pendingAssistantMessage]);

    try {
      const uploaded = await uploadAttachment(file, activeUserId);
      const response = await sendChat(originalText, activeUserId, uploaded.record_key);
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

  async function handleSapLogin() {
    const uid = sapLoginInput.trim();
    if (!uid) return;
    setSapLoginLoading(true);
    setSapLoginError(null);
    try {
      const user = await sapLogin(uid);
      setActiveUserId(user.user_id);
      window.localStorage.setItem(ACTIVE_USER_STORAGE_KEY, user.user_id);
      setDemoUsers((prev) => {
        const filtered = prev.filter((u) => u.user_id !== user.user_id);
        return [user, ...filtered];
      });
      setSapLoginInput("");
    } catch (err) {
      setSapLoginError(err instanceof Error ? err.message : "Login failed. Check the user ID and try again.");
    } finally {
      setSapLoginLoading(false);
    }
  }

  function handleLogout() {
    window.localStorage.removeItem(ACTIVE_USER_STORAGE_KEY);
    setActiveUserId("");
    setMessages([]);
    setActiveConversationId(null);
    activeConvIdRef.current = null;
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
      durationMs: response.trace.duration_ms,
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
  const isSapMode = (health?.connector_backend ?? "") === "successfactors";
  const showSapLogin = isSapMode && !activeUserId;

  if (showSapLogin) {
    return (
      <div className="sap-login-screen">
        <div className="sap-login-card">
          <div className="sap-login-card__logo">
            <img src={logo} alt="PeoplePilot" style={{ width: 56, height: 56, objectFit: "contain" }} />
          </div>
          <h1 className="sap-login-card__title">Welcome to PeoplePilot</h1>
          <p className="sap-login-card__sub">Sign in with your SAP SuccessFactors User ID</p>
          <div className="sap-login-card__form">
            <input
              className="sap-login-card__input"
              type="text"
              placeholder="e.g. cosys_ml"
              value={sapLoginInput}
              onChange={(e) => setSapLoginInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void handleSapLogin()}
              disabled={sapLoginLoading}
              autoFocus
            />
            <button
              className="sap-login-card__btn"
              type="button"
              onClick={() => void handleSapLogin()}
              disabled={sapLoginLoading || !sapLoginInput.trim()}
            >
              {sapLoginLoading ? "Signing in…" : "Sign In"}
            </button>
          </div>
          {sapLoginError && <p className="sap-login-card__error">{sapLoginError}</p>}
        </div>
      </div>
    );
  }

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
          <img src={logo} alt="PeoplePilot" className="brand-icon" style={{ width: 32, height: 32, objectFit: "contain" }} />
          <span className="brand-name">PeoplePilot</span>
        </button>

        <nav className="sidebar__nav">
          <span className="sidebar__section-label">AI ASSISTANT</span>
          <button
            type="button"
            className="nav-item nav-item--primary"
            onClick={startNewChat}
          >
            <span className="nav-item__icon">✦</span>
            New Chat
          </button>
          <button
            type="button"
            className={`nav-item ${activeTab === "chat" ? "nav-item--active" : ""}`}
            onClick={() => setActiveTab("chat")}
          >
            <span className="nav-item__icon"><ChatBubbleIcon /></span>
            Chat History
          </button>

          {conversations.filter((c) => isSapMode || c.userId === activeUserId).length > 0 && (
            <>
              <span className="sidebar__section-label sidebar__section-label--recents">Recents</span>
              {conversations
                .filter((c) => isSapMode || c.userId === activeUserId)
                .slice(0, 15)
                .map((conv) => (
                  <button
                    key={conv.id}
                    type="button"
                    className={`conv-item ${activeConversationId === conv.id ? "conv-item--active" : ""}`}
                    onClick={() => loadConversation(conv)}
                  >
                    <span className="conv-item__icon"><ChatBubbleIcon /></span>
                    <span className="conv-item__title">{conv.title}</span>
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

          <span className="sidebar__section-label">DATA & TOOLS</span>
          <button
            type="button"
            className={`nav-item ${activeTab === "history" ? "nav-item--active" : ""}`}
            onClick={() => setActiveTab("history")}
          >
            <span className="nav-item__icon"><HistoryIcon /></span>
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
            <span className="nav-item__icon"><AuditIcon /></span>
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
            <span className="nav-item__icon"><GearIcon /></span>
            Trace & Debug
          </button>
        </nav>

        <div className="sidebar__bottom" ref={userMenuRef}>
          {/* SAP mode: just show current user + logout */}
          {isSapMode ? (
            <div className="sidebar__user sidebar__user--sap">
              <div className="user-avatar">
                {activeUser ? userInitials(activeUser.display_name) : "?"}
              </div>
              <div className="user-info">
                <div className="user-name">{activeUser?.display_name ?? activeUserId}</div>
                <div className="user-role">{activeUser?.job_title || activeUser?.role || ""}</div>
              </div>
              <button
                type="button"
                className="sidebar__logout-btn"
                title="Sign out"
                onClick={handleLogout}
              >↩</button>
            </div>
          ) : (
            <>
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
            </>
          )}
        </div>
      </aside>

      {/* ── Main area ── */}
      <div className="main-area">
        <header className="topbar">
          <div className="topbar__left">
            <span className="topbar__page">SuccessFactors HR</span>
            <span className="topbar__dot-sep">·</span>
            <span className="topbar__breadcrumb">{TAB_LABELS[activeTab]}</span>
          </div>
          <div className="topbar__right">
            <span className="topbar__local-badge">{health?.model_inference ?? "Local"}</span>
            <button type="button" className="topbar__bell" title="Notifications">🔔</button>
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
            {weather && (
              <div className="weather-widget">
                <span className="weather-widget__emoji">{weather.emoji}</span>
                <span className="weather-widget__temp">{weather.temp}°C</span>
                <span className="weather-widget__desc">{weather.desc}</span>
                {weather.city && <span className="weather-widget__city">· {weather.city}</span>}
              </div>
            )}
            <div className="welcome-icon-wrap">
              <img src={logo} alt="PeoplePilot" style={{ width: 64, height: 64, objectFit: "contain" }} />
            </div>
            <h1 className="welcome-heading">
              How can I help you with your{" "}
              <span className="welcome-heading__accent">HR data</span> today?
            </h1>
            <p className="welcome-sub">
              Get quick answers about absences, time off, and employee records — securely from your SAP SuccessFactors.
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
                  <div className="category-card__body">
                    <div className="category-card__head">
                      <div className={`category-card__icon-wrap ${cat.colorClass}`}>
                        <cat.Icon />
                      </div>
                      <h3 className="category-card__title">{cat.title}</h3>
                    </div>
                    <p className="category-card__desc">{cat.description}</p>
                    <ul className="category-card__prompts">
                      {cat.prompts.map((prompt) => (
                        <li
                          key={prompt}
                          className="category-card__prompt"
                          onClick={() => setInputValue(prompt)}
                        >
                          <span className="category-card__prompt-arrow">&gt;</span>
                          {prompt}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="category-card__footer">
                    <span className="category-card__badge">☆ {cat.badge}</span>
                  </div>
                </div>
              ))}
            </div>

            {/* FAQ Section */}
            <div className="faq-section">
              <div className="faq-section__header">
                <h2 className="faq-section__title">Frequently Asked Questions</h2>
                <button type="button" className="faq-section__view-all">View all</button>
              </div>
              <div className="faq-grid">
                {FAQ_ITEMS.map((item, i) => (
                  <div key={i} className={`faq-item ${openFaq === i ? "faq-item--open" : ""}`}>
                    <button
                      type="button"
                      className="faq-item__question"
                      onClick={() => setOpenFaq(openFaq === i ? null : i)}
                    >
                      <span>{item.q}</span>
                      <span className="faq-item__chevron">&gt;</span>
                    </button>
                    {openFaq === i && (
                      <div className="faq-item__answer">{item.a}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Chat view with messages */}
        {activeTab === "chat" && !showWelcome && (
          <div className="chat-view">
            <div className="chat-view__messages">
              <MessageList messages={messages} pendingElapsedSeconds={pendingElapsedSeconds} onUploadAttachment={(msg, file) => void handleUploadAndResubmit(msg, file)} />
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

        {/* Floating bot button — only on non-chat tabs so it never overlaps the composer */}
        {activeTab !== "chat" && (
          <button type="button" className="floating-bot-btn" title="New Chat" onClick={startNewChat}>
            🤖
          </button>
        )}
      </div>
    </div>
  );
}

export default App;
