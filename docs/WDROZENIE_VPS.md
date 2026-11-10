# Przygotowanie MONIVEX 0.4.0 do VPS i HTTPS

Przygotowano profil i lokalne testy. Nie wykonano wdrożenia na VPS, zmiany DNS ani wystawienia tej instalacji do internetu. Poniższe polecenia są instrukcją dla administratora przyszłego hosta.

## Oddzielny profil

`compose.yaml` zachowuje instalację lokalną, loopback i dotychczasowy wolumen `monivex_data`. `compose.public.yaml` jest **samodzielnym** profilem o nazwie `monivex-public`, z własnym wolumenem `monivex-public_data` oraz wolumenami certyfikatów Caddy. Nie uruchamiaj go jako drugiego pliku `-f` nad lokalnym Compose. Sam wybór profilu nie przenosi ani nie usuwa lokalnej bazy.

Wymagany Docker Engine i Compose 2.24.4+ (także do testów z `!override`). Publiczny host powinien mieć poprawny zegar, trwały dysk i domenę z rekordami A/AAAA wskazującymi ten host. Udostępnij 80/TCP i 443/TCP, opcjonalnie 443/UDP dla HTTP/3. Dostęp administracyjny do VPS skonfiguruj osobno. Caddy potrzebuje DNS oraz dostępu wychodzącego do wystawcy certyfikatów. Nie używamy serwera Vite w tym profilu.

```sh
cp .env.public.example .env.public
chmod 600 .env.public
# Wpisz domenę bez https://, portu i ścieżki oraz adres kontaktowy ACME.
# Wygeneruj osobny sekret inicjalizacyjny i trwały klucz szyfrowania.
# Jeżeli przenosisz istniejącą bazę, ZACHOWAJ jej dotychczasowy klucz.
docker compose --env-file .env.public -f compose.public.yaml config --quiet
docker compose --env-file .env.public -f compose.public.yaml up --build -d
docker compose --env-file .env.public -f compose.public.yaml ps
```

Używaj `config --quiet`; zwykłe `config` wyświetla rozwinięte zmienne, również sekrety. Nie dołączaj wyniku do zgłoszeń diagnostycznych. `.env.public` jest ignorowany przez Git. Klucza nie przekazuj w URL ani czacie.

Przejdź kreator pod `https://TWOJA_DOMENA`, utwórz właściciela, zaloguj się i skonfiguruj TOTP z kodami odzyskiwania. Po tym możesz włączyć wymóg 2FA dla administratorów. Brak publicznej rejestracji. Inicjalizacja wymaga dodatkowego sekretu i nie może zostać powtórzona po utworzeniu instalacji.

## Granice dostępu i proxy

Jedynie Caddy publikuje porty. WEB, API i worker nie mają mapowania portów hosta; SQLite jest plikiem w prywatnym wolumenie. Caddy kieruje ruch do Nginx, który serwuje SPA i przekazuje `/api` do API. Publiczna powłoka logowania nie zawiera danych administracyjnych. Endpointy administracyjne wymagają sesji, uprawnień, a przy zmianach również Origin i CSRF. Publiczne wyjątki to inicjalizacja z sekretem, jej minimalny status i przepływ logowania. Heartbeat zachowuje maszynowe uwierzytelnienie tokenem Bearer; nie jest administracyjnym API.

Caddy automatycznie uzyskuje i odnawia certyfikat, przekierowuje HTTP na HTTPS i dodaje HSTS. Zachowaj jego wolumeny `/data` i `/config` przy aktualizacjach. API administracyjne Caddy jest wyłączone. Kontener Caddy ma system plików tylko do odczytu, trwałe wolumeny i jedynie capability `NET_BIND_SERVICE`; API i worker działają jako UID/GID 10001 bez capabilities. Nie montujemy Docker Socket w usługach.

Nagłówki CSP, `nosniff`, `DENY` i `no-referrer` są ustawiane przez Nginx. Cookies pełnej sesji i wyzwania: HttpOnly, Secure, SameSite Strict, bez Domain; ścieżki odpowiednio `/api` i `/api/auth`. Profil publiczny na stałe wymaga Secure i konstruuje dokładny Origin HTTPS z domeny. API odmawia startu publicznego profilu bez HTTPS, poprawnego klucza, Secure i zaufanego proxy. CORS nie jest otwierany. Eksplorator `/docs`, `/redoc`, `/openapi.json` jest wyłączony; `/api/health/ready` służy wewnętrznemu health check i jest blokowane przez Caddy. Uwierzytelnione informacje o workerze są nadal dostępne.

