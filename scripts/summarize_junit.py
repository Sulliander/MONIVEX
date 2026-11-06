"""Publish counts only; raw failures and input data stay out of the job summary."""

import argparse
import os
from pathlib import Path
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("--name", default="Testy")
    args = parser.parse_args()
    report = Path(args.report)
    if not report.exists():
        text = f"### {args.name}\nBrak zakończonego raportu JUnit.\n"
    else:
        root = ET.parse(report).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        count = {
            key: sum(int(s.get(key, "0")) for s in suites)
            for key in ["tests", "failures", "errors", "skipped"]
        }
        text = f"### {args.name}\nŁącznie: **{count['tests']}** · zaliczone: **{count['tests'] - count['failures'] - count['errors'] - count['skipped']}** · nieudane: **{count['failures'] + count['errors']}** · pominięte: **{count['skipped']}**\n"
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            stream.write(text)
    print(text)


if __name__ == "__main__":
    main()
