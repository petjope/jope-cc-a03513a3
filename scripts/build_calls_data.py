#!/usr/bin/env python3
"""Agrege les exports FreedomVoice pour la section 06 Calls.

Entrees : les deux exports agreges deposes par Zach dans le dossier Drive
"Call Metrics 2026 (from FreedomVoice)". Chacun est accepte soit en .xls brut,
soit en dump base64 (ce que renvoie le connecteur Google Drive).

  - generalStats.xls          : une ligne par jour, volume et abandons
  - userStatisticsReport.xls  : une ligne par agent, inbound / outbound / talk

Le callDetailsReport.xls n'est pas necessaire : le nombre d'appels tombes en
messagerie se deduit des deux fichiers agreges (total - abandonnes - inbound
decroches par un agent).

Les durees FreedomVoice sont en minutes decimales.

Usage :
  python scripts/build_calls_data.py <generalStats> <userStatisticsReport> [--month YYYY-MM]
"""
import base64, json, os, sys, xlrd

# Les moyennes hold / talk sont ponderees par le volume total du jour. Cette
# ponderation reproduit exactement les 0:25 et 4:35 du fichier de Zach ; une
# moyenne simple sur les jours servis donnerait 0:27 et 6:38.
WEIGHT = 'intTotalCalls'


def read_sheet(path):
    """Lit un .xls BIFF, que le fichier soit binaire ou encode en base64."""
    with open(path, 'rb') as f:
        raw = f.read()
    if not raw.startswith((b'\x09\x08', b'\xd0\xcf')):
        raw = base64.b64decode(raw)
    # logfile=stderr : ces exports n ont pas de record CODEPAGE et xlrd ecrit
    # son avertissement sur stdout par defaut, ce qui casserait le JSON.
    book = xlrd.open_workbook(file_contents=raw, logfile=sys.stderr)
    sheet = book.sheet_by_index(0)
    head = [sheet.cell_value(0, c) for c in range(sheet.ncols)]
    rows = []
    for r in range(1, sheet.nrows):
        rows.append(dict(zip(head, [sheet.cell_value(r, c) for c in range(sheet.ncols)])))
    return rows


def mmss(minutes):
    return '%d:%02d' % (int(minutes), round((minutes - int(minutes)) * 60))


