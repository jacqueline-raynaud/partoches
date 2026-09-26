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

from .extraire import extraire
from .page import construire_page

EMPLACEMENTS = [r'C:\Program Files\Audiveris\Audiveris.exe', '/opt/audiveris/bin/Audiveris',
                '/Applications/Audiveris.app/Contents/MacOS/Audiveris']


def trouver_audiveris(option):
    for c in (option, os.environ.get('AUDIVERIS'), shutil.which('Audiveris'), *EMPLACEMENTS):
        if c and Path(c).exists():
            return c
    sys.exit("Audiveris introuvable : installe-le (voir README) ou indique son chemin avec --audiveris.")


def lancer_audiveris(exe, pdf, dossier):
    """Reconnaissance optique ; les paroles demandent les langues Tesseract fra/eng (voir README)."""
    copie = Path(dossier) / Path(pdf).name
    shutil.copy(pdf, copie)
    subprocess.run([exe, '-batch', '-export',
                    '-option', 'org.audiveris.omr.text.Language.defaultSpecification=fra+eng',
                    '-output', str(dossier), str(copie)], check=True)
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
