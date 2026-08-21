#!/usr/bin/env python3
"""Commandes Shopify par mois (juin 2026 -> mois precedent inclus).
Prerequis : variables d'environnement SHOPIFY_STORE (ex: petjope.myshopify.com)
et SHOPIFY_ADMIN_TOKEN (Admin API access token, scope read_orders).
Sortie : JSON {"2026-06": 7665, "2026-07": 8385, ...}
"""
import os, sys, json, datetime as dt
import urllib.request

STORE = os.environ.get("SHOPIFY_STORE")
TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN")
if not STORE or not TOKEN:
    sys.exit("Definir SHOPIFY_STORE et SHOPIFY_ADMIN_TOKEN (voir README-SETUP.md, etape 4).")

URL = f"https://{STORE}/admin/api/2025-07/graphql.json"

def orders_count(start, end):
    q = {"query": f'{{ ordersCount(query: "created_at:>={start} created_at:<{end}", limit: 100000) {{ count }} }}'}
    req = urllib.request.Request(URL, data=json.dumps(q).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": TOKEN})
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read())
    return data["data"]["ordersCount"]["count"]

def month_starts():
    first = dt.date(2026, 6, 1)
    today = dt.date.today()
    cur_month_start = today.replace(day=1)
    d = first
    while d < cur_month_start:
        nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield d, min(nxt, cur_month_start)
        d = nxt

result = {}
for start, end in month_starts():
    result[start.strftime("%Y-%m")] = orders_count(start.isoformat(), end.isoformat())

print(json.dumps(result, indent=2))
