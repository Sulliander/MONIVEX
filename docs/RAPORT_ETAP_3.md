# Raport etapu 3 — MONIVEX 0.3.0

## Zmiana funkcjonalna

Dodano zarządzanie zasobami infrastruktury, grupami hierarchicznymi, tagami i relacjami monitorów. Panel pozwala tworzyć, edytować i usuwać urządzenia, grupy i tagi, konfigurować i edytować monitory, duplikować je, przeglądać historię, wykonywać testy ręczne i zmiany zbiorcze. Wyszukiwanie, filtry i paginacja monitorów działają w backendzie; liczniki pulpitu obejmują całą instalację.

Konfigurator ma sekcje podstawowe, warunki, zaawansowane i powiązania, w tym HTTP Basic/Bearer, nagłówki i POST. Sekrety można pozostawić, zastąpić lub usunąć; istniejących wartości nie można odczytać. Przy zmianie originu nie wolno niejawnie wysłać dawnych sekretów na nowy serwer. Kopia heartbeat otrzymuje nowy token, a kopia zwykłego monitora domyślnie nie otrzymuje sekretów.

## Dane, współbieżność i bezpieczeństwo

Migracja `0003` tworzy grupy, tagi, zasoby, powiązania oraz trwały przydział identyfikatorów. Nie przepisuje tabeli monitorów, co przy włączonych kluczach obcych SQLite mogłoby usunąć dotychczasową historię przez kaskadę. Test zachowuje wyniki, incydenty i sesję podczas cofnięcia do 0002 oraz ponownego upgrade.

Edycja i usuwanie sprawdzają rewizję. Operacje zbiorcze obejmują wszystkich wybranych monitorów albo nie zmieniają żadnego. Współbieżne przenoszenie grup nie tworzy cyklu. Identyfikatory API nie są ponownie przydzielane po usunięciu. Worker rozpoznaje także datę utworzenia instancji i odrzuca wynik sprzed zmiany rewizji lub usunięcia/odtworzenia obiektu. Zmiana warunków zamyka stary incydent z przyczyną `configuration_changed`, odróżnioną od `recovered`.

Backend nadal egzekwuje role, sesje, Origin/CSRF, politykę CIDR, pinning DNS i szyfrowanie. Usunięcie zasobu odłącza monitory, zachowując ich pracę i historię. Usunięcie monitora jest destrukcyjne, z jednoznacznym potwierdzeniem. Zasób agreguje stany aktywnych kontroli i osobno wskazuje liczbę wstrzymanych; nie rozciąga awarii jednej usługi na inne monitory.

## Interfejs i dowody wizualne

Dopracowano kontrast jasnego motywu i kolor stanu działającego workera. Dodano odświeżanie stanów także w tle oraz test utraty aktywności okna — widok nie zatrzymuje się na pierwszym stanie UNKNOWN. Daty korzystają ze strefy zapisanej w instalacji; test obejmuje zimowy i letni czas w Polsce. Zrzuty pochodzą z działającego backendu, workera i przeglądarki. W czasie testu heartbeat jest rzeczywiście wysyłany do API, nie podstawiany w UI.

Dziesięć ekranów obejmuje logowanie, pustą instalację, grupy, zasoby, konfigurator, monitory, zasób z monitorem, pulpit ciemny/jasny oraz widok mobilny. Hasła, sekrety i tokeny są maskowane. Dwa rzeczywiste obrazy dodano do README; kompletna galeria powstaje jako artefakt, poza kodem aplikacji i danymi produkcyjnymi.

## Weryfikacja lokalna

| Kontrola | Wynik |
| --- | --- |
| Pełny backend pytest | **61 zaliczonych, 1 pominięty** |
| Frontend Vitest | **9/9 zaliczonych** |
| Chromium przez pełny Compose | **1/1 zaliczony**, pełny przepływ etapów 1–3 |
| Zrzuty i galeria | **10 rzeczywistych, bezpiecznych PNG**, JUnit i `index.html` |
| Migracja i historia | Zachowane wyniki, incydenty i sesje |
| Wyścigi, rewizje, stary wynik, ID po usunięciu | Zaliczone |
| Sekrety i zmiana originu | Zaliczone |
| Atomowość operacji zbiorczych i filtry | Zaliczone |
| Globalne liczniki / paginacja ponad 1000 wpisów | Zaliczone |
| TypeScript, Vite, ESLint, Ruff i `git diff --check` | Zaliczone |
| Audyty Python i npm | **0 znanych podatności** w momencie sprawdzenia |
| Compose API/WEB/worker | Healthy na świeżym wolumenie |
| Worker przy zatrzymanym API | Zapisuje nowe wyniki, zachowuje dzierżawę i monitory po restarcie API |

Pominięty test to rzeczywisty ICMP: lokalny runtime nie pozwala utworzyć gniazda ping. Pozostaje to ograniczeniem środowiska, a nie zaliczoną kontrolą. Nie wykonano wdrożenia produkcyjnego ani skanowania rzeczywistej infrastruktury. PostgreSQL nadal nie jest zweryfikowany.

## GitHub Actions

Poprzedni workflow etapów 1–2 został potwierdzony na publicznej stronie GitHub jako **Success** (backend, frontend i kontenery): [przebieg 42198497682](https://github.com/Sulliander/MONIVEX/actions/runs/42198497682).

Nowy workflow przypina oficjalne akcje v6 do SHA, stosuje Ubuntu 24.04/Node 24 i zapisuje raporty JUnit dla backendu, frontendu i przeglądarki. Artefakt `monivex-ui-evidence-N` zawiera galerię, PNG i JUnit; nie obejmuje `.env`, baz, nagrań, śladów formularzy ani surowych logów. Retencja wynosi siedem dni. Przebiegi bieżącej gałęzi: [Actions — etap 3](https://github.com/Sulliander/MONIVEX/actions?query=branch%3Acodex%2Fmonivex-stage-3). Dokładne wyniki zdalnego przebiegu są niezależne od powyższych wyników lokalnych i widoczne w podsumowaniu danego uruchomienia.

API GitHub jest blokowane przez aktualną politykę sieci środowiska. Dodanie `api.github.com` zapisano w szkicu ustawień; zastosowanie wymaga zapisania i publikacji konfiguracji przez użytkownika. Publiczna strona GitHub umożliwia niezależny odczyt statusu i podsumowania, więc blokada API nie zatrzymała implementacji ani testów.

## Uruchomienie, ograniczenia i kolejny etap

Zachowaj wolumen, `.env` i klucz szyfrowania; przed aktualizacją wykonaj backup offline przy zatrzymanym API i workerze. Następnie `docker compose up --build -d` wykona 0003 i uruchomi usługi. Używaj nowych ekranów „Urządzenia i serwery”, „Grupy”, „Tagi” i „Monitory”. Instrukcje i semantyka stanów: ZARZADZANIE_INFRASTRUKTURA.md; artefakty CI: TESTY_I_ZRZUTY.md.

Wersja 0.3.0 jest gotowa do lokalnego testowania. Powiadomienia, pełna obsługa incydentów, raporty/SLA, retencja, MFA i automatyczny backup nadal należą do kolejnych etapów. Nie deklarujemy stabilnej 1.0, audytu całego produktu ani testów docelowej sieci LAN/HTTPS. Następny etap: incydenty, reguły alertów, SMTP/webhook i trwała kolejka z ponawianiem oraz deduplikacją. Nie wykonano merge do main.
