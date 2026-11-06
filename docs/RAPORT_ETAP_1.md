# Raport etapu 1 — MONIVEX 0.1.0

## 1. Architektura

WEB: React/TypeScript/Vite, Router, Query, RHF/Zod, i18next, Tailwind i komponent przycisku zgodny z konwencją shadcn/ui. API: FastAPI/Pydantic, SQLAlchemy 2, Argon2id. Baza SQLite z WAL i migracjami Alembic. WEB i API działają pod jednym originem przez Nginx. Migracje wykonuje oddzielny jednorazowy kontener; przyszły worker jest celowo poza zakresem etapu 1.

## 2. Pliki i moduły

- `backend/app/`: konfiguracja środowiska, połączenia, modele, walidacja, bezpieczeństwo i endpointy.
- `backend/migrations/`: jawna początkowa migracja z bezpiecznym singletonem instalacji.
- `backend/tests/`: izolowane bazy z prawdziwymi migracjami i testy integracyjne.
- `frontend/src/`: kreator, logowanie, układ panelu, konto, klient API, polskie zasoby i motywy.
- `frontend/e2e/`: rzeczywisty przepływ przeglądarkowy na jednorazowej bazie.
- Dockerfile obu aplikacji, `compose.yaml`, konfiguracja Nginx, `.env.example`, lockfile zależności.
- `.github/workflows/ci.yml`, README, CONTRIBUTING, SECURITY, CHANGELOG oraz dokumentacja instalacji, API, administracji i planu.

Istniejącą licencję Apache 2.0 zachowano. Nie zmieniano zdalnego repozytorium i nie wykonano merge.

## 3. Działające funkcje

Jednorazowa inicjalizacja chroniona sekretem wdrożenia, atomowe utworzenie właściciela i ustawień, odrzucenie ponownej inicjalizacji, logowanie, trwałe sesje z terminem ważności, HttpOnly/SameSite/Secure, Origin i CSRF, limit prób logowania zapisany w bazie, zmiana hasła i unieważnianie sesji, wylogowanie jednego lub wszystkich urządzeń. Podstawowy audyt jest zapisywany w bazie.

Polski kreator, responsywna nawigacja, zwijane menu, motyw ciemny/jasny/systemowy, stany ładowania i błędów, potwierdzenie wylogowania wszystkich urządzeń, panel bezpieczeństwa konta. Dashboard jawnie informuje o braku silnika i nie pokazuje fikcyjnego zdrowego stanu. Nazwa instalacji i strefa czasowa pochodzą z API.

## 4. Uruchomienie

Skopiuj `.env.example` do `.env`, ustaw własny losowy sekret minimum 32 znaki i dokładny publiczny origin. Dla lokalnego HTTP ustaw `MONIVEX_COOKIE_SECURE=false`; dla HTTPS pozostaw true. Uruchom `docker compose up --build -d`. Domyślny port to 8080, bind tylko na loopback. Host nie potrzebuje Node ani Pythona. Szczegóły LAN, Caddy i Nginx w INSTALACJA.md.

## 5. Pierwsza konfiguracja

Powitanie → login właściciela, hasło minimum 12 znaków i sekret wdrożenia → nazwa instalacji i strefa → informacja o przyszłych opcjach SMTP/monitorów → podsumowanie. Po zapisie następuje logowanie. Sekret inicjalizacyjny nie jest zwracany przez API. Brak publicznej rejestracji i możliwości utworzenia drugiego właściciela przez kreator.

## 6. Wykonane kontrole

| Kontrola | Wynik końcowy |
| --- | --- |
| pytest backendu | **11/11 zaliczonych** na aktualnych zależnościach |
| Vitest / React Testing Library | **3/3 zaliczone** |
| Chromium / Playwright bez Dockera | **1/1 zaliczony**, pełny przepływ |
| Chromium / Playwright przez Compose | **1/1 zaliczony**, pełny przepływ przez Nginx/API/SQLite |
| TypeScript i produkcyjna budowa Vite | Zaliczona |
| Ruff i ESLint (z katalogów opisanych w README) | Zaliczone |
| Budowa obrazów API i WEB | Zaliczona z weryfikacją TLS i CA proxy |
| Compose na nowym wolumenie | Migracje zakończone, API i WEB **healthy** |
| Restart API | Gotowość wróciła, inicjalizacja zachowana, powtórny setup **409**, niezalogowany dostęp **401** |
| Migracje upgrade / ponowienie / downgrade / upgrade | Zaliczona w pytest |
| pip-audit zależności produkcyjnych | **0 znanych podatności** w momencie sprawdzenia |
| npm audit (także zależności developerskie) | **0 znanych podatności** w momencie sprawdzenia |
| `pip check`, `git diff --check` | Zaliczone |

