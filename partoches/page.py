"""Construit la page de lecture autonome (un seul fichier HTML) à partir des versions MusicXML.

Usage : python -m partoches.page dossier_versions [page.html]
"""
import json
import sys
from pathlib import Path

MODELE = Path(__file__).resolve().parent.parent / 'web' / 'modele.html'


def titre_lisible(titre):
    """« À TOI, LA GLOIRE » -> « À toi, la gloire »."""
    return titre[:1] + titre[1:].lower() if titre.isupper() else titre


def construire_page(dossier, sortie=None):
    dossier = Path(dossier)
    sortie = Path(sortie) if sortie else dossier / 'partoches.html'
    info = json.loads((dossier / 'info.json').read_text(encoding='utf-8'))
    xml = {k: (dossier / f'{k}.musicxml').read_text(encoding='utf-8') for k in info['versions']}
    # erreurs connues : notées à la main dans a-verifier.txt, ou mesures douteuses repérées à l'extraction
    fichier = dossier / 'a-verifier.txt'
    a_verifier = fichier.read_text(encoding='utf-8').strip() if fichier.exists() else ''
    if not a_verifier and info.get('a_verifier'):
        a_verifier = ' ; '.join(info['a_verifier']) + '.'
    titre = titre_lisible(info['titre'])
    donnees = dict(titre=titre, info=info, xml=xml, a_verifier=a_verifier)
    # "</" échappé pour ne pas fermer la balise <script> qui contient les données
    blob = json.dumps(donnees, ensure_ascii=False).replace('</', r'<\/')
    html = MODELE.read_text(encoding='utf-8').replace('__TITRE__', titre).replace('__DATA__', blob)
    sortie.write_text(html, encoding='utf-8')
    return sortie


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    print(construire_page(*sys.argv[1:]))
