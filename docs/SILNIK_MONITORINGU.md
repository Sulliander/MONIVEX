# Silnik monitoringu — etap 2

## Uruchomienie i zakres

Compose uruchamia niezależny proces `python -m app.worker` po migracjach. API może zostać zatrzymane i zrestartowane bez zatrzymywania workera. Worker nie potrzebuje sesji ani sekretu inicjalizacji. Przy starcie odczytuje monitory i harmonogram z tej samej bazy. Nie odtwarza masowo pominiętych cykli: po wyniku wyznacza następny termin jako czas zakończenia + interwał.

Dostępne kontrole: ICMP (gniazdo datagramowe Linux), TCP, HTTP/HTTPS, DNS UDP z przejściem na TCP przy odpowiedzi uciętej, certyfikat TLS, SMTP z opcjonalnym STARTTLS, HTTP JSON oraz heartbeat. SMTP wysyła tylko EHLO/STARTTLS/QUIT, nigdy wiadomości. TLS zawsze sprawdza zaufanie i nazwę hosta; dla wewnętrznego CA dostarcz zaufany pakiet certyfikatów przez montowanie i `SSL_CERT_FILE`. Nie wyłączaj sprawdzania certyfikatów. TLS raportuje ostrzeżenie przed wygaśnięciem.

Formularz WWW pozwala utworzyć monitor, wstrzymać/wznowić go, przejrzeć ostatnie wyniki i wykonać test ręczny. Rozbudowana edycja, duplikowanie, powiązania, operacje zbiorcze i pełny konfigurator pozostają etapem 3. Nagłówki, Basic Auth, Bearer i treść POST są obecnie dostępne przez API `secrets`, nie przez formularz WWW. Pole JSON wskazuje listę kluczy i indeksów; nie uruchamia wyrażeń ani kodu. Warunek porównuje typ i prostą wartość JSON.

## Polityka celów

`MONIVEX_ALLOWED_NETWORKS` to lista CIDR rozdzielona przecinkami, wspólna dla API i workera. Pusta lista domyślnie blokuje wszystkie połączenia sieciowe. Prywatne podsieci LAN mogą być jawnie dopuszczone. Ustaw wyłącznie zakresy, które wolno monitorować. Nie używaj szerokiego `0.0.0.0/0` ani `::/0` jako skrótu konfiguracji. Listy nie zmienia się przez panel ani REST API. Heartbeat nie wymaga dostępu wychodzącego.

Przed zapisem monitora sprawdzamy rozwiązywanie celu. Przed KAŻDYM połączeniem worker ponownie rozwiązuje nazwę, sprawdza wszystkie odpowiedzi DNS i łączy się z konkretnym zweryfikowanym numerycznym adresem. Oryginalna nazwa zostaje w Host i TLS SNI. Mieszana odpowiedź DNS z niedozwolonym adresem jest odrzucana. Przekierowania są domyślnie wyłączone; po włączeniu limit wynosi pięć przejść. Każdy nowy cel podlega tej samej kontroli. Nie dopuszczamy przekierowania HTTPS → HTTP; po zmianie originu usuwamy wszystkie własne nagłówki, autoryzację i treść, również przy powrocie na pierwotny origin.

Zawsze blokowane są adresy multicast, unspecified, link-local, IPv4-mapped IPv6, 6to4/Teredo i znane adresy usług metadanych. Lista CIDR nie zastępuje zapory hosta, kontroli routingu, uprawnień administratora i izolacji sieci. Endpointy monitoringu nie udostępniają treści odpowiedzi, szczegółowych wyjątków ani sekretów.

Uprawnienia backendu: Owner/Administrator/Operator mogą tworzyć monitory, wstrzymywać je i inicjować ręczne testy; Viewer może tylko czytać. Nie dodano jeszcze zarządzania dodatkowymi kontami (etap 6). Nazwy ról zapisane w bazie nie są dowodem wdrożenia całego modułu RBAC.

## Sekrety i heartbeat

Opcjonalny `MONIVEX_ENCRYPTION_KEY` zawiera klucz Fernet: 32 losowe bajty zakodowane base64url. Przykładowe wygenerowanie na hoście z OpenSSL: `openssl rand -base64 32 | tr '/+' '_-'`. Zachowaj ten sam klucz przy aktualizacjach i osobno zaszyfruj go wraz z backupem. Brak klucza blokuje zapis sekretów HTTP. Błędny klucz podczas odczytu daje UNKNOWN, nie fałszywy wynik awarii usługi. Hasła/tokeny/nagłówki i treść POST są szyfrowane; API zwraca tylko informację `has_credentials`. Adres URL i publiczne warunki są jawne: nie wkładaj tokenów do query string.

