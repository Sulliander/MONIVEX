# Plan implementacji MONIVEX

## Architektura i granice etapu 1

Modularny monolit API (FastAPI, Pydantic, SQLAlchemy 2), osobny WEB (React, TypeScript, Vite) i przyszły proces WORKER. WEB komunikuje się z API przez ten sam origin `/api`; Nginx serwuje SPA i przekazuje API. SQLite na trwałym wolumenie, WAL, klucze obce i busy timeout 15 sekund. Migracje Alembic wykonuje jednorazowy kontener przed API. PostgreSQL jest kierunkiem rozwoju, nie zweryfikowaną funkcją.

Frontend: Router, TanStack Query, React Hook Form i Zod, polskie zasoby i18next, Tailwind i przycisk według konwencji shadcn/ui (Radix Slot, CVA). Recharts pozostaje zależnością dla przyszłych wykresów; etap 1 nie fabrykuje telemetrii. Motywy ciemny, jasny i systemowy, responsywny układ i zwijane menu.

## Model danych

Obecnie: `installation` (singleton, nazwa, strefa, data), `users` (unikalny login, hash Argon2id, rola, data), `sessions` (hash losowego tokenu, użytkownik, hash CSRF, termin), `login_limits` (hash klucza, licznik, okno), `audit_events` (aktor, akcja, data). Czas przechowywany jako UTC epoch; strefa dotyczy prezentacji.

Kolejne migracje wprowadzą resources, groups (parent_id), tags i tabele powiązań, monitors (typ i wersjonowana konfiguracja), check_results, incidents, notification_jobs, maintenance_windows i worker_leases. Unikalny aktywny incydent na monitor oraz atomowy zapis wyniku, stanu i zdarzenia. Jedna dzierżawa schedulera na instalację; krótkie transakcje, ograniczona równoległość i brak sieciowych operacji w transakcji.

## API i bezpieczeństwo

JSON, prefiks `/api`, statusy HTTP, OpenAPI. Pydantic ogranicza rozmiary pól. Sekret inicjalizacji minimum 32 znaki, dostarczany przez administratora poza WWW, przekazywany nagłówkiem. Singleton w transakcji chroni przed równoczesnym utworzeniem dwóch właścicieli. Brak rejestracji publicznej i endpointu resetującego instalację.

Sesje serwerowe: token 256-bitowy, wyłącznie hash w bazie, HttpOnly, SameSite Strict, Secure domyślnie, stała ważność 12 godzin. CSRF: dopasowanie Origin i token per sesja na operacjach modyfikujących. Logowanie i inicjalizacja również wymagają dokładnego Origin. CORS nie jest otwierany. Brak zaufania do dowolnych nagłówków proxy. Limity logowania są trwałe, współdzielone przez procesy API (10 prób / 15 minut). Nginx sprawia, że limit jest wspólny dla instalacji; identyfikacja klienta za zaufanym proxy wymaga przyszłej konfiguracji.

Nie przechowujemy haseł i tokenów w logach ani odpowiedziach walidacji. Panel nie zmienia sekretów uruchomieniowych. Bez roota i bez Docker Socket. Obsługa dodatkowych ról i TOTP wymaga etapu 6, nie deklarujemy ich obecnie. Polityka SSRF i pinning sprawdzonych adresów DNS muszą poprzedzić połączenia monitoringu w etapie 2; w etapie 1 użytkownik nie inicjuje połączeń do hostów.

## Kolejność i kryteria odbioru

1. **Fundamenty (bieżący zakres):** migracje, inicjalizacja, sesje, kreator, panel i Compose. Odbiór: testy transakcyjności inicjalizacji i zabezpieczeń, logowanie/wylogowanie, trwałość po restarcie, budowa WEB, działające health checks. Testy i ograniczenia w RAPORT_ETAP_1.md.
2. **Silnik:** niezależny worker, scheduler, osiem typów kontroli, heartbeat, historia, progi i maszyna stanów. Odbiór: rzeczywiste testowe usługi, awaria/powrót, restart API bez przerwy w workerze, blokady schedulera, SSRF i DNS rebinding.
3. **Zarządzanie:** zasoby, grupy, tagi, konfigurator, operacje zbiorcze i ręczny test bez zmiany stanu. Zależy od modelu i polityki celów etapu 2.
4. **Incydenty i alerty:** outbox w bazie, deduplikacja, ponawianie i niezależna wysyłka SMTP/webhook. Odbiór: jedna awaria = jeden incydent, niedostępne SMTP nie blokuje kontroli.
5. **Analityka:** SSE, agregacja, wykresy, CSV/PDF z polskimi znakami. UNKNOWN wyłączony z mianownika dostępności, maintenance raportowane osobno. Definicję czasu i interpolacji ustalić przed wdrożeniem raportów.
6. **Administracja:** egzekwowane role, MFA i odzyskiwanie, maintenance, szyfrowane kopie i offline restore, retencja, edycja ustawień. Testy ostatniego Ownera, przywracania i integralności.
7. **Stabilizacja:** testy integracyjne, wydajnościowe, migracji i bezpieczeństwa; audyt dokumentacji. Dopiero po nich rozważenie 1.0.0.

Każdy etap opiera się na poprzednich i kończy działającym przyrostem. Obecny numer 0.1.0 oznacza fundamenty, nie stabilne wydanie MONIVEX 1.0.


## Przyrost etapu 2

Zaimplementowano niezależny worker, trwałą dzierżawę, osiem kontroli, maszynę stanów, historię i minimalny model incydentu z unikalnym otwartym wpisem. Migracja 0002 dodaje `monitors`, `check_results`, `incidents`, `worker_lease`. Ochrona i zakres: SILNIK_MONITORINGU.md; wyniki walidacji: RAPORT_ETAP_2.md. Podstawowy formularz i pauza umożliwiają testowanie silnika przez WWW; pełna edycja, zasoby i powiązania nadal należą do etapu 3. Obecna wersja to 0.2.0, nadal rozwojowa.


## Przyrost etapu 3

Migracja 0003 dodaje `groups`, `tags`, `resources`, tabele powiązań oraz licznik przydziału identyfikatorów. Monitor otrzymuje grupę, zasób, priorytet i tagi. Dodano hierarchię bez cykli, zasady agregacji stanów, CRUD, rewizje, kopiowanie i atomowe operacje zbiorcze. API sprawdza konflikty oraz powiązania, a worker odrzuca wyniki sprzed zmiany instancji lub rewizji. Konfigurator zachowuje lub jawnie zastępuje sekrety bez ich ujawniania. Etap 3 ma własne testy migracji, współbieżności, ochrony sekretów i przeglądarki; CI generuje raporty i zrzuty rzeczywistej aplikacji. Wersja 0.3.0 pozostaje rozwojowa.
