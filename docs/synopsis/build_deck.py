"""Combine slides/*.html into one standalone deck.html (open in any browser).

Usage: python docs/synopsis/build_deck.py
Keys in the deck: ← → to move, F for fullscreen, Ctrl+P to save as PDF.
"""
import re
from pathlib import Path

HERE = Path(__file__).parent
ORDER = ["cover", "problem", "fastslow", "flow", "examples", "academics", "guardrails",
         "observability", "status", "results", "research", "evaluation", "stack", "plan",
         "future", "thanks"]

# Lucide-style 24x24 stroke icons
ICONS = {
    "Lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "Book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
    "Code": '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    "Users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "Verified": '<circle cx="12" cy="8" r="6"/><path d="M15.5 13 17 22l-5-3-5 3 1.5-9"/>',
    "Clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "Chat": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "Search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "Lightning": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "Globe": '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    "Key": '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>',
    "Database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
    "Warning": '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "Star": '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    "GraduationCap": '<path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/><line x1="22" y1="10" x2="22" y2="16"/>',
    "Lightbulb": '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z"/>',
    "CheckCircle": '<circle cx="12" cy="12" r="10"/><polyline points="8 12 11 15 16 9"/>',
    "Activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
}


def icon(m):
    name, style = m.group(1), m.group(2)
    return (f'<svg style="{style};flex:none" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


def arrow(m):
    style = m.group(1)
    fill = re.search(r"background:([^;]+)", style).group(1)
    style = re.sub(r"background:[^;]+;?", "", style)
    return (f'<svg style="{style};flex:none" viewBox="0 0 56 32" preserveAspectRatio="none">'
            f'<polygon points="0,10 34,10 34,0 56,16 34,32 34,22 0,22" fill="{fill}"/></svg>')


def connectors(html):
    lines = []
    for m in re.finditer(r'<x-connector x1="(\d+)" y1="(\d+)" x2="(\d+)" y2="(\d+)" head="(\w+)"[^>]*color:([^;"]+);border-width:(\d+)px[^>]*></x-connector>\n?', html):
        x1, y1, x2, y2, head, color, w = m.groups()
        mid = f"m{len(lines)}"
        marker = (f'<defs><marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" '
                  f'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker></defs>') if head == "end" else ""
        end = f' marker-end="url(#{mid})"' if head == "end" else ""
        lines.append(f'{marker}<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}"{end}/>')
    html = re.sub(r'<x-connector[^>]*></x-connector>\n?', "", html)
    if lines:
        svg = ('<svg style="position:absolute;left:0;top:0;width:1920px;height:1080px" '
               'viewBox="0 0 1920 1080">' + "".join(lines) + "</svg>")
        html = re.sub(r'(<section[^>]*>)', r'\1' + svg, html, count=1)
    return html


def convert(html):
    html = re.sub(r'<x-icon name="(\w+)" style="([^"]*)"></x-icon>', icon, html)
    html = re.sub(r'<x-shape kind="arrow-right" style="([^"]*)"></x-shape>', arrow, html)
    return connectors(html)


slides = "\n".join(
    re.sub(r"Smriti · \d+", f"Smriti · {n}", convert((HERE / "slides" / f"{s}.html").read_text()))
    for n, s in enumerate(ORDER, 1))

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smriti – Synopsis</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400..700&family=IBM+Plex+Sans:wght@400;600&family=JetBrains+Mono&family=Noto+Sans+Devanagari:wght@600&display=swap">
<style>
  html, body {{ margin:0; height:100%; background:#0B141D; overflow:hidden; }}
  #stage {{ position:absolute; left:50%; top:50%; width:1920px; height:1080px; transform-origin:center; }}
  section {{ position:absolute; inset:0; width:1920px; height:1080px; box-sizing:border-box; }}
  section:not(.active) {{ display:none !important; }}
  section * {{ margin:0; box-sizing:border-box; }}
  section ul {{ padding-left:1.1em; }}
  section aside {{ display:none; }}
  section table {{ border-collapse:collapse; }}
  section th {{ text-align:left; font-weight:600; border-bottom:2px solid #12202E; padding:12px 16px; }}
  section td {{ border-bottom:1px solid #DDD8CC; padding:12px 16px; }}
  #counter {{ position:fixed; right:16px; bottom:12px; color:#8FA1B3; font:14px sans-serif; }}
  @media print {{
    @page {{ size:1920px 1080px; margin:0; }}
    html, body {{ height:auto; overflow:visible; background:none; }}
    #stage {{ position:static; transform:none !important; }}
    section, section:not(.active) {{ position:relative; display:flex !important; page-break-after:always; break-after:page; }}
    #counter {{ display:none; }}
  }}
</style></head>
<body><div id="stage">
{slides}
</div><div id="counter"></div>
<script>
  const s = [...document.querySelectorAll('section')];
  let i = Math.max(0, Math.min(s.length - 1, parseInt(location.hash.slice(1) || '1') - 1));
  function show() {{
    s.forEach((el, k) => el.classList.toggle('active', k === i));
    document.getElementById('counter').textContent = (i + 1) + ' / ' + s.length;
    history.replaceState(null, '', '#' + (i + 1));
  }}
  function fit() {{
    const k = Math.min(innerWidth / 1920, innerHeight / 1080);
    document.getElementById('stage').style.transform = `translate(-50%,-50%) scale(${{k}})`;
  }}
  addEventListener('keydown', e => {{
    if (['ArrowRight', 'PageDown', ' '].includes(e.key)) i = Math.min(s.length - 1, i + 1);
    else if (['ArrowLeft', 'PageUp'].includes(e.key)) i = Math.max(0, i - 1);
    else if (e.key === 'f') document.documentElement.requestFullscreen?.();
    else return;
    show();
  }});
  addEventListener('click', e => {{ i = e.clientX > innerWidth / 2 ? Math.min(s.length - 1, i + 1) : Math.max(0, i - 1); show(); }});
  addEventListener('resize', fit); fit(); show();
</script></body></html>
"""
(HERE / "deck.html").write_text(page)
print("wrote", HERE / "deck.html")
