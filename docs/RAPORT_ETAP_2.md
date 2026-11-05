# Raport etapu 2 — MONIVEX 0.2.0

## Zaimplementowany przyrost

Niezależny proces workera uruchamiany przez Docker Compose lub `python -m app.worker`. Trwały harmonogram, limit równoległości, timeout całej kontroli, dzierżawa jednego lidera, atomowe zapisy wyników/stanu/incydentów i ochrona przed ponownym zapisem wyniku. Migracja `0002` dodaje tabele monitorów, historii kontroli, incydentów i dzierżawy. Fundamenty i konta z etapu 1 pozostają zachowane.

Kontrole: TCP, ICMP, HTTP/HTTPS (metoda, kody, fragment treści, autoryzacja i nagłówki przez API, przekierowania i próg czasu), DNS (UDP/TCP), TLS (zaufanie, nazwa, wygaśnięcie), SMTP/EHLO i STARTTLS, HTTP JSON (bez wykonywania kodu) oraz heartbeat. Rzeczywisty ICMP zależy od możliwości systemu — ograniczenie środowiska opisano poniżej.

Maszyna stanów: UP, DEGRADED, DOWN, PENDING, UNKNOWN i PAUSED. Konfigurowalne serie błędów i sukcesów; jedna ciągła awaria prowadzi do jednego otwartego incydentu. Przywrócenie działania automatycznie zamyka incydent po osiągnięciu progu. Nie wdrożono jeszcze powiadomień.

## Bezpieczeństwo

Administrator ustala dozwolone CIDR poza panelem (`MONIVEX_ALLOWED_NETWORKS`). Domyślnie połączenia są zablokowane; jawnie dopuszczone LAN pozostaje obsługiwane. Sprawdzane są wszystkie odpowiedzi DNS przed każdym połączeniem i przekierowaniem. Połączenia używają przypiętych adresów IP przy zachowaniu Host i SNI. Blokowane są adresy szczególne i metadanych, obniżenie HTTPS do HTTP oraz przekazywanie sekretów między originami.

Dane uwierzytelniające HTTP, własne nagłówki i treść POST są szyfrowane kluczem Fernet dostarczanym poza WWW. Token heartbeat jest losowy, zwracany tylko raz i przechowywany jako hash; klient wysyła go nagłówkiem, nie w URL. Wyniki i logi nie zawierają treści odpowiedzi, surowych wyjątków ani sekretów. Backend sprawdza role przy tworzeniu, pauzie i ręcznym teście; Viewer ma tylko podgląd. Test ręczny nie zmienia produkcyjnych wyników ani harmonogramu.

## Interfejs i API

Polski formularz podstawowych ustawień wszystkich ośmiu typów, lista bieżących stanów, wstrzymanie/wznowienie, test ręczny, historia i jednorazowe wyświetlenie tokenu heartbeat. Dashboard korzysta z prawdziwych danych, pokazuje kondycję workera i otwarte incydenty, a stary zielony stan zastępuje UNKNOWN. Odświeżanie odbywa się przez polling; SSE i rozbudowane wykresy pozostają późniejszym etapem.

Szczegóły endpointów: [API](API.md). Dokładna semantyka stanów, terminów heartbeat, polityki, dzierżawy i ograniczeń: [Silnik monitoringu](SILNIK_MONITORINGU.md).

## Wyniki kontroli

| Kontrola | Wynik |
| --- | --- |
| Wszystkie testy pytest | **48 zaliczonych, 1 pominięty** |
| Testy komponentów WEB | **5/5 zaliczonych** |
| TypeScript / Vite | Budowanie zaliczone |
| Ruff / ESLint / `git diff --check` | Zaliczone |
| Audyt zależności Python | **0 znanych podatności** po aktualizacji dnspython do 2.9.0 |
| Audyt npm | **0 znanych podatności** |
| Budowa obrazów API/WEB | Zaliczona, bez wyłączania TLS |
| Compose na nowym wolumenie | Migracje zakończone; API, WEB i worker healthy |
| Chromium przez Compose | **1/1 zaliczony**, wraz z heartbeat, historią i pauzą/wznowieniem |
| Rzeczywisty worker w osobnym procesie | HTTP UP → DOWN → restart workera → UP; jeden incydent, zachowana historia, bez API |
| Zachowanie kont i sesji przy migracji 0001 → 0002 | Zaliczone |
| Zapis wyników przy zatrzymanym API w Compose | Zaliczone: nowe wyniki bez API, ta sama dzierżawa i zachowane monitory po jego restarcie |

