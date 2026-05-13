from __future__ import annotations

from datetime import date

from app.schemas.api import DemoUserSummary
from app.schemas.domain import AbsenceRecord, Employee, Holiday, WorkDay, WorkSchedule

MOCK_EMPLOYEES: list[Employee] = [
    Employee(
        employee_id="90000638",
        display_name="Fouzi Lekjaa",
        first_name="Fouzi",
        last_name="Lekjaa",
        email="fouzi.lekjaa@frmf.ma",
        aliases=["Fouzi", "Lekjaa"],
    ),
    Employee(
        employee_id="90000712",
        display_name="Walid Regragi",
        first_name="Walid",
        last_name="Regragi",
        email="walid.regragi@frmf.ma",
        manager_employee_id="90000638",
        aliases=["Walid", "Regragi"],
    ),
    Employee(
        employee_id="90000726",
        display_name="Mouna Bennani",
        first_name="Mouna",
        last_name="Bennani",
        email="mouna.bennani@frmf.ma",
        manager_employee_id="90000638",
        aliases=["Mouna"],
    ),
    Employee(
        employee_id="90000730",
        display_name="Leila Haddad",
        first_name="Leila",
        last_name="Haddad",
        email="leila.haddad@frmf.ma",
        manager_employee_id="90000638",
        aliases=["Leila"],
    ),
    Employee(
        employee_id="90000714",
        display_name="Assistant Coach",
        first_name="Assistant",
        last_name="Coach",
        email="assistant.coach@frmf.ma",
        manager_employee_id="90000712",
        aliases=[],
    ),
    Employee(
        employee_id="90000718",
        display_name="Ilham Tbato",
        first_name="Ilham",
        last_name="Tbato",
        email="ilham.tbato@frmf.ma",
        manager_employee_id="90000712",
        aliases=["Ilham"],
        sap_user_id="90000663",
    ),
    Employee(
        employee_id="90000722",
        display_name="Eduardo Dominguez",
        first_name="Eduardo",
        last_name="Dominguez",
        email="eduardo.dominguez@frmf.ma",
        manager_employee_id="90000712",
        aliases=["Eduardo"],
    ),
    Employee(
        employee_id="90000736",
        display_name="Visionage Video",
        first_name="Visionage",
        last_name="Video",
        email="visionage.video@frmf.ma",
        manager_employee_id="90000712",
        aliases=[],
    ),
]

MOCK_ABSENCES: list[AbsenceRecord] = [
    AbsenceRecord(
        absence_id="ABS-001",
        employee_id="90000718",
        employee_display_name="Ilham Tbato",
        absence_type="Sick Leave",
        start_date=date(2026, 1, 12),
        end_date=date(2026, 1, 12),
        days=1.0,
    ),
    AbsenceRecord(
        absence_id="ABS-002",
        employee_id="90000718",
        employee_display_name="Ilham Tbato",
        absence_type="Annual Leave",
        start_date=date(2026, 2, 3),
        end_date=date(2026, 2, 5),
        days=3.0,
    ),
    AbsenceRecord(
        absence_id="ABS-003",
        employee_id="90000722",
        employee_display_name="Eduardo Dominguez",
        absence_type="Sick Leave",
        start_date=date(2026, 3, 11),
        end_date=date(2026, 3, 11),
        days=1.0,
    ),
    AbsenceRecord(
        absence_id="ABS-004",
        employee_id="90000722",
        employee_display_name="Eduardo Dominguez",
        absence_type="Annual Leave",
        start_date=date(2026, 3, 25),
        end_date=date(2026, 3, 26),
        days=2.0,
    ),
    AbsenceRecord(
        absence_id="ABS-005",
        employee_id="90000712",
        employee_display_name="Walid Regragi",
        absence_type="Annual Leave",
        start_date=date(2026, 4, 2),
        end_date=date(2026, 4, 3),
        days=2.0,
    ),
    AbsenceRecord(
        absence_id="ABS-006",
        employee_id="90000712",
        employee_display_name="Walid Regragi",
        absence_type="Sick Leave",
        start_date=date(2026, 5, 2),
        end_date=date(2026, 5, 2),
        days=1.0,
    ),
]

# Morocco public holidays 2026
MOCK_HOLIDAYS: list[Holiday] = [
    Holiday(date="2026-01-01", name="New Year's Day", name_fr="Jour de l'An"),
    Holiday(date="2026-01-11", name="Manifesto of Independence Day", name_fr="Présentation du Manifeste de l'Indépendance"),
    Holiday(date="2026-03-20", name="Eid Al-Fitr (Day 1)", name_fr="Aïd Al-Fitr (1er jour)", type="religious"),
    Holiday(date="2026-03-21", name="Eid Al-Fitr (Day 2)", name_fr="Aïd Al-Fitr (2ème jour)", type="religious"),
    Holiday(date="2026-05-01", name="Labour Day", name_fr="Fête du Travail"),
    Holiday(date="2026-05-27", name="Eid Al-Adha (Day 1)", name_fr="Aïd Al-Adha (1er jour)", type="religious"),
    Holiday(date="2026-05-28", name="Eid Al-Adha (Day 2)", name_fr="Aïd Al-Adha (2ème jour)", type="religious"),
    Holiday(date="2026-06-17", name="Islamic New Year", name_fr="Nouvel An Hijri", type="religious"),
    Holiday(date="2026-07-30", name="Throne Day", name_fr="Fête du Trône"),
    Holiday(date="2026-08-14", name="Oued Ed-Dahab Day", name_fr="Anniversaire de la Récupération de Oued Ed-Dahab"),
    Holiday(date="2026-08-20", name="Revolution of the King and the People", name_fr="Fête de la Révolution du Roi et du Peuple"),
    Holiday(date="2026-08-21", name="Youth Day", name_fr="Fête de la Jeunesse"),
    Holiday(date="2026-08-26", name="Prophet's Birthday", name_fr="Aïd Al-Mawlid Annabawi", type="religious"),
    Holiday(date="2026-11-06", name="Green March Day", name_fr="Fête de la Marche Verte"),
    Holiday(date="2026-11-18", name="Independence Day", name_fr="Fête de l'Indépendance"),
]

