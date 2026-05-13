import { useRef } from "react";
import type { ChatMessage } from "../types/api";
import { StatusPill } from "./StatusPill";

function formatDuration(ms: number): string {
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${m}m ${s}s`;
}

const ABSENCE_LABELS: Record<string, string> = {
  // ── MAR_ codes ───────────────────────────────────────
  MAR_SICKLEAVE: "Sick Leave",
  MAR_VACA_EXE: "Vacation",
  MAR_VACATION: "Vacation",
  MAR_DOCVT: "Doctor's Visit / Medical Test",
  MAR_WRKAC: "Work-related Accident",
  MAR_COMIL: "Common Illness",
  MAR_ILLAC: "Illness or Accident",
  MAR_EXAMS: "Exams",
  MAR_TRAIN: "Training",
  MAR_FORCEMAJEURE: "Inescapable Duty",
  MAR_INSDU: "Inescapable Duty",
  MAR_MARLEAV: "Marriage Leave",
  MAR_CHLDM: "Child Marriage of an Employee",
  MAR_MATLEAV: "Maternity Leave",
  MAR_PATLEAV: "Paternity Leave",
  MAR_DAYOF: "Day / Time Off in Lieu",
  MAR_DESPC: "Death of Spouse / Child",
  MAR_DE2DK: "Death of Family Member (2nd Degree)",
  MAR_SURPC: "Surgical Procedure (Spouse / Child)",
  MAR_MOVEH: "Moving House",
  MAR_CIRLEAV: "Circumcision Leave of Child",
  MAR_COMPUL: "Compulsory Leave of Absence (Childcare)",
  MAR_VOLLA: "Voluntary Leave of Absence",
  MAR_UNJUSTIFIEDABSENCE: "Unjustified Absence",
  MAR_UNJUSTIFIEDABSENC: "Unjustified Absence",
  MAR_JUSTABS: "Justified Absence",
  MAR_REMOTE_WORK: "Remote Work",
  // ── MA_ codes (legacy) ───────────────────────────────
  MA_SICK_LEAVE: "Sick Leave",
  MA_VACAT: "Vacation",
  MA_DOCVT: "Doctor's Visit / Medical Test",
  MA_WRKAC: "Work-related Accident",
  MA_COMIL: "Common Illness",
  MA_ILLAC: "Illness or Accident",
  MA_EXAMS: "Exams",
  MA_TRAIN: "Training",
  MA_INSDU: "Inescapable Duty",
  MA_MARLEAV: "Marriage Leave",
  MA_CHLDM: "Child Marriage of an Employee",
  MA_MATLEAV: "Maternity Leave",
  MA_PATLEAV: "Paternity Leave",
  MA_DAYOF: "Day / Time Off in Lieu",
  MA_DESPC: "Death of Spouse / Child",
  MA_DE2DK: "Death of Family Member (2nd Degree)",
  MA_SURPC: "Surgical Procedure (Spouse / Child)",
  MA_MOVEH: "Moving House",
  MA_CIRLEAV: "Circumcision",
  MA_COMPUL: "Compulsory Leave of Absence (Childcare)",
  MA_VOLLA: "Voluntary Leave of Absence",
  MA_UNJUSTIFIEDABSENCE: "Unjustified Absence",
  MA_JUSTABS: "Justified Absence",
  MA_REMOTE_WORK: "Remote Work",
  MA_Work: "Remote Work",
};

function getAbsenceLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return ABSENCE_LABELS[code] ?? code;
}

interface MessageListProps {
  messages: ChatMessage[];
  pendingElapsedSeconds?: number;
  onUploadAttachment?: (message: ChatMessage, file: File) => void;
}

interface AbsenceRow {
  user_id: string;
  absence_type: string;
  start_date: string;
  end_date: string;
  approval_status: string;
  quantity_in_days: number | null;
}

interface AbsenceData {
  absences: AbsenceRow[];
  employeeName: string | null;
  startDate: string;
  endDate: string;
  isWorkforce: boolean;
  department: string | null;
  isDepartmentOverlap: boolean;
  memberNames: Record<string, string>;
}

function extractAbsenceData(message: ChatMessage): AbsenceData | null {
  if (message.role !== "assistant" || message.status !== "success" || !message.minimizedResult) {
    return null;
  }
  const absences = message.minimizedResult.absences;
  if (!Array.isArray(absences) || absences.length === 0) return null;

  const resultType = message.minimizedResult.type as string | undefined;

  if (resultType === "department_overlap") {
    const targetEmployee = message.minimizedResult.target_employee as Record<string, string> | null | undefined;
    const dateRange = message.minimizedResult.date_range as Record<string, string> | undefined;
    const memberNames = (message.minimizedResult.member_names as Record<string, string> | null) ?? {};
    return {
      absences: absences as AbsenceRow[],
      employeeName: targetEmployee?.name ?? targetEmployee?.userId ?? null,
      startDate: dateRange?.startDate ?? "",
      endDate: dateRange?.endDate ?? "",
      isWorkforce: true,
      department: (message.minimizedResult.department as string | null) ?? null,
      isDepartmentOverlap: true,
      memberNames,
    };
  }

  const employee = message.minimizedResult.employee as Record<string, string> | null | undefined;
  const dateRange = message.minimizedResult.date_range as Record<string, string> | undefined;
  const memberNames = (message.minimizedResult.member_names as Record<string, string> | null) ?? {};
  const hasMemberNames = Object.keys(memberNames).length > 0;

  return {
    absences: absences as AbsenceRow[],
    employeeName: employee?.name ?? employee?.userId ?? null,
    startDate: dateRange?.startDate ?? "",
    endDate: dateRange?.endDate ?? "",
    isWorkforce: employee == null,
    department: null,
    isDepartmentOverlap: hasMemberNames,
    memberNames,
  };
}

function statusBadgeClass(status: string): string {
  const s = status.toLowerCase();
  if (s === "approved") return "absence-badge--approved";
  if (s === "pending") return "absence-badge--pending";
  if (s === "rejected" || s === "cancelled") return "absence-badge--rejected";
  return "absence-badge--default";
}

function toXmlSafe(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildSpreadsheetML(headers: string[], rows: (string | number | null)[][]): string {
  const xmlRows = [headers as (string | number | null)[], ...rows]
    .map(
      (row) =>
        `<Row>${row
          .map((cell) =>
            typeof cell === "number"
              ? `<Cell><Data ss:Type="Number">${cell}</Data></Cell>`
              : `<Cell><Data ss:Type="String">${toXmlSafe(cell)}</Data></Cell>`
          )
          .join("")}</Row>`
    )
    .join("\n      ");

  return `<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
          xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <Styles>
    <Style ss:ID="Header">
      <Font ss:Bold="1"/>
    </Style>
  </Styles>
  <Worksheet ss:Name="Absences">
    <Table>
      ${xmlRows}
    </Table>
  </Worksheet>
</Workbook>`;
}

function downloadExcel(message: ChatMessage) {
  const headers = ["Employee", "Absence Type", "Start Date", "End Date", "Status", "Days"];
  let rows: (string | number | null)[][];
  let employeeLabel: string;
  let period: string;

  const comparison = message.minimizedResult?.comparison as ComparisonData | undefined;
  if (comparison) {
    const absences = (message.minimizedResult?.absences as AbsenceRow[] | undefined) ?? [];
    const dateRange = message.minimizedResult?.date_range as Record<string, string> | undefined;
    employeeLabel = `${comparison.employee_a.name}_vs_${comparison.employee_b.name}`;
    period = dateRange ? `${dateRange.startDate}_${dateRange.endDate}` : "export";
    rows = absences.map((a) => {
      const name = a.user_id === comparison.employee_a.user_id ? comparison.employee_a.name : comparison.employee_b.name;
      return [name, getAbsenceLabel(a.absence_type), a.start_date ?? "", a.end_date ?? "", a.approval_status ?? "", a.quantity_in_days ?? null];
    });
  } else {
    const data = extractAbsenceData(message);
    if (!data) return;
    const { absences, employeeName, startDate, endDate, isWorkforce, isDepartmentOverlap, memberNames } = data;
    employeeLabel = employeeName ?? "All_Employees";
    period = startDate && endDate ? `${startDate}_${endDate}` : "export";
    rows = absences.map((a) => {
      const emp = isWorkforce
        ? (isDepartmentOverlap ? (memberNames[a.user_id] ?? a.user_id) : a.user_id)
        : (employeeName ?? a.user_id);
      return [emp, getAbsenceLabel(a.absence_type), a.start_date ?? "", a.end_date ?? "", a.approval_status ?? "", a.quantity_in_days ?? null];
    });
  }

  const xml = buildSpreadsheetML(headers, rows);
  const blob = new Blob([xml], { type: "application/vnd.ms-excel;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `absences_${employeeLabel.replace(/\s+/g, "_")}_${period}.xls`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}



function buildOutlookUrl(absence: AbsenceRow, label: string): string {
  const nextDay = new Date(absence.end_date + "T00:00:00");
  nextDay.setDate(nextDay.getDate() + 1);
  const enddt = nextDay.toISOString().slice(0, 10);
  const absenceName = getAbsenceLabel(absence.absence_type);

  const params = new URLSearchParams({
    subject: `${absenceName} — ${label}`,
    startdt: absence.start_date,
    enddt,
    body: [
      `Employee: ${label}`,
      `Type: ${absenceName}`,
      `Status: ${absence.approval_status || "—"}`,
      absence.quantity_in_days != null ? `Duration: ${absence.quantity_in_days} day(s)` : "",
    ]
      .filter(Boolean)
      .join("\n"),
    allday: "true",
  });

  return `https://outlook.live.com/calendar/0/deeplink/compose?${params.toString()}`;
}