Backend sprawdza też równoczesną inicjalizację (dokładnie jeden właściciel), brak ujawniania danych w błędach walidacji, hashe Argon2id i tokenów, wygasanie sesji, ochronę Origin/CSRF, ciasteczka, limity prób i zmianę hasła. Test przeglądarkowy obejmuje zmianę motywu, odświeżenie, zmianę hasła, ponowne logowanie i menu/wylogowanie na ekranie 390 px.

Pierwsze próby wykryły i pozwoliły usunąć problem praw plików konfiguracyjnych w obrazach bez roota oraz korzystanie przez wget z proxy przy lokalnym health checku. Ustalono limit oczekiwania E2E odpowiedni dla kosztu Argon2 w izolowanym runtime. Nie obniżano parametrów haszowania i nie wyłączano weryfikacji TLS ani asercji.

CI zostało przygotowane; zdalnego uruchomienia GitHub Actions w tym zadaniu nie wykonano. Przykłady HTTPS przez Caddy/Nginx nie były uruchamiane. Pozostają nieblokujące ostrzeżenia bundlera o rozmiarze pakietu JS i adnotacjach biblioteki Zod oraz ostrzeżenie Starlette o przyszłym przejściu TestClient na httpx2.

## 7. Ograniczenia

To fundamenty, nie działający system monitoringu: brak workera, monitorów, historii kontroli, alertów, raportów, zasobów/grup/tagów, SSE, MFA, panelu użytkowników, backup/restore i retencji. Menu tych modułów informuje o przyszłych etapach. Obecnie istnieje tylko konto właściciela; dodatkowe role nie są deklarowane jako działające. Audyt nie ma jeszcze ekranu WWW. Ustawienia instalacji zapisuje kreator; panel pozwala zmieniać motyw i hasło, nie wszystkie ustawienia produktu.

PostgreSQL nie jest zweryfikowany ani oferowany jako wspierana baza. Za dołączonym Nginx limit logowania jest wspólny dla instalacji. Nowa karta może wymagać ponownego logowania, aby otrzymać CSRF. Nie ma procedury odzyskiwania zapomnianego hasła właściciela w WWW. Pełne polityki SSRF, role i szyfrowanie sekretów innych niż hasła będą konieczne przed dodaniem odpowiednich funkcji.

## 8. Dalsza jakość

Przed wydaniem produkcyjnym potrzebne są m.in. audyt niezależny, MFA i odzyskiwanie kont, testy reverse proxy z HTTPS/LAN, obciążenia i pełnego przywracania danych. Należy dopracować rozpoznawanie zaufanego proxy, retencję, logi strukturalne oraz dzielenie pakietów WEB. Brak znanych podatności w audycie nie jest dowodem braku błędów bezpieczeństwa.

## 9. Gotowość do lokalnych testów

**Tak, etap 1 jest gotowy do lokalnego testowania.** Testy używały wyłącznie jednorazowych kont i baz. Ich kontenery i wolumen zostały usunięte po walidacji, aby nie pozostawić zainicjalizowanej instalacji z testowym, losowym hasłem. W repozytorium nie ma `.env` z sekretami ani testowych baz. Nie wykonano wdrożenia produkcyjnego ani publikacji stabilnego wydania.

## 10. Kolejny etap

Etap 2: polityka dozwolonych celów i ochrona DNS/SSRF, jeden niezależny scheduler, ograniczona współbieżność, prawdziwe kontrole, trwały harmonogram, historia oraz maszyna stanów. Najpierw testowalny przepływ kontroli i zapisu; następnie kolejne typy. Nie zaczynano masowej implementacji etapów 2–7.