Testy protokołów uruchamiały własne serwery loopback: TCP, HTTP/JSON, DNS UDP/TCP, HTTPS, certyfikaty TLS z testowym CA oraz SMTP z STARTTLS. Weryfikacja certyfikatów pozostała włączona; testy odrzucają błędną nazwę i wygasły certyfikat. Sprawdzono zachowanie nazwy SNI przy przypięciu IP. Testy DNS/SSRF odrzucają mieszaną odpowiedź, metadane i niebezpieczne przekierowanie. Sprawdzono limity odpowiedzi i timeouty, brak sekretów po zmianie originu, wyścig liderów, fencing starego lidera, rewizje, idempotencję zapisu, wstrzymanie, progi powrotu i nieaktualność.

Pominięty test to rzeczywisty ICMP loopback: runtime odmówił uprawnień gniazda ping. Kod zwraca w tej sytuacji UNKNOWN z polskim komunikatem. Nie zaliczono tego jako działającego ICMP. Konfigurację uprawnień grupy kernela należy sprawdzić na docelowym Debianie.

Pierwszy test przeglądarkowy zatrzymał się na niedopasowanym selektorze pola „Typ”. Po zastosowaniu selektora roli z nazwą dostępną dla przeglądarki cały przepływ przeszedł na świeżej bazie. Nie pominięto asercji ani funkcji monitoringu.

GitHub Actions rozszerzono o pełny test z workerem i sprawdzenie działania podczas zatrzymania API. Nie wykonywano zdalnego uruchomienia Actions ani publikacji obrazów. Testy dotyczyły wyłącznie lokalnych, jednorazowych usług; nie skanowano rzeczywistej infrastruktury i nie wykonywano wdrożenia produkcyjnego.

## Uruchomienie i konfiguracja

1. Zachowaj wolumen oraz `.env`; przed aktualizacją wykonaj kopię offline przy zatrzymanym API i workerze.
2. Ustaw `MONIVEX_ALLOWED_NETWORKS` na podsieci, do których masz uprawnienia. Pusta lista pozwala korzystać z heartbeat, lecz blokuje kontrole sieciowe.
3. Jeśli potrzebujesz sekretów HTTP, ustaw trwały `MONIVEX_ENCRYPTION_KEY` (32 losowe bajty base64url). Nie regeneruj go przy aktualizacji; zachowaj zaszyfrowaną kopię poza aplikacją.
4. Uruchom `docker compose up --build -d`. Alembic wykona migrację, a worker wystartuje niezależnie od API.
5. Po zalogowaniu otwórz „Monitory”, dodaj kontrolę i sprawdź wyniki. Dla heartbeat bezpiecznie zapisz token pokazywany tylko raz i dostarczaj sygnały POST z nagłówkiem Authorization.

Instrukcje lokalne, reverse proxy i narzędzia testowe: [Instalacja](INSTALACJA.md).

## Ograniczenia i kolejny krok

Wersja rozwojowa 0.2.0 jest przeznaczona do lokalnych testów. ICMP wymaga potwierdzenia uprawnień na docelowym systemie. SQLite jest jedyną zweryfikowaną bazą. Pulpit i lista obejmują do 1000 pierwszych monitorów; pełna paginacja i statystyki większej instalacji wymagają dalszej pracy. Nie ma jeszcze retencji, agregacji, alertów, pełnego panelu incydentów, MFA i automatycznego backup/restore. Zaufane proxy, HTTPS/LAN i obciążenie produkcyjne wymagają odrębnych testów.

Kolejny etap: pełne zarządzanie zasobami, grupami i tagami, edycja i duplikowanie monitorów, powiązania, operacje zbiorcze oraz rozbudowany konfigurator (etap 3). Następnie reguły powiadomień i trwała kolejka (etap 4). Nie oznaczono aplikacji jako stabilnej 1.0 i nie wykonano merge.

Jednorazowy projekt Compose oraz jego wolumen usunięto po walidacji. W repozytorium pozostają kod, zależności, testy i dokumentacja; nie pozostawiono testowej instalacji z losowym hasłem właściciela.
