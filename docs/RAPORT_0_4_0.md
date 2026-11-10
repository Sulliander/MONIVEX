# Raport MONIVEX 0.4.0 — bezpieczeństwo i przygotowanie VPS

Data: 10 listopada 2026. Baza zmian: `main` po scaleniu etapów 1–3 (`2c7554c`). Wersję oznaczono w API, interfejsie, manifestach i dokumentacji jako **0.4.0**, nadal rozwojową. Zmiany przygotowano na osobnej gałęzi `codex/monivex-0-4-security`. Nie wykonano scalenia `main`, wdrożenia na VPS, zmiany DNS ani publicznej publikacji tej instalacji.

## Wykonane funkcje

Rozbudowano istniejące uwierzytelnianie Argon2id i sesje serwerowe. Login otrzymał spójny wygląd, dostępne pola i przełącznik widoczności hasła, informację o Caps Lock, błędy backendu, odliczanie blokady oraz drugi ekran TOTP/odzyskiwania. Wygasłe i unieważnione sesje czyszczą panel i prowadzą do logowania. Hasła i kody nie są zapisywane w pamięci trwałej przeglądarki. Nowa karta uzyskuje CSRF bez ponownego logowania.

Dodano TOTP zgodne z RFC 6238: SHA-1, sześć cyfr, 30 sekund, format `otpauth` kompatybilny z Microsoft Authenticator, Google Authenticator i 2FAS. Każde konto może samodzielnie rozpocząć konfigurację QR lub ręczną, potwierdzić kodem, regenerować recovery oraz wyłączyć 2FA po ponownym uwierzytelnieniu. Sekret aktywuje się dopiero po potwierdzeniu i jest szyfrowany także w fazie oczekiwania. Kody odzyskiwania: dziesięć losowych 128-bitowych wartości, jednorazowe wyświetlenie/pobranie, tylko hashe SHA-256 w bazie. Nie ma endpointu odczytu aktywnego sekretu.

Przy 2FA samo hasło tworzy wyłącznie pięciominutowe wyzwanie, bez pełnej sesji i dostępu do panelu. Trwałe limity chronią IP, login, wyzwanie i operacje ponownego uwierzytelnienia. Akceptowany krok TOTP i atomowe zużycie recovery zapobiegają ponownemu oraz równoczesnemu użyciu. Aktywacja/wyłączenie/regeneracja odnawiają bieżącą sesję i kończą pozostałe; zmiana hasła i logout-all kończą wszystkie sesje/wyzwania. Logowanie recovery również unieważnia pozostałe sesje i wyzwania.

Ustawienia konta zawierają zmianę hasła z potwierdzeniem i drugim składnikiem, status 2FA, liczbę recovery, własne sesje i ich unieważnianie, logout-all oraz stronicowany własny dziennik bezpieczeństwa. Właściciel może wymusić 2FA dla administratorów dopiero po aktywacji własnego drugiego składnika. Administrator bez 2FA zachowuje dostęp do konfiguracji konta; pozostałe funkcje są blokowane w UI i API do aktywacji.

Przygotowano samodzielny `compose.public.yaml` z Caddy/HTTPS, ścisłym łańcuchem Caddy → Nginx → API, Secure cookies, Origin/CSRF i HSTS/CSP. Tylko Caddy publikuje porty; API, baza i worker pozostają bez publicznych portów. API ignoruje fałszywe nagłówki spoza wskazanego proxy. Profil lokalny i jego wolumen pozostają osobne. Nie dodano rejestracji publicznej, otwartego CORS ani resetu/obejścia 2FA.

## Zgodność i aktualizacja

Migracja `0004` dodaje dane bezpieczeństwa bez przebudowy tabel użytkowników, sesji, monitorów lub historii. Test aktualizacji na rzeczywistym schemacie `0003` zachowuje konto, hash hasła, stary cookie/CSRF, monitor, wynik i incydent. Starsze sesje dostają niezależny identyfikator listy; nieznane metadane są czytelnie oznaczone. Domyślnie nie wymuszamy 2FA. Zachowano konfigurator, zarządzanie infrastrukturą, kontrole, historie, heartbeat oraz niezależność workera.

