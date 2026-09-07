#!/usr/bin/env python3
"""Agrege les donnees adverse events / quality complaints pour la section 07.

Entrees :
  - les deux dumps Google Drive des Sheets JAERS et QCRS (JSON {fileContent})
  - les unites vendues Shopify (consommables, hors leaflets et goodies)
  - les unites Amazon US (table agregee par jour)
  - les comptages par tag Gorgias

Usage :
  python scripts/build_safety_data.py <dump_JAERS.json> <dump_QCRS.json>
"""
import json, re, sys, collections

# ---------------------------------------------------------------- denominateurs
# Shopify DTC, consommables uniquement : chews 60/15/2, GB-01, WS-01, No-Guilt.
# Exclus : leaflets, bandanas, cartes cadeaux, e-books, produits de test.
SHOPIFY_CONSUMABLE = {
    '2026-01': 13069, '2026-02': 14413, '2026-03': 17149, '2026-04': 15088,
    '2026-05': 19527, '2026-06': 19436, '2026-07': 21449, '2026-08': 21386,
}
# Amazon US, unites commandees (sales_and_traffic_report_by_date)
AMAZON_DAILY = {
 '2026-01': [135,107,107,150,126,111,130,164,106,128,169,107,129,115,156,123,138,143,143,151,140,144,127,112,134,157,135,151,139,146,135],
 '2026-02': [179,125,132,129,103,107,114,156,161,157,155,142,245,139,172,227,160,147,161,130,140,207,158,171,148,142,99,156],
 '2026-03': [165,197,141,158,141,133,162,185,169,180,161,150,144,161,208,155,141,153,143,149,129,171,151,161,175,151,185,179,183,195,163],
 '2026-04': [147,135,135,164,172,166,156,186,169,135,156,214,186,214,182,168,137,174,183,176,168,182,156,156,145,178,200,174,128,151],
 '2026-05': [142,159,177,164,191,175,148,144,163,182,188,169,215,179,155,150,193,188,157,163,160,148,160,148,183,182,168,178,151,163,186],
 '2026-06': [215,165,209,174,152,171,182,188,205,214,187,141,159,239,223,205,228,194,178,184,216,196,780,350,196,164,154,219,194,204],
 '2026-07': [156,163,171,190,217,172,195,196,198,170,192,201,219,217,195,201,200,173,208,214,199,186,212,173,193,250,268,198,186,201,208],
 '2026-08': [192,240,272,217,236,227,183,190,228,252,255,222,259,198,202,232,262,201,247,200,185,203,248,243,235,224,224,210,230,257,239],
}
# Comptages par tag Gorgias (source de verite du volume)
# 2026-07 corrige de 22 a 23 pour le QC : la requete du 04/09/2026 renvoie 23,
# ce qui est aussi le chiffre publie dans la page de juillet.
GORGIAS_TAG = {
 '2026-01': (42, 4), '2026-02': (28, 3), '2026-03': (43, 12), '2026-04': (28, 12),
 '2026-05': (41, 14), '2026-06': (47, 26), '2026-07': (51, 23), '2026-08': (74, 19),
}
# Comptages AE du resume de Jamie (seule source pour janvier a avril)
JAMIE_AE = {'2026-01': 41, '2026-02': 23, '2026-03': 35, '2026-04': 26, '2026-05': 37, '2026-06': 34}

# Valeurs de registre figees, publiees le 27/08/2026 et non recalculees.
# Motif : au 04/09/2026 le log detaille JAERS ne contient plus que 5 lignes de
# mai contre 21 lors du pull du 27/08. Les lignes ont ete retirees ou archivees
# hors du log cote Google Sheet. Recalculer ferait passer la barre de mai de 21
# a 5 sans qu aucun cas ait disparu dans la realite. Mai reste donc a 21 et
# l ecart est signale en note. A revoir avec Jamie.
AE_REGISTER_PINNED = {'2026-05': 21}

