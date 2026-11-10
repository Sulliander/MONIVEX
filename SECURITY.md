# Bezpieczeństwo

Wersja 0.4.0 jest rozwojowa. Nie deklarujemy audytu bezpieczeństwa ani gotowości produkcyjnej. Dla instalacji sieciowej używaj HTTPS, silnego sekretu inicjalizacyjnego i aktualnych zależności. Nie montuj Docker Socket. Przechowuj kopie oraz `.env` poza repozytorium.

Podejrzenie podatności zgłoś prywatnie przez GitHub Security Advisories repozytorium, jeśli dostępne. Nie publikuj aktywnych tokenów, danych infrastruktury ani instrukcji pozwalających przejąć konkretną instalację w publicznym zgłoszeniu. Jeśli prywatny kanał jest niedostępny, poproś opiekunów o jego udostępnienie bez ujawniania szczegółów podatności.

Zagrożenia i obecne ograniczenia opisują docs/PLAN_IMPLEMENTACJI.md i docs/ADMINISTRACJA.md. Politykę CIDR, pinning DNS, przekierowania i przechowywanie sekretów opisuje docs/SILNIK_MONITORINGU.md. TOTP i kody odzyskiwania są dostępne; zarządzanie dodatkowymi użytkownikami pozostaje kolejnym etapem. [Zasady uwierzytelniania](docs/BEZPIECZENSTWO_KONTA.md) oraz [publiczny profil HTTPS](docs/WDROZENIE_VPS.md) opisują aktualny model ochrony.

Zasady edycji originu z zachowanymi sekretami, rewizji i operacji zbiorczych opisuje docs/ZARZADZANIE_INFRASTRUKTURA.md. Artefakty CI zawierają wyłącznie jawnie wybrane, maskowane obrazy i raporty testowej instalacji; nie obejmują baz, konfiguracji i śladów sesji.

Sekrety TOTP są szyfrowane tym samym trwałym kluczem instalacji co sekrety monitorów. API ujawnia wyłącznie nowy, nieaktywny sekret podczas konfiguracji QR/ręcznej; po aktywacji nie istnieje endpoint jego odczytu. Kody odzyskiwania mają 128 bitów losowej entropii i wyłącznie hashe SHA-256 w bazie. Testy i zrzuty nie są niezależnym audytem ani testem penetracyjnym rzeczywistego VPS.