Wymagane są kopia offline, zachowanie dotychczasowego klucza i wykonanie migracji przed startem nowego API. Nie należy uruchamiać kodu 0.4 na starym schemacie bez migracji. Ochrona replay i stan wyzwania/recovery przetrwały uruchomienie nowego, osobnego procesu API. Profil HTTPS sprawdza także zachowanie istniejącej sesji po restarcie API i WEB.

## Wyniki weryfikacji

| Sprawdzenie | Wynik lokalny |
| --- | --- |
| Backend — jednostkowe, API, protokoły, współbieżność, migracje i nowe procesy | **93 zaliczone, 1 pominięty** |
| Frontend — Vitest | **14 zaliczonych** |
| Ruff, ESLint, TypeScript i build WEB | Zaliczone |
| Chromium — pełny przepływ z etapami 1–3 i bezpieczeństwem konta | Zaliczone; raport JUnit i 19 maskowanych zrzutów |
| Publiczny profil z lokalnym HTTPS | Certyfikat, redirect HTTP→HTTPS, Secure cookies, HSTS/CSP, ochrona API, Origin/CSRF, fałszywe nagłówki, brute force, porty i restart — zaliczone |
| Niezależność workera podczas zatrzymania i restartu API | Zaliczone |
| Audyt zależności Python / npm | Brak zgłoszonych znanych podatności w wykonanym audycie |

Pominięty test dotyczy uprawnień kernela dla ICMP w tym runtime. Uruchomiono testy RFC 6238, równoczesnego TOTP i recovery, wygasania/limitów, izolacji użytkowników, ochrony sekretów i polityki administratorów. Przeglądarka używa rzeczywistego API i workera, nie atrap odpowiedzi. Zrzuty maskują hasła, QR, sekret ręczny, kody i metadane sesji. Raporty i galeria nie zawierają bazy, konfiguracji środowiskowej, pobranego pliku kodów, trace ani nagrań formularzy.

CI rozszerzono o pełny przepływ bezpieczeństwa w Chromium i lokalny test profilu HTTPS. Nadal wykonuje regresję backendu, interfejsu, audyty, budowę obrazów, test niezależności workera oraz publikuje tylko bezpieczne raporty i zrzuty.

## Ograniczenia i dalsza gotowość

To przyrost bezpieczeństwa przed kolejnymi modułami, nie deklaracja gotowości MONIVEX 1.0 ani niezależny audyt. Nie wykonano testu penetracyjnego realnego hosta, prawdziwego ACME/DNS, zapory i obciążenia VPS. Format TOTP sprawdzono standardowymi wektorami i w przepływie aplikacji; fizyczne telefony nie były przedmiotem testu.

Przechowuj klucz szyfrowania i recovery osobno oraz bezpiecznie. Utrata/podmiana klucza nie jest obsługiwana automatyczną rotacją; bez telefonu i wszystkich recovery nie istnieje publiczny bypass. Nie dodano resetu hasła przez e-mail, panelu zarządzania dodatkowymi użytkownikami, automatycznego backup/restore ani retencji. Nie zmieniono kierunku architektury: obecnie zweryfikowano SQLite, nie PostgreSQL. Limity uwzględniają także poprawne próby. Metadane przeglądarki nie są dowodem tożsamości urządzenia.

Budowa WEB zgłasza informacyjne ostrzeżenie o rozmiarze głównego pakietu JS i adnotacjach zależności Zod; nie blokuje kompilacji. TestClient sygnalizuje przyszłą zmianę biblioteki HTTP w Starlette; bieżące testy przechodzą. Nie tworzono obejść walidacji TLS ani nagłówków bezpieczeństwa w celu przejścia testów.

Dalsze prace mogą objąć niezależny przegląd bezpieczeństwa, próbę odtworzenia kopii na wybranym VPS, dopiero potem osobno zatwierdzone wdrożenie oraz kolejne moduły powiadomień/administracji. Instrukcje: [konto](BEZPIECZENSTWO_KONTA.md), [VPS](WDROZENIE_VPS.md), [API](API.md), [testy](TESTY_I_ZRZUTY.md).
