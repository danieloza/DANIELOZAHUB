from pathlib import Path

ROOT = Path(".")
EXTS = {".html", ".css", ".js"}

def fix(text: str) -> str:
    # klasyczne odkręcanie mojibake: "Ä™" -> "ę", "Â©" -> "©"
    try:
        return text.encode("latin1").decode("utf-8")
    except Exception:
        return text

def ensure_meta_charset(html: str) -> str:
    low = html.lower()
    if "<meta charset" in low:
        return html
    i = low.find("<head")
    if i == -1:
        return html
    j = low.find(">", i)
    if j == -1:
        return html
    return html[:j+1] + '\n  <meta charset="utf-8">' + html[j+1:]

for p in ROOT.rglob("*"):
    if p.is_file() and p.suffix.lower() in EXTS:
        raw = p.read_text(encoding="utf-8", errors="replace")
        if any(x in raw for x in ["Ã", "Â", "Ä", "Å"]):
            new = fix(raw)
            if p.suffix.lower() == ".html":
                new = ensure_meta_charset(new)
            # zapis UTF-8 bez BOM
            p.write_text(new, encoding="utf-8", newline="\n")
            print("FIX:", p)
        else:
            # tylko dopilnuj meta w html
            if p.suffix.lower() == ".html":
                new = ensure_meta_charset(raw)
                if new != raw:
                    p.write_text(new, encoding="utf-8", newline="\n")
                    print("META:", p)

print("DONE")
