# Site Direction (2026-02-17)

## North Star
Strona ma byc **czytelnym hubem wartosci biznesowej**, a nie zbiorem narzedzi i eksperymentalnych podstron.

Jedno zdanie produktu:
- "Dowoze systemy AI i automatyzacje od problemu biznesowego do mierzalnego wyniku."

## Positioning
- Segment: SMB / lokalne uslugi / founderzy potrzebujacy szybkich automatyzacji i wdrozen AI.
- Obietnica: szybkie wdrozenie + mierzalne KPI + prosty UX dla zespolu.

## Information Architecture (docelowa)
1. `index.html` - wejscie, value proposition, CTA
2. `oferta.html` - pakiety i proces wspolpracy
3. `portfolio.html` - 3 filary (Product, Automation, Web Presence)
4. `demo.html` - publiczny podglad flow i proof
5. `audyt.html` - lead magnet / kwalifikacja
6. `kontakt.html` - konwersja

Pages techniczne (`kling`, `gemini`, `seedance`, `seedream`, `tools`) traktowac jako podstrony produktowe, nie glowna narracja.

## Messaging Rules
Kazdy case i kazda usluga musi miec ten sam format:
- Problem
- Decyzje
- Wynik (liczby)
- Linki / proof
- Moja rola

## Conversion Strategy
Primary CTA:
- "Umow audyt" -> `audyt.html` / `kontakt.html`

Secondary CTA:
- "Zobacz demo" -> `demo.html`
- "Zobacz case" -> `portfolio.html`

## KPI (na 8 tygodni)
- + poprawa CTR do `kontakt.html`
- + liczba wyslanych formularzy kontaktowych
- + czas na stronie `portfolio.html`
- + odsetek sesji z przejsciem `index -> oferta -> kontakt`

## Technical Direction
1. Stabilizowac wspolny shell (header/footer/typografia) na wszystkich aktywnych stronach.
2. Ograniczyc inline CSS/JS i przenosic do `assets/`.
3. Kazda nowa strona tylko po decyzji IA (bez kolejnych wariantow `*-v2`, `*-fixed`, `*.bak`).
4. Legacy trzymac tylko w `_legacy_archive`.

## Execution Backlog
### P0
- Ujednolicic copy i polskie znaki (usunac mojibake) na aktywnych stronach.
- Dodac mini case snippets na `index.html` prowadz¹ce do `portfolio.html`.
- Ujednolicic CTA wording na wszystkich stronach.

### P1
- Dodaæ analityke eventow CTA (klik audyt/demo/kontakt).
- Skrocic i uproscic `oferta.html` pod decyzje zakupowa.
- Dodac 2-min demo video embed w `demo.html`.

### P2
- SEO techniczne (title/description/canonical/OG).
- Performance pass (assets compression + lazy load).
