# DANIELOZA AI Site

## PL
Publiczne portfolio DANIELOZA.AI: strona ofertowa, case studies, demo narzedzi AI i panel administracyjny do obslugi leadow.

### Zakres strony
- Strony glowne: `index.html`, `oferta.html`, `kontakt.html`, `faq.html`
- Portfolio i audyt: `portfolio.html`, `case-studies.html`, `audyt.html`
- Studio/demo: `demo.html`, `kling.html`, `seedance-1-5-pro.html`, `gemini.html`, `seedream-4-0.html`, `seedream-4-5.html`
- SEO i legal: `robots.txt`, `sitemap.xml`, `privacy.html`, `cookies.html`

### Stack
- HTML5
- CSS3 (`assets/css/style.css`)
- JavaScript (`assets/js/main.js`)
- Backend API (Python/FastAPI) w katalogu `backend/`

### Uruchomienie lokalne
Opcja 1:
```powershell
.\start-dev.ps1
```

Opcja 2:
```powershell
cd C:\Users\syfsy\OneDrive\Desktop\DANIELOZA_AI_site
python -m http.server 5500 --bind 127.0.0.1
```

Otworz: `http://127.0.0.1:5500`

### Najwazniejsze pliki projektowe
- Mapowanie eventow: `ANALYTICS_EVENTS.md`
- Konfiguracja GA4: `GA4_REPORTING_SETUP.md`, `assets/js/analytics.config.js`
- Playbook operacyjny: `OPERATIONS_PLAYBOOK.md`
- Plan dlugoterminowy: `MASTER_EXECUTION_PLAN_2026-2027.md`

### Admin i API (skrot)
- Admin prosty: `admin-simple.html`
- Admin techniczny: `admin.html`
- Lead API: `POST /api/leads`
- Analytics API: `POST /api/analytics/events`
- Admin API: `/api/admin/*`

### Licencja
Projekt prywatny portfolio. Wykorzystanie tylko za zgoda autora.

---

## EN
Public portfolio website for DANIELOZA.AI: offer pages, case studies, AI tool demos, and an admin workspace for lead operations.

### Site scope
- Main pages: `index.html`, `oferta.html`, `kontakt.html`, `faq.html`
- Portfolio and audit: `portfolio.html`, `case-studies.html`, `audyt.html`
- Studio/demo pages: `demo.html`, `kling.html`, `seedance-1-5-pro.html`, `gemini.html`, `seedream-4-0.html`, `seedream-4-5.html`
- SEO and legal: `robots.txt`, `sitemap.xml`, `privacy.html`, `cookies.html`

### Stack
- HTML5
- CSS3 (`assets/css/style.css`)
- JavaScript (`assets/js/main.js`)
- Backend API (Python/FastAPI) in `backend/`

### Run locally
Option 1:
```powershell
.\start-dev.ps1
```

Option 2:
```powershell
cd C:\Users\syfsy\OneDrive\Desktop\DANIELOZA_AI_site
python -m http.server 5500 --bind 127.0.0.1
```

Open: `http://127.0.0.1:5500`

### Key project docs
- Event map: `ANALYTICS_EVENTS.md`
- GA4 setup: `GA4_REPORTING_SETUP.md`, `assets/js/analytics.config.js`
- Operations playbook: `OPERATIONS_PLAYBOOK.md`
- Long-term roadmap: `MASTER_EXECUTION_PLAN_2026-2027.md`

### Admin and API (summary)
- Simple admin: `admin-simple.html`
- Technical admin: `admin.html`
- Lead API: `POST /api/leads`
- Analytics API: `POST /api/analytics/events`
- Admin API: `/api/admin/*`

### License
Private portfolio project. Reuse only with author permission.
