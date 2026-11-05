# Administracja — etapy 1 i 2

Kreator jest dostępny tylko do inicjalizacji instalacji. Utworzenie właściciela wymaga sekretu wdrożenia o długości co najmniej 32 znaków. Baza zapewnia singleton instalacji, również przy konkurencyjnych żądaniach. Nie ma publicznej rejestracji.

Hasła mają minimum 12 znaków, zalecana losowa fraza z menedżera haseł. Konta i sesje przechowuje baza. Sesje wygasają po 12 godzinach (konfigurowalne przez `MONIVEX_SESSION_HOURS`, 1–168 godzin przy uruchomieniu bez Compose override). Zmiana hasła oraz wylogowanie wszystkich urządzeń natychmiast unieważniają sesje. Token CSRF znajduje się w sessionStorage karty, token sesji w ciasteczku HttpOnly. Po otwarciu nowej karty może być konieczne ponowne logowanie, aby uzyskać CSRF; nie kopiuj tokenów ręcznie.

Limit 10 prób / 15 minut jest zapisywany w bazie, a nie pamięci procesu. Za dołączonym Nginx obowiązuje wspólnie dla klientów instalacji. To świadome ograniczenie etapu 1; zaplanuj prawidłowe rozpoznawanie adresów wyłącznie z zaufanych proxy przed szerokim wdrożeniem.

Zdarzenia inicjalizacji, logowania (także nieudanego), wylogowania i zmiany hasła są utrwalane w `audit_events`; ekran audytu będzie w etapie 6. Zdarzenia nie zawierają haseł, tokenów ani treści formularzy.

## Kopia offline

Etap 1 nie zawiera panelu backupu i odzyskiwania kont. Przed zmianą wersji zatrzymaj API i worker (`docker compose stop api worker`), zrób kopię całego wolumenu przy zatrzymanych procesach zapisujących (również plików WAL/SHM, jeśli występują) i zabezpiecz ją poza hostem. Zachowaj osobno także klucz `MONIVEX_ENCRYPTION_KEY`, jeśli zapisano sekrety monitorów. Kopia zawiera hashe i sesje: traktuj ją jako poufną i szyfruj narzędziem administratora. Przywracaj tylko do zgodnej wersji, przy zatrzymanych usługach, zachowując UID/GID 10001. Nie edytuj ręcznie hashy haseł. Pełny, testowany mechanizm backup/restore i odzyskiwania będzie osobnym etapem.

## Ograniczenia

Worker i monitory są dostępne. Przeczytaj [zasady silnika](SILNIK_MONITORINGU.md), ustaw politykę CIDR i zachowaj klucz szyfrowania przed dodaniem sekretów HTTP. Test SMTP sprawdza usługę; nie wysyła wiadomości alarmowych. Brak jeszcze powiadomień, dodatkowych użytkowników, MFA, pełnej edycji ustawień instalacji i retencji wyników/audytu. Nie traktuj tej wersji jako gotowego wydania produkcyjnego.
