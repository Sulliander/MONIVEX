# Instalacja i rozwój

## Docker Compose

Skopiuj `.env.example` do `.env`, ogranicz prawa `chmod 600 .env`. Sekret wygeneruj lokalnie kryptograficznym generatorem (np. `openssl rand -hex 32`) i wprowadź do `.env`; nie przesyłaj go przez czat ani repozytorium. Ustaw dokładny origin bez końcowego ukośnika, zgodny z adresem w przeglądarce. `localhost` i `127.0.0.1` to różne originy.

`docker compose up --build -d` buduje API i WEB, wykonuje migracje, uruchamia API i worker, a po gotowości API także WEB. Zmiany infrastruktury wymagają ponownego utworzenia kontenerów. `docker compose logs api migrate web` służy diagnostyce; nie włączaj logowania treści żądań ani nagłówków uwierzytelniających. Kontroluj stan przez `docker compose ps` oraz `/api/health/ready`.

Dane znajdują się w nazwanym wolumenie `monivex_data`. `docker compose down` go zachowuje, `down -v` bezpowrotnie usuwa także konta i historię. Nigdy nie używaj `down -v` przy aktualizacji. Przed aktualizacją wykonaj kopię offline i przeczytaj migracje. Nie uruchamiaj równolegle dwóch kontenerów migracji na tej samej bazie.

## Reverse proxy

Aplikacja zakłada ścieżkę główną `/`, nie podkatalog. API nie jest publikowane na hoście; tylko WEB. Dla proxy na hoście pozostaw bind `127.0.0.1`, port 8080 i ustaw origin HTTPS. Nie przekazuj zaufania do nagłówków proxy od dowolnych klientów.

Caddy (zastąp nazwę swoją domeną lub wewnętrzną nazwą):

```caddyfile
monitor.example.org {
    reverse_proxy 127.0.0.1:8080
}
```

W sieci bez publicznej domeny można użyć `tls internal`; zainstaluj zaufanie do własnego CA na urządzeniach użytkowników. Dostęp do internetu nie jest wymagany do działania aplikacji, ale jest potrzebny do pobrania obrazów i zależności podczas budowy.

Nginx na hoście (po skonfigurowaniu certyfikatu dla własnej nazwy):

```nginx
server {
    listen 443 ssl;
    server_name monitor.example.org;
    ssl_certificate /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/key.pem;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
    }
}
```

## Rozwój bez Dockera

Python 3.12+, Node 24+. Zainstaluj zależności zgodnie z README. W terminalu API:

```sh
cd backend
export MONIVEX_DATABASE_URL=sqlite:////tmp/monivex-dev.db
export MONIVEX_PUBLIC_ORIGIN=http://localhost:5173
export MONIVEX_COOKIE_SECURE=false
# Wprowadź własny sekret bez echo i bez zapisywania w historii:
read -rs MONIVEX_SETUP_TOKEN
export MONIVEX_SETUP_TOKEN
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

W drugim terminalu `cd frontend && npm run dev`. Vite przekazuje `/api` do lokalnego backendu. Serwer developerski nie służy do publicznego wdrożenia.

## Środowisko z proxy i własnym CA

Dockerfile obsługują opcjonalny sekret BuildKit `proxy_ca`. W zarządzanym środowisku dodaj go do `build.secrets` API i WEB przez lokalny plik override (poza repozytorium). Backend wymaga pełnego pakietu zaufanych CA (np. `/etc/ssl/certs/ca-certificates.crt`), a Node używa go jako dodatkowego CA. Nie wyłączaj TLS ani sprawdzania podpisów. Sekret montowany jest tylko podczas instalowania zależności, nie trafia do obrazu.

## Test przeglądarkowy na jednorazowej bazie

`frontend/e2e/foundation.spec.ts` przechodzi prawdziwy kreator oraz logowanie, zmianę hasła i wylogowanie. Wymaga **nowej testowej instalacji**. Nie uruchamiaj go na instalacji użytkownika: test tworzy właściciela i zmienia jego hasło. Ustaw `MONIVEX_TEST_URL` na adres testowego WEB i `MONIVEX_TEST_SETUP_TOKEN` na jego sekret, następnie w `frontend` wykonaj `npx playwright install chromium` i `npx playwright test`. Można użyć zainstalowanego Chromium przez `MONIVEX_CHROMIUM=/usr/bin/chromium`. Test nie zapisuje screenshotów ani nagrań formularza z sekretami. CI uruchamia go na nowym wolumenie.

Python ma przypięte zależności bezpośrednie w `requirements.txt` oraz sprawdzone wersje przechodnie w `requirements.lock` (ograniczenia `-c requirements.lock`). WEB używa `npm ci` i `package-lock.json`. Override minimatch dotyczy wyłącznie drzewa typescript-eslint: usuwa znaną podatność w narzędziu developerskim; zgodność sprawdzają linting, testy i kompilacja.


## Worker bez Dockera

W osobnym terminalu backendu ustaw tę samą bazę, listę `MONIVEX_ALLOWED_NETWORKS` i opcjonalny `MONIVEX_ENCRYPTION_KEY` co API, a następnie uruchom `.venv/bin/python -m app.worker`. Nie uruchamiaj workera wewnątrz uvicorn/reload. Baza po migracjach, routing i polityka celów są wymagane. Stan sprawdź po zalogowaniu przez `/api/health/worker`. W Compose proces jest już zdefiniowany i nie wymaga dodatkowej usługi.

Aktualizacja etapu 1 do 2: wykonaj kopię offline przy zatrzymanym API i workerze, zachowaj `.env` i wolumen, uzupełnij politykę celów i opcjonalny klucz szyfrowania, następnie `docker compose up --build -d`. Alembic wykona migrację `0002` bez usuwania kont i sesji. Nie używaj `down -v` na instalacji z danymi.


Po przejściu testu przeglądarkowego z `MONIVEX_TEST_WORKER=1` na jednorazowym stacku można sprawdzić niezależność workera: `python3 scripts/verify_worker_compose.py --project NAZWA_PROJEKTU_TESTOWEGO --env-file PLIK_TESTOWY --url ADRES_TESTOWEGO_WEB`. Polecenie celowo zatrzymuje API testowego projektu, sprawdza przyrost wyników w workerze i uruchamia API ponownie. Nie uruchamiaj go na produkcji. W CI jest wykonywane po Chromium, a dane są usuwane po testach.


## Aktualizacja do 0.3.0

Zachowaj dane i klucz szyfrowania; przed aktualizacją wykonaj kopię offline przy zatrzymanych API i workerze. `docker compose up --build -d` wykona migrację `0003`: zasoby, grupy, tagi, powiązania i przydział identyfikatorów bez przepisywania tabeli monitorów. Testy obejmują zachowanie wcześniejszych wyników, incydentów i sesji. Cofnięcie tej migracji usuwa nowe metadane — nie stosuj go jako zamiennika backupu. Poradnik nowych ekranów: ZARZADZANIE_INFRASTRUKTURA.md; artefakty CI: TESTY_I_ZRZUTY.md.