_STANDARD_WORK_DAYS = [
    WorkDay(day_of_week="Monday",    start_time="08:30", end_time="17:30", hours=8.0),
    WorkDay(day_of_week="Tuesday",   start_time="08:30", end_time="17:30", hours=8.0),
    WorkDay(day_of_week="Wednesday", start_time="08:30", end_time="17:30", hours=8.0),
    WorkDay(day_of_week="Thursday",  start_time="08:30", end_time="17:30", hours=8.0),
    WorkDay(day_of_week="Friday",    start_time="08:30", end_time="17:00", hours=8.0),
]

MOCK_WORK_SCHEDULES: dict[str, WorkSchedule] = {
    emp.employee_id: WorkSchedule(
        employee_id=emp.employee_id,
        employee_display_name=emp.display_name,
        schedule_name="Standard Morocco (40h/week)",
        work_days=_STANDARD_WORK_DAYS,
        hours_per_week=40.0,
        days_per_week=5,
    )
    for emp in []  # filled below after MOCK_EMPLOYEES is defined
}


def _build_work_schedules() -> dict[str, WorkSchedule]:
    return {
        emp.employee_id: WorkSchedule(
            employee_id=emp.employee_id,
            employee_display_name=emp.display_name,
            schedule_name="Standard Morocco (40h/week)",
            work_days=_STANDARD_WORK_DAYS,
            hours_per_week=40.0,
            days_per_week=5,
        )
        for emp in MOCK_EMPLOYEES
    }


DEMO_USERS: list[DemoUserSummary] = [
    DemoUserSummary(
        user_id="demo_fouzi_lekjaa",
        display_name="Fouzi Lekjaa",
        role="hr_admin",
        job_title="Président, FRMF",
        employee_id="90000638",
        description="FRMF President — full access to all HR data and team absences.",
    ),
    DemoUserSummary(
        user_id="demo_walid_regragi",
        display_name="Walid Regragi",
        role="manager",
        job_title="Sélectionneur National",
        employee_id="90000712",
        description="Head Coach Men's National Team — access to self and direct reports.",
    ),
    DemoUserSummary(
        user_id="demo_mouna_bennani",
        display_name="Mouna Bennani",
        role="hr_admin",
        job_title="Responsable RH",
        employee_id="90000726",
        description="HR Operations Manager — full HR data access.",
    ),
    DemoUserSummary(
        user_id="demo_leila_haddad",
        display_name="Leila Haddad",
        role="employee",
        job_title="Directrice Administrative",
        employee_id="90000730",
        description="Administrative Director — can view own absence data only.",
    ),
    DemoUserSummary(
        user_id="demo_assistant_coach",
        display_name="Assistant Coach",
        role="employee",
        job_title="Entraîneur Adjoint",
        employee_id="90000714",
        description="Assistant Coach — can view own absence data only.",
    ),
    DemoUserSummary(
        user_id="demo_ilham_tbato",
        display_name="Ilham Tbato",
        role="employee",
        job_title="Analyste Performance",
        employee_id="90000718",
        description="Performance Analyst — can view own absence data only.",
    ),
    DemoUserSummary(
        user_id="demo_eduardo_dominguez",
        display_name="Eduardo Dominguez",
        role="employee",
        job_title="Préparateur Physique",
        employee_id="90000722",
        description="Physical Trainer — can view own absence data only.",
    ),
    DemoUserSummary(
        user_id="demo_visionage_video",
        display_name="Visionage Video",
        role="employee",
        job_title="Analyste Vidéo",
        employee_id="90000736",
        description="Video Analyst — can view own absence data only.",
    ),
]

DEMO_ACCESS_MAP: dict[str, list[str]] = {
    "demo_fouzi_lekjaa": [e.employee_id for e in MOCK_EMPLOYEES],
    "demo_walid_regragi": ["90000712", "90000714", "90000718", "90000722", "90000736"],
    "demo_mouna_bennani": [e.employee_id for e in MOCK_EMPLOYEES],
    "demo_leila_haddad": ["90000730"],
    "demo_assistant_coach": ["90000714"],
    "demo_ilham_tbato": ["90000718"],
    "demo_eduardo_dominguez": ["90000722"],
    "demo_visionage_video": ["90000736"],
}
