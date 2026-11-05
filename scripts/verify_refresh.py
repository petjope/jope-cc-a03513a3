#!/usr/bin/env python3
"""Verification prealable d un rafraichissement de page (regle du 23 octobre 2026).

Un rafraichissement reprend la page du mois courant, src/{M}.html, pour y
mettre une source arrivee apres la livraison du 5 : export d appels, fichier
manuel, unites Amazon, registres relus, Return Tracker relu. Avant de publier,
ce script compare la page a son instantane pris avant modification et refuse
tout changement hors des cartes que la source arrivee a le droit de toucher.
Les chiffres Gorgias et Shopify sont geles a la lecture du 5 : un
rafraichissement ne les bouge jamais.

Usage :
  python scripts/verify_refresh.py 2026-09
      compare src/2026-09.html a src/_prev-2026-09.html selon data/pending-2026-09.json,
      ecrit data/refresh-2026-09.md (le rapport, repris dans l email) et sort 1 si
      une regle est violee.
  python scripts/verify_refresh.py 2026-09 --post
      apres publication : verifie qu aucun mot en clair du dashboard ni aucun
      jeton {{B}} ne subsiste dans docs/.

Codes de sortie : 0 = publiable, 1 = bloque (ne pas publier), 2 = usage.
"""
import datetime, html, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cartes qu une source arrivee a le droit de modifier. 'exec' = KPIs et alertes
# du resume executif, toujours autorises car ils resument les sections.
# 'meta' = en-tete, pied de page, bandeau Data health : toujours autorises.
ALLOWED = {
    'calls':          {'06', '03'},         # section 06 + placeholder "Abandoned calls" de la 03
    'manual':         {'05', '02'},         # per-agent + carte "Shopify chat agent"
    'amazon':         {'07'},
    'registers':      {'07'},
    'returns':        {'04'},
    'outbound_sheet': {'06'},
    # Ajoute le 5 novembre 2026. Le connecteur Gorgias demandait une
    # re-authorisation le matin de la livraison d octobre : aucune des requetes
    # A a F n a pu partir et les sections 01 a 05 sont parties entierement en
    # "pending". Cette source n existe que pour ce cas, une lecture qui n a
    # jamais eu lieu le 5, jamais pour relire des chiffres deja publies.
    'gorgias':        {'01', '02', '03', '04', '05'},
}
ALWAYS = {'exec', 'meta'}

# Valeurs geles : KPIs executifs issus de Gorgias et Shopify. Un rafraichissement
# ne peut pas les faire bouger, quelle que soit la source arrivee.
FROZEN_KPIS = ['Contact rate', 'Tickets replied', 'Jay solo share', 'PC conversion']

BLOCK_RE = re.compile(r'<header>|<footer>|<div class="kpis|<div class="card|<div class="alerts"|<div class="datahealth"|<!-- ====+ [A-Z ]')
SECTION_RE = re.compile(r'<span class="tag">(\d\d)</span>')
NUM_RE = re.compile(r'(?<![\w.])[+\-−]?\d[\d,]*(?:\.\d+)?%?')
MONTHS = 'January|February|March|April|May|June|July|August|September|October|November|December'
DATE_RE = re.compile(r'(?:%s) \d{1,2}(?:, \d{4})?|\d{1,2} (?:%s)|\d{4}-\d{2}-\d{2}' % (MONTHS, MONTHS))


def text_of(fragment):
    t = re.sub(r'<script.*?</script>', ' ', fragment, flags=re.S)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = html.unescape(t)
    return re.sub(r'\s+', ' ', t).strip()


def blocks(doc):
    """Decoupe la page en blocs (section, genre, titre) -> texte normalise."""
    body = doc.split('<script>')[0]
    starts = [m.start() for m in BLOCK_RE.finditer(body)] + [len(body)]
    out = []
    counts = {}
    for i in range(len(starts) - 1):
        frag = body[starts[i]:starts[i + 1]]
        head = frag[:40]
        if head.startswith('<!--'):
            continue
        before = body[:starts[i]]
        tags = SECTION_RE.findall(before)
        if head.startswith('<header>') or head.startswith('<footer>') or head.startswith('<div class="datahealth"'):
            section = 'meta'
        elif not tags:
            section = 'exec'
        else:
            section = tags[-1]
        kind = ('header' if head.startswith('<header>') else 'footer' if head.startswith('<footer>')
                else 'kpis' if head.startswith('<div class="kpis') else 'card' if head.startswith('<div class="card')
                else 'alerts' if head.startswith('<div class="alerts') else 'datahealth')
        m = re.search(r'<h3>(.*?)</h3>|<div class="bignum">(.*?)</div>', frag, flags=re.S)
        title = text_of(m.group(1) or m.group(2)) if m else kind
        key = (section, kind, title)
        counts[key] = counts.get(key, 0) + 1
        out.append(((section, kind, title, counts[key]), text_of(frag), frag))
    return out