MONTHS = ['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06','2026-07','2026-08']
LABELS = {'2026-01':'Jan','2026-02':'Feb','2026-03':'Mar','2026-04':'Apr','2026-05':'May','2026-06':'Jun','2026-07':'Jul','2026-08':'Aug'}

# ---------------------------------------------------------------- familles QC
QC_FAMILIES = [
    # "crumb" et non "crumbl" : attrape crumbs, crumbly, crumbled. "disintegrat" ajoute
    # apres relecture manuelle des lignes non classees du 21/08/2026.
    ('Crumbling / broken',  r'crumb|crush|powder|dust|broke|break|fell apart|falling apart|smash|in pieces|to pieces|disintegrat|half bag'),
    ('Off smell',           r'smell|odor|odour|ferment|rancid|stale'),
    ('Colour / mould',      r'colou?r|discolo|yellow|mold|mould|spots|way dark|darker'),
    ('Texture',             r'too hard|too soft|melt|sticky|stuck together|greasy|so dry|very dry|dried out'),
    ('Batch inconsistency', r'different from|completely different|not look or feel|changed the formula|not the same as'),
    ('Refusal to eat',      r"won'?t eat|will not eat|refuse|won'?t touch|not eat them|stopped eating"),
    ('Packaging / seal',    r'seal|zipper|torn|leak|resealab|bag was open|package.{0,12}damag'),
    # "consistently short" / "short 1 or 2 chews" ajoutes apres relecture de la
    # ligne non classee d aout 2026 : un sachet incomplet est un compte manquant,
    # pas un defaut de texture. Mot-cle plutot que classement a la main, pour que
    # le mois suivant le retrouve tout seul.
    ('Missing / wrong',     r'missing|wrong (item|product)|did ?n.?t receive|did not receive|only received|consistently short|short \d'),
    ('Pending information', r'waiting on customer|awaiting (customer|response)'),
]

def cells(line):
    return [x.strip() for x in line.strip('|').split('|')]

def month_of(s):
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s or '')
    return f'{m.group(3)}-{int(m.group(1)):02d}' if m else None

def load_rows(path, min_cols):
    content = json.load(open(path, encoding='utf-8'))['fileContent']
    out = []
    for line in content.split('\n'):
        if not line.startswith('|'):
            continue
        c = cells(line)
        if len(c) >= min_cols and month_of(c[1]):
            out.append(c)
    return out

def norm_category(raw):
    """Normalise les variantes d'ecriture des categories AE."""
    s = re.sub(r'\s+', '', (raw or '')).lower()
    if not s.startswith('adverseevent'):
        return None                      # ligne non-AE : ignoree (decision du 21/08)
    if 'stomach' in s or 'vomit' in s: return 'GI: vomiting / upset'
    if 'diarrhea' in s:                return 'GI: diarrhea'
    if 'skin' in s or 'allergic' in s: return 'Skin / allergic'
    if 'lameness' in s:                return 'Lameness'
    if 'seizure' in s:                 return 'Seizure'
    if 'other' in s:                   return 'Other'
    return 'Other'

def norm_tier(raw):
    m = re.search(r'Tier\s*([123])', raw or '')
    return f'Tier {m.group(1)}' if m else 'Unknown'

def norm_product(text):
    t = (text or '').upper().replace(' ', '')
    if re.search(r'HJD?60|HJ60', t):  return 'HJD60'
    if re.search(r'GB-?0?1', t):      return 'GB-01'
    if re.search(r'WS-?0?1', t):      return 'WS-01'
    if 'SKIN' in t:                   return 'Skin'
    if 'CALM' in t:                   return 'Calm'
    return None

def is_amazon(row):
    """Canal Amazon : la note (col G) ou la colonne "Amazon FIle" (col M) le nomme."""
    notes = row[6] if len(row) > 6 else ''
    azfile = row[12] if len(row) > 12 else ''
    return 'amazon' in f'{notes} {azfile}'.lower()

