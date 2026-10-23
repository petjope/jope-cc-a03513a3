#!/usr/bin/env python3
"""Pre-controle local du rafraichissement quotidien (regle du 23 octobre 2026).

Lance par scripts/run-monthly.bat chaque matin quand le mois est deja livre.
Il lit data/pending-{M}.json, ecrit par la generation du 5, et dit s il vaut
la peine de reveiller l agent (/cc-refresh) pour aller sonder les trackers.
Il ne touche a aucun connecteur : c est l agent qui sonde Drive, Windsor et
les Sheets, et seulement quand ce script repond 0.

Usage : python scripts/check_refresh.py 2026-09
Sortie : 0 = lancer /cc-refresh (la raison est imprimee)
         1 = rien a faire aujourd hui (la raison est imprimee)
         2 = usage

Regles :
- pas de fichier d etat, ou aucune source "pending" : rien a faire ;
- le fichier manuel attendu existe sur disque : lancer, sans attendre ;
- deja sonde aujourd hui (last_check) : rien a faire ;
- plus de MAX_AGE_DAYS apres la publication : on arrete de sonder, le mois
  suivant est deja en route et la page ne sera plus republiee.
"""
import datetime, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_AGE_DAYS = 45


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r'\d{4}-\d{2}', sys.argv[1]):
        print(__doc__)
        return 2
    month = sys.argv[1]
    today = datetime.date.today()
    state_p = os.path.join(ROOT, 'data', 'pending-%s.json' % month)
    if not os.path.exists(state_p):
        print('refresh %s : pas de fichier d etat, rien a faire' % month)
        return 1
    try:
        state = json.load(open(state_p, encoding='utf-8'))
    except ValueError as e:
        print('refresh %s : fichier d etat illisible (%s), rien a faire' % (month, e))
        return 1
    sources = state.get('sources') or {}
    pending = sorted(k for k, v in sources.items() if (v or {}).get('status') == 'pending')
    if not pending:
        print('refresh %s : aucune source en attente, rien a faire' % month)
        return 1
    published = state.get('published')
    try:
        age = (today - datetime.date.fromisoformat(published)).days
    except (TypeError, ValueError):
        age = 0
    if age > MAX_AGE_DAYS:
        print('refresh %s : publie il y a %d jours, on ne sonde plus (%s encore en attente)' % (month, age, ', '.join(pending)))
        return 1
    manual = os.path.join(ROOT, 'data', 'manual-%s.md' % month)
    if 'manual' in pending and os.path.exists(manual):
        print('refresh %s : data/manual-%s.md est arrive, lancer /cc-refresh' % (month, month))
        return 0
    if state.get('last_check') == today.isoformat():
        print('refresh %s : trackers deja sondes aujourd hui, en attente de %s' % (month, ', '.join(pending)))
        return 1
    print('refresh %s : en attente de %s, sonder les trackers' % (month, ', '.join(pending)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