def numbers(t):
    return [n for n in NUM_RE.findall(t)]


def numbers_nodate(t):
    """Les chiffres du bloc, dates retirees : ce qui ne doit pas bouger quand on ne
    fait que redater une carte encore en attente ("as of October 23")."""
    return numbers(DATE_RE.sub(' ', t))


def kpi_value(doc, label):
    m = re.search(r'<div class="label">%s</div><div class="value">(.*?)</div>' % re.escape(label), doc)
    return text_of(m.group(1)) if m else None


def check_refresh(month):
    cur_p = os.path.join(ROOT, 'src', '%s.html' % month)
    prev_p = os.path.join(ROOT, 'src', '_prev-%s.html' % month)
    state_p = os.path.join(ROOT, 'data', 'pending-%s.json' % month)
    report_p = os.path.join(ROOT, 'data', 'refresh-%s.md' % month)
    problems, lines = [], []

    for p, what in ((cur_p, 'page du mois'), (prev_p, 'instantane avant modification'), (state_p, 'etat des sources')):
        if not os.path.exists(p):
            print('BLOQUE : %s introuvable (%s)' % (what, os.path.relpath(p, ROOT)))
            return 1
    cur = open(cur_p, encoding='utf-8').read()
    prev = open(prev_p, encoding='utf-8').read()
    state = json.load(open(state_p, encoding='utf-8'))
    refresh = state.get('last_refresh') or {}
    arrived = list(refresh.get('sources') or [])
    date = refresh.get('date') or datetime.date.today().isoformat()
    if not arrived:
        problems.append('last_refresh.sources est vide dans %s : aucune source declaree, rien ne justifie une republication.' % os.path.relpath(state_p, ROOT))
    unknown = [s for s in arrived if s not in ALLOWED]
    if unknown:
        problems.append('Sources inconnues dans last_refresh.sources : %s (connues : %s).' % (unknown, sorted(ALLOWED)))
    allowed = set(ALWAYS)
    for s in arrived:
        allowed |= ALLOWED.get(s, set())
    # Sections des sources encore en attente : la formulation et la date peuvent
    # changer ("as of October 23"), aucun chiffre ne le peut.
    pending_sections = set()
    for s, v in (state.get('sources') or {}).items():
        if (v or {}).get('status') == 'pending':
            pending_sections |= ALLOWED.get(s, set())

    # 1. Blocs modifies, et droit de les modifier
    pb = {k: t for k, t, _ in blocks(prev)}
    cb = {k: t for k, t, _ in blocks(cur)}
    changed = []
    for k in sorted(set(pb) | set(cb), key=lambda k: (k[0], k[1], k[2], k[3])):
        a, b = pb.get(k), cb.get(k)
        if a == b:
            continue
        section, kind, title, idx = k
        if a is None:
            status = 'ajoute'
            removed, added = [], numbers(b)
        elif b is None:
            status = 'supprime'
            removed, added = numbers(a), []
        else:
            status = 'modifie'
            na, nb = numbers(a), numbers(b)
            removed = [n for n in na if n not in nb]
            added = [n for n in nb if n not in na]
        label = '%s / %s%s' % ('section ' + section if section not in ALWAYS else section, title, '' if idx == 1 else ' (%d)' % idx)
        ok = section in allowed
        if not ok and section in pending_sections and a is not None and b is not None                 and numbers_nodate(a) == numbers_nodate(b):
            ok = True
            status = 'redate seulement, chiffres inchanges'
        changed.append((label, status, removed, added, ok))
        if not ok:
            problems.append('Bloc modifie hors perimetre : %s (sources arrivees : %s).' % (label, ', '.join(arrived) or 'aucune'))

    # 2. KPIs geles
    # Un KPI gele est un chiffre DEJA PUBLIE : il ne bouge pas, parce qu il
    # bouge tout seul avec le temps (reponses tardives, conversions) et qu une
    # page dont les niveaux changent a chaque relecture n est plus comparable a
    # elle-meme. Un KPI encore sur "pending" n a jamais ete lu : il n y a aucun
    # niveau a proteger, et le remplir une premiere fois est precisement ce que
    # le rafraichissement sert a faire. C est la seule breche, et elle se ferme
    # d elle-meme des que la valeur est ecrite.
    for lab in FROZEN_KPIS:
        a, b = kpi_value(prev, lab), kpi_value(cur, lab)
        if a == b:
            continue
        if (a or '').strip().lower() == 'pending':
            lines.append('KPI %s renseigne pour la premiere fois : pending -> %s.' % (lab, b))
            continue
        problems.append('KPI gele modifie : %s, %s -> %s. Les chiffres Gorgias et Shopify ne bougent pas lors d un rafraichissement.' % (lab, a, b))

    # 3. Plus de "pending" dans les cartes des sources arrivees
    for s in arrived:
        for k, t, frag in blocks(cur):
            if k[0] not in ALLOWED.get(s, set()) or k[1] not in ('card', 'kpis'):
                continue
            if k[2].startswith('Outbound calls') and s != 'outbound_sheet':
                continue
            if k[2] in ('CSAT', 'Save rate'):
                continue
            if re.search(r'<div class="value">pending</div>|class="todo">Pending', frag):
                problems.append('La source "%s" est declaree arrivee mais le bloc %s / %s affiche encore "pending".' % (s, k[0], k[2]))

    # 4. Trace du rafraichissement sur la page
    dh = next((t for k, t, _ in blocks(cur) if k[1] == 'datahealth'), '')
    if 'refreshed on' not in dh:
        problems.append('Le bandeau Data health ne porte pas de ligne "refreshed on ..." datant le rafraichissement.')
    if 'refreshed' not in text_of(re.search(r'<header>.*?</header>', cur, flags=re.S).group(0) if re.search(r'<header>.*?</header>', cur, flags=re.S) else ''):
        problems.append('L en-tete de la page ne mentionne pas le rafraichissement ("refreshed ...").')

    # 5. Fenetre glissante : jamais avant juin 2026 dans les series CC
    m4 = re.search(r"const M4=\[(.*?)\]", cur)
    if m4 and re.search(r"'(January|February|March|April|May)'", m4.group(1)):
        problems.append('La fenetre M4 contient un mois anterieur a juin 2026.')

    # 6. Jeton de navigation
    if '{{B}}' not in cur:
        problems.append('Aucun jeton {{B}} dans la page : les liens de navigation doivent rester relatifs a docs/ via {{B}}.')

    # Rapport
    lines.append('# Refresh %s, %s' % (month, date))
    lines.append('')
    lines.append('Sources arrived: %s' % (', '.join(arrived) or 'none'))
    still = [k for k, v in (state.get('sources') or {}).items() if v.get('status') == 'pending']
    lines.append('Still pending: %s' % (', '.join(still) or 'none'))
    lines.append('')
    lines.append('## Changed blocks (%d)' % len(changed))
    for label, status, removed, added, ok in changed:
        flag = '' if ok else '  <-- OUT OF SCOPE'
        lines.append('- %s: %s%s' % (label, status, flag))
        if removed or added:
            lines.append('    numbers out: %s' % (', '.join(removed) or '-'))
            lines.append('    numbers in:  %s' % (', '.join(added) or '-'))
    lines.append('')
    lines.append('## Verdict')
    if problems:
        lines.append('BLOCKED, not published:')
        lines += ['- ' + p for p in problems]
    else:
        lines.append('OK, publishable. Frozen KPIs unchanged: %s.' % ', '.join('%s %s' % (l, kpi_value(cur, l)) for l in FROZEN_KPIS))
    open(report_p, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('\nRapport : %s' % os.path.relpath(report_p, ROOT))
    return 1 if problems else 0


def check_post(month):
    """Apres publication : rien en clair dans docs/, aucun jeton {{B}}."""
    src = open(os.path.join(ROOT, 'src', '%s.html' % month), encoding='utf-8').read()
    sentinels = set()
    for m in re.finditer(r'<h3>(.*?)</h3>', src):
        t = text_of(m.group(1))
        if len(t) >= 8:
            sentinels.add(t)
    sentinels |= {'Data health', 'Question for', 'Sources.', 'gaia.tickets', 'Gorgias warehouse'}
    bad = []
    for dirpath, _, files in os.walk(os.path.join(ROOT, 'docs')):
        for f in files:
            if not f.endswith('.html'):
                continue
            p = os.path.join(dirpath, f)
            d = open(p, encoding='utf-8').read()
            hits = [s for s in sentinels if s in d]
            if '{{B}}' in d:
                hits.append('{{B}}')
            if hits:
                bad.append('%s : %s' % (os.path.relpath(p, ROOT), ', '.join(sorted(hits)[:5])))
    if bad:
        print('BLOQUE : du clair ou un jeton subsiste dans docs/ :\n  ' + '\n  '.join(bad))
        return 1
    print('OK : docs/ ne contient ni mot du dashboard en clair ni jeton {{B}} (%d sentinelles testees).' % len(sentinels))
    return 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 1 or not re.fullmatch(r'\d{4}-\d{2}', args[0]):
        print(__doc__)
        return 2
    if '--post' in sys.argv:
        return check_post(args[0])
    return check_refresh(args[0])


if __name__ == '__main__':
    sys.exit(main())