def build(general_path, user_path, month=None):
    # ------------------------------------------------------------ inbound / jour
    days = [r for r in read_sheet(general_path) if r['strTheDate'] != 'Totals']
    total = sum(r['intTotalCalls'] for r in days)
    abandoned = sum(r['intAbandonedCalls'] for r in days)
    if total == 0:
        raise SystemExit('generalStats ne contient aucun appel : verifier la plage de dates de l export.')

    def weighted(col):
        den = sum(r[WEIGHT] for r in days)
        return sum(r[col] * r[WEIGHT] for r in days) / den if den else 0.0

    peak = max(days, key=lambda r: r['intTotalCalls'])
    worst = max(days, key=lambda r: r['dblAbandonedRate'])

    # ---------------------------------------------------------------- par agent
    agents = [r for r in read_sheet(user_path) if r['HandledCalls'] > 0]
    inbound = sum(r['InboundCalls'] for r in agents)
    outbound = sum(r['OutboundCalls'] for r in agents)
    handled = sum(r['HandledCalls'] for r in agents)

    # Controle d integrite : FreedomVoice pose HandledCalls = Inbound + Outbound.
    broken = [r['UserDisplayName'].strip() for r in agents
              if r['HandledCalls'] != r['InboundCalls'] + r['OutboundCalls']]

    # Les appels ni abandonnes ni decroches par un agent sont partis en
    # messagerie ou sur le standard automatique.
    voicemail = total - abandoned - inbound

    return {
        'month': month,
        'period': {'start': days[0]['strTheDate'], 'end': days[-1]['strTheDate'], 'days': len(days)},
        'inbound': {
            'total_calls': int(total),
            'abandoned_calls': int(abandoned),
            'abandon_rate_pct': round(100 * abandoned / total, 1),
            'answered_by_agent': int(inbound),
            'to_voicemail': int(voicemail),
            'reached_human_pct': round(100 * inbound / total, 1),
            'avg_hold_min': round(weighted('dblHoldTimeAvg'), 2),
            'avg_hold_mmss': mmss(weighted('dblHoldTimeAvg')),
            'avg_talk_min': round(weighted('dblTalkTimeAvg'), 2),
            'avg_talk_mmss': mmss(weighted('dblTalkTimeAvg')),
            'days_with_calls': sum(1 for r in days if r['intTotalCalls'] > 0),
            'peak_day': {'date': peak['strTheDate'], 'calls': int(peak['intTotalCalls'])},
            'worst_abandon_day': {'date': worst['strTheDate'],
                                  'rate_pct': round(worst['dblAbandonedRate'], 1)},
        },
        'agents': {
            'active': len(agents),
            'inbound_calls': int(inbound),
            'outbound_calls': int(outbound),
            'handled_calls': int(handled),
            'total_talk_min': round(sum(r['TotalTalkTime'] for r in agents), 1),
            'integrity_ok': not broken,
            'integrity_failed_for': broken,
            'rows': [{
                'agent': r['UserDisplayName'].strip(),
                'inbound': int(r['InboundCalls']),
                'outbound': int(r['OutboundCalls']),
                'handled': int(r['HandledCalls']),
                'talk_min': round(r['TotalTalkTime'], 1),
                'avg_inbound_talk_min': round(r['InboundTalkTimeAverage'], 2),
            } for r in sorted(agents, key=lambda r: -r['HandledCalls'])],
        },
        'daily': [{
            'date': r['strTheDate'],
            'calls': int(r['intTotalCalls']),
            'abandoned': int(r['intAbandonedCalls']),
            'abandon_rate_pct': round(r['dblAbandonedRate'], 1),
        } for r in days],
    }


def update_history(path, month, res):
    """Ajoute le mois au fichier d historique et renvoie la fenetre glissante.

    Motif (demande de Jeremy, 4 septembre 2026) : la section 06 doit se lire dans
    le temps comme les autres. Les exports FreedomVoice etant ecrases chaque mois
    dans Drive, le seul moyen de garder une serie est de conserver nous-memes
    l agregat au moment ou on le lit. Le fichier ne contient que des totaux
    mensuels, aucun nom d agent et aucun numero, donc il peut vivre dans le depot.
    """
    hist = {}
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            hist = json.load(fh).get('months', {})
    inb = res['inbound']
    hist[month] = {
        'total_calls': inb['total_calls'],
        'abandoned': inb['abandoned_calls'],
        'answered_by_agent': inb['answered_by_agent'],
        'to_voicemail': inb['to_voicemail'],
        'abandon_rate_pct': inb['abandon_rate_pct'],
        'reached_human_pct': inb['reached_human_pct'],
        'avg_hold_mmss': inb['avg_hold_mmss'],
        'avg_talk_mmss': inb['avg_talk_mmss'],
        'outbound_calls': res['agents']['outbound_calls'],
        'period': res['period']['start'] + ' - ' + res['period']['end'],
    }
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'months': dict(sorted(hist.items()))}, fh, indent=2)
        fh.write(chr(10))
    # fenetre glissante : 6 mois au plus, du plus ancien au plus recent
    keys = sorted(hist)[-6:]
    return [dict(hist[k], month=k) for k in keys]


if __name__ == '__main__':
    argv = sys.argv[1:]
    month = None
    history = None
    if '--month' in argv:
        i = argv.index('--month')
        month = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]
    if '--history' in argv:
        i = argv.index('--history')
        history = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith('--')]
    if len(args) != 2:
        raise SystemExit(__doc__)
    res = build(args[0], args[1], month)
    if history and month:
        res['history'] = update_history(history, month, res)
    print(json.dumps(res, indent=2))
