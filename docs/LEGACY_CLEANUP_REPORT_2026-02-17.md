# Legacy Cleanup Report (2026-02-17)

## Goal
Usunac chaos z root projektu bez utraty historii: nic nie kasowane, tylko archiwizowane.

## Actions completed
Utworzono katalog:
- `_legacy_archive/`
  - `patch-scripts/`
  - `html-backups/`
  - `html-variants/`
  - `fix-scripts/`

Przeniesiono:
- patch scripts: `patch-*.ps1`, `scan-and-patch-kling.ps1`
- fix script: `fix_mojibake.py`
- backup/variant HTML: `*.bak*`, `index.fixed.html`, `index.merged.html`, itp.
- nieuzywane warianty: `portfolio.navfixed.html`, `seedance-15-pro1.html`, `seedance-console.html`, `seedance-ui.html`

## Current clean root (active)
- Core pages: `index`, `oferta`, `portfolio`, `demo`, `audyt`, `kontakt`, `faq`, `o-mnie`
- Product pages: `kling`, `gemini`, `seedance-15-pro`, `seedream-4-0`, `seedream-4-5`, `tools`
- Runtime/scripts: `start-dev.ps1`, `start-dev.bat`, `start-backend.ps1`

## Guardrails (from now)
1. Brak nowych plikow typu `*.bak`, `*.fixed`, `*.merged` w root.
2. Brak patch scriptow w root.
3. Kazdy eksperyment laduje od razu do `_legacy_archive` lub osobnego brancha.
4. Root zawiera tylko aktywne strony i pliki runtime.
