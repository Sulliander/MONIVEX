# Testy, GitHub Actions i zrzuty ekranów

Workflow „Kontrola jakości” działa przy push, pull request i ręcznym uruchomieniu obsługiwanym przez GitHub. Nie publikuje obrazów jako stabilnych wydań. Używa Ubuntu 24.04, Pythona 3.12 i Node 24; oficjalne akcje są przypięte do pełnych SHA zweryfikowanych tagów v6.

## Wyniki i artefakty

- Backend: pytest, JUnit, Ruff i audyt zależności. Artefakt `backend-junit`.
- Frontend: testy komponentów i dat/stref, TypeScript/Vite, ESLint oraz audyt npm. Artefakt `frontend-junit`.
- Pełny stack: świeży wolumen, migracje, API/WEB/worker, Chromium, kontrola ciągłości workera bez API i sprzątanie. Artefakt `monivex-ui-evidence-N` zawiera `index.html`, raport JUnit oraz dziesięć zrzutów PNG.

W repozytorium otwórz „Actions”, wybierz przebieg i sekcję „Artifacts”. Pobierz galerię, rozpakuj ZIP i otwórz `index.html`. Artefakty są przechowywane przez siedem dni. Podsumowania zliczają zaliczone, nieudane i pominięte testy; test pominięty nie jest zaliczany jako sukces. Starsze przebiegi mogą nie mieć galerii, bo funkcja została dodana w etapie 3.

## Co sprawdza przeglądarka

Rzeczywiste utworzenie właściciela, logowanie i sesję po odświeżeniu, zmianę hasła, motywy, heartbeat i jego historię, pauzę/wznowienie, grupę i podgrupę, tag, urządzenie, powiązanie monitora z zasobem, duplikowanie, zmianę zbiorczą, usunięcie kopii oraz widok mobilny i wylogowanie. Heartbeat jest wysyłany regularnie do prawdziwego endpointu podczas testu; zielony stan nie jest podstawiany w interfejsie.

Wszystkie dane to jednorazowa instalacja testowa, nie demonstracyjna zawartość aplikacji. Zrzuty wykonuje Playwright na działających ekranach. Pola haseł, sekcje sekretów i karta tokenu są maskowane. Nie zapisujemy nagrań, trace, baz, pliku `.env`, tokenów ani logów treści żądań do artefaktów. Galeria jest statyczna i pokazuje tylko jawnie wybrane obrazy. Pełne ślady DOM z ewentualnej awarii nie są publikowane.

## Powtórzenie lokalne

Na nowym, wyłącznie testowym stacku ustaw:

```sh
export MONIVEX_TEST_URL=http://localhost:8080
export MONIVEX_TEST_WORKER=1
export MONIVEX_TEST_MANAGEMENT=1
export MONIVEX_SCREENSHOTS=1
# MONIVEX_TEST_SETUP_TOKEN podaj bezpiecznie z konfiguracji jednorazowej instalacji.
cd frontend
npx playwright install chromium
npx playwright test
cd ..
python3 scripts/build_evidence_gallery.py
```

Można wybrać systemowy Chromium przez `MONIVEX_CHROMIUM=/usr/bin/chromium`. Test inicjalizuje instalację i zmienia hasło — nie używaj go na istniejących danych użytkownika. Przy powtarzaniu użyj nowego wolumenu oraz wyczyść wyłącznie wygenerowany katalog `frontend/artifacts`. Nie usuwaj danych produkcyjnych.

`scripts/verify_worker_compose.py` celowo zatrzymuje API wskazanego jednorazowego projektu, sprawdza przyrost wyników i ponownie uruchamia API. Szczegóły w INSTALACJA.md. Skanowanie zależności i zrzuty nie zastępują audytu, testów obciążenia ani testów całej docelowej infrastruktury.

## Dostęp z chmury Codex

Push do GitHub uruchamia workflow. Jego status można sprawdzić także na publicznej stronie przebiegu. Odczyt logów i artefaktów przez `gh` wymaga dostępu do `api.github.com` i odpowiedniego uwierzytelniania. Zapisanie domeny w szkicu ustawień środowiska nie stosuje jeszcze zmiany — ustawienia trzeba zapisać i opublikować. Nie obchodź blokad sieci ani nie umieszczaj tokenów w czacie.
