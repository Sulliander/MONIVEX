# Zarządzanie infrastrukturą — MONIVEX 0.3.0

## Urządzenia, grupy i tagi

„Urządzenia i serwery” to ewidencja zasobów: nazwa, opis, adres IP/DNS, rodzaj, system operacyjny, środowisko, grupa i tagi. Jeden zasób może mieć wiele monitorów. Zmiana adresu w ewidencji nie przestawia samoczynnie celów kontroli — monitor jest niezależną konfiguracją konkretnej usługi. Usunięcie zasobu odłącza monitory, ale pozostawia ich działanie i historię.

Grupy tworzą hierarchię o dowolnej liczbie poziomów. Nie można ustawić grupy jako własnego przodka, także przy jednoczesnych zmianach przez dwóch operatorów. Nazwy rodzeństwa są unikalne (dla ASCII bez rozróżniania wielkości liter). Przed usunięciem grupy trzeba przenieść podgrupy i odłączyć przypisane zasoby oraz monitory. Tagi są unikalne, normalizowane do małych liter i mają nazwy z liter ASCII, cyfr, `_` i `-`. Usunięcie tagu usuwa powiązania, a nie monitory lub zasoby.

Stan zasobu jest obliczany z aktualnych stanów jego monitorów. Kolejność ważności aktywnych kontroli: DOWN → PENDING → DEGRADED → UNKNOWN → UP. Jeśli wszystkie są wstrzymane, zasób ma PAUSED. Bez monitorów ma UNKNOWN. Przy częściowo wstrzymanym monitoringu obliczamy stan pozostałych kontroli i pokazujemy osobny licznik wstrzymanych. Awaria jednej usługi nie zmienia stanów pozostałych monitorów.

## Konfigurator monitorów

Formularz ma sekcje „Podstawowe”, „Warunki poprawności”, „Zaawansowane” i „Powiązania”. Obsługuje wszystkie typy kontroli z etapu 2, ich warunki, progi, interwały, priorytet, grupę, tagi i zasób. Dla HTTP można skonfigurować Basic Auth, Bearer, własne nagłówki i treść POST. Sekrety nie są odczytywane z API; przy edycji wybierz pozostawienie, zastąpienie całego zestawu albo usunięcie.

Zmiana originu HTTP przy zachowanych sekretach jest odrzucana. Trzeba jawnie usunąć stare dane lub wprowadzić nowe. Zapobiega to wysłaniu istniejącego hasła na nowy serwer. Klucz `MONIVEX_ENCRYPTION_KEY` jest ustawieniem wdrożenia, a nie polem panelu. Nie wpisuj tokenów do URL, nazwy ani opisu.

Typ istniejącego monitora jest stały. Dla innego protokołu utwórz nowy monitor. Duplikowanie kopiuje konfigurację i powiązania, ale rozpoczyna nową historię i harmonogram. Domyślnie nie kopiuje sekretów; ich zaszyfrowane skopiowanie wymaga jawnego zaznaczenia. Kopia heartbeat zawsze otrzymuje nowy token pokazywany tylko raz. Oryginalny token i historia nigdy nie są udostępniane kopii.

Test ręczny nadal nie zmienia stanu, historii, harmonogramu ani incydentów. Zmiana warunków kontroli zamyka dotychczasowy incydent z przyczyną `configuration_changed`; nie udaje potwierdzonego powrotu usługi. Monitor przechodzi do UNKNOWN i wymaga nowej kontroli. Wstrzymanie nie zamyka incydentu technicznego. Usunięcie monitora jest destrukcyjne i wymaga potwierdzenia: usuwa również jego wyniki i incydenty.

## Filtrowanie i operacje zbiorcze

Lista i pulpit odświeżają wyniki także przy nieaktywnym oknie przeglądarki. Lista monitorów ma paginację po 50 pozycji, wyszukiwanie literalnej nazwy, filtry typu, stanu, urządzenia, grupy i tagu oraz sortowanie. Filtr grupy uwzględnia podgrupy i grupę powiązanego zasobu. Filtr tagu uwzględnia własne tagi monitora oraz tagi jego zasobu. To zakres filtrowania, a nie automatyczna zmiana przypisań. Liczniki pulpitu obejmują wszystkie monitory, niezależnie od rozmiaru strony; tabela przeglądu nadal pokazuje do 1000 pierwszych wpisów.

Zaznacz monitory na stronie i wybierz wstrzymanie, wznowienie, usunięcie lub zmianę ustawień. Maksymalnie 100 monitorów w jednym żądaniu API. Puste pola konfiguracji zbiorczej oznaczają pozostawienie wartości. Grupa i zasób mają osobną opcję „Bez przypisania”, a tagi można pozostawić, zastąpić lub usunąć. Cała operacja jest atomowa: błędna konfiguracja, brak elementu lub nieaktualna rewizja powodują odrzucenie wszystkich zmian.

Edycja i usuwanie korzystają z rewizji obiektu. Jeśli inny użytkownik zmienił dane, otrzymasz komunikat o konflikcie; odśwież dane przed ponowną edycją. Identyfikatory tworzone przez API nie są ponownie przydzielane po usunięciu, a worker dodatkowo rozpoznaje instancję monitora. Wynik kontroli rozpoczętej przed edycją/usunięciem nie nadpisze nowych danych.

## Bezpieczeństwo i ograniczenia

Backend egzekwuje role, sesje, Origin i CSRF. Viewer ma podgląd; Owner/Administrator/Operator zarządzają infrastrukturą. Nie dodano jeszcze panelu tworzenia dodatkowych użytkowników, TOTP, alarmowania ani backupu. Polityka CIDR, sprawdzanie DNS i ochrona przekierowań pozostają aktywne przy tworzeniu, edycji, kopiowaniu i ręcznym teście. Samo przypisanie zasobu nie rozszerza dozwolonych celów.

Daty wyników, incydentów i cykli workera są prezentowane w strefie zapisanej przy inicjalizacji instalacji. SQLite jest nadal jedyną zweryfikowaną bazą. Długotrwałe wdrożenie wymaga retencji i dalszych testów obciążenia. Nie deklarujemy stabilnego wydania 1.0 ani pełnego audytu bezpieczeństwa.
