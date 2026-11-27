"""DCRUST eSamarth weekly timetable + calendar models, cse.dcrust.online-style renderers, and RAG facts."""

from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAY_SHORT = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
WEEKDAY_TITLE = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
CLASS_TYPE_LABEL = {"L": "Lecture", "LAB": "Lab", "T": "Tutorial", "S": "Seminar"}
_COURSE_CODE = re.compile(r"\b([A-Z]{2,5}\d{2,4}[A-Z]{0,3})\b")


@dataclass
class TimetableEvent:
    date: str          # YYYY-MM-DD
    weekday: int       # 0=Monday .. 6=Sunday
    weekday_name: str
    start_time: str    # HH:MM (24h)
    end_time: str      # HH:MM (24h)
    section_code: str
    course_code: str
    course_name: str
    class_type: str    # "L" | "LAB" | "T" | "S"
    status: str        # "PRESENT" | "ABSENT" | "LEAVE" | "SCHEDULED"


@dataclass
class WeeklySlot:
    weekday: int
    weekday_name: str
    start_time: str
    end_time: str
    section_code: str
    course_code: str
    course_name: str
    class_type: str


@dataclass
class TimetableReport:
    roll_number: str
    semester_label: str
    fetched_at: str
    weekly_slots: list[WeeklySlot] = field(default_factory=list)
    events: list[TimetableEvent] = field(default_factory=list)
    source_url: str = "https://dcrustm.samarth.edu.in/index.php/student-attendance/attendance/view-time-table"


def _infer_class_type(section_code: str, course_name: str) -> str:
    sec = section_code.upper()
    name = course_name.upper()
    if "SEMINAR" in name:
        return "S"
    if "LAB" in name or re.search(r"(?:-|_)P\b", sec):
        return "LAB"
    if re.search(r"(?:-|_)T\b", sec) and not re.search(r"3A$", sec):
        return "T"
    return "L"


def _split_desc(desc: str, title: str) -> tuple[str, str]:
    text = " ".join(desc.split()).strip()
    if ":" in text:
        left, right = (p.strip() for p in text.split(":", 1))
        return left, right
    m = _COURSE_CODE.search(text or title.upper())
    return (m.group(1) if m else title), text or title


def _normalize_status(raw_status: object) -> str:
    s = str(raw_status or "").strip().upper()
    if s in {"PRESENT", "P"}:
        return "PRESENT"
    if s in {"ABSENT", "A"}:
        return "ABSENT"
    if s in {"LEAVE", "L"}:
        return "LEAVE"
    return "SCHEDULED"


