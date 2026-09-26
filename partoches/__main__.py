"""Chaîne complète : PDF -> Audiveris -> versions MusicXML -> page de lecture.

Usage :
  python -m partoches partition.pdf [--sortie dossier] [--mxl audiveris.mxl] [--audiveris Audiveris.exe]

Sans --mxl, Audiveris est lancé sur le PDF. Son emplacement est cherché dans
--audiveris, puis la variable d'environnement AUDIVERIS, puis les dossiers d'installation habituels.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

from .extraire import extraire
from .page import construire_page

# fichiers de langue Tesseract (fra/eng) rangés dans le projet ; voir README
TESSDATA = Path(__file__).resolve().parent.parent / 'tessdata'
EMPLACEMENTS = [r'C:\Program Files\Audiveris\Audiveris.exe', '/opt/audiveris/bin/Audiveris',
                '/Applications/Audiveris.app/Contents/MacOS/Audiveris']


def trouver_audiveris(option):
    for c in (option, os.environ.get('AUDIVERIS'), shutil.which('Audiveris'), *EMPLACEMENTS):
        if c and Path(c).exists():
            return c
    sys.exit("Audiveris introuvable : installe-le (voir README) ou indique son chemin avec --audiveris.")


def pages_de_musique(pdf):
    """Numéros (à partir de 1) des pages qui ont des portées : au moins 5 longs traits horizontaux.

    Audiveris abandonne tout le fichier si une page n'a pas de portée (page de paroles, par exemple).
    """
    pages = []
    for i, p in enumerate(pymupdf.open(pdf), start=1):
        largeur, traits = p.rect.width, 0
        for d in p.get_drawings():
            for it in d['items']:
                if it[0] == 'l' and abs(it[1].y - it[2].y) < 0.5 and abs(it[2].x - it[1].x) > 0.3 * largeur:
                    traits += 1
                elif it[0] == 're' and it[1].height < 1.5 and it[1].width > 0.3 * largeur:
                    traits += 1
        if traits >= 5:
            pages.append(i)
    return pages


def plages(nums):
    """[1, 2, 3, 5] -> ['1-3', '5']"""
    res, debut = [], None
    for i, n in enumerate(nums):
        if debut is None:
            debut = n
        if i + 1 == len(nums) or nums[i + 1] != n + 1:
            res.append(f'{debut}-{n}' if n != debut else str(n))
            debut = None
    return res


def lancer_audiveris(exe, pdf, dossier):
    """Reconnaissance optique des pages de musique ; les paroles demandent les langues Tesseract (voir README)."""
    copie = Path(dossier) / Path(pdf).name
    shutil.copy(pdf, copie)
    pages = pages_de_musique(pdf)
    if not pages:
        sys.exit("Aucune page avec des portées dans ce PDF : est-ce bien une partition vectorielle ?")
    env = dict(os.environ)
    if TESSDATA.is_dir():
        env['TESSDATA_PREFIX'] = str(TESSDATA)
    subprocess.run([exe, '-batch', '-export', '-sheets', *plages(pages),
                    '-option', 'org.audiveris.omr.text.Language.defaultSpecification=fra+eng',
                    '-output', str(dossier), str(copie)], check=True, env=env)
    mxl = copie.with_suffix('.mxl')
    if not mxl.exists():
        sys.exit(f"Audiveris n'a pas produit {mxl.name} : voir le journal dans {dossier}.")
    return mxl


def main():
    ap = argparse.ArgumentParser(description="Retranscrit une partition PDF en versions chœur, voix, piano et guitare.")
    ap.add_argument('pdf')
    ap.add_argument('--sortie', help="dossier des résultats (par défaut : à côté du PDF)")
    ap.add_argument('--mxl', help="MusicXML déjà produit par Audiveris (saute la reconnaissance)")
    ap.add_argument('--audiveris', help="chemin de l'exécutable Audiveris")
    a = ap.parse_args()

    pdf = Path(a.pdf)
    sortie = Path(a.sortie) if a.sortie else pdf.with_suffix('')
    sortie.mkdir(parents=True, exist_ok=True)
    if a.mxl:
        mxl = Path(a.mxl)
    else:
        travail = Path(tempfile.mkdtemp(prefix='audiveris-'))
        mxl = lancer_audiveris(trouver_audiveris(a.audiveris), pdf, travail)
        shutil.copy(mxl, sortie / 'audiveris.mxl')
    info = extraire(pdf, mxl, sortie)
    page = construire_page(sortie)
    print(f"{info['nb_mesures']} mesures, {info['nb_accords']} accords, {info['nb_syllabes']} syllabes, "
          f"{len(info['corrections'])} corrections automatiques.\nPage : {page}")


if __name__ == '__main__':
    main()