function addAllToOutlook(message: ChatMessage) {
  const data = extractAbsenceData(message);
  if (!data) return;
  const { absences, employeeName, isWorkforce } = data;
  absences
    .filter((a) => a.start_date && a.end_date)
    .forEach((a) => {
      const label = isWorkforce ? a.user_id : (employeeName ?? a.user_id);
      window.open(buildOutlookUrl(a, label), "_blank", "noopener,noreferrer");
    });
}

interface ComparisonStats {
  total_absences: number;
  total_days: number;
  by_type: Record<string, { count: number; days: number }>;
}

interface ComparisonEmployee {
  user_id: string;
  name: string;
  stats: ComparisonStats;
}

interface ComparisonData {
  employee_a: ComparisonEmployee;
  employee_b: ComparisonEmployee;
}

function ComparisonView({ message }: { message: ChatMessage }) {
  if (!message.minimizedResult) return null;
  const comparison = message.minimizedResult.comparison as ComparisonData | undefined;
  if (!comparison) return null;

  const dateRange = message.minimizedResult.date_range as Record<string, string> | undefined;
  const period = dateRange ? `${dateRange.startDate} to ${dateRange.endDate}` : "";
  const absences = message.minimizedResult.absences as AbsenceRow[] | undefined ?? [];
  const { employee_a, employee_b } = comparison;

  const allTypes = Array.from(new Set([
    ...Object.keys(employee_a.stats.by_type),
    ...Object.keys(employee_b.stats.by_type),
  ]));

  return (
    <div>
      <p className="absence-summary">
        Absence comparison: <strong>{employee_a.name}</strong> vs <strong>{employee_b.name}</strong>
        {period ? ` — ${period}` : ""}
      </p>

      <div className="comparison-cards">
        {[employee_a, employee_b].map((emp) => (
          <div key={emp.user_id} className="comparison-card">
            <div className="comparison-card__header">
              <div className="comparison-card__avatar">{emp.name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2)}</div>
              <div>
                <div className="comparison-card__name">{emp.name}</div>
                <div className="comparison-card__sub">{emp.stats.total_absences} absence{emp.stats.total_absences !== 1 ? "s" : ""} · {emp.stats.total_days} day{emp.stats.total_days !== 1 ? "s" : ""}</div>
              </div>
            </div>
            {allTypes.length > 0 && (
              <div className="comparison-card__breakdown">
                {allTypes.map(t => {
                  const info = emp.stats.by_type[t];
                  if (!info) return null;
                  return (
                    <div key={t} className="comparison-card__type-row">
                      <span className="comparison-card__type-label">{getAbsenceLabel(t)}</span>
                      <span className="comparison-card__type-val">{info.count}× · {info.days}d</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      {absences.length > 0 && (
        <div className="absence-table-wrapper" style={{ marginTop: 16 }}>
          <table className="absence-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Absence Type</th>
                <th>Start Date</th>
                <th>End Date</th>
                <th>Status</th>
                <th>Days</th>
              </tr>
            </thead>
            <tbody>
              {absences.map((a, i) => {
                const name = a.user_id === employee_a.user_id ? employee_a.name : employee_b.name;
                return (
                  <tr key={i}>
                    <td>{name}</td>
                    <td>{getAbsenceLabel(a.absence_type)}</td>
                    <td>{a.start_date || "—"}</td>
                    <td>{a.end_date || "—"}</td>
                    <td><span className={`absence-badge ${statusBadgeClass(a.approval_status ?? "")}`}>{a.approval_status || "—"}</span></td>
                    <td>{a.quantity_in_days != null ? a.quantity_in_days : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AbsenceTable({ data }: { data: AbsenceData }) {
  const { absences, employeeName, startDate, endDate, isWorkforce, department, isDepartmentOverlap, memberNames } = data;
  const label = employeeName ?? "all employees";
  const period = startDate === endDate ? startDate : `${startDate} to ${endDate}`;
  const count = absences.length;
  const showDays = absences.some((a) => a.quantity_in_days != null);
  const resolveEmployee = (userId: string) => memberNames[userId] ?? userId;

  const summaryText = isDepartmentOverlap
    ? <>
        Found <strong>{count}</strong> absence record{count !== 1 ? "s" : ""}
        {department
          ? <> for other employees in the <strong>{department}</strong> department</>
          : employeeName
            ? <> for <strong>{label}</strong>'s direct reports</>
            : " for your team"}
        {period ? ` — ${period}` : ""}
        {employeeName && department ? <> (same period as <strong>{label}</strong>)</> : null}
      </>
    : <>
        Found <strong>{count}</strong> absence record{count !== 1 ? "s" : ""} for{" "}
        <strong>{label}</strong>
        {period ? ` — ${period}` : ""}
      </>;

  return (
    <div>
      <p className="absence-summary">
        {summaryText}
      </p>
      <div className="absence-table-wrapper">
        <table className="absence-table">
          <thead>
            <tr>
              {isWorkforce && <th>Employee</th>}
              <th>Absence Type</th>
              <th>Start Date</th>
              <th>End Date</th>
              <th>Status</th>
              {showDays && <th>Days</th>}
            </tr>
          </thead>
          <tbody>
            {absences.map((a, i) => (
              <tr key={i}>
                {isWorkforce && <td>{isDepartmentOverlap ? resolveEmployee(a.user_id) : a.user_id}</td>}
                <td>{getAbsenceLabel(a.absence_type)}</td>
                <td>{a.start_date || "—"}</td>
                <td>{a.end_date || "—"}</td>
                <td>
                  <span className={`absence-badge ${statusBadgeClass(a.approval_status ?? "")}`}>
                    {a.approval_status || "—"}
                  </span>
                </td>
                {showDays && (
                  <td>{a.quantity_in_days != null ? a.quantity_in_days : "—"}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface PendingRequest {
  timeType: string;
  startDate: string;
  endDate: string;
  quantityInDays: number | null;
  approvalStatus: string;
  externalCode: string | null;
}

interface HolidayRow {
  date: string;
  name: string;
  type: string;
}

function daysUntil(dateStr: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(dateStr + "T00:00:00");
  return Math.round((target.getTime() - today.getTime()) / 86400000);
}

function formatHolidayDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function HolidayTable({ message }: { message: ChatMessage }) {
  if (!message.minimizedResult) return null;
  const raw = message.minimizedResult.holidays;
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const holidays = raw as HolidayRow[];
  const employeeName = message.minimizedResult.employee_name as string | null | undefined;
  const employeeFound = message.minimizedResult.employee_found as boolean | undefined;

  let headerLine: string;
  if (employeeName && employeeFound === false) {
    headerLine = `Employee "${employeeName}" not found — showing company public holidays`;
  } else if (employeeName) {
    headerLine = `Holidays found for ${employeeName}`;
  } else {
    headerLine = "Public holidays";
  }

  return (
    <div className="holiday-table-wrapper">
      <p className="holiday-table-header">{headerLine} <span className="holiday-table-count">({holidays.length})</span></p>
      <table className="holiday-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Holiday</th>
            <th>Type</th>
            <th>Days Until</th>
          </tr>
        </thead>
        <tbody>
          {holidays.map((h) => {
            const diff = daysUntil(h.date);
            const isPast = diff < 0;
            const isToday = diff === 0;
            const typeKey = (h.type ?? "public").toLowerCase();
            return (
              <tr key={h.date} className={isPast ? "holiday-row--past" : ""}>
                <td className="holiday-date">{formatHolidayDate(h.date)}</td>
                <td className="holiday-name">{h.name}</td>
                <td>
                  <span className={`holiday-type-badge holiday-type-badge--${typeKey}`}>
                    {(h.type ?? "public").replace(/_/g, " ")}
                  </span>
                </td>
                <td className="holiday-days-until">
                  {isPast ? (
                    <span className="holiday-days--past">Passed</span>
                  ) : isToday ? (
                    <span className="holiday-days--today">Today</span>
                  ) : (
                    <span className="holiday-days--future">{diff} day{diff !== 1 ? "s" : ""}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

interface WorkDay { day: string; start: string; end: string; hours: number; }

function WorkScheduleCard({ message }: { message: ChatMessage }) {
  if (!message.minimizedResult) return null;
  const ws = message.minimizedResult.work_schedule as Record<string, unknown> | null | undefined;
  if (!ws) return null;
  const employeeName = message.minimizedResult.employee_name as string | null | undefined;
  const rawDisplayName = ws.employee_display_name as string | undefined;
  const isIdLike = rawDisplayName != null && /^\d+$/.test(rawDisplayName);
  const name = employeeName ?? (isIdLike ? undefined : rawDisplayName) ?? "Employee";
  const scheduleName = (ws.schedule_name as string | undefined) ?? "Standard";
  const hoursPerWeek = ws.hours_per_week as number | undefined;
  const daysPerWeek = ws.days_per_week as number | undefined;
  const workDays = (ws.work_days as WorkDay[] | undefined) ?? [];

  return (
    <div className="work-schedule-card">
      <div className="work-schedule-card__header">
        <span className="work-schedule-card__name">{name}</span>
        <span className="work-schedule-card__badge">{scheduleName}</span>
      </div>
      <div className="work-schedule-card__stats">
        {daysPerWeek != null && <span>{daysPerWeek} days/week</span>}
        {hoursPerWeek != null && <span>{hoursPerWeek}h/week</span>}
      </div>
      {workDays.length > 0 && (
        <table className="work-schedule-table">
          <thead>
            <tr>
              <th>Day</th>
              <th>Start</th>
              <th>End</th>
              <th>Hours</th>
            </tr>
          </thead>
          <tbody>
            {workDays.map((d) => (
              <tr key={d.day}>
                <td className="ws-day">{d.day}</td>
                <td className="ws-time">{d.start}</td>
                <td className="ws-time">{d.end}</td>
                <td className="ws-hours">{d.hours}h</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function PendingRequestsTable({ message }: { message: ChatMessage }) {
  if (!message.minimizedResult) return null;
  const raw = message.minimizedResult.pending_requests;
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const requests = raw as PendingRequest[];
  const displayName = (message.minimizedResult.display_name as string | null) ?? null;

  return (
    <div>
      <p className="absence-summary">
        Found <strong>{requests.length}</strong> pending leave request{requests.length !== 1 ? "s" : ""}
        {displayName ? <> for <strong>{displayName}</strong></> : null}
      </p>
      <div className="absence-table-wrapper">
        <table className="absence-table">
          <thead>
            <tr>
              <th>Leave Type</th>
              <th>Start Date</th>
              <th>End Date</th>
              <th>Days</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {requests.map((r, i) => (
              <tr key={i}>
                <td>{getAbsenceLabel(r.timeType)}</td>
                <td>{r.startDate || "—"}</td>
                <td>{r.endDate || "—"}</td>
                <td>{r.quantityInDays != null ? r.quantityInDays : "—"}</td>
                <td>
                  <span className={`absence-badge ${statusBadgeClass(r.approvalStatus ?? "")}`}>
                    {r.approvalStatus || "—"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AttachmentUploadButton({ onUpload }: { message: ChatMessage; onUpload: (file: File) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        style={{ display: "none" }}
        accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onUpload(file);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        className="download-btn"
        style={{ background: "#0070d2", color: "#fff", border: "none" }}
        onClick={() => inputRef.current?.click()}
      >
        📎 Upload Document
      </button>
    </>
  );
}

export function MessageList({ messages, pendingElapsedSeconds = 0, onUploadAttachment }: MessageListProps) {
  return (
    <>
      {messages.map((message) => {
        const absenceData = extractAbsenceData(message);
        const isComparison = !!(message.minimizedResult?.comparison);
        const isPendingRequests = message.role === "assistant" && !message.pending &&
          Array.isArray(message.minimizedResult?.pending_requests);
        const holidays = message.minimizedResult?.holidays;
        const isHolidayResult = message.role === "assistant" && !message.pending &&
          Array.isArray(holidays) && (holidays as unknown[]).length > 0;
        const isWorkSchedule = message.role === "assistant" && !message.pending &&
          !!(message.minimizedResult?.work_schedule);
        const needsAttachment = message.role === "assistant" && !message.pending &&
          message.minimizedResult?.needs_attachment === true;
        return (
          <article
            key={message.id}
            className={`message-card message-card--${message.role} ${message.pending ? "message-card--pending" : ""}`}
          >
            <div className="message-card__meta">
              <span>{message.role === "user" ? "You" : "Assistant"}</span>
              {message.pending ? (
                <span className="pending-indicator">Thinking locally... {pendingElapsedSeconds}s</span>
              ) : null}
              {message.status ? <StatusPill label={message.status} tone={message.status} /> : null}
              {message.role === "assistant" && !message.pending && message.durationMs != null ? (
                <span className="response-duration">{formatDuration(message.durationMs)}</span>
              ) : null}
              {(absenceData || isComparison) ? (
                <>
                  <button
                    type="button"
                    className="download-btn"
                    onClick={() => downloadExcel(message)}
                  >
                    ⬇ Excel
                  </button>
                  <button
                    type="button"
                    className="outlook-link"
                    style={{ border: "none", cursor: "pointer" }}
                    onClick={() => addAllToOutlook(message)}
                  >
                    📅 Add to Calendar
                  </button>
                </>
              ) : null}
              {needsAttachment && onUploadAttachment ? (
                <AttachmentUploadButton
                  message={message}
                  onUpload={(file) => onUploadAttachment(message, file)}
                />
              ) : null}
            </div>
            {isComparison ? (
              <ComparisonView message={message} />
            ) : absenceData ? (
              <AbsenceTable data={absenceData} />
            ) : isPendingRequests ? (
              <PendingRequestsTable message={message} />
            ) : isWorkSchedule ? (
              <WorkScheduleCard message={message} />
            ) : isHolidayResult ? (
              <HolidayTable message={message} />
            ) : (
              <p className="message-card__text">{message.text}</p>
            )}
          </article>
        );
      })}
    </>
  );
}
