#!/usr/bin/env python3
"""Publie les pages du dashboard : resout {{B}} puis chiffre vers docs/.

Un meme fichier de src/ part vers deux emplacements de profondeur differente,
docs/index.html et docs/archive/{YYYY-MM}.html. Un chemin relatif ecrit en dur
est donc juste dans l un et casse dans l autre : c etait le cas du lien vers
juillet dans l archive d aout. Les liens de navigation s ecrivent relatifs a
docs/ avec le prefixe {{B}}, remplace ici par '' a la racine et '../' dans
archive/.

Usage :
  CC_PASSPHRASE="..." python scripts/publish.py 2026-08
"""
import os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONTH_NAME = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
              'August', 'September', 'October', 'November', 'December']


def label_of(month):
    y, m = month.split('-')
    return '%s %s' % (MONTH_NAME[int(m) - 1], y)


def encrypt(src, dest, label):
    """Substitue {{B}} selon la profondeur de dest, puis chiffre."""
    rel = os.path.relpath(dest, os.path.join(ROOT, 'docs')).replace('\\', '/')
    base = '../' * rel.count('/')
    html = open(src, encoding='utf-8').read().replace('{{B}}', base)
    tmp = tempfile.NamedTemporaryFile('w', suffix='.html', encoding='utf-8',
                                      delete=False, newline='')
    tmp.write(html)
    tmp.close()
    try:
        subprocess.run(['node', os.path.join(ROOT, 'scripts', 'encrypt_page.js'),
                        tmp.name, dest, label], check=True, shell=(os.name == 'nt'))
    finally:
        os.unlink(tmp.name)
    print('  %-34s <- %s' % (rel, os.path.basename(src)))


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage : python scripts/publish.py {YYYY-MM}')
    month = sys.argv[1]
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        raise SystemExit('Mois attendu au format YYYY-MM.')
    if not os.environ.get('CC_PASSPHRASE'):
        raise SystemExit('CC_PASSPHRASE absente.')

    src = lambda n: os.path.join(ROOT, 'src', n)
    docs = lambda *p: os.path.join(ROOT, 'docs', *p)

    cur = src('%s.html' % month)
    if not os.path.exists(cur):
        raise SystemExit('%s introuvable.' % cur)

    print('Publication de %s' % month)
    encrypt(cur, docs('index.html'), label_of(month))
    encrypt(cur, docs('archive', '%s.html' % month), label_of(month))

    # Les archives plus anciennes sont republiees : leur barre de navigation
    # doit lister le nouveau mois et la page questions.
    for name in sorted(os.listdir(os.path.join(ROOT, 'src'))):
        m = re.fullmatch(r'(\d{4}-\d{2})\.html', name)
        if m and m.group(1) != month:
            encrypt(src(name), docs('archive', name), label_of(m.group(1)))

    if os.path.exists(src('questions.html')):
        encrypt(src('questions.html'), docs('archive', 'questions.html'),
                'Questions & answers')

    # Garde-fou : rien en clair, aucun jeton oublie dans docs/.
    bad = []
    for dirpath, _, files in os.walk(os.path.join(ROOT, 'docs')):
        for f in files:
            if not f.endswith('.html'):
                continue
            p = os.path.join(dirpath, f)
            if '{{B}}' in open(p, encoding='utf-8').read():
                bad.append(os.path.relpath(p, ROOT))
    if bad:
        raise SystemExit('Jeton {{B}} non resolu dans : %s' % ', '.join(bad))
    print('OK, aucun jeton {{B}} restant.')


main()
