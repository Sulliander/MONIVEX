# Bezpieczeństwo konta — MONIVEX 0.4.0

Cały interfejs pozostaje polski. Ustawienia → Bezpieczeństwo konta udostępniają działające formularze, sesje i własny dziennik. Nie dodano drugiego systemu autoryzacji ani publicznej rejestracji.

## Włączenie 2FA

1. Ustaw trwały klucz `MONIVEX_ENCRYPTION_KEY` w konfiguracji API. Jeżeli już szyfruje sekrety monitorów, użyj dokładnie tego samego klucza. Zachowaj go przy restartach, aktualizacjach i backupie.
2. W ustawieniach wybierz „Skonfiguruj 2FA” i potwierdź obecnym hasłem.
3. Zeskanuj QR w Microsoft Authenticator, Google Authenticator albo 2FAS. Możesz też ręcznie przepisać sekret jako konto TOTP. Używamy standardowego `otpauth`, SHA-1, sześciu cyfr i okresu 30 sekund. Włącz automatyczną synchronizację czasu telefonu i serwera.
4. Wpisz kod i potwierdź aktywację. Samo wyświetlenie QR nie aktywuje 2FA. Oczekująca konfiguracja wygasa po 10 minutach; rozpoczęcie kolejnej unieważnia poprzednią.
5. Zachowaj dziesięć kodów odzyskiwania. Wyświetlamy je tylko w odpowiedzi na aktywację lub regenerację. Możesz pobrać plik; aplikacja nie zapisuje kodów w localStorage ani sessionStorage. Potwierdź zapis i ukryj kody. Nie przechowuj jedynej kopii na telefonie z aplikacją TOTP.

Sekret nowej konfiguracji jest z konieczności dostępny w odpowiedzi inicjującej QR/ręczne wpisanie. Odpowiedź jest `no-store`. Po aktywacji API nie zwraca sekretu. Aktywny i oczekujący sekret są szyfrowane Fernet; kodów odzyskiwania nie szyfrujemy odwracalnie — zapisujemy wyłącznie SHA-256 z identyfikatorem użytkownika. Każdy kod ma 128 bitów losowej entropii, dlatego nie jest traktowany jak hasło o niskiej entropii. Hasła nadal korzystają z Argon2id.

## Logowanie i odzyskiwanie drugiego składnika

Konto bez aktywnego 2FA loguje się dotychczasowym hasłem. Konto z 2FA po poprawnym haśle otrzymuje jedynie losowy, hashowany w bazie, pięciominutowy token wyzwania w osobnym HttpOnly/Secure/SameSite Strict cookie. Nie ma wtedy pełnej sesji ani dostępu do panelu/API konta. Drugi ekran przyjmuje TOTP lub jeden kod odzyskiwania.

Akceptujemy bieżący przedział TOTP oraz jeden sąsiedni w każdą stronę. Zapamiętujemy najwyższy zaakceptowany krok: użytego przedziału nie można ponownie wykorzystać, także na innym urządzeniu, w drugim procesie API i po restarcie. Po udanej operacji poczekaj na nowy kod. Kody odzyskiwania są atomowo usuwane przy użyciu. Równoczesne żądania nie mogą zużyć tego samego kodu dwukrotnie.

Logowanie kodem odzyskiwania kończy inne pełne sesje i wszystkie pozostałe wyzwania użytkownika. Nie wyłącza 2FA. W razie utraty telefonu zaloguj się hasłem i kodem odzyskiwania; następnie wyłącz 2FA hasłem i kolejnym kodem oraz skonfiguruj nowy telefon. Przy obowiązującym wymogu administratorów najpierw zmień politykę jako właściciel. Brak telefonu i wszystkich kodów nie daje publicznej ścieżki obejścia 2FA. Nie dodano resetu hasła przez e-mail ani administracyjnego backdoora.

## Limity i ponowne uwierzytelnienie

Liczniki są trwałe w SQLite i nie znikają po restarcie:

- hasło: maksymalnie 10 prób / 15 minut na adres klienta i niezależnie na login;
- drugi etap: maksymalnie 5 błędów na wyzwanie, 10 prób / 15 minut na konto i 30 / 15 minut na adres;
- operacje wymagające ponownego uwierzytelnienia: 10 prób / 15 minut na konto;
- inicjalizacja: 10 prób / 15 minut na adres.

Liczą się także poprawne próby; to konserwatywny limit, a nie licznik wyłącznie błędów. `429` zawiera `Retry-After`, ekran logowania pokazuje czas blokady. Nieznany login i złe hasło zwracają ten sam komunikat. Po pięciu błędach kodu rozpocznij logowanie ponownie; nowe wyzwanie nie zeruje limitu konta.

Zmiana hasła, wyłączenie 2FA, regeneracja kodów oraz zmiana polityki wymagają hasła i — przy aktywnym 2FA — nowego TOTP lub nieużytego kodu odzyskiwania. Aktywacja, wyłączenie i regeneracja kończą pozostałe sesje/wyzwania i odnawiają token bieżącej sesji wraz z CSRF. Zmiana hasła kończy wszystkie sesje i wyzwania; trzeba zalogować się ponownie. Nowe hasło wymaga minimum 12 znaków oraz potwierdzenia w formularzu. Zmiana polityki stosuje nowy wymóg również wobec istniejących sesji.

## Sesje i zdarzenia

Lista sesji pokazuje własne urządzenia, adres klienta, czas utworzenia i wygaśnięcia. Identyfikatory listy są losowe i niezależne od hasha ciasteczka. Możesz zakończyć wybraną sesję lub wylogować wszystkie urządzenia. Próba unieważnienia cudzej sesji zwraca 404. Sesje sprzed aktualizacji pozostają ważne; brakujące metadane są oznaczone jako nieznane.

Nowa karta uzyskuje CSRF przez POST `/api/auth/csrf` z kontrolą Origin i istniejącej sesji. Ten endpoint nie wymaga wcześniejszego CSRF; zwraca stały dla danego tokenu sesji, nieprzewidywalny dla innych originów token. Pozostałe operacje sesyjne wymagają Origin i CSRF. Interfejs jednokrotnie odzyskuje CSRF po jego odrzuceniu, bez pętli ponawiania. Wygaśnięcie lub unieważnienie sesji usuwa dane panelu z pamięci klienta i wraca do logowania.

Dziennik udostępnia tylko własne zdarzenia bezpieczeństwa, najnowsze najpierw, ze stronicowaniem. Nie zawiera haseł, sekretów TOTP, kodów, surowych tokenów sesji ani treści formularzy. Błędne logowanie jest przypisywane kontu tylko wtedy, gdy podany login istnieje; odpowiedź logowania nie ujawnia tej informacji. Adres i user agent są metadanymi sesji, a nie dowodem tożsamości urządzenia.

## Polityka administratorów

Tylko właściciel zmienia wymóg 2FA. Włączenie wymaga wcześniej aktywnego 2FA na własnym koncie i ponownego uwierzytelnienia. Wymóg dotyczy ról `owner` i `administrator`, pozostałe role nadal mogą samodzielnie używać opcjonalnego 2FA.

Administrator bez 2FA po zalogowaniu widzi ustawienia bezpieczeństwa i może skonfigurować drugi składnik, zmienić hasło lub się wylogować. Pozostałe API oraz panel infrastruktury są niedostępne do czasu aktywacji. Nie wyłączaj 2FA administratora przy aktywnym wymogu — backend odrzuca taką operację. Wymóg jest domyślnie wyłączony po migracji i nie odcina wcześniejszych kont.
