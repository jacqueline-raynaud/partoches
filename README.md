# Partoches

Retranscrire une partition PDF en quelque chose de lisible sur ordinateur ou tablette,
avec des versions pour le chœur (soprano, alto, ténor, basse), le piano et la guitare.

**État : prototype.** Testé sur une seule partition, un cantique à 4 voix gravé avec LilyPond
(voir [`exemples/a-toi-la-gloire`](exemples/a-toi-la-gloire)).

## Ce que ça produit

À partir d'un PDF, un dossier contenant :

| Fichier | Contenu |
|---|---|
| `satb.musicxml` | Le chœur, une portée par voix, avec les paroles |
| `soprano` / `alto` / `tenor` / `basse.musicxml` | Chaque voix seule, avec les paroles (les accords sont sur la soprano) |
| `piano.musicxml` | Les deux portées d'origine, sans paroles |
| `guitare.musicxml` | La mélodie avec les accords |
| `partoches.html` | Une page de lecture autonome : choix de la version, transposition, accords en Do Ré Mi ou C D E, grilles de guitare, écoute des voix |
| `info.json` | Tessitures, accords, statistiques, corrections automatiques appliquées |

Les fichiers MusicXML s'ouvrent aussi dans MuseScore pour corriger ou imprimer.

## Comment ça marche

```
PDF ──► Audiveris ──► MusicXML brut ──► extraire.py ──► versions MusicXML ──► page.py ──► partoches.html
        (notes,                          + texte du PDF                                  (Verovio : affichage,
         rythmes)                        (paroles, accords)                              transposition, écoute)
```

1. **Audiveris** (reconnaissance optique de partitions) lit les notes et les rythmes. Il le fait bien,
   mais lit mal les paroles et ne reconnaît pas les accords écrits en Do Ré Mi.
2. **`partoches/extraire.py`** tire parti du PDF vectoriel : paroles, accords et têtes de notes y sont
   du texte avec une position exacte. On cale les positions d'Audiveris sur celles du PDF, puis on
   rattache chaque syllabe et chaque accord à sa note. Les traits d'union dessinés donnent le
   découpage des syllabes. Quelques erreurs de rythme courantes sont corrigées automatiquement.
   Les voix sont ensuite séparées avec [music21](https://music21.org).
3. **`partoches/page.py`** assemble une page HTML unique qui affiche la partition avec
   [Verovio](https://www.verovio.org) (chargé depuis jsDelivr).

## Installation

- Python 3.10 ou plus : `pip install -r requirements.txt`
- [Audiveris](https://github.com/Audiveris/audiveris/releases) 5.11 ou plus (il embarque son propre Java).
  Si l'installeur Windows échoue, une extraction sans droits administrateur suffit :
  `msiexec /a Audiveris-5.11.0-windowsConsole-x86_64.msi /qn TARGETDIR=C:\chemin\audiveris`
- Les langues de lecture de texte d'Audiveris, sans lesquelles il ignore les paroles :
  télécharger `fra.traineddata` et `eng.traineddata` depuis
  [tesseract-ocr/tessdata](https://github.com/tesseract-ocr/tessdata) dans
  `%APPDATA%\AudiverisLtd\audiveris\config\tessdata` (Windows).

## Utilisation

```bash
python -m partoches ma-partition.pdf --sortie resultats/ma-partition
```

Indiquer l'emplacement d'Audiveris avec `--audiveris chemin\Audiveris.exe` ou la variable
d'environnement `AUDIVERIS`. Pour repartir d'un MusicXML Audiveris déjà produit (ou corrigé dans
MuseScore) : `--mxl fichier.mxl`.

Un fichier `a-verifier.txt` placé dans le dossier de sortie s'affiche dans la page (erreurs connues
à corriger à la main). Relancer ensuite `python -m partoches.page dossier` pour régénérer la page seule.

## Limites connues

- **PDF LilyPond seulement** : la lecture du texte s'appuie sur les polices de LilyPond
  (Emmentaler, DejaVuSans, Century Schoolbook). Un PDF issu de MuseScore, Finale ou d'un scan
  demandera d'autres règles, ou de se contenter de la lecture d'Audiveris.
- **Une page, deux portées, deux voix par portée** (le format cantique SATB). Les accords servent
  à repérer les systèmes : une partition sans accords n'est pas encore gérée.
- **Pas d'harmonisation** : une mélodie seule ne devient pas un chœur à 4 voix.
- Pas de tablature de guitare (grilles d'accords uniquement), pas de reprises ni de D.C. à l'écoute.
- La tonalité affichée suppose un mode majeur.

Les PDF sources ne sont pas versionnés (`.gitignore`) : la musique peut être libre de droits
sans que la gravure le soit.