def qc_family(reason, notes):
    t0 = (notes or '').strip()
    if not t0 or t0.lower() == 'notes':
        return 'Empty row'
    r = (reason or '').lower()
    if 'packaging' in r or 'bags' in r:            return 'Packaging / seal'
    if 'shipping' in r or 'transit' in r:          return 'Shipping damage'
    t = (notes or '').lower()
    for name, pattern in QC_FAMILIES:
        if re.search(pattern, t):
            return name
    return 'Unclassified'

def truncation_guard(name, rows, months):
    """Le connecteur Drive tronque un Sheet volumineux sans le dire : il ne
    renvoie que les lignes les plus recentes, et la coupure avance a mesure que
    l onglet grossit. Constate sur JAERS le 7 septembre 2026, ou mai est passe de
    21 lignes le 27 aout a 5 le 4 septembre puis 0, alors que le registre en
    portait 37. Un mois tronque se lit comme un mois calme : il faut donc refuser
    de le rapporter plutot que de publier un chiffre trop bas.

    Regle : le mois le plus ancien reellement lisible est celui qui suit la plus
    vieille ligne rendue, puisque cette ligne peut elle-meme etre le reste d un
    mois coupe en deux. Tout mois de la fenetre situe avant est declare
    inaccessible. Si le mois rapporte en fait partie, on s arrete : la page
    afficherait un chiffre faux sans que personne le voie.
    """
    seen = sorted(m for m in (month_of(r[1]) for r in rows) if m)
    if not seen:
        raise SystemExit(f'{name} : aucune ligne datee lue, dump vide ou illisible.')
    oldest = seen[0]
    unreachable = [m for m in months if m <= oldest]
    if not unreachable:
        return []
    print(f'!!! TRONCATURE {name} : la plus vieille ligne rendue est datee de {oldest}.')
    print(f'    Mois de la fenetre qui ne peuvent pas etre comptes : {", ".join(unreachable)}.')
    print('    Le connecteur Drive ne rend que la fin du Sheet. Ne pas publier ces')
    print('    mois depuis ce dump : les demander a Jamie ou les laisser en pending.')
    if months[-1] in unreachable:
        raise SystemExit(f'{name} : le mois rapporte ({months[-1]}) est dans la zone tronquee, arret.')
    return unreachable


