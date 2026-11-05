# MONIVEX

Polskojęzyczna, otwarta platforma self-hosted do monitorowania infrastruktury. Licencja Apache 2.0.

**Stan: 0.2.0 — fundamenty i silnik monitoringu, wersja rozwojowa.** Działa kreator właściciela, logowanie, sesje i polski panel z trzema motywami. Niezależny worker wykonuje kontrole ICMP, TCP, HTTP/HTTPS, DNS, TLS, SMTP, HTTP JSON i heartbeat, zapisuje historię, potwierdza awarie/powroty i atomowo prowadzi incydenty. WWW pozwala dodawać, wstrzymywać i testować monitory oraz przeglądać wyniki. Dashboard wykrywa nieaktualność workera i danych. Powiadomienia, raporty i pełne zarządzanie infrastrukturą pozostają kolejnymi etapami.

Kontrole sieciowe wymagają jawnego dopuszczenia podsieci przez administratora. ICMP zależy od uprawnień gniazd ping w kernelu; w runtime testowym nie był dostępny. [Zakres, bezpieczeństwo i ograniczenia silnika](docs/SILNIK_MONITORINGU.md).

## Szybki start lokalny

Wymagany Docker Engine i Docker Compose v2; host nie potrzebuje Node ani Pythona.

```sh
cp .env.example .env
# Ustaw w .env własny losowy MONIVEX_SETUP_TOKEN (minimum 32 znaki).
# Dla lokalnego HTTP ustaw MONIVEX_COOKIE_SECURE=false.
# Ustaw MONIVEX_ALLOWED_NETWORKS na dozwolone CIDR albo zacznij od heartbeat.
docker compose up --build -d
docker compose ps
```

Otwórz panel na porcie 8080 lokalnego hosta. Przejdź kreator: powitanie → login, silne hasło i sekret wdrożenia → nazwa i strefa czasowa → informacja o opcjach → podsumowanie. Następnie zaloguj się. Sekret nie jest hasłem właściciela i nie pozwala powtórzyć zakończonej inicjalizacji.

Domyślnie port jest przypisany do loopback; dla LAN ustaw odpowiedni interfejs przez `MONIVEX_BIND_ADDRESS`, dokładny `MONIVEX_PUBLIC_ORIGIN` i reguły zapory. Zalecane HTTPS, także w LAN. Dla HTTPS pozostaw `MONIVEX_COOKIE_SECURE=true`. Nie wystawiaj niezabezpieczonego HTTP do internetu.

## Dokumentacja

- [Silnik monitoringu i polityka celów](docs/SILNIK_MONITORINGU.md)
- [Raport etapu 2](docs/RAPORT_ETAP_2.md)

- [Instalacja i reverse proxy](docs/INSTALACJA.md)
- [Administracja](docs/ADMINISTRACJA.md)
- [Architektura i plan etapów](docs/PLAN_IMPLEMENTACJI.md)
- [API](docs/API.md)
- [Raport i weryfikacja etapu 1](docs/RAPORT_ETAP_1.md)
- [Współpraca](CONTRIBUTING.md) · [Bezpieczeństwo](SECURITY.md) · [Zmiany](CHANGELOG.md)

## Testy i rozwój

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -c requirements.lock
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests migrations
cd ../frontend
npm ci
npm test
npm run lint
npm run build
```

Instrukcje startu bez Dockera: [Instalacja](docs/INSTALACJA.md). Nie wykonuj wdrożeń produkcyjnych bez osobnej weryfikacji. Nie dodawaj danych rzeczywistej infrastruktury, haseł, baz i tokenów do repozytorium.
