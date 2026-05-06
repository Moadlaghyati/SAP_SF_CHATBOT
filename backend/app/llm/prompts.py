from __future__ import annotations

import calendar as _cal
import json
from datetime import date, timedelta

from app.schemas.llm import AnswerGenerationPayload


def build_absence_extraction_prompt(question: str, current_date: date) -> str:
    today = current_date
    days_since_monday = today.weekday()
    this_week_start = today - timedelta(days=days_since_monday)
    this_week_end = this_week_start + timedelta(days=6)
    next_week_start = this_week_start + timedelta(days=7)
    next_week_end = next_week_start + timedelta(days=6)
    last_week_start = this_week_start - timedelta(days=7)
    last_week_end = last_week_start + timedelta(days=6)
    this_month_start = today.replace(day=1)
    this_month_end = today.replace(day=_cal.monthrange(today.year, today.month)[1])
    if today.month == 12:
        next_month_start = date(today.year + 1, 1, 1)
    else:
        next_month_start = date(today.year, today.month + 1, 1)
    next_month_end = next_month_start.replace(day=_cal.monthrange(next_month_start.year, next_month_start.month)[1])
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    return f"""You are an HR assistant parameter extractor. Extract structured query parameters from the user's absence-related question.

Today is {today.isoformat()}.

Return ONLY valid JSON with this exact schema:
{{
  "scope": "self|specific_employee|direct_report_or_team|workforce|comparison|unknown",
  "employee_name": "string or null",
  "employee_name_b": "string or null",
  "user_id": "string or null",
  "start_date": "YYYY-MM-DD or null",
  "end_date": "YYYY-MM-DD or null",
  "needs_clarification": false,
  "clarification_message": "string or null"
}}

Scope rules:
- "self": user asks about themselves — "my absences", "show my absence", "do I have leave", "my vacation"
- "specific_employee": asks about a named person — "Walid's absences", "show absences for Ahmed Bennani", "how many days did Sara take"
- "direct_report_or_team": asks about their own team or department — "my team", "my direct reports", "who on my team is absent", "our department", "our team", "absences in our department", "absences in my department", "give me the absences of our department", "show department absences"
- "workforce": asks about everyone or an unspecified group — "who is absent", "who will be absent", "who will absent", "can you see who will absent", "show all absences", "who is off today", "list everyone absent"
- "comparison": comparing exactly two DIFFERENT named employees — "compare Walid and Ahmed", "Walid vs Ahmed absences"
  • IMPORTANT: "compare Walid this year and last year" is NOT comparison — it is ONE person over two periods → use "specific_employee" with the wider date range (earlier start_date, later end_date)
  • Only use "comparison" when the user explicitly names two distinct people
- "unknown": truly cannot determine the target even from context

Date format rule:
- When a date is written as DD-MM-YYYY (e.g. "04-05-2026"), treat it as day=04, month=05, year=2026 (European format). NEVER interpret it as MM-DD-YYYY.
- When written as YYYY-MM-DD (e.g. "2026-05-04"), treat it as ISO standard: year=2026, month=05, day=04.

Date reference table — use these exact values:
- "today" → {today.isoformat()} to {today.isoformat()}
- "tomorrow" → {(today + timedelta(days=1)).isoformat()} to {(today + timedelta(days=1)).isoformat()}
- "yesterday" → {(today - timedelta(days=1)).isoformat()} to {(today - timedelta(days=1)).isoformat()}
- "next N days" (e.g. "next 2 days", "next 3 days") → {today.isoformat()} to today + N days
- "next day" → {today.isoformat()} to {(today + timedelta(days=1)).isoformat()}
- "this week" → {this_week_start.isoformat()} to {this_week_end.isoformat()}
- "next week" → {next_week_start.isoformat()} to {next_week_end.isoformat()}
- "next 2 weeks" → {today.isoformat()} to {(today + timedelta(days=14)).isoformat()}
- "next 3 weeks" → {today.isoformat()} to {(today + timedelta(days=21)).isoformat()}
- "next N weeks" → start_date = today, end_date = today + N*7 days
- "next N weeks starting from [date]" → start_date = that date, end_date = that date + N*7 days
- "last week" → {last_week_start.isoformat()} to {last_week_end.isoformat()}
- "this month" → {this_month_start.isoformat()} to {this_month_end.isoformat()}
- "next month" → {next_month_start.isoformat()} to {next_month_end.isoformat()}
- "last month" → {last_month_start.isoformat()} to {last_month_end.isoformat()}
- "this year" → {today.year}-01-01 to {today.year}-12-31
- "last year" → {today.year - 1}-01-01 to {today.year - 1}-12-31
- "next year" → {today.year + 1}-01-01 to {today.year + 1}-12-31
- Combined periods like "this month and next week" or "next week and this month" → take the union: use the earlier start_date and the later end_date
- Named month + year like "April 2026" → first and last day of that month
- If no date is mentioned at all → ALWAYS default to the current year: {today.year}-01-01 to {today.year}-12-31
- Use "today" ({today.isoformat()}) ONLY when the user explicitly says "today", "right now", or "currently" — NEVER use today as a default for vague requests like "show my absence" or "see my absences"

Clarification rules:
- Set needs_clarification=true ONLY when scope is "specific_employee" and no employee name or user_id can be found
- Never ask for clarification about dates — always apply the defaults above
- Never ask for clarification about scope when it can be reasonably inferred from the question

French language note:
- French words like "cette" (this), "ce" (this), "ces" (these), "mon" (my), "ma" (my), "de" (of), "du" (of the), "le" (the), "la" (the), "les" (the), "et" (and) are NOT employee names — they are grammar words. Never treat them as a second employee name.
- "cette année" = "this year", "ce mois" = "this month", "cette semaine" = "this week"
- French query patterns: "les absences de [NAME]" = absences of [NAME] → specific_employee; "mon équipe" = my team → direct_report_or_team; "mes absences" = my absences → self; "qui est absent" = who is absent → workforce

Examples:
- "show my absences this month" → {{"scope":"self","start_date":"{this_month_start.isoformat()}","end_date":"{this_month_end.isoformat()}","needs_clarification":false}}
- "who is absent today" → {{"scope":"workforce","start_date":"{today.isoformat()}","end_date":"{today.isoformat()}","needs_clarification":false}}
- "can you see who will absent this month and next week" → {{"scope":"workforce","start_date":"{this_month_start.isoformat()}","end_date":"{max(this_month_end, next_week_end).isoformat()}","needs_clarification":false}}
- "show Walid Regragi absences in April 2026" → {{"scope":"specific_employee","employee_name":"Walid Regragi","start_date":"2026-04-01","end_date":"2026-04-30","needs_clarification":false}}
- "Je veux voir les absences de Walid Regragi cette année" → {{"scope":"specific_employee","employee_name":"Walid Regragi","start_date":"{today.year}-01-01","end_date":"{today.year}-12-31","needs_clarification":false}}
- "montre moi les absences de Ahmed Bennani ce mois" → {{"scope":"specific_employee","employee_name":"Ahmed Bennani","start_date":"{this_month_start.isoformat()}","end_date":"{this_month_end.isoformat()}","needs_clarification":false}}
- "mes absences cette année" → {{"scope":"self","start_date":"{today.year}-01-01","end_date":"{today.year}-12-31","needs_clarification":false}}
- "qui est absent aujourd'hui" → {{"scope":"workforce","start_date":"{today.isoformat()}","end_date":"{today.isoformat()}","needs_clarification":false}}
- "absences de mon équipe cette semaine" → {{"scope":"direct_report_or_team","start_date":"{this_week_start.isoformat()}","end_date":"{this_week_end.isoformat()}","needs_clarification":false}}
- "compare Walid and Ahmed absences this year" → {{"scope":"comparison","employee_name":"Walid","employee_name_b":"Ahmed","start_date":"{today.year}-01-01","end_date":"{today.year}-12-31","needs_clarification":false}}
- "compare absences of Walid Regragi this year and last year" → {{"scope":"specific_employee","employee_name":"Walid Regragi","start_date":"{today.year - 1}-01-01","end_date":"{today.year}-12-31","needs_clarification":false}}
- "who on my team is absent this week" → {{"scope":"direct_report_or_team","start_date":"{this_week_start.isoformat()}","end_date":"{this_week_end.isoformat()}","needs_clarification":false}}
- "can you give me the absences of last week in our department" → {{"scope":"direct_report_or_team","start_date":"{last_week_start.isoformat()}","end_date":"{last_week_end.isoformat()}","needs_clarification":false}}
- "i want to know the absences of last week in our department" → {{"scope":"direct_report_or_team","start_date":"{last_week_start.isoformat()}","end_date":"{last_week_end.isoformat()}","needs_clarification":false}}
- "who will be absent in the next 2 weeks starting from 04-05-2026" → {{"scope":"workforce","start_date":"2026-05-04","end_date":"2026-05-18","needs_clarification":false}}
- "who will be absent in the next 3 weeks" → {{"scope":"workforce","start_date":"{today.isoformat()}","end_date":"{(today + timedelta(days=21)).isoformat()}","needs_clarification":false}}
- "who is absent tomorrow" → {{"scope":"workforce","start_date":"{(today + timedelta(days=1)).isoformat()}","end_date":"{(today + timedelta(days=1)).isoformat()}","needs_clarification":false}}
- "show absences for next 5 days" → {{"scope":"workforce","start_date":"{today.isoformat()}","end_date":"{(today + timedelta(days=5)).isoformat()}","needs_clarification":false}}

Question: {question}""".strip()


