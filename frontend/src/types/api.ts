export type RequestStatus =
  | "success"
  | "clarification_required"
  | "forbidden"
  | "not_found"
  | "unsupported"
  | "invalid_input"
  | "unavailable"
  | "error";

export interface DemoUserSummary {
  user_id: string;
  display_name: string;
  role: "employee" | "manager" | "hr_admin";
  job_title?: string;
  employee_id: string | null;
  description: string;
}

export interface DemoUsersResponse {
  items: DemoUserSummary[];
  active_user_id: string | null;
}

export interface LocalModelSummary {
  name: string;
  modified_at: string | null;
  size: number | null;
  family: string | null;
  parameter_size: string | null;
  quantization_level: string | null;
}

export interface LocalModelsResponse {
  backend: string;
  active_model: string | null;
  items: LocalModelSummary[];
}

export interface SwitchLocalModelResponse {
  backend: string;
  active_model: string;
}

export interface HealthComponent {
  name: string;
  ok: boolean;
  details: string;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
  connector_backend: string;
  llm_backend: string;
  llm_model: string | null;
  model_inference: string;
  external_ai_calls: string;
  components: HealthComponent[];
}

export interface ToolTrace {
  request_id: string;
  request_message: string;
  process_steps: Array<{
    step: string;
    status: string;
    detail: string;
    data: Record<string, unknown>;
    timestamp: string;
  }>;
  detected_intent: string | null;
  parsed_request: Record<string, unknown>;
  tool_name: string | null;
  tool_arguments: Record<string, unknown>;
  data_source: string | null;
  authorization_outcome: string;
  authorization_reason: string | null;
  target_employee_id: string | null;
  target_employee_display_name: string | null;
  model_inference: string;
  llm_backend: string | null;
  llm_model: string | null;
  external_ai_calls: string;
  status: string;
  errors: string[];
  minimized_result: Record<string, unknown> | null;
  answer_metadata: Record<string, unknown>;
  created_at: string;
  completed_at: string | null;
  duration_ms: number | null;
}

export interface ChatResponse {
  request_id: string;
  status: RequestStatus;
  answer: string;
  trace: ToolTrace;
}

export interface RequestListItem {
  request_id: string;
  created_at: string;
  acting_user: string;
  user_role: string;
  question: string;
  parsed_intent: string | null;
  tool_name: string | null;
  target_employee_id: string | null;
  authorization_outcome: string;
  status: RequestStatus;
  duration_ms: number | null;
}

export interface RequestDetail extends RequestListItem {
  answer: string | null;
  trace: ToolTrace | null;
}

export interface RequestListResponse {
  items: RequestListItem[];
}

export interface AuditRecord {
  request_id: string;
  timestamp: string;
  acting_user: string;
  user_role: string;
  original_question: string;
  parsed_intent: string | null;
  tool_called: string | null;
  target_employee: string | null;
  authorization_outcome: string;
  final_status: RequestStatus;
  duration_ms: number;
  data_source: string | null;
}

export interface AuditListResponse {
  items: AuditRecord[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: RequestStatus;
  requestId?: string;
  pending?: boolean;
  minimizedResult?: Record<string, unknown> | null;
}