def _fmt_12h(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def _title_case_course(name: str) -> str:
    minor = {"and", "or", "for", "of", "the", "in", "to", "with"}
    words = name.strip().split()
    out: list[str] = []
    for i, w in enumerate(words):
        lw = w.lower()
        if i > 0 and lw in minor:
            out.append(lw)
        elif w.upper() in {"AI", "ML", "OS", "DBMS", "SQL", "OOP", "DSA", "UI", "UX", "HPC", "II", "III"}:
            out.append(w.upper())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def _infer_section_label(slots: list[WeeklySlot]) -> str:
    sections: Counter[str] = Counter()
    for s in slots:
        m = re.search(r"-0?\d-([A-Z])-", s.section_code.upper())
        if m:
            sections[m.group(1)] += 1
    if sections:
        return f"Section {sections.most_common(1)[0][0]}"
    return ""


def _semester_ended_notice(report: TimetableReport) -> str:
    if not report.events:
        return ""
    last_iso = max(e.date for e in report.events)
    today_iso = dt.datetime.now(tz=_IST).date().isoformat()
    if last_iso < today_iso:
        pretty = dt.date.fromisoformat(last_iso).strftime("%d %b %Y").lstrip("0")
        return f"This semester's classes ended on {pretty}. Showing your last timetable."
    return ""


def build_timetable_report(
    roll_number: str,
    semester_label: str,
    raw_events: list[dict],
    *,
    current_class_ids: set[str] | None = None,
    fetched_at: str | None = None,
) -> TimetableReport:
    """Build a current-semester Weekly Table + Calendar report from Samarth `get-classes-of-student` events."""
    tz = _IST
    now_local = dt.datetime.now(tz=tz)
    date_label = fetched_at or now_local.strftime("%a, %b %d")

    filtered_raw = [
        ev for ev in raw_events
        if (current_class_ids is None or str(ev.get("id", "")) in current_class_ids)
        and isinstance(ev.get("start"), (int, float))
    ]
    if current_class_ids and not filtered_raw and raw_events:
        starts = [ev["start"] for ev in raw_events if isinstance(ev.get("start"), (int, float))]
        if starts:
            latest_ts = max(starts)
            cutoff = latest_ts - 140 * 86400
            filtered_raw = [ev for ev in raw_events if isinstance(ev.get("start"), (int, float)) and ev["start"] >= cutoff]

    events: list[TimetableEvent] = []
    slot_counts: Counter[tuple[int, str, str, str, str, str, str]] = Counter()

    for ev in filtered_raw:
        s_dt = dt.datetime.fromtimestamp(ev["start"], tz=tz)
        end_ts = ev.get("end")
        e_dt = dt.datetime.fromtimestamp(end_ts, tz=tz) if isinstance(end_ts, (int, float)) else (s_dt + dt.timedelta(hours=1))
        sec = str(ev.get("title", "")).strip()
        c_code, c_name = _split_desc(str(ev.get("desc", "")), sec)
        c_type = _infer_class_type(sec, c_name)
        wd = s_dt.weekday()
        st = s_dt.strftime("%H:%M")
        en = e_dt.strftime("%H:%M")

        events.append(
            TimetableEvent(
                date=s_dt.strftime("%Y-%m-%d"),
                weekday=wd,
                weekday_name=WEEKDAY_NAMES[wd],
                start_time=st,
                end_time=en,
                section_code=sec,
                course_code=c_code,
                course_name=c_name,
                class_type=c_type,
                status=_normalize_status(ev.get("attendance_status")),
            )
        )
        slot_counts[(wd, st, en, sec, c_code, c_name, c_type)] += 1

    events.sort(key=lambda e: (e.date, e.start_time, e.course_code))

    max_freq = max(slot_counts.values(), default=0)
    min_freq = 2 if max_freq >= 3 else 1
    weekly_slots = [
        WeeklySlot(
            weekday=wd,
            weekday_name=WEEKDAY_NAMES[wd],
            start_time=st,
            end_time=en,
            section_code=sec,
            course_code=c_code,
            course_name=c_name,
            class_type=c_type,
        )
        for (wd, st, en, sec, c_code, c_name, c_type), cnt in sorted(slot_counts.items())
        if cnt >= min_freq
    ]

    return TimetableReport(
        roll_number=roll_number,
        semester_label=semester_label,
        fetched_at=date_label,
        weekly_slots=weekly_slots,
        events=events,
    )


def _grid_bounds(slots: list[WeeklySlot]) -> tuple[list[int], int, int]:
    days_present = {s.weekday for s in slots}
    active_days = [d for d in range(5)] + ([5] if 5 in days_present else []) + ([6] if 6 in days_present else [])
    start_hours = [int(s.start_time.split(":")[0]) for s in slots] or [9]
    end_hours = [
        int(s.end_time.split(":")[0]) + (1 if int(s.end_time.split(":")[1]) > 0 else 0)
        for s in slots
    ] or [17]
    return active_days, min(start_hours), max(end_hours)


def format_timetable_markdown(report: TimetableReport, *, center_date: dt.date | None = None) -> str:
    """Render a Day-by-Row Weekly Timetable Table + Subjects legend + Calendar excerpt in Markdown."""
    if not report.weekly_slots and not report.events:
        return (
            f"### {report.semester_label} Timetable · {report.fetched_at}\n\n"
            f"No current-semester timetable events were found on Samarth for roll number `{report.roll_number}`."
        )

    active_days, min_h, max_h = _grid_bounds(report.weekly_slots)
    hours = list(range(min_h, max_h))
    notice = _semester_ended_notice(report)
    sec_lbl = _infer_section_label(report.weekly_slots)
    sub_meta = f"Roll No. `{report.roll_number}` · {report.semester_label}" + (f" · {sec_lbl}" if sec_lbl else "")

    grid: dict[tuple[int, int], str] = {}
    for s in report.weekly_slots:
        sh = int(s.start_time.split(":")[0])
        eh = int(s.end_time.split(":")[0]) + (1 if int(s.end_time.split(":")[1]) > 0 else 0)
        pretty = _title_case_course(s.course_name)
        label = f"**{pretty}** (`{s.course_code} · {s.class_type}`)"
        grid[(s.weekday, sh)] = f"{grid[(s.weekday, sh)]} / {label}" if (s.weekday, sh) in grid else label
        for h in range(sh + 1, eh):
            cont = f"← *{s.course_code} (cont.)*"
            grid[(s.weekday, h)] = f"{grid[(s.weekday, h)]} / {cont}" if (s.weekday, h) in grid else cont

    time_hdr = " | ".join(f"{_fmt_12h(f'{h:02d}:00')} to {_fmt_12h(f'{h + 1:02d}:00')}" for h in hours)
    sep_hdr = " | ".join(":---:" for _ in hours)

    lines = [f"### Timetable · {sub_meta}"]
    if notice:
        lines.append(f"> ℹ️ {notice}")
    lines.extend(["", f"| DAY | {time_hdr} |", f"| :--- | {sep_hdr} |"])

    today_wd = dt.datetime.now(tz=dt.timezone.utc).astimezone().weekday()
    for d in active_days:
        day_lbl = f"**{WEEKDAY_SHORT[d]}** `TODAY`" if d == today_wd else f"**{WEEKDAY_SHORT[d]}**"
        cells = [grid.get((d, h), "—") for h in hours]
        if all(c == "—" for c in cells):
            cells = ["*No classes*" if i == len(hours) // 2 else "" for i in range(len(hours))]
        lines.append(f"| {day_lbl} | {' | '.join(cells)} |")

    seen_subjects: dict[str, WeeklySlot] = {}
    for s in report.weekly_slots:
        seen_subjects.setdefault(s.course_code, s)
    if seen_subjects:
        lines.extend(["", "**SUBJECTS:**"])
        for code, s in seen_subjects.items():
            t_lbl = CLASS_TYPE_LABEL.get(s.class_type, "Lecture")
            lines.append(f"- **{_title_case_course(s.course_name)}** (`{code} · {t_lbl}`)")

    if report.events:
        ref = center_date or dt.datetime.now(tz=dt.timezone.utc).astimezone().date()
        week_start = ref - dt.timedelta(days=ref.weekday())
        week_end = week_start + dt.timedelta(days=6)
        week_events = [e for e in report.events if week_start.isoformat() <= e.date <= week_end.isoformat()]
        cal_title = f"This Week's Calendar ({week_start.isoformat()} to {week_end.isoformat()})"
        if not week_events:
            last_d = dt.date.fromisoformat(report.events[-1].date)
            w_start = last_d - dt.timedelta(days=last_d.weekday())
            w_end = w_start + dt.timedelta(days=6)
            week_events = [e for e in report.events if w_start.isoformat() <= e.date <= w_end.isoformat()]
            cal_title = f"Latest Scheduled Week Calendar ({w_start.isoformat()} to {w_end.isoformat()})"

        lines.extend(["", f"**{cal_title}:**"])
        by_day: dict[str, list[TimetableEvent]] = {}
        for ev in week_events:
            by_day.setdefault(f"{ev.date} ({WEEKDAY_TITLE[ev.weekday]})", []).append(ev)
        badge = {"PRESENT": "● PRESENT", "ABSENT": "○ ABSENT", "LEAVE": "◐ LEAVE", "SCHEDULED": "• SCHEDULED"}
        for day_lbl, evs in by_day.items():
            items = "; ".join(
                f"`{_fmt_12h(e.start_time)}–{_fmt_12h(e.end_time)}` **{_title_case_course(e.course_name)}** ({e.course_code}, {badge[e.status]})"
                for e in evs
            )
            lines.append(f"- **{day_lbl}:** {items}")

    return "\n".join(lines).strip()


def _to_minutes(hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return h * 60 + m


def timetable_to_ui_props(report: TimetableReport) -> dict:
    """Serialize a TimetableReport for Chainlit's DcrustTimetable CustomElement (matching cse.dcrust.online/timetable)."""
    active_days, min_h, max_h = _grid_bounds(report.weekly_slots)
    hours = list(range(min_h, max_h))
    notice = _semester_ended_notice(report)
    section_label = _infer_section_label(report.weekly_slots)
    today_wd = dt.datetime.now(tz=_IST).weekday()

    subjects_map: dict[str, dict] = {}
    for s in report.weekly_slots:
        if s.course_code not in subjects_map:
            subjects_map[s.course_code] = {
                "code": s.course_code,
                "name": _title_case_course(s.course_name),
                "sectionCode": s.section_code,
                "typeShort": s.class_type,
                "typeLabel": CLASS_TYPE_LABEL.get(s.class_type, "Lecture"),
                "colorIndex": len(subjects_map),
            }

    days_data = []
    for d in active_days:
        day_slots = [s for s in report.weekly_slots if s.weekday == d]
        rows = [
            {
                "startHour": int(s.start_time.split(":")[0]),
                "span": max(
                    1,
                    int(s.end_time.split(":")[0]) + (1 if int(s.end_time.split(":")[1]) > 0 else 0) - int(s.start_time.split(":")[0]),
                ),
                "code": s.course_code,
                "name": _title_case_course(s.course_name),
                "typeShort": s.class_type,
                "startLabel": _fmt_12h(s.start_time),
                "endLabel": _fmt_12h(s.end_time),
                "colorIndex": subjects_map[s.course_code]["colorIndex"],
            }
            for s in day_slots
        ]
        days_data.append(
            {
                "weekday": d,
                "label": WEEKDAY_SHORT[d],
                "isToday": d == today_wd,
                "slots": rows,
            }
        )

    cal_day_count = 7 if (6 in active_days or any(e.weekday == 6 for e in report.events)) else len(active_days)

    return {
        "rollNumber": report.roll_number,
        "semesterLabel": report.semester_label,
        "sectionLabel": section_label,
        "notice": notice,
        "gridStartHour": min_h,
        "gridEndHour": max_h,
        "calDayCount": cal_day_count,
        "hours": [
            {"hour": h, "start": _fmt_12h(f"{h:02d}:00"), "end": _fmt_12h(f"{h + 1:02d}:00")}
            for h in hours
        ],
        "days": days_data,
        "subjects": list(subjects_map.values()),
        "events": [
            {
                "date": e.date,
                "startMin": _to_minutes(e.start_time),
                "endMin": _to_minutes(e.end_time),
                "start": _fmt_12h(e.start_time),
                "end": _fmt_12h(e.end_time),
                "code": e.course_code,
                "name": _title_case_course(e.course_name),
                "section": e.section_code,
                "type": e.class_type,
                "status": e.status,
                "colorIndex": subjects_map.get(e.course_code, {}).get("colorIndex", 0),
            }
            for e in report.events
        ],
    }


def format_timetable_html(report: TimetableReport) -> str:
    """Render standalone Day-by-Row Weekly Table + Calendar HTML matching cse.dcrust.online/timetable."""
    props = timetable_to_ui_props(report)
    palette = [
        ("#eef2ff", "#c7d2fe", "#1e1b4b", "#4338ca", "#4f46e5"),  # indigo
        ("#fef9e7", "#fde68a", "#451a03", "#92400e", "#f59e0b"),  # amber
        ("#eff6ff", "#bfdbfe", "#172554", "#0369a1", "#0ea5e9"),  # sky
        ("#ecfdf5", "#a7f3d0", "#064e3b", "#047857", "#10b981"),  # emerald
        ("#fff1f2", "#fecdd3", "#4c0519", "#9f1239", "#f43f5e"),  # rose
        ("#f5f3ff", "#ddd6fe", "#2e1065", "#6d28d9", "#8b5cf6"),  # violet
    ]
    hours = props["hours"]
    today_badge = '<span class="today-pill">TODAY</span>'

    hour_ths = "".join(
        f'<th><div class="th-top">{html_lib.escape(h["start"])}</div>'
        f'<div class="th-sub">to {html_lib.escape(h["end"])}</div></th>'
        for h in hours
    )

    body_rows: list[str] = []
    for day in props["days"]:
        day_cls = "day-col today-row" if day["isToday"] else "day-col"
        day_cell = (
            f'<td class="{day_cls}"><div class="day-name">{html_lib.escape(day["label"])}</div>'
            f'{today_badge if day["isToday"] else ""}</td>'
        )
        if not day["slots"]:
            row_cls = ' class="today-row"' if day["isToday"] else ""
            body_rows.append(
                f'<tr{row_cls}>{day_cell}<td colspan="{max(1, len(hours))}" class="no-classes">No classes</td></tr>'
            )
            continue

        by_start = {}
        for s in day["slots"]:
            by_start.setdefault(s["startHour"], []).append(s)

        cells: list[str] = [day_cell]
        idx = 0
        while idx < len(hours):
            h = hours[idx]["hour"]
            items = by_start.get(h, [])
            if not items:
                cls = "empty-cell today-row" if day["isToday"] else "empty-cell"
                cells.append(f'<td class="{cls}"></td>')
                idx += 1
                continue
            span = max(1, min(items[0]["span"], len(hours) - idx))
            cards = []
            for s in items:
                bg, brd, fg, subfg, _ = palette[s["colorIndex"] % len(palette)]
                cards.append(
                    f'<div class="slot-card" style="background:{bg};border-color:{brd};color:{fg};">'
                    f'<div class="slot-title">{html_lib.escape(s["name"])}</div>'
                    f'<div class="slot-code" style="color:{subfg};">{html_lib.escape(s["code"])} · {html_lib.escape(s["typeShort"])}</div>'
                    "</div>"
                )
            span_attr = f' colspan="{span}"' if span > 1 else ""
            td_cls = ' class="today-row"' if day["isToday"] else ""
            cells.append(f'<td{span_attr}{td_cls}>{"".join(cards)}</td>')
            idx += span
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    legend_items = "".join(
        f'<div class="subj-item">'
        f'<span class="subj-dot" style="background:{palette[s["colorIndex"] % len(palette)][4]};"></span>'
        f'<div><div class="subj-name">{html_lib.escape(s["name"])}</div>'
        f'<div class="subj-meta">{html_lib.escape(s["code"])} · {html_lib.escape(s["typeLabel"])}</div></div>'
        "</div>"
        for s in props["subjects"]
    )
    notice_html = (
        f'<div class="notice-banner">{html_lib.escape(props["notice"])}</div>'
        if props["notice"]
        else ""
    )
    def _safe_inline_json(val: object) -> str:
        return json.dumps(val).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    events_json = _safe_inline_json(props["events"])
    palette_json = _safe_inline_json([
        {"bg": p[0], "brd": p[1], "fg": p[2], "sub": p[3]}
        for p in palette
    ])
    grid_start_hour = props["gridStartHour"]
    grid_end_hour = props["gridEndHour"]
    cal_day_count = props["calDayCount"]
    sem_line = html_lib.escape(props["semesterLabel"] + (f" · {props['sectionLabel']}" if props["sectionLabel"] else ""))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Timetable · {html_lib.escape(props["rollNumber"])}</title>
<style>
* {{ box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:#f8fafc; color:#0f172a; margin:0; padding:1.5rem 1rem; }}
.wrap {{ max-width:1180px; margin:0 auto; }}
.hdr {{ display:flex; align-items:center; gap:0.85rem; margin-bottom:1rem; }}
.hdr-icon {{ width:42px; height:42px; border-radius:12px; background:#eef2ff; color:#4f46e5; display:flex; align-items:center; justify-content:center; font-size:1.25rem; }}
h1 {{ margin:0; font-size:1.45rem; font-weight:800; }}
.roll-line {{ font-size:0.86rem; color:#475569; margin-top:2px; }}
.sem-line {{ font-size:0.82rem; color:#4f46e5; font-weight:600; }}
.notice-banner {{ background:#eef2ff; border:1px solid #c7d2fe; color:#3730a3; padding:0.75rem 1rem; border-radius:0.75rem; font-size:0.85rem; font-weight:500; margin-bottom:1rem; }}
.tabs-pill {{ display:grid; grid-template-columns:1fr 1fr; background:#e2e8f0; border-radius:0.8rem; padding:4px; margin-bottom:1rem; }}
.tab-btn {{ border:none; background:transparent; padding:0.55rem 1rem; border-radius:0.6rem; font-weight:700; font-size:0.82rem; letter-spacing:0.4px; color:#475569; cursor:pointer; }}
.tab-btn.active {{ background:#ffffff; color:#312e81; box-shadow:0 1px 3px rgba(0,0,0,0.08); }}
.card {{ background:#ffffff; border:1px solid #e2e8f0; border-radius:1rem; overflow:hidden; box-shadow:0 1px 3px rgba(15,23,42,0.04); margin-bottom:1rem; }}
.table-wrap {{ overflow-x:auto; }}
table.tt {{ width:100%; border-collapse:collapse; min-width:860px; }}
table.tt th, table.tt td {{ border:1px solid #f1f5f9; padding:0.5rem; vertical-align:middle; }}
table.tt thead th {{ background:#f8fafc; font-weight:600; padding:0.65rem 0.4rem; text-align:center; }}
.th-top {{ font-size:0.78rem; color:#334155; font-weight:700; }}
.th-sub {{ font-size:0.7rem; color:#94a3b8; margin-top:2px; }}
.day-col {{ width:78px; text-align:center; font-weight:700; font-size:0.82rem; color:#334155; }}
.today-row {{ background:#f5f7ff; }}
.today-pill {{ display:inline-block; margin-top:4px; padding:1px 7px; border-radius:999px; background:#4f46e5; color:#fff; font-size:0.62rem; font-weight:800; }}
.no-classes {{ text-align:center; color:#94a3b8; font-style:italic; font-size:0.82rem; padding:1rem; }}
.slot-card {{ border:1px solid; border-radius:0.65rem; padding:0.65rem 0.55rem; text-align:center; min-height:68px; display:flex; flex-direction:column; justify-content:center; }}
.slot-title {{ font-size:0.8rem; font-weight:700; line-height:1.25; }}
.slot-code {{ font-size:0.7rem; font-weight:700; margin-top:4px; }}
.legend {{ padding:1rem 1.25rem; }}
.legend-hdr {{ font-size:0.72rem; font-weight:800; letter-spacing:1px; color:#64748b; margin-bottom:0.85rem; }}
.legend-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:0.85rem 1.5rem; }}
.subj-item {{ display:flex; align-items:flex-start; gap:0.65rem; }}
.subj-dot {{ width:9px; height:9px; border-radius:50%; margin-top:5px; flex-shrink:0; }}
.subj-name {{ font-size:0.88rem; font-weight:700; color:#0f172a; }}
.subj-meta {{ font-size:0.75rem; color:#64748b; margin-top:1px; }}
.hidden {{ display:none; }}
.cal-top {{ display:flex; justify-content:space-between; align-items:center; padding:1rem 1.25rem; border-bottom:1px solid #e2e8f0; }}
.cal-nav {{ display:flex; align-items:center; gap:0.75rem; }}
.nav-circle {{ width:34px; height:34px; border-radius:50%; border:1px solid #e2e8f0; background:#ffffff; color:#475569; font-size:1rem; font-weight:700; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; }}
.nav-circle:hover {{ background:#f8fafc; }}
.nav-circle:disabled {{ opacity:0.4; cursor:default; }}
.cal-range {{ font-size:0.95rem; font-weight:800; color:#0f172a; line-height:1.25; }}
.cal-sub {{ font-size:0.75rem; color:#64748b; margin-top:2px; }}
.today-btn {{ border:1px solid #c7d2fe; background:#eef2ff; color:#4f46e5; border-radius:999px; padding:0.42rem 1rem; font-size:0.72rem; font-weight:800; letter-spacing:0.6px; cursor:pointer; }}
.today-btn:hover {{ background:#e0e7ff; }}
.wk-scroll {{ overflow-x:auto; }}
.wk-wrap {{ min-width:780px; }}
.wk-hdr {{ display:grid; border-bottom:1px solid #e2e8f0; background:#f8fafc; }}
.wk-hdr-day {{ padding:0.7rem 0.4rem; text-align:center; border-left:1px solid #e2e8f0; }}
.wk-hdr-day.is-today {{ background:#eef2ff; }}
.wk-dow {{ font-size:0.68rem; font-weight:700; color:#64748b; letter-spacing:0.5px; }}
.wk-hdr-day.is-today .wk-dow {{ color:#4f46e5; }}
.wk-dom {{ font-size:0.92rem; font-weight:800; color:#0f172a; margin-top:2px; }}
.wk-hdr-day.is-today .wk-dom {{ color:#312e81; }}
.wk-body {{ display:grid; position:relative; }}
.wk-axis {{ position:relative; background:#ffffff; }}
.wk-tick {{ position:absolute; right:8px; transform:translateY(-50%); font-size:0.68rem; font-weight:600; color:#64748b; white-space:nowrap; }}
.wk-day-col {{ position:relative; border-left:1px solid #f1f5f9; }}
.wk-hour-line {{ position:absolute; left:0; right:0; border-top:1px solid #f1f5f9; pointer-events:none; }}
.wk-empty {{ position:absolute; top:22px; left:0; right:0; text-align:center; font-size:0.78rem; color:#94a3b8; }}
.wk-ev {{ position:absolute; border:1px solid; border-radius:0.55rem; padding:0.45rem 0.55rem; overflow:hidden; display:flex; flex-direction:column; justify-content:flex-start; }}
.wk-ev-top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:6px; }}
.wk-ev-name {{ font-size:0.76rem; font-weight:700; line-height:1.25; }}
.wk-ev-code {{ font-size:0.66rem; font-weight:700; margin-top:3px; }}
.wk-dot {{ width:7px; height:7px; border-radius:50%; flex-shrink:0; margin-top:4px; }}
.cal-foot {{ text-align:center; font-size:0.76rem; color:#94a3b8; margin-top:0.5rem; margin-bottom:0.25rem; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <div class="hdr-icon">📅</div>
    <div>
      <h1>Timetable</h1>
      <div class="roll-line">Roll No. <strong>{html_lib.escape(props["rollNumber"])}</strong></div>
      <div class="sem-line">{sem_line}</div>
    </div>
  </div>
  {notice_html}
  <div class="tabs-pill">
    <button class="tab-btn active" id="btn-table" onclick="showTab('table')">▦ TABLE</button>
    <button class="tab-btn" id="btn-cal" onclick="showTab('cal')">🗓 CALENDAR</button>
  </div>
  <div id="tab-table">
    <div class="card table-wrap">
      <table class="tt">
        <thead><tr><th>DAY</th>{hour_ths}</tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    </div>
    <div class="card legend">
      <div class="legend-hdr">SUBJECTS</div>
      <div class="legend-grid">{legend_items}</div>
    </div>
  </div>
  <div id="tab-cal" class="hidden">
    <div class="card">
      <div class="cal-top">
        <div class="cal-nav">
          <button id="wk-prev" class="nav-circle" onclick="shiftWeek(-1)" aria-label="Previous week">&lsaquo;</button>
          <button id="wk-next" class="nav-circle" onclick="shiftWeek(1)" aria-label="Next week">&rsaquo;</button>
          <div>
            <div class="cal-range" id="cal-range"></div>
            <div class="cal-sub" id="cal-sub"></div>
          </div>
        </div>
        <button class="today-btn" onclick="jumpToday()">TODAY</button>
      </div>
      <div class="wk-scroll">
        <div class="wk-wrap">
          <div class="wk-hdr" id="wk-hdr"></div>
          <div class="wk-body" id="wk-body"></div>
        </div>
      </div>
    </div>
    <div class="cal-foot">Synced from Samarth ERP</div>
  </div>
</div>
<script>
const EVENTS = {events_json};
const PALETTE = {palette_json};
const GRID_START_HOUR = {grid_start_hour};
const GRID_END_HOUR = {grid_end_hour};
const CAL_DAYS = {cal_day_count};
const ROW_H = 68;
const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const DOW_LABELS = ["MON","TUE","WED","THU","FRI","SAT","SUN"];
const STATUS_DOTS = {{ PRESENT:"#10b981", ABSENT:"#ef4444", LEAVE:"#f59e0b" }};

function parseIso(iso) {{
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}}
function toIso(d) {{
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}}
function mondayOf(d) {{
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dow = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - dow);
  return copy;
}}
function addDays(d, n) {{
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  copy.setDate(copy.getDate() + n);
  return copy;
}}
function fmtHour(h) {{
  if (h === 0) return "12 AM";
  if (h < 12) return h + " AM";
  if (h === 12) return "12 PM";
  return (h - 12) + " PM";
}}
function esc(s) {{
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}}

const WEEKS = (() => {{
  if (!EVENTS.length) {{
    return [toIso(mondayOf(new Date()))];
  }}
  const sorted = [...EVENTS].sort((a, b) => a.date.localeCompare(b.date));
  const firstMon = mondayOf(parseIso(sorted[0].date));
  const lastMon = mondayOf(parseIso(sorted[sorted.length - 1].date));
  const list = [];
  for (let cur = new Date(firstMon); cur <= lastMon; cur = addDays(cur, 7)) {{
    list.push(toIso(cur));
  }}
  return list;
}})();

let weekIdx = (() => {{
  const todayMon = toIso(mondayOf(new Date()));
  const exact = WEEKS.indexOf(todayMon);
  if (exact >= 0) return exact;
  return WEEKS.length ? WEEKS.length - 1 : 0;
}})();

function showTab(t) {{
  document.getElementById("tab-table").classList.toggle("hidden", t !== "table");
  document.getElementById("tab-cal").classList.toggle("hidden", t !== "cal");
  document.getElementById("btn-table").classList.toggle("active", t === "table");
  document.getElementById("btn-cal").classList.toggle("active", t === "cal");
  if (t === "cal") renderCal();
}}
function shiftWeek(delta) {{
  const next = weekIdx + delta;
  if (next >= 0 && next < WEEKS.length) {{
    weekIdx = next;
    renderCal();
  }}
}}
function jumpToday() {{
  const todayMon = toIso(mondayOf(new Date()));
  const exact = WEEKS.indexOf(todayMon);
  weekIdx = exact >= 0 ? exact : (WEEKS.length ? WEEKS.length - 1 : 0);
  renderCal();
}}
function formatRange(monDate) {{
  const endDate = addDays(monDate, CAL_DAYS - 1);
  if (monDate.getMonth() === endDate.getMonth() && monDate.getFullYear() === endDate.getFullYear()) {{
    return monDate.getDate() + " \u2013 " + endDate.getDate() + " " + MONTHS_SHORT[endDate.getMonth()] + " " + endDate.getFullYear();
  }}
  if (monDate.getFullYear() === endDate.getFullYear()) {{
    return monDate.getDate() + " " + MONTHS_SHORT[monDate.getMonth()] + " \u2013 " + endDate.getDate() + " " + MONTHS_SHORT[endDate.getMonth()] + " " + endDate.getFullYear();
  }}
  return monDate.getDate() + " " + MONTHS_SHORT[monDate.getMonth()] + " " + monDate.getFullYear() + " \u2013 " + endDate.getDate() + " " + MONTHS_SHORT[endDate.getMonth()] + " " + endDate.getFullYear();
}}
function renderCal() {{
  const monIso = WEEKS[weekIdx] || toIso(mondayOf(new Date()));
  const monDate = parseIso(monIso);
  const todayIso = toIso(new Date());
  document.getElementById("cal-range").textContent = formatRange(monDate);
  document.getElementById("cal-sub").textContent = "Week " + (weekIdx + 1) + " of " + Math.max(1, WEEKS.length);
  document.getElementById("wk-prev").disabled = weekIdx <= 0;
  document.getElementById("wk-next").disabled = weekIdx >= WEEKS.length - 1;

  const colTemplate = "64px repeat(" + CAL_DAYS + ", minmax(0, 1fr))";
  const hdrEl = document.getElementById("wk-hdr");
  const bodyEl = document.getElementById("wk-body");
  hdrEl.style.gridTemplateColumns = colTemplate;
  bodyEl.style.gridTemplateColumns = colTemplate;

  const days = [];
  for (let i = 0; i < CAL_DAYS; i++) {{
    const d = addDays(monDate, i);
    days.push({{ dow: DOW_LABELS[i], dom: d.getDate(), iso: toIso(d) }});
  }}

  hdrEl.innerHTML = "<div></div>" + days.map(d =>
    "<div class='wk-hdr-day" + (d.iso === todayIso ? " is-today" : "") + "'>" +
      "<div class='wk-dow'>" + d.dow + "</div>" +
      "<div class='wk-dom'>" + d.dom + "</div>" +
    "</div>"
  ).join("");

  const totalHours = Math.max(1, GRID_END_HOUR - GRID_START_HOUR);
  const gridHeight = totalHours * ROW_H;
  const startMinBase = GRID_START_HOUR * 60;

  let axisHtml = "<div class='wk-axis' style='height:" + gridHeight + "px;'>";
  for (let h = GRID_START_HOUR; h <= GRID_END_HOUR; h++) {{
    const topPx = h === GRID_START_HOUR ? 8 : (h === GRID_END_HOUR ? gridHeight - 8 : (h - GRID_START_HOUR) * ROW_H);
    axisHtml += "<div class='wk-tick' style='top:" + topPx + "px;'>" + fmtHour(h) + "</div>";
  }}
  axisHtml += "</div>";

  let linesHtml = "";
  for (let i = 1; i < totalHours; i++) {{
    linesHtml += "<div class='wk-hour-line' style='top:" + (i * ROW_H) + "px;'></div>";
  }}

  const colsHtml = days.map(d => {{
    const dayEvs = EVENTS.filter(e => e.date === d.iso).sort((a, b) => (a.startMin || 0) - (b.startMin || 0));
    if (!dayEvs.length) {{
      return "<div class='wk-day-col' style='height:" + gridHeight + "px;'>" + linesHtml + "<div class='wk-empty'>No classes</div></div>";
    }}
    const evsHtml = dayEvs.map((ev, idx) => {{
      const sMin = typeof ev.startMin === "number" ? ev.startMin : startMinBase;
      const eMin = typeof ev.endMin === "number" ? ev.endMin : sMin + 60;
      const top = Math.max(2, ((sMin - startMinBase) / 60) * ROW_H + 2);
      const height = Math.max(44, ((eMin - sMin) / 60) * ROW_H - 4);
      const pal = PALETTE[(ev.colorIndex || 0) % PALETTE.length];
      const dotColor = STATUS_DOTS[ev.status] || "";
      const dotHtml = dotColor ? "<span class='wk-dot' title='" + esc(ev.status) + "' style='background:" + dotColor + ";'></span>" : "";
      return "<div class='wk-ev' style='top:" + top + "px;height:" + height + "px;left:4px;right:4px;background:" + pal.bg + ";border-color:" + pal.brd + ";color:" + pal.fg + ";'>" +
        "<div class='wk-ev-top'><div class='wk-ev-name'>" + esc(ev.name) + "</div>" + dotHtml + "</div>" +
        "<div class='wk-ev-code' style='color:" + pal.sub + ";'>" + esc(ev.code) + " &middot; " + esc(ev.type || "L") + "</div>" +
      "</div>";
    }}).join("");
    return "<div class='wk-day-col' style='height:" + gridHeight + "px;'>" + linesHtml + evsHtml + "</div>";
  }}).join("");

  bodyEl.innerHTML = axisHtml + colsHtml;
}}
</script>
</body>
</html>"""


def timetable_to_facts_and_chunks(report: TimetableReport) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, str]]]:
    """Convert a TimetableReport into structured (page, attribute, value) facts and RAG chunks."""
    facts: list[tuple[int, str, str]] = [
        (1, "Samarth Timetable Semester", report.semester_label),
    ]
    by_day: dict[int, list[WeeklySlot]] = {}
    by_course: dict[str, list[WeeklySlot]] = {}
    for s in report.weekly_slots:
        by_day.setdefault(s.weekday, []).append(s)
        by_course.setdefault(s.course_code, []).append(s)

    for wd, slots in sorted(by_day.items()):
        wname = WEEKDAY_NAMES[wd]
        summary = "; ".join(f"{s.start_time}-{s.end_time}: {s.course_code} ({s.course_name})" for s in slots)
        facts.append((1, f"Samarth {wname} timetable", summary))
        facts.append((1, f"{wname} class schedule", summary))

    for code, slots in sorted(by_course.items()):
        cname = slots[0].course_name
        sched = "; ".join(f"{WEEKDAY_TITLE[s.weekday]} {s.start_time}-{s.end_time}" for s in slots)
        facts.append((1, f"{code} class schedule", sched))
        if cname:
            facts.append((1, f"{cname} class schedule", sched))

    md = format_timetable_markdown(report)
    chunks: list[tuple[int, str, str]] = [(1, md, "DCRUST Samarth Timetable")]
    return facts, chunks
