import type { ChatMessage } from "../types/api";
import { StatusPill } from "./StatusPill";

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

function toIcsDate(dateStr: string): string {
  // Convert "2026-01-15" → "20260115"
  return dateStr.replace(/-/g, "");
}

function addOneDay(dateStr: string): string {
  // iCal DTEND for all-day events is exclusive (day after last day)
  const d = new Date(dateStr + "T00:00:00");
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10).replace(/-/g, "");
}

function downloadICS(message: ChatMessage) {
  const data = extractAbsenceData(message);
  if (!data) return;

  const { absences, employeeName, isWorkforce } = data;
  const employeeLabel = employeeName ?? "All Employees";
  const now = new Date().toISOString().replace(/[-:.]/g, "").slice(0, 15) + "Z";

  const events = absences
    .filter((a) => a.start_date && a.end_date)
    .map((a, i) => {
      const name = isWorkforce ? a.user_id : employeeLabel;
      const summary = `${a.absence_type || "Absence"} — ${name}`;
      const description = [
        `Employee: ${name}`,
        `Type: ${a.absence_type || "—"}`,
        `Status: ${a.approval_status || "—"}`,
        a.quantity_in_days != null ? `Duration: ${a.quantity_in_days} day(s)` : "",
      ]
        .filter(Boolean)
        .join("\\n");

      return [
        "BEGIN:VEVENT",
        `UID:absence-${i}-${a.start_date}-${a.user_id}@hr-assistant`,
        `DTSTAMP:${now}`,
        `DTSTART;VALUE=DATE:${toIcsDate(a.start_date)}`,
        `DTEND;VALUE=DATE:${addOneDay(a.end_date)}`,
        `SUMMARY:${summary}`,
        `DESCRIPTION:${description}`,
        "STATUS:CONFIRMED",
        "END:VEVENT",
      ].join("\r\n");
    });

  const icsContent = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//SAP HR Assistant//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    ...events,
    "END:VCALENDAR",
  ].join("\r\n");

  const blob = new Blob([icsContent], { type: "text/calendar;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `absences_${employeeLabel.replace(/\s+/g, "_")}.ics`;
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

export function MessageList({ messages, pendingElapsedSeconds = 0 }: MessageListProps) {
  return (
    <>
      {messages.map((message) => {
        const absenceData = extractAbsenceData(message);
        const isComparison = !!(message.minimizedResult?.comparison);
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
            </div>
            {isComparison ? (
              <ComparisonView message={message} />
            ) : absenceData ? (
              <AbsenceTable data={absenceData} />
            ) : (
              <p className="message-card__text">{message.text}</p>
            )}
          </article>
        );
      })}
    </>
  );
}
