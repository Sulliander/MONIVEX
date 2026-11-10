# Administracja — MONIVEX 0.4.0

Kreator jest dostępny tylko do inicjalizacji instalacji. Utworzenie właściciela wymaga sekretu wdrożenia o długości co najmniej 32 znaków. Baza zapewnia singleton instalacji, również przy konkurencyjnych żądaniach. Nie ma publicznej rejestracji.

Hasła mają minimum 12 znaków, zalecana losowa fraza z menedżera haseł. Konta i sesje przechowuje baza. Sesje wygasają po 12 godzinach (konfigurowalne przez `MONIVEX_SESSION_HOURS`, 1–168 godzin przy uruchomieniu bez Compose override). Zmiana hasła oraz wylogowanie wszystkich urządzeń natychmiast unieważniają sesje. Token CSRF znajduje się w sessionStorage karty, token sesji w ciasteczku HttpOnly. Nowa karta uzyskuje CSRF automatycznie przez chroniony Origin endpoint; nie kopiuj tokenów ręcznie.

Limit 10 prób / 15 minut jest zapisywany w bazie, a nie pamięci procesu. Za dołączonym Nginx obowiązuje wspólnie dla klientów instalacji. Profil publiczny poprawnie rozpoznaje klientów w łańcuchu Caddy → Nginx → API; szczegóły: [VPS](WDROZENIE_VPS.md). Limit obejmuje też konto, więc zmiana adresu klienta nie omija blokady konta.

Zdarzenia inicjalizacji, logowania (także nieudanego), wylogowania i zmiany hasła są utrwalane w `audit_events`; własny dziennik bezpieczeństwa jest dostępny w ustawieniach konta. Pełny dziennik administracyjny pozostaje przyszłym zakresem. Zdarzenia nie zawierają haseł, tokenów ani treści formularzy.

## Kopia offline

Wersja 0.4.0 nie zawiera panelu backupu; odzyskiwanie drugiego składnika korzysta z jednorazowych kodów. Przed zmianą wersji zatrzymaj API i worker (`docker compose stop api worker`), zrób kopię całego wolumenu przy zatrzymanych procesach zapisujących (również plików WAL/SHM, jeśli występują) i zabezpiecz ją poza hostem. Zachowaj osobno także klucz `MONIVEX_ENCRYPTION_KEY`, jeśli zapisano sekrety monitorów lub skonfigurowano 2FA. Utrata lub podmiana klucza uniemożliwi odszyfrowanie TOTP. Kopia zawiera hashe i sesje: traktuj ją jako poufną i szyfruj narzędziem administratora. Przywracaj tylko do zgodnej wersji, przy zatrzymanych usługach, zachowując UID/GID 10001. Nie edytuj ręcznie hashy haseł. Pełny, testowany mechanizm backup/restore i odzyskiwania będzie osobnym etapem.

## Ograniczenia

Worker i monitory są dostępne. Przeczytaj [zasady silnika](SILNIK_MONITORINGU.md), ustaw politykę CIDR i zachowaj klucz szyfrowania przed dodaniem sekretów HTTP. Test SMTP sprawdza usługę; nie wysyła wiadomości alarmowych. Brak jeszcze powiadomień, zarządzania dodatkowymi użytkownikami, pełnej edycji ustawień instalacji i retencji wyników/audytu. Nie traktuj tej wersji jako gotowego wydania produkcyjnego.

## Bezpieczeństwo konta

[Instrukcja TOTP, odzyskiwania, sesji i polityki administratorów](BEZPIECZENSTWO_KONTA.md). Przed wymuszeniem 2FA skonfiguruj własny drugi składnik i zachowaj kody. Właściciel bez aktywnego 2FA nie może włączyć wymogu. Administrator bez 2FA zachowuje dostęp do konfiguracji swojego konta, a pozostałe API odrzuca operacje do czasu aktywacji.
