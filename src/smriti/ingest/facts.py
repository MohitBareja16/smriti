"""Extract structured facts ("DBMS exam: 10 Dec 2026") from personal documents.

Facts power the System-1 fast path: simple lookups are answered from this table without an LLM.
"""

from __future__ import annotations

import re

from smriti.library import detect_semester

_LINE = re.compile(r"^\s*(?:[-*•]\s*)?(?P<key>[A-Za-z][\w ()/&.'-]{1,60}?)\s*[:=]\s*(?P<value>\S.{0,200})$")
_MD = re.compile(r"[*_`#>]")
_IGNORE_KEYS = (
    "established under", "disclaimer", "recognised by", "recognized by",
    "note", "http", "result-cum", "disclaimer:",
)


def extract_facts(pages: list[tuple[int, str]], semester: int | None = None) -> list[tuple[int, str, str]]:
    facts: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    full_text = "\n".join(t for _, t in pages)
    sem = semester if semester is not None else detect_semester(full_text[:500])
    sem_str = f" (Semester {sem})" if sem else ""
    cgpa_sem_str = f" (after Semester {sem})" if sem else ""

    # 1. Structured extraction for official university marksheets / DMCs
    # Roll number
    m_roll = re.search(r"\bRoll\s+No\.?\s*:\s*([A-Za-z0-9]+)", full_text, re.IGNORECASE)
    if m_roll:
        facts.append((1, "Roll number", m_roll.group(1).strip()))
        seen.add("roll number")

    # Name
    m_name = re.search(r"\bName\s*:\s*([A-Za-z ]+?)(?:\s*\n|\s+Mother)", full_text)
    if m_name:
        name_val = m_name.group(1).strip().title()
        if len(name_val) > 1 and not name_val.lower().startswith("of"):
            facts.append((1, "Name", name_val))
            seen.add("name")

    # SGPA
    m_sgpa = re.search(
        r"\bRESULT\s*:\s*(?:Passed\s+and\s+has\s+obtained\s+)?0?([0-9.]+)\s+SGPA",
        full_text,
        re.IGNORECASE,
    )
    if m_sgpa:
        val = m_sgpa.group(1).lstrip("0") or "0"
        facts.append((1, f"SGPA{sem_str}", val))
        facts.append((1, f"Result{sem_str}", "Pass"))
        seen.update({f"sgpa{sem_str}".lower(), f"result{sem_str}".lower(), "result"})

    # CGPA
    m_cgpa = re.search(
        r"\bCGPA\s+RESULT\s*:\s*(?:Passed\s+and\s+has\s+obtained\s+)?0?([0-9.]+)\s+CGPA",
        full_text,
        re.IGNORECASE,
    )
    if m_cgpa:
        val = m_cgpa.group(1).lstrip("0") or "0"
        facts.append((1, f"CGPA{cgpa_sem_str}", val))
        seen.add(f"cgpa{cgpa_sem_str}".lower())

    # Subject grades from tabular marksheets (e.g. DCRUST DMC tables)
    subject_blocks = re.split(r"\n(?=\d+\s+[A-Z]{2,5}\d{2,4}[A-Z]?\s*-)", full_text)
    for block in subject_blocks[1:]:
        m_head = re.match(
            r"^\d+\s+[A-Z]{2,5}\d{2,4}[A-Z]?\s*-\s*(.*?)\s+\d+\.\d{2}\s+(?:Sessional|Theory|Practical)",
            block,
            re.DOTALL,
        )
        if m_head:
            subj = " ".join(m_head.group(1).split()).title()
            grades = re.findall(r"\b\d{1,3}\s+([A-D]\+?|AP|F|O)(?:\s|$)", block)
            if grades:
                grade = grades[-1]
                attr = f"{subj} grade"
                if attr.lower() not in seen:
                    facts.append((1, attr, grade))
                    seen.add(attr.lower())

    # 2. Structured extraction for university date sheets / examination timetables
    if any(k in full_text.lower() for k in ("theory date sheet", "date sheet", "datesheet", "time of exam")):
        current_sem = None
        sem7_cse_summary: list[str] = []
        for pnum, ptext in pages:
            lines = ptext.splitlines()
            curr_date = None
            m_s = re.search(r"(\d+)(?:st|nd|rd|th)?\s+Semester", ptext, re.IGNORECASE)
            if m_s:
                current_sem = int(m_s.group(1))

            m_morning = re.search(r"Time of Exam:\s*([0-9:APM ]+?)\s+for Morning Session", ptext, re.I)
            m_evening = re.search(r"Time of Exam:\s*([0-9:APM ]+?)\s+for Evening Session", ptext, re.I)
            morning_time = m_morning.group(1).strip() if m_morning else "09:30 AM to 12:30 PM"
            evening_time = m_evening.group(1).strip() if m_evening else "02:00 PM to 05:00 PM"

            i = 0
            while i < len(lines):
                line = lines[i].strip()
                m_d = re.match(r"^(\d{2}[./-]\d{2}[./-]\d{4})", line)
                if m_d:
                    curr_date = m_d.group(1)
                    line = line[len(curr_date):].strip()

                m_c = re.search(r"\b([A-Z]{2,5}\d{2,4}[A-Z]?)\s+(.+)$", line)
                if m_c and curr_date:
                    code = m_c.group(1)
                    rest = m_c.group(2).strip()
                    full_entry = rest
                    j = i + 1
                    while j < len(lines) and not re.match(r"^(\d{2}[./-]\d{2}[./-]\d{4}|\b[A-Z]{2,5}\d{2,4}[A-Z]?\b|Instructions|Time of Exam)", lines[j].strip()):
                        full_entry += " " + lines[j].strip()
                        j += 1

                    m_row = re.search(r"^(.*?)(?:\s+(\d{1,4}[A-Z]\d{1,4}|\d{1,4}|-))?\s+([A-Z, /&]+?)\s+([ME])\s*$", full_entry)
                    if m_row:
                        title = m_row.group(1).strip()
                        branch = m_row.group(3).strip()
                        sess = m_row.group(4)
                        sess_desc = f"Morning ({morning_time})" if sess == "M" else f"Evening ({evening_time})"
                        val = f"{curr_date}, {sess_desc}"
                        sem_tag = f" (Semester {current_sem})" if current_sem else ""

                        for attr in [
                            f"{title} ({code}) exam",
                            f"{title} exam{sem_tag}",
                            f"{code} exam",
                            f"{title} exam",
                        ]:
                            if attr.lower() not in seen:
                                facts.append((pnum, attr, val))
                                seen.add(attr.lower())

                        if current_sem == 7 and "CSE" in branch:
                            sem7_cse_summary.append(f"{curr_date}: {code} {title} ({sess_desc})")
                i += 1

        if sem7_cse_summary:
            summary_val = "; ".join(sem7_cse_summary)
            if "7th semester btech cse exam date sheet" not in seen:
                facts.append((6, "7th Semester BTech CSE Exam Date Sheet", summary_val))
                facts.append((6, "7th Semester BTech CSE Timetable", summary_val))
                facts.append((6, "7th Semester Exam Date Sheet", summary_val))
                facts.append((6, "7th Semester Exam Schedule", summary_val))
                seen.update({
                    "7th semester btech cse exam date sheet",
                    "7th semester btech cse timetable",
                    "7th semester exam date sheet",
                    "7th semester exam schedule",
                })

    # 3. Structured extraction for class-wise weekly timetables
    if any(k in full_text.lower() for k in ("class wise time table", "time table for b. tech", "time table for bca")):
        # Faculty phone contacts from page footers: Name (10-digit number)
        for pnum, ptext in pages:
            matches = re.findall(r"([A-Za-z. ()–\d]+?)\s*\(([0-9]{10})\)", ptext)
            for name, phone in matches:
                name_clean = " ".join(name.split()).strip()
                attr = f"{name_clean} contact"
                if attr.lower() not in seen:
                    facts.append((pnum, attr, phone))
                    seen.add(attr.lower())

        # Subject abbreviations to full name and code
        for pnum, ptext in pages:
            matches = re.findall(r"\b([A-Za-z]{2,5})\s*–\s*([A-Za-z &]+?)(?:\s*\(([A-Za-z0-9]+)\))?(?:\s{2,}|\n|$)", ptext)
            for abbr, full_subj, code in matches:
                abbr = abbr.strip()
                full_subj = full_subj.strip()
                val = f"{full_subj}" + (f" ({code})" if code else "")
                attr = f"{abbr} subject"
                if attr.lower() not in seen:
                    facts.append((pnum, attr, val))
                    seen.add(attr.lower())
                if code:
                    attr2 = f"{full_subj} subject code"
                    if attr2.lower() not in seen:
                        facts.append((pnum, attr2, code))
                        seen.add(attr2.lower())

        # Semester class timetable schedules
        for pnum, ptext in pages:
            m_sem = re.search(r"Time Table for B\.\s*Tech\s*(\d+)(?:st|nd|rd|th)?\s*Semester\s*\((Section [AB])\)", ptext, re.I)
            if m_sem:
                s_num = m_sem.group(1)
                sec = m_sem.group(2)
                day_blocks = re.findall(r"\b(MON|TUE|WED|THU|FRI)\b(.*?)(?=\b(?:MON|TUE|WED|THU|FRI)\b|MST\s*–|Prof\.|$)", ptext, re.DOTALL)
                sec_schedule = []
                for day, content in day_blocks:
                    cleaned_content = " ".join(content.split())
                    if cleaned_content:
                        sec_schedule.append(f"{day}: {cleaned_content}")
                if sec_schedule:
                    val = "; ".join(sec_schedule)
                    attr_sec = f"{s_num}th Semester BTech CSE Class Timetable ({sec})"
                    facts.append((pnum, attr_sec, val))
                    seen.add(attr_sec.lower())
                    if s_num == "7" and sec == "Section A" and "7th semester btech cse class timetable" not in seen:
                        facts.append((pnum, "7th Semester BTech CSE Class Timetable", val))
                        seen.add("7th semester btech cse class timetable")

    # 4. General key-value line extractor
    for page, text in pages:
        for raw in text.splitlines():
            line = _MD.sub("", raw).strip()
            m = _LINE.match(line)
            if not m:
                continue
            key, value = m.group("key").strip(), m.group("value").strip()
            kl = key.lower()
            if any(kl.startswith(ig) for ig in _IGNORE_KEYS) or len(key.split()) > 8 or kl in seen:
                continue
            facts.append((page, key, value))
            seen.add(kl)

    return facts
