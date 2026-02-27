# Encoding QA Report

Date: 2026-02-19  
Scope: `*.html`, `*.js`, `*.md` (excluding `_legacy_archive/**`)

## Result
- Mojibake scan status: PASS
- Found broken encoding markers (`Ã`, `â`, `Ä`, `Ĺ`, `Ă`, `ďż`, `�`): 0
- Replacement label without value (`data-track` without `data-track-label`): already 0 (validated in CTA map report)

## Commands used
- `rg -n --glob '!_legacy_archive/**' --glob '*.html' --glob '*.js' --glob '*.md' '�|Ã|â|Ä|Ĺ|Ă|ďż|â€“|â€”|â€|Â' .`

## Notes
- Active production files are clean from encoding artifacts.
- Historical encoding artifacts remain only in archive files under `_legacy_archive/`, intentionally excluded from production QA.
