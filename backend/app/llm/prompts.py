from __future__ import annotations

import json
from datetime import date

from app.schemas.llm import AnswerGenerationPayload


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
- Format the response with Markdown when it improves readability.
- Use a Markdown table for structured comparisons, records, breakdowns, or multi-row results.
- Use short paragraphs for narrative answers and bullet lists for options or capabilities.
- Do not claim access to company systems, SAP SuccessFactors, or private employee data unless such data is explicitly provided.
- If the user asks for unavailable enterprise data, explain that you do not have that data in the current demo.

Answer:
""".strip()

    return f"""
You are a local HR assistant answer model.
Use only the payload provided below. Do not invent employee data or tool results.

Rules:
- Keep the answer concise and professional.
- Format the response with Markdown when it improves readability.
- Use a Markdown table for absence lists, absence breakdowns, or any answer with repeated fields.
- Use short paragraphs for simple counts, clarifications, permission denials, and unsupported-scope messages.
- Use bullet lists for capabilities, next steps, or choices.
- If the payload contains mode="sap_absence_tool_results", treat sap_result as data returned by the absence retrieval tool.
- For SAP absence tool results, answer the user's actual request after reading the retrieved rows. Do not just repeat the raw summary unless the user only asked to list records.
- If several SAP tool calls were made, combine, compare, count, or summarize all returned rows as needed by the user.
- If request_status is "forbidden", state lack of permission clearly and briefly.
- If request_status is "clarification_required", ask for the missing clarification.
- If request_status is "unsupported", explain the current demo scope and suggest what the user can ask instead.
- Do not mention internal architecture unless the user asks.
- Do not mention any data that is not present in the payload.

Payload:
{json.dumps(payload.model_dump(mode="json"), ensure_ascii=True)}
""".strip()