def build_extraction_prompt(question: str, current_date: date) -> str:
    return f"""
You are a local HR assistant extraction model.
Today is {current_date.isoformat()}.

Supported intents:
- absence_count
- absence_list
- absence_breakdown
- general_chat
- unsupported

Return JSON only using this exact schema:
{{
  "intent": "absence_count|absence_list|absence_breakdown|general_chat|unsupported",
  "employee_reference": "string or null",
  "start_date": "YYYY-MM-DD or null",
  "end_date": "YYYY-MM-DD or null",
  "absence_type": "string or null",
  "needs_clarification": true,
  "clarification_reason": "string or null"
}}

Rules:
- Do not invent unsupported fields.
- Convert date phrases such as "Q1 2026", "March 2026", "04/2026", "this month", or "last month" into explicit ISO dates.
- Treat common typos such as "mounth" as "month".
- Treat "leave", "leaves", "vacation", "PTO", "time off", and "sick leave" as absence-related retrieval requests.
- If the message is a greeting, thanks, help request, or general conversation that does not require employee data retrieval, set intent to "general_chat".
- If the user asks for HR data or actions outside this demo's scope, set intent to "unsupported".
- If you are unsure about the employee or the date range, set needs_clarification=true.
- If a field is unknown, use null.
- Output valid JSON only with double quotes.

Examples:
- "hello" -> general_chat
- "what can you do?" -> general_chat
- "how many absences did Sara Bennani have between 2026-01-01 and 2026-03-31?" -> absence_count
- "what is Sara Bennani's payroll amount?" -> unsupported

Question:
{question}
""".strip()