def main():
    ae_rows = load_rows(sys.argv[1], 13)
    qc_rows = load_rows(sys.argv[2], 7)
    ae_unreachable = truncation_guard('JAERS', ae_rows, MONTHS)
    qc_unreachable = truncation_guard('QCRS', qc_rows, MONTHS)
    if ae_unreachable or qc_unreachable:
        print()

    ae_by_month = collections.Counter()
    ae_cat = collections.defaultdict(collections.Counter)
    ae_tier = collections.defaultdict(collections.Counter)
    ae_prod = collections.defaultdict(collections.Counter)
    ae_lot = collections.Counter()
    ae_skipped = collections.Counter()
    for r in ae_rows:
        m = month_of(r[1])
        if m not in MONTHS:
            continue
        cat = norm_category(r[5])
        if cat is None:
            ae_skipped[m] += 1
            continue
        ae_by_month[m] += 1
        ae_cat[m][cat] += 1
        ae_tier[m][norm_tier(r[6])] += 1
        p = norm_product(r[11]) or norm_product(r[7])
        ae_prod[m][p or 'unknown'] += 1
        lot = re.sub(r'\D', '', r[10] or '')
        if len(lot) >= 6:
            ae_lot[lot] += 1

    qc_by_month = collections.Counter()
    qc_fam = collections.defaultdict(collections.Counter)
    qc_prod = collections.defaultdict(collections.Counter)
    qc_chan = collections.defaultdict(collections.Counter)
    qc_chan_fam = collections.defaultdict(collections.Counter)
    unclassified = []
    seen = set()
    for r in qc_rows:
        m = month_of(r[1])
        if m not in MONTHS:
            continue
        key = (r[3], r[1], (r[6] or '')[:60])       # dedoublonnage
        if key in seen:
            continue
        seen.add(key)
        fam = qc_family(r[5], r[6])
        if fam == 'Empty row':          # ligne sans note : ne compte pas comme plainte
            qc_fam[m][fam] += 1
            continue
        qc_by_month[m] += 1
        qc_fam[m][fam] += 1
        if fam == 'Unclassified':
            unclassified.append((m, (r[6] or '')[:150]))
        # Produit : la reference CRN (colonne H) porte le prefixe produit et est
        # remplie sur ~92% des lignes ; le texte des notes ne sert qu en secours.
        qc_prod[m][norm_product(r[7] if len(r) > 7 else '')
                   or norm_product(r[6]) or 'unknown'] += 1
        # Canal : le registre est la seule source qui le porte. Une plainte compte
        # comme Amazon quand la note ou la colonne "Amazon FIle" le nomme.
        chan = 'amazon' if is_amazon(r) else 'dtc'
        qc_chan[m][chan] += 1
        qc_chan_fam[(m, chan)][fam] += 1

    print('=== DENOMINATEURS (unites consommables) ===')
    print('mois | Shopify DTC | Amazon US | total')
    units = {}
    for m in MONTHS:
        az = sum(AMAZON_DAILY[m])
        units[m] = SHOPIFY_CONSUMABLE[m] + az
        print(f'{LABELS[m]:4} | {SHOPIFY_CONSUMABLE[m]:11} | {az:9} | {units[m]:6}')

    def ae_register(m):
        if m in AE_REGISTER_PINNED:
            return AE_REGISTER_PINNED[m]
        return ae_by_month[m] if m >= '2026-05' else JAMIE_AE.get(m, 0)

    print()
    print('=== ADVERSE EVENTS ===')
    # Le taux publie est registre / unites DTC SEULES (regle du denominateur par
    # canal, 25/08/2026 : 2 cas sur 115 de mai a juillet venaient d Amazon alors
    # qu Amazon pese 22% des unites). La colonne tag/DTC ne sert qu a comparer :
    # elle porte la serie jusqu a juin, le registre la porte a partir de juillet.
    # Ne jamais comparer une valeur registre a une valeur tag (rupture de methode).
    print('mois | tag Gorgias | registre | registre/1000 DTC | tag/1000 DTC | Tier3')
    for m in MONTHS:
        tag = GORGIAS_TAG[m][0]
        reg = ae_register(m)
        dtc = SHOPIFY_CONSUMABLE[m]
        t3 = ae_tier[m].get('Tier 3', 0)
        print(f'{LABELS[m]:4} | {tag:11} | {reg:8} | {1000*reg/dtc:17.2f} |'
              f' {1000*tag/dtc:12.2f} | {t3}')

    print()
    print('=== QUALITY COMPLAINTS ===')
    # Seuils poses le 28/08/2026 (decision Jeremy, demande de Christine) :
    #   - taux QC toutes plaintes, tous canaux : alerte 0.75, cible 0.35 (KPI d en tete)
    #   - crumbling seul, sous-ensemble : alerte 0.50, cible 0.25 (carte de la section 07)
    # Les deux paires sont calibrees par la meme methode, moyenne + 1/2 ecart-type de
    # leur propre serie, et declenchent les memes trois mois : mars, avril et juin.
    QC_ALERT, QC_TARGET = 0.75, 0.35
    CR_ALERT, CR_TARGET = 0.50, 0.25
    def flag(rate, alert, target):
        return 'ALERTE' if rate > alert else ('  ok  ' if rate > target else ' cible')
    print('mois | tag Gorgias | registre | QC /1000 (tous canaux) | seuil | crumbling | cr /1000 | seuil')
    for m in MONTHS:
        tag = GORGIAS_TAG[m][1]
        reg = qc_by_month[m]
        cr = qc_fam[m].get('Crumbling / broken', 0)
        qc_rate = 1000*reg/units[m]
        cr_rate = 1000*cr/units[m]
        print(f'{LABELS[m]:4} | {tag:11} | {reg:8} | {qc_rate:22.2f} | {flag(qc_rate, QC_ALERT, QC_TARGET)} |'
              f' {cr:9} | {cr_rate:8.2f} | {flag(cr_rate, CR_ALERT, CR_TARGET)}')

    print()
    print('=== QC par canal (regle du denominateur par canal) ===')
    print('mois | cas DTC | cas AZ | u. DTC | u. AZ | DTC/1000 | AZ/1000 | total/1000')
    for m in MONTHS:
        dtc_n, az_n = qc_chan[m].get('dtc', 0), qc_chan[m].get('amazon', 0)
        dtc_u, az_u = SHOPIFY_CONSUMABLE[m], sum(AMAZON_DAILY[m])
        print(f'{LABELS[m]:4} | {dtc_n:7} | {az_n:6} | {dtc_u:6} | {az_u:5} |'
              f' {1000*dtc_n/dtc_u:8.2f} | {1000*az_n/az_u:7.2f} |'
              f' {1000*(dtc_n+az_n)/units[m]:10.2f}')
    print('moyennes de l annee   DTC : %.2f   Amazon : %.2f' % (
        1000*sum(qc_chan[m].get('dtc', 0) for m in MONTHS)/sum(SHOPIFY_CONSUMABLE[m] for m in MONTHS),
        1000*sum(qc_chan[m].get('amazon', 0) for m in MONTHS)/sum(sum(AMAZON_DAILY[m]) for m in MONTHS)))
    print('crumbling par canal, annee   DTC : %.2f   Amazon : %.2f' % (
        1000*sum(qc_chan_fam[(m, 'dtc')].get('Crumbling / broken', 0) for m in MONTHS)/sum(SHOPIFY_CONSUMABLE[m] for m in MONTHS),
        1000*sum(qc_chan_fam[(m, 'amazon')].get('Crumbling / broken', 0) for m in MONTHS)/sum(sum(AMAZON_DAILY[m]) for m in MONTHS)))

    print()
    print('=== AE par categorie (mai a juillet, detail disponible) ===')
    cats = ['GI: vomiting / upset','GI: diarrhea','Skin / allergic','Other','Lameness','Seizure']
    print('categorie'.ljust(22), ' '.join(LABELS[m].rjust(5) for m in MONTHS[4:]))
    for c in cats:
        print(c.ljust(22), ' '.join(str(ae_cat[m].get(c,0)).rjust(5) for m in MONTHS[4:]))

    print()
    print('=== AE par Tier (mai a juillet) ===')
    for t in ['Tier 1','Tier 2','Tier 3','Unknown']:
        print(t.ljust(22), ' '.join(str(ae_tier[m].get(t,0)).rjust(5) for m in MONTHS[4:]))

    print()
    print('=== QC par famille (janvier a juillet) ===')
    fams = [f[0] for f in QC_FAMILIES] + ['Shipping damage','Unclassified','Empty row']
    print('famille'.ljust(22), ' '.join(LABELS[m].rjust(4) for m in MONTHS), '  total')
    for f in fams:
        vals = [qc_fam[m].get(f,0) for m in MONTHS]
        print(f.ljust(22), ' '.join(str(v).rjust(4) for v in vals), str(sum(vals)).rjust(7))

    last = MONTHS[-1]
    print()
    print(f'=== produit ({LABELS[last]}) ===')
    print('AE :', dict(ae_prod[last]))
    print('QC :', dict(qc_prod[last]))
    print('QC canal :', dict(qc_chan[last]))
    print()
    print(f'=== lots avec le plus d AE (detail disponible, mai a {LABELS[last]}) ===')
    for lot, n in ae_lot.most_common(6):
        print(f'   lot {lot} : {n} AE, soit {1000*n/2700:.1f} pour 1000 unites du lot')
    print()
    print('=== lignes AE non-AE ignorees ===', dict(ae_skipped))
    print('=== QC non classees a lire a la main :', len(unclassified))
    for m, t in unclassified:
        print('   ', m, '|', t)

main()