Po utworzeniu heartbeat API zwraca losowy token **tylko raz**. W bazie znajduje się SHA-256 tokenu; panel nie potrafi go ponownie odczytać. Wywołuj POST `/api/heartbeats/{id}` z `Authorization: Bearer <token>`. Bez tokenu odpowiedź jest 404. Nie umieszczaj tokenu w URL, logach ani historii poleceń. Pierwszy sygnał jest oczekiwany do `created_at + interval + grace_seconds`; wcześniej wynik pozostaje UNKNOWN. Aktualność po pierwszym sygnale: `heartbeat_at + interval + grace_seconds`. Awaria jest wykrywana przez następny cykl schedulera i skonfigurowany próg nieudanych kontroli, nie natychmiast po przekroczeniu terminu. Powtarzane sygnały są scalane do najwyżej jednego zapisu na sekundę.

## Stany i incydenty

- Nieudana kontrola: PENDING, następnie DOWN po `failure_threshold` kolejnych błędach.
- Pierwszy DOWN atomowo tworzy incydent. Unikalny indeks dopuszcza tylko jeden otwarty incydent na monitor.
- Przy otwartym incydencie potrzeba `recovery_threshold` kolejnych poprawnych kontroli; przed osiągnięciem progu stan to PENDING. UP i DEGRADED oznaczają poprawną kontrolę, przy czym DEGRADED sygnalizuje próg czasu lub ważności certyfikatu.
- UNKNOWN zeruje serie błędów i powrotów, ale nie zamyka otwartego incydentu.
- Wstrzymanie nie wykonuje kontroli i nie zamyka incydentu. Wznowienie zaczyna od UNKNOWN; faktyczny powrót musi potwierdzić worker.
- Test ręczny nie zapisuje wyniku produkcyjnego, nie przestawia harmonogramu, nie zmienia stanu i nie tworzy incydentu. Jego wykonanie jest audytowane i ograniczone liczbą równoległych prób oraz limitem prób użytkownika.

Gdy ostatni cykl workera ma ponad 10 sekund albo wynik jest starszy niż interwał + timeout + 10 sekund, API prezentuje UNKNOWN. Zapisany dawny stan można odróżnić jako `recorded_state`; panel nie wyświetla go jako aktualnej zielonej dostępności. PAUSED ma pierwszeństwo przed nieaktualnością.

## Scheduler i niezawodność

Jeden lider utrzymuje w SQLite dzierżawę odnawianą co około sekundę (domyślnie ważną 30 sekund). Inne procesy pozostają w gotowości. Każdy zapis wyniku w krótkiej transakcji sprawdza właściciela i ważność dzierżawy, rewizję monitora, ostatni wynik oraz aktualność snapshotu heartbeat. Dzięki temu wynik po utracie lidera, wstrzymaniu lub ponowieniu tego samego zapisu jest odrzucany. Zapis wyniku, liczników, stanu i incydentu jest atomowy. Operacje sieciowe odbywają się poza transakcjami; równoległość workera domyślnie wynosi 10 (`MONIVEX_WORKER_CONCURRENCY`). Czas całej kontroli, łącznie z DNS i przekierowaniami, jest ograniczony timeoutem. Treść HTTP do kontroli warunków ma limit 1 MiB.

Worker zapisuje logi zdarzeń w JSON bez surowych wyjątków, URL i sekretów. Utrata bazy jest ponawiana w kolejnym cyklu. Utrata dzierżawy blokuje zapis przez starego lidera, nawet gdy stary proces po opóźnieniu zakończy wcześniej rozpoczęte połączenie. Proces poprawnie kończony zwalnia dzierżawę; po SIGKILL drugi proces czeka na jej wygaśnięcie.

## Ograniczenia

ICMP wymaga, aby kernel pozwalał grupie procesu (w obrazie GID 10001) używać gniazd ping, np. przez właściwą dla wdrożenia konfigurację `net.ipv4.ping_group_range`. Nie wymaga Docker Socket ani roota w aplikacji. Runtime chmurowy użyty w testach odmówił tej operacji; wynik jest UNKNOWN, a rzeczywisty test ICMP pominięto. Nie deklarujemy go jako zweryfikowanego w tym środowisku.

Kontrole w tej implementacji łączą się bezpośrednio z dopuszczonymi celami (w tym TCP/UDP/ICMP); administrator musi zapewnić routing i uprawnienia sieci. Nie jest to mechanizm korzystania z poświadczeń przechowywanych w proxy chmurowym. W Codex testowano wyłącznie własne serwery loopback i jednorazowy stack Docker; nie skanowano sieci LAN ani publicznych usług.

SQLite pozostaje jedyną testowaną bazą. Pulpit i lista obejmują na razie do 1000 pierwszych monitorów (paginacja i statystyki całej większej instalacji wymagają dalszej pracy), historia odpowiedzi API do 1000 wyników na zapytanie. Nie wdrożono jeszcze retencji i agregacji, zatem dane rosną; przed długotrwałym wdrożeniem produkcyjnym konieczne są kolejne etapy. Incydenty są tworzone i zamykane automatycznie, ale nie ma jeszcze powiadomień ani panelu obsługi incydentów. Raporty, SLA, SSE, prace serwisowe, MFA i automatyczny backup nie są funkcjami etapu 2.
