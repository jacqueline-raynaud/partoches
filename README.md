# Partoches

Retranscrire une partition PDF en quelque chose de lisible sur ordinateur ou tablette,
avec des versions pour le chœur (soprano, alto, ténor, basse), le piano et la guitare.

**État : prototype.** Deux modes de lecture, choisis automatiquement :

- **PDF LilyPond** (testé sur un cantique à 4 voix, voir [`exemples/a-toi-la-gloire`](exemples/a-toi-la-gloire)) :
  lecture fine, avec paroles et accords tirés du texte du PDF, et versions chœur, voix, piano et guitare.
- **Autres PDF** (testé sur un piano solo Noviscore) : la lecture d'Audiveris telle quelle, et des
  versions piano, mélodie (note la plus aiguë de la main droite) et guitare (mélodie + accords
  reconnus par Audiveris). Pas de paroles, et les mesures au rythme douteux sont signalées dans la page.

## Ce que ça produit

À partir d'un PDF, un dossier contenant :

| Fichier | Contenu |
|---|---|
| `satb.musicxml` | Le chœur, une portée par voix, avec les paroles (LilyPond) |
| `soprano` / `alto` / `tenor` / `basse.musicxml` | Chaque voix seule, avec les paroles ; les accords sont sur la soprano (LilyPond) |
| `melodie.musicxml` | La mélodie seule (autres PDF) |
| `piano.musicxml` | Les deux portées d'origine |
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
- Les langues de lecture de texte d'Audiveris, sans lesquelles il ignore les paroles et les accords :
  télécharger `fra.traineddata` et `eng.traineddata` depuis
  [tesseract-ocr/tessdata](https://github.com/tesseract-ocr/tessdata) dans le dossier `tessdata/`
  du projet (ignoré par Git). La commande les transmet à Audiveris par la variable `TESSDATA_PREFIX`.

## Utilisation

```bash
python -m partoches ma-partition.pdf --sortie resultats/ma-partition
```

Indiquer l'emplacement d'Audiveris avec `--audiveris chemin\Audiveris.exe` ou la variable
d'environnement `AUDIVERIS`. Pour repartir d'un MusicXML Audiveris déjà produit (ou corrigé dans
MuseScore) : `--mxl fichier.mxl`.

Seules les pages qui ont des portées sont envoyées à Audiveris : une page de paroles seule, par
exemple, est ignorée (sinon Audiveris abandonne tout le fichier).

Un fichier `a-verifier.txt` placé dans le dossier de sortie s'affiche dans la page (erreurs connues
à corriger à la main). Relancer ensuite `python -m partoches.page dossier` pour régénérer la page seule.

## Limites connues

- **Lecture fine réservée à LilyPond** : elle s'appuie sur les polices de LilyPond (Emmentaler,
  DejaVuSans, Century Schoolbook), sur une seule page, deux portées et deux voix par portée (le
  format cantique SATB). Les accords servent à repérer les systèmes. Les autres PDF passent en mode
  générique, sans paroles.
- **Triolets** : Audiveris se trompe souvent sur les mesures qui en contiennent ; elles sont listées
  dans la page (« Encore à corriger à la main »).
- **Pas d'harmonisation** : une mélodie seule ne devient pas un chœur à 4 voix.
- Pas de tablature de guitare (grilles d'accords simplifiées : les accords enrichis comme `add9` ou
  `13` sont ramenés à leur forme de base). L'écoute joue les barres de reprise, mais pas les D.C.
  ni les « Reprendre à » écrits en texte.
- La tonalité affichée suppose un mode majeur.

Les PDF sources ne sont pas versionnés (`.gitignore`) : la musique peut être libre de droits
sans que la gravure le soit.
