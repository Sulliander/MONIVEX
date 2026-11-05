# Bezpieczeństwo

Wersja 0.2.0 jest rozwojowa. Nie deklarujemy audytu bezpieczeństwa ani gotowości produkcyjnej. Dla instalacji sieciowej używaj HTTPS, silnego sekretu inicjalizacyjnego i aktualnych zależności. Nie montuj Docker Socket. Przechowuj kopie oraz `.env` poza repozytorium.

Podejrzenie podatności zgłoś prywatnie przez GitHub Security Advisories repozytorium, jeśli dostępne. Nie publikuj aktywnych tokenów, danych infrastruktury ani instrukcji pozwalających przejąć konkretną instalację w publicznym zgłoszeniu. Jeśli prywatny kanał jest niedostępny, poproś opiekunów o jego udostępnienie bez ujawniania szczegółów podatności.

Zagrożenia i obecne ograniczenia opisują docs/PLAN_IMPLEMENTACJI.md i docs/ADMINISTRACJA.md. Politykę CIDR, pinning DNS, przekierowania i przechowywanie sekretów opisuje docs/SILNIK_MONITORINGU.md. Moduł zarządzania dodatkowymi użytkownikami i TOTP pozostają kolejnym etapem.
