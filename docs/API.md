# API — etapy 1 i 2

OpenAPI: `/openapi.json`, eksplorator: `/docs` na wewnętrznym porcie API (8000). Port ten nie jest publikowany przez Compose. Nazwy endpointów i pól pozostają angielskie, komunikaty aplikacyjne są polskie.

| Metoda i ścieżka | Dostęp i zachowanie |
| --- | --- |
| GET `/api/health/ready` | Publiczne, sprawdza schemat i połączenie z bazą |
| GET `/api/setup/status` | Publiczne, zwraca tylko `initialized` |
| POST `/api/setup` | Origin i `X-Setup-Token`; username, password, installation_name, timezone; tylko raz |
| POST `/api/auth/login` | Origin, username/password; ustawia HttpOnly cookie i zwraca `csrf_token` |
| GET `/api/auth/me` | Sesja; id, username, role |
| POST `/api/auth/logout` | Sesja, Origin i CSRF; unieważnia bieżącą sesję |
| POST `/api/auth/logout-all` | Sesja, Origin i CSRF; unieważnia wszystkie sesje użytkownika |
| POST `/api/auth/password` | Sesja, Origin i CSRF; current_password/new_password; unieważnia wszystkie sesje |
| GET `/api/installation` | Sesja; nazwa, strefa, język, wersja |
| GET `/api/dashboard` | Sesja; aktualne stany, ostatni cykl workera i otwarte incydenty |

Operacje sesyjne modyfikujące wymagają `X-CSRF-Token` uzyskanego przy logowaniu. Tokenów nie przekazuj w URL. Błędy: 401 brak sesji lub błędne logowanie, 403 niepoprawny Origin/CSRF/sekret, 409 ponowna inicjalizacja, 422 walidacja (bez zwracania danych wejściowych), 429 limit prób, 503 niedostępność bazy.


## Monitoring

| Metoda i ścieżka | Dostęp i zachowanie |
| --- | --- |
| GET `/api/monitors` | Sesja; bez sekretów, do 1000 monitorów, stan uwzględnia nieaktualność |
| POST `/api/monitors` | Edytor; tworzy monitor, sprawdza politykę celu; heartbeat zwraca token tylko raz |
| PATCH `/api/monitors/{id}/pause` | Edytor; `{"paused":true/false}`, unieważnia wyniki kontroli rozpoczętych przed zmianą |
| POST `/api/monitors/{id}/test` | Edytor; test istniejącej konfiguracji bez zmiany danych produkcyjnych |
| GET `/api/monitors/{id}/results?limit=100` | Sesja; maksymalnie 1000 wyników, najnowsze pierwsze |
| GET `/api/health/worker` | Sesja; `running/stale` i `last_cycle_at` |
| POST `/api/heartbeats/{id}` | Maszynowy, bez sesji; tylko `Authorization: Bearer`, błędny token → 404 |

Edytor to Owner, Administrator lub Operator; backend odrzuca próby Viewer. Sesyjne operacje modyfikujące nadal wymagają Origin i CSRF. Nie ma testu dowolnego celu przez endpoint publiczny. `MONIVEX_ALLOWED_NETWORKS` jest ustawieniem wdrożenia poza panelem.

Przykładowa publiczna konfiguracja TCP (cel musi zostać dopuszczony przez administratora):

```json
{"name":"Usługa testowa","kind":"tcp","interval":60,"timeout":5,"failure_threshold":3,"recovery_threshold":2,"config":{"host":"service.example.org","port":443}}
```

Typy `kind`: `icmp`, `tcp`, `http`, `dns`, `tls`, `smtp`, `http_json`, `heartbeat`. Szczegółowy schemat generuje OpenAPI. HTTP: `url`, `method`, `expected_codes`, `follow_redirects`, `contains`, `warning_ms`; JSON dodatkowo `json_path` (lista kluczy/indeksów) i `expected_value` (prosta wartość JSON). DNS: `host` serwera, `port`, `domain`, `record_type`, `expected_answer` w zapisie tekstowym rekordu. TLS: `host`, `port`, `expiry_warning_days`. SMTP: `host`, `port`, `starttls`. Heartbeat: `grace_seconds`.

Opcjonalne `secrets` HTTP: `username`, `password`, `bearer`, `headers` (słownik), `body`. Nie łącz Basic i Bearer. Te dane są szyfrowane kluczem wdrożenia i nie są zwracane ponownie. Nie wkładaj sekretów do `config.url` ani do nazw monitorów. Ręczny test zwraca wyłącznie `status`, `duration_ms` i bezpieczny polski komunikat, bez treści odpowiedzi i danych uwierzytelniających.


## Zarządzanie — etap 3

- GET/POST `/api/groups`, PUT/DELETE `/api/groups/{id}` — hierarchia bez cykli; usunięcie tylko pustej grupy.
- GET/POST `/api/tags`, PUT/DELETE `/api/tags/{id}` — unikalne tagi i powiązania.
- GET/POST `/api/resources`, PUT/DELETE `/api/resources/{id}` — zasoby z grupą, tagami i wyliczonym stanem. Usunięcie nie usuwa monitorów.
- GET `/api/monitors/search` — `q`, `kind`, `state`, `group_id`, `tag_id`, `resource_id`, `sort=name|priority|state|id`, `descending`, `offset`, `limit` (1–200); odpowiedź `{items,total,offset,limit}`.
- GET/PUT/DELETE `/api/monitors/{id}` — pełna publiczna konfiguracja i edycja bez ujawniania sekretów.
- POST `/api/monitors/{id}/duplicate` — `name`, `revision`, opcjonalne `copy_credentials=false`; nowy heartbeat zwraca nowy token tylko raz.
- POST `/api/monitors/bulk` — `monitor_ids` (1–100), `revisions` (mapa id → rewizja), `operation=configure|pause|resume|delete`; zmiany albo wszystkie, albo żadne.

PUT wymaga bieżącej `revision` w JSON, DELETE w parametrze zapytania. Konflikt → 409. Identyfikatory utworzone przez API nie są ponownie używane po usunięciu. Monitor ma `group_id`, `resource_id`, `tag_ids` i `priority=low|normal|high|critical`. Przy PUT brak `secrets` zachowuje szyfrogram, `secrets` zastępuje cały zestaw, `clear_credentials=true` usuwa go. Zmiana originu wymaga jawnego usunięcia/zastąpienia sekretów. Typ istniejącego monitora jest stały.

Konfiguracja zbiorcza zmienia interwał, timeout, progi, priorytet oraz powiązania. Pominięcie pola pozostawia wartość, `group_id:null`/`resource_id:null` odłącza, `tag_ids:[]` czyści tagi. Błąd walidacji lub rewizji odrzuca całą operację. Stany wynikają z workera; konfiguracja nie przyjmuje ręcznie podanego stanu dostępności.

`/api/dashboard` zwraca dodatkowo `counts` obejmujące wszystkie monitory. Starsze GET `/api/monitors` pozostaje zgodne z poprzednim formatem tablicy do 1000 pozycji; nowy interfejs używa paginacji `/search`.
