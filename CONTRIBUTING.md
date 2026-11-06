# Współpraca

Przeczytaj docs/PLAN_IMPLEMENTACJI.md. Przygotuj mały, spójny przyrost z testami i dokumentacją po polsku. Kod i API nazywaj po angielsku. Teksty interfejsu dodawaj w frontend/src/locales/pl.json; nie dodawaj obecnie angielskiego interfejsu. Nie używaj danych rzeczywistej infrastruktury.

Uruchom testy backendu, Ruff, testy WEB, ESLint i kompilację TypeScript/Vite zgodnie z README. Migracje zapisuj jawnie, nigdy nie importuj bieżących modeli w historycznej migracji. Nowa funkcja nie może udawać danych ani obchodzić zabezpieczeń. Zmiany zależności wymagają aktualizacji lockfile i audytu. Zgłaszaj PR do przeglądu; nie oznaczaj wydania jako stabilne bez etapu 7.
