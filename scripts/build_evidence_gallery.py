"""Build a static gallery from explicitly sanitized Playwright screenshots only."""

import os
from html import escape
from pathlib import Path
import xml.etree.ElementTree as ET


def main():
    root = Path("frontend/artifacts")
    screens = root / "screenshots"
    root.mkdir(parents=True, exist_ok=True)
    titles = {
        "01-logowanie": "Logowanie",
        "02-pulpit-ciemny": "Nowa instalacja",
        "03-grupy": "Grupy hierarchiczne",
        "04-urzadzenia": "Urządzenia i serwery",
        "05-konfigurator": "Konfigurator monitora",
        "06-monitory": "Zarządzanie monitorami",
        "07-urzadzenie-z-monitorem": "Urządzenie z rzeczywistym monitorem",
        "08-pulpit-ciemny": "Pulpit — motyw ciemny",
        "09-pulpit-jasny": "Pulpit — motyw jasny",
        "10-mobilny": "Widok mobilny",
    }
    cards = []
    for image in sorted(screens.glob("*.png")):
        url = "screenshots/" + image.name
        title = titles.get(image.stem, image.stem)
        cards.append(
            f'<article><h2>{escape(title)}</h2><a href="{escape(url)}"><img loading="lazy" src="{escape(url)}" alt="{escape(title)}"></a></article>'
        )
    summary = "Brak zakończonego raportu testów."
    report = root / "test-results.xml"
    if report.exists():
        tree = ET.parse(report).getroot()
        keys = ["tests", "failures", "errors", "skipped"]
        counts = {key: int(tree.get(key, "0")) for key in keys}
        if tree.tag == "testsuites" and not any(counts.values()):
            counts = {
                key: sum(
                    int(suite.get(key, "0")) for suite in tree.findall("testsuite")
                )
                for key in keys
            }
        summary = f"Testy: {counts['tests']} · błędy: {counts['failures'] + counts['errors']} · pominięte: {counts['skipped']}"
    page = (
        """<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MONIVEX — dowody testów</title><style>body{margin:0;background:#0b101a;color:#e5edf8;font:15px system-ui}main{max-width:1250px;margin:auto;padding:48px 24px}h1{font-size:32px}p{color:#9eacc1;line-height:1.7}article{margin:36px 0;background:#111925;padding:20px;border:1px solid #243044;border-radius:12px}h2{font-size:18px}img{max-width:100%;height:auto;border-radius:8px}a{color:#5ce2c3}.badge{color:#5ce2c3;font-size:12px;text-transform:uppercase;letter-spacing:2px}</style><main><div class="badge">MONIVEX 0.3.0 · środowisko testowe</div><h1>Rzeczywiste ekrany i testy aplikacji</h1><p>Galeria powstaje podczas testów pełnego stacku Docker Compose. Dane są jednorazowymi danymi testowymi; wyniki monitoringu pochodzą z działającego workera. Sekrety i pola prywatne są maskowane. Nie dołączamy baz, konfiguracji środowiskowej, nagrań ani śladów formularzy.</p><p>"""
        + escape(summary)
        + """</p><p><a href="test-results.xml">Raport JUnit XML</a></p>"""
        + "".join(cards)
        + """</main></html>"""
    )
    (root / "index.html").write_text(page, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            stream.write(
                f"### Galeria ekranów\nZapisane, bezpieczne zrzuty: **{len(cards)}**. {summary}\n"
            )
    print(f"Galeria: {len(cards)} bezpiecznych zrzutów. {summary}")


if __name__ == "__main__":
    main()