Zaufanie adresom klientów ma trzy ograniczone kroki:

1. Caddy ignoruje nieufne przychodzące nagłówki forwarding i ustawia własny `X-Forwarded-For`.
2. Nginx przyjmuje adres klienta tylko od Caddy `172.30.44.2/32`, odrzuca inne nagłówki i ustawia pojedynczy `X-Monivex-Client-IP`.
3. Uvicorn ma `--no-proxy-headers`. API odczytuje własny nagłówek tylko od Nginx `172.30.44.3/32`, odrzuca listy i nie ufa `X-Forwarded-For`, `Forwarded` ani `X-Real-IP` od klienta.

Adres API to `.4`. Dynamiczne adresy kontenerów są ograniczone do `172.30.44.128/25`, aby nie zajęły stałych adresów proxy. Jeżeli `172.30.44.0/24` koliduje z siecią hosta, przed wdrożeniem spójnie zmień IPAM, stałe adresy, `MONIVEX_TRUSTED_PROXIES` oraz `set_real_ip_from` w `deploy/nginx.public.conf`. Nie ustawiaj `0.0.0.0/0`, `::/0` ani dowolnego zaufania do nagłówków. Nie dodawaj CDN/proxy przed Caddy bez osobnej konfiguracji i ponownych testów tego łańcucha. Lokalny profil nadal ma konserwatywny, wspólny limit adresowy za Nginx.

## Aktualizacja i przeniesienie danych

Przed aktualizacją zatrzymaj WEB, API i worker oraz wykonaj szyfrowaną kopię offline całego wolumenu. Zachowaj konfigurację, ten sam klucz szyfrowania i wolumeny Caddy. Nie uruchamiaj dwóch migratorów tej samej bazy jednocześnie. Przykład dla już wybranego publicznego profilu:

```sh
docker compose --env-file .env.public -f compose.public.yaml stop web api worker
# Wykonaj i zweryfikuj kopię offline poza repozytorium.
docker compose --env-file .env.public -f compose.public.yaml build
docker compose --env-file .env.public -f compose.public.yaml run --rm migrate
docker compose --env-file .env.public -f compose.public.yaml up -d --force-recreate
```

Migracja 0004 jest dodatkiem do schematu 0003 i zachowuje konta, monitory, sesje oraz historię. Nie uruchamiaj nowego kodu na schemacie sprzed migracji. Nie używaj `down -v` ani downgrade jako zamiennika backupu. Przy zmianie domeny przeglądarka będzie potrzebować logowania pod nowym originem, mimo że sesje w bazie zostały zachowane.

Przeniesienie lokalnej instalacji wymaga osobnej kopii offline i odtworzenia jej w publicznym wolumenie przed pierwszym startem API, z UID/GID 10001 i tym samym kluczem. Nie inicjalizuj nowego właściciela na kopii już skonfigurowanej bazy. Nie łącz pracujących instalacji z jednym plikiem SQLite przez sieciowy system plików. Procedura pełnego automatycznego backup/restore pozostaje kolejnym zakresem.

## Weryfikacja lokalna i zakres gotowości

`scripts/verify_public_https.py` uruchamia **jednorazowy** projekt `monivex-https-test`, używa tego profilu z lokalnym CA Caddy zamiast ACME, weryfikuje certyfikat i sprząta własne kontenery/wolumeny. Wymaga wolnej podsieci profilu i portów loopback 18081/18443. Nie uruchamiaj dwóch kopii testu naraz. Uruchom go po zbudowaniu i oznaczeniu obrazów `monivex-api:0.4.0` oraz `monivex-web:0.4.0`. CI przygotowuje te tagi automatycznie.

Sprawdzane są: uwierzytelnienie API, brak rejestracji, certyfikat/HSTS/CSP, Secure cookies, Origin/CSRF, fałszywe nagłówki proxy, limit prób mimo ich zmiany, brak dodatkowych portów i sesja po restarcie API/WEB. Nie wyłączamy weryfikacji TLS. Test nie sprawdza prawdziwej domeny, ACME, zapory konkretnego VPS ani wydajności hosta. Profil jest przygotowany do dalszej weryfikacji wdrożeniowej; nie jest deklaracją niezależnego audytu bezpieczeństwa lub ukończenia MONIVEX 1.0.
