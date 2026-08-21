#!/usr/bin/env python3
"""Envoie l'email mensuel du dashboard CC.
Prerequis (variables d'environnement, voir README-SETUP.md etape 6) :
  GMAIL_USER          adresse Gmail d'envoi
  GMAIL_APP_PASSWORD  mot de passe d'application Gmail (16 caracteres)
  CC_RECIPIENTS       destinataires separes par des virgules
Usage :
  python3 scripts/send_email.py --month 2026-07 --url https://... --summary "..."
"""
import os, sys, argparse, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

p = argparse.ArgumentParser()
p.add_argument("--month", required=True)
p.add_argument("--url", required=True)
p.add_argument("--summary", default="")
args = p.parse_args()

user = os.environ.get("GMAIL_USER")
pwd = os.environ.get("GMAIL_APP_PASSWORD")
to = os.environ.get("CC_RECIPIENTS")
if not (user and pwd and to):
    sys.exit("Definir GMAIL_USER, GMAIL_APP_PASSWORD, CC_RECIPIENTS.")

summary_html = "".join(f"<li>{l.strip()}</li>" for l in args.summary.split("\n") if l.strip())
html = f"""
<div style="font-family:Arial,sans-serif;max-width:620px">
  <h2 style="margin-bottom:4px">Jope Customer Care · {args.month}</h2>
  <p>The monthly Customer Care dashboard is live:</p>
  <p><a href="{args.url}" style="background:#0F6E56;color:#fff;padding:10px 18px;
     border-radius:8px;text-decoration:none;display:inline-block">Open the dashboard</a></p>
  <ul>{summary_html}</ul>
  <p style="color:#777;font-size:13px">Generated automatically. Questions for the team are inside the dashboard.</p>
</div>"""

msg = MIMEMultipart("alternative")
msg["Subject"] = f"Jope CC Dashboard · {args.month}"
msg["From"] = user
msg["To"] = to
msg.attach(MIMEText(html, "html"))

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
    s.login(user, pwd)
    s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
print(f"Email envoye a : {to}")