def build_answer_prompt(payload: AnswerGenerationPayload) -> str:
    if payload.intent == "general_chat":
        return f"""
You are a local AI assistant running fully on-device.

The user sent this message:
{json.dumps(payload.user_message or "", ensure_ascii=True)}

Rules:
- Respond naturally and helpfully like a real chatbot.
- You may use general knowledge and reasoning.
- Keep the answer clear and concise unless the user asks for depth.
- Do not claim access to company systems, SAP SuccessFactors, or private employee data unless such data is explicitly provided.
- If the user asks for unavailable enterprise data, explain that you do not have that data in the current demo.

Answer:
""".strip()

    return f"""
You are a helpful HR assistant. Use only the data in the payload below to answer the user's question.

Rules:
- Answer in the same language the user used.
- Be conversational, clear, and concise.
- If request_status is "forbidden", politely explain the lack of permission.
- If request_status is "clarification_required", ask for the missing information naturally.
- If request_status is "unsupported", explain what the assistant can help with instead.
- When presenting absence records, summarise them in plain sentences (e.g. "Ahmed had 3 absences totalling 7 days: 2 sick leaves and 1 annual leave."). List individual records only when there are 5 or fewer.
- Do not mention internal field names, IDs, or JSON keys in your answer.
- Do not invent any data not present in the payload.

User question: {json.dumps(payload.user_message or "", ensure_ascii=True)}

Payload:
{json.dumps(payload.model_dump(mode="json"), ensure_ascii=True)}
""".strip()
