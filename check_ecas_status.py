import os
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path

SECURITY_URL = "https://services3.cic.gc.ca/ecas/security.do"
AUTH_URL = "https://services3.cic.gc.ca/ecas/authenticate.do"

STATE_PATH = Path("last_status.txt")

# --------- Email config (env vars) ----------
EMAIL_SENDER = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]   # Gmail App Password
EMAIL_TO = os.environ["EMAIL_TO"]               # you (only recipient)
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))

# --------- eCAS auth inputs (env vars) ----------
ECAS_IDENTIFIER = os.environ["ECAS_IDENTIFIER"]
ECAS_SURNAME = os.environ["ECAS_SURNAME"]
ECAS_DOB = os.environ["ECAS_DOB"]                      # YYYY-MM-DD
ECAS_COUNTRY = os.environ.get("ECAS_COUNTRY", "207")
ECAS_IDENTIFIER_TYPE = os.environ.get("ECAS_IDENTIFIER_TYPE", "1")


def accept_terms(session: requests.Session) -> None:
    session.get(SECURITY_URL, timeout=30).raise_for_status()
    payload = {"lang": "", "app": "ecas", "securityInd": "agree", "_target1": "Continue"}
    session.post(SECURITY_URL, data=payload, timeout=30, allow_redirects=True).raise_for_status()


def authenticate(session: requests.Session) -> str:
    payload = {
        "lang": "",
        "_page": "_target0",
        "app": "ecas",
        "identifierType": str(ECAS_IDENTIFIER_TYPE),
        "identifier": ECAS_IDENTIFIER,
        "surname": ECAS_SURNAME,
        "dateOfBirth": ECAS_DOB,
        "countryOfBirth": str(ECAS_COUNTRY),
        "_submit": "Continue",
    }
    r = session.post(AUTH_URL, data=payload, timeout=30, allow_redirects=True)
    r.raise_for_status()
    return r.text


def extract_name_and_status(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    # Your snippet shows the status in a link to viewcasehistory.do
    a = soup.select_one('a[href^="viewcasehistory.do"]')
    if not a:
        Path("debug_ecas_after_auth.html").write_text(html, encoding="utf-8")
        return ("(name not found)", "⚠️ Status not found (see debug_ecas_after_auth.html)")

    status_text = a.get_text(" ", strip=True)

    # Applicant name is in the first <td> of the same row
    person_name = "(name not found)"
    tr = a.find_parent("tr")
    if tr:
        tds = tr.find_all("td")
        if tds:
            person_name = " ".join(tds[0].get_text(" ", strip=True).split())

    return person_name, status_text


def load_previous_status() -> str:
    return STATE_PATH.read_text(encoding="utf-8").strip() if STATE_PATH.exists() else ""


def save_current_status(status: str) -> None:
    STATE_PATH.write_text(status, encoding="utf-8")


def send_email(subject: str, body: str) -> None:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)


def main() -> None:
    session = requests.Session()
    accept_terms(session)
    html = authenticate(session)

    person_name, status = extract_name_and_status(html)

    prev = load_previous_status()
    changed = (prev != "" and status != prev)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    subject = f"eCAS: {status}" + (" 🆕" if changed else "")
    body = "\n".join([
        f"Run time: {now}",
        f"Applicant: {person_name}",
        f"Current status: {status}",
        f"Previous status: {prev if prev else '(first run)'}",
        f"Changed: {'YES' if changed else 'NO'}",
    ])

    send_email(subject, body)
    save_current_status(status)

    print(f"OK - emailed {EMAIL_TO}; status='{status}'; changed={changed}")


if __name__ == "__main__":
    main()
