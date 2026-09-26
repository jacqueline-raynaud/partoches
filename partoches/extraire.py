"""PDF vectoriel (LilyPond) + MusicXML Audiveris -> versions SATB / voix / piano / guitare.

Audiveris reconnaît bien les notes et les rythmes, mais lit mal les paroles et les
accords. Comme le PDF est vectoriel, on lit ces textes directement dans le PDF,
avec leur position exacte, puis on les rattache aux notes par leur abscisse.

Usage : python -m partoches.extraire partition.pdf audiveris.mxl dossier_sortie
"""
import copy
import json
import re
import sys
from pathlib import Path

import pymupdf
from music21 import clef, converter, harmony, instrument, layout, metadata, note, stream

SOLFEGE = {'Do': 'C', 'Ré': 'D', 'Re': 'D', 'Mi': 'E', 'Fa': 'F', 'Sol': 'G', 'La': 'A', 'Si': 'B'}
ALTERATION = {'♯': '#', '#': '#', '♭': '-', 'b': '-'}
SYLLABIC = {(False, False): 'single', (False, True): 'begin', (True, True): 'middle', (True, False): 'end'}
# (clé du fichier, nom affiché, portée d'Audiveris 0/1, voix Audiveris, clé)
VOIX = [('soprano', 'Soprano', 0, '1', clef.TrebleClef), ('alto', 'Alto', 0, '2', clef.TrebleClef),
        ('tenor', 'Ténor', 1, '1', clef.Treble8vbClef), ('basse', 'Basse', 1, '2', clef.BassClef)]


# ------------------------------------------------------------------ lecture du PDF
def lire_pdf(pdf_path):
    page = pymupdf.open(pdf_path)[0]
    spans = []
    for b in page.get_text('rawdict')['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                t = ''.join(c['c'] for c in s['chars'])
                if t.strip():
                    x0, y0, x1, y1 = s['bbox']
                    spans.append(dict(t=t, x0=x0, y0=y0, x1=x1, y1=y1, font=s['font'], size=round(s['size'], 1)))
    traits = [d['rect'] for d in page.get_drawings() if d['rect'].width < 4 and d['rect'].height < 0.5]
    return spans, traits


def noms_accords(spans):
    """Noms d'accords LilyPond : racine en DejaVuSans, exposant plus petit, dièse en glyphe Emmentaler."""
    sups = [s for s in spans if s['font'] == 'DejaVuSans' and s['size'] < 10]
    dieses = [s for s in spans if s['font'].startswith('Emmentaler') and s['size'] > 17 and s['t'] == '\x07']
    accords = []
    for s in sorted([s for s in spans if s['font'] == 'DejaVuSans' and s['size'] > 10], key=lambda s: (round(s['y0']), s['x0'])):
        prec = accords[-1] if accords else None
        if prec and abs(prec['y0'] - s['y0']) < 2 and s['t'] == 'm' and s['x0'] - prec['x1'] < 8:
            prec['t'] += 'm'  # "Do" + ♯ + "m" arrivent en morceaux séparés
            prec['x1'] = s['x1']
            continue
        s = dict(s)
        d = next((g for g in dieses if abs((g['y0'] + g['y1']) / 2 - (s['y0'] + s['y1']) / 2) < 8 and -1 < g['x0'] - s['x1'] < 3), None)
        if d:
            s['t'] += '♯'
            s['x1'] = d['x1']
        accords.append(s)
    for a in accords:
        a['sup'] = next((s['t'] for s in sups if abs(s['y0'] - a['y0']) < 8 and -1 < s['x0'] - a['x1'] < 3), '')
    return sorted(accords, key=lambda s: (s['y0'], s['x0']))


def figure_accord(texte, sup):
    m = re.match(r'(Do|Ré|Re|Mi|Fa|Sol|La|Si)\s*([♯♭#b]?)\s*(m?)', texte)
    if not m:
        return None
    return SOLFEGE[m.group(1)] + ALTERATION.get(m.group(2), '') + m.group(3) + sup


def systemes_pdf(spans, accords):
    """Un système = une ligne d'accords, suivie de ses lignes de couplets ("1 -", "2 -"…)."""
    tetes = [s for s in spans if s['font'].startswith('Emmentaler') and s['size'] < 17 and s['t'] in ('\x00', '\x01', '\x03')]
    etiquettes = sorted([s for s in spans if s['font'] == 'CenturySchL-Bold' and re.match(r'\d -', s['t'])], key=lambda s: s['y0'])
    paroles = [s for s in spans if s['font'] == 'CenturySchL-Roma' and s['size'] == 10.5]
    systemes = []
    for a in accords:
        if not systemes or a['y0'] - systemes[-1]['y_accords'] > 30:
            systemes.append(dict(y_accords=a['y0'], accords=[]))
        systemes[-1]['accords'].append(a)
    if not systemes:
        raise SystemExit("Aucun nom d'accord trouvé dans le PDF : ce prototype s'appuie sur eux pour repérer les systèmes.")
    for i, sy in enumerate(systemes):
        y_fin = systemes[i + 1]['y_accords'] if i + 1 < len(systemes) else float('inf')
        labels = [l for l in etiquettes if sy['y_accords'] < l['y0'] < y_fin]
        sy['y_couplets'] = [l['y0'] for l in labels]
        y_haut = sy['y_couplets'][0] if labels else sy['y_accords'] + 60
        sy['tetes'] = sorted({round(h['x0'], 1) for h in tetes if sy['y_accords'] < h['y0'] < y_haut})
        sy['paroles'] = [sorted([s for s in paroles if abs(s['y0'] - vy) < 4], key=lambda s: s['x0']) for vy in sy['y_couplets']]
    return systemes


# ------------------------------------------------------------------ calage PDF <-> MusicXML
def caler_attaques(sy, mesures):
    """Abscisse PDF de chaque attaque (mesure, temps) de la portée du haut.

    Audiveris donne des positions en « tenths » relatives à la mesure ; on les cumule
    puis on cale linéairement sur les têtes de notes du PDF (moindres carrés).
    """
    attaques, cumul = {}, 0
    for m in mesures:
        for n in m.recurse().notes:
            if n.style.absoluteX is not None:
                attaques.setdefault((m.number, float(n.getOffsetInHierarchy(m))), cumul + n.style.absoluteX)
        cumul += m.layoutWidth
    xs = sorted(attaques.items(), key=lambda kv: kv[1])
    t0, t1 = xs[0][1], xs[-1][1]
    h0, h1 = sy['tetes'][0], sy['tetes'][-1]
    a = (h1 - h0) / (t1 - t0)
    for _ in range(3):
        paires = [(t, min(sy['tetes'], key=lambda h: abs(h - (a * (t - t0) + h0)))) for _, t in xs]
        mt = sum(p[0] for p in paires) / len(paires)
        mh = sum(p[1] for p in paires) / len(paires)
        a = sum((p[0] - mt) * (p[1] - mh) for p in paires) / sum((p[0] - mt) ** 2 for p in paires)
        h0, t0 = mh, mt
    sy['attaques'] = [(k, a * (t - t0) + h0) for k, t in xs]


def attaque_proche(sy, x):
    return min(sy['attaques'], key=lambda o: abs(o[1] - x))[0]


def trait_entre(traits, a, b):
    return any(a['x1'] - 1 < h.x0 < b['x0'] + 1 and a['y0'] < h.y0 < a['y1'] + 2 for h in traits)


def copier_barres(src, dst):
    """Garde les barres de reprise : sans elles, l'écoute saute les passages répétés."""
    if src.leftBarline is not None:
        dst.leftBarline = copy.deepcopy(src.leftBarline)
    if src.rightBarline is not None:
        dst.rightBarline = copy.deepcopy(src.rightBarline)


# ------------------------------------------------------------------ programme principal
def extraire(pdf_path, mxl_path, dossier):
    """Choisit le mode : lecture fine du texte pour LilyPond, sinon résultat d'Audiveris seul."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    spans, traits = lire_pdf(pdf_path)
    if any(s['font'].startswith('Emmentaler') for s in spans):
        info = extraire_lilypond(pdf_path, mxl_path, dossier, spans, traits)
    else:
        info = extraire_generique(pdf_path, mxl_path, dossier, spans)
    (dossier / 'info.json').write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding='utf-8')
    return info


def extraire_lilypond(pdf_path, mxl_path, dossier, spans, traits):
    corrections = []
    accords_pdf = noms_accords(spans)
    systemes = systemes_pdf(spans, accords_pdf)

    partition = converter.parse(mxl_path)
    haut, bas = partition.parts[0], partition.parts[1]
    portees = (haut, bas)
    MESURE = haut.getElementsByClass(stream.Measure)[0].barDuration.quarterLength

    # 1) corrections de rythme : accord dans une voix unique, voix incomplète
    for part in portees:
        for m in part.getElementsByClass(stream.Measure):
            for v in m.voices:
                for c in list(v.getElementsByClass('Chord')):
                    p = max(c.pitches) if v.id == '1' else min(c.pitches)
                    n = note.Note(p, quarterLength=c.quarterLength)
                    v.replace(c, n)
                    corrections.append(f"Mesure {m.number}, voix {v.id} : accord {[x.nameWithOctave for x in c.pitches]} ramené à {n.nameWithOctave}")
                manque = MESURE - v.highestTime
                if manque > 0:
                    v.append(note.Rest(quarterLength=manque))
                    corrections.append(f"Mesure {m.number}, voix {v.id} : silence ajouté ({manque} temps manquants)")

    # 2) calage des systèmes
    mesures_sys, cur = [], None
    for m in haut.getElementsByClass(stream.Measure):
        if m.number == 1 or any(sl.isNew for sl in m.getElementsByClass(layout.SystemLayout)):
            cur = []
            mesures_sys.append(cur)
        cur.append(m)
    if len(mesures_sys) != len(systemes):
        raise SystemExit(f"{len(mesures_sys)} systèmes chez Audiveris contre {len(systemes)} dans le PDF.")
    for sy, mesures in zip(systemes, mesures_sys):
        caler_attaques(sy, mesures)

    # 3) accords
    mesures_haut = {m.number: m for m in haut.getElementsByClass(stream.Measure)}
    accords = []
    for sy in systemes:
        for a in sy['accords']:
            fig = figure_accord(a['t'], a['sup'])
            if not fig:
                corrections.append(f"Accord illisible ignoré : {a['t']}{a['sup']}")
                continue
            num, temps = attaque_proche(sy, a['x0'])
            mesures_haut[num].insert(temps, harmony.ChordSymbol(fig))
            accords.append(dict(pdf=a['t'] + a['sup'], figure=fig, mesure=num, temps=temps))

    # 4) paroles : syllabes du PDF, traits d'union dessinés -> découpage
    for n in partition.recurse().notes:
        n.lyrics = []
    syllabes = {}  # (mesure, temps) -> {couplet: (texte, syllabic)}
    for sy in systemes:
        for couplet, ligne in enumerate(sy['paroles'], start=1):
            for i, s in enumerate(ligne):
                avant = i > 0 and trait_entre(traits, ligne[i - 1], s)
                apres = i + 1 < len(ligne) and trait_entre(traits, s, ligne[i + 1])
                cle = attaque_proche(sy, (s['x0'] + s['x1']) / 2 - 2.8)
                syllabes.setdefault(cle, {})[couplet] = (s['t'], SYLLABIC[(avant, apres)])

    # chaque syllabe va, dans chaque voix, sur la note attaquée à cet instant ; si la
    # voix tient une note, sur la première note attaquée avant la syllabe suivante
    def t_abs(num, temps):
        return (num - 1) * MESURE + temps

    instants = sorted((t_abs(*k), v) for k, v in syllabes.items())
    for part in portees:
        for vid in ('1', '2'):
            notes = sorted(((t_abs(m.number, float(n.getOffsetInHierarchy(m))), n)
                            for m in part.getElementsByClass(stream.Measure) for v in m.voices if v.id == vid
                            for n in v.getElementsByClass(note.Note)), key=lambda x: x[0])
            prises = set()
            for i, (t, par_couplet) in enumerate(instants):
                t_suiv = instants[i + 1][0] if i + 1 < len(instants) else float('inf')
                cible = next((n for nt, n in notes if nt == t), None) or \
                    next((n for nt, n in notes if t < nt < t_suiv and id(n) not in prises), None)
                if cible is None:
                    continue
                prises.add(id(cible))
                for couplet, (txt, syl) in sorted(par_couplet.items()):
                    cible.addLyric(txt, lyricNumber=couplet)
                    cible.lyrics[-1].syllabic = syl

    # 5) versions
    titre = next(s['t'] for s in spans if s['size'] > 14)
    haut_de_page = [s['t'] for s in spans if s['font'] == 'CenturySchL-Roma' and s['size'] < 10 and s['y0'] < systemes[0]['y_accords']]
    compositeur = next((t for t in haut_de_page if t.startswith('Musique')), '')
    tonalite = haut.recurse().getElementsByClass('KeySignature')[0].asKey('major')

    def nouvelle(parts, sous_titre):
        s = stream.Score()
        s.metadata = metadata.Metadata(title=titre, composer=compositeur)
        s.metadata.movementName = sous_titre
        for p in parts:
            s.insert(0, p)
        return s

    def extraire_voix(part, vid, nom, cle, avec_accords):
        p = stream.Part(id=nom)
        p.partName = nom
        for m in part.getElementsByClass(stream.Measure):
            nm = stream.Measure(number=m.number)
            if m.timeSignature:
                nm.timeSignature = copy.deepcopy(m.timeSignature)
            if m.keySignature:
                nm.keySignature = copy.deepcopy(m.keySignature)
            copier_barres(m, nm)
            for v in m.voices:
                if v.id == vid:
                    for e in v.notesAndRests:
                        nm.insert(e.getOffsetInHierarchy(m), copy.deepcopy(e))
            if avec_accords:
                for cs in m.getElementsByClass(harmony.ChordSymbol):
                    nm.insert(cs.offset, copy.deepcopy(cs))
            p.append(nm)
        p.getElementsByClass(stream.Measure)[0].insert(0, cle)
        p.insert(0, instrument.Vocalist())
        p.getElementsByClass(stream.Measure)[-1].rightBarline = 'final'
        return p

    versions, tessitures, satb = {}, {}, []
    for cle_f, nom, portee, vid, cle in VOIX:
        p = extraire_voix(portees[portee], vid, nom, cle(), avec_accords=(cle_f == 'soprano'))
        satb.append(p)
        hauteurs = [n.pitch for n in p.recurse().getElementsByClass(note.Note)]
        tessitures[cle_f] = (min(hauteurs).nameWithOctave, max(hauteurs).nameWithOctave)
        versions[cle_f] = nouvelle([copy.deepcopy(p)], nom)
    versions['satb'] = nouvelle(satb, 'Chœur SATB')

    piano = []
    for part in portees:  # les deux portées d'origine, sans paroles
        p = copy.deepcopy(part)
        for n in p.recurse().notes:
            n.lyrics = []
        p.insert(0, instrument.Piano())
        piano.append(p)
    versions['piano'] = nouvelle(piano, 'Piano')
    versions['guitare'] = nouvelle([extraire_voix(haut, '1', 'Mélodie', clef.TrebleClef(), True)], 'Guitare (mélodie + accords)')

    for k, sc in versions.items():
        sc.write('musicxml', fp=dossier / f'{k}.musicxml')

    nb_couplets = max(len(sy['paroles']) for sy in systemes)
    nb_syllabes = sum(len(v) for v in syllabes.values())
    return dict(mode_lecture='lilypond', titre=titre, compositeur=compositeur, en_tete=haut_de_page,
                detail=f"4 voix · {nb_couplets} couplet{'s' if nb_couplets > 1 else ''}",
                versions=['satb', 'soprano', 'alto', 'tenor', 'basse', 'piano', 'guitare'],
                tonique=tonalite.tonic.pitchClass, mode=tonalite.mode,
                nb_mesures=len(mesures_haut), nb_couplets=nb_couplets,
                tessitures=tessitures, accords=sorted({a['figure'] for a in accords}), nb_accords=len(accords),
                nb_syllabes=nb_syllabes, corrections=corrections, a_verifier=[],
                etapes=['PDF LilyPond', 'Audiveris (notes, rythmes)', 'texte du PDF (paroles, accords)',
                        'music21 (voix, piano, guitare)', 'Verovio (affichage, transposition, écoute)'],
                resume=f"{len(mesures_haut)} mesures reconnues à 4 voix, {nb_syllabes} syllabes réparties sur "
                       f"{nb_couplets} couplets, {len(accords)} accords relevés dans le PDF.")


# ------------------------------------------------------------------ mode générique
EN_TETE = re.compile(r'^(Auteur|Compositeur|Paroles|Musique|Interprète|Arrangement)\s*:', re.I)


def melodie_de(part, avec_accords):
    """Ligne mélodique = note la plus aiguë à chaque instant de la portée (toutes voix confondues)."""
    mel = stream.Part(id='Mélodie')
    mel.partName = 'Mélodie'
    for m in part.getElementsByClass(stream.Measure):
        nm = stream.Measure(number=m.number)
        if m.timeSignature:
            nm.timeSignature = copy.deepcopy(m.timeSignature)
        if m.keySignature:
            nm.keySignature = copy.deepcopy(m.keySignature)
        copier_barres(m, nm)
        travail = copy.deepcopy(m)
        for cs in list(travail.recurse().getElementsByClass(harmony.ChordSymbol)):
            cs.activeSite.remove(cs)  # un symbole d'accord compte comme un accord pour chordify
        for e in travail.chordify().notesAndRests:
            if e.isRest:
                nm.insert(e.offset, note.Rest(quarterLength=e.quarterLength))
            else:
                n = note.Note(max(e.pitches), quarterLength=e.quarterLength)
                n.tie = e.tie
                nm.insert(e.offset, n)
        if avec_accords:
            for cs in m.recurse().getElementsByClass(harmony.ChordSymbol):
                nm.insert(cs.getOffsetInHierarchy(m), copy.deepcopy(cs))
        mel.append(nm)
    mel.getElementsByClass(stream.Measure)[0].insert(0, clef.TrebleClef())
    mel.insert(0, instrument.Vocalist())
    mel.getElementsByClass(stream.Measure)[-1].rightBarline = 'final'
    return mel


def extraire_generique(pdf_path, mxl_path, dossier, spans):
    """PDF d'une autre origine : on garde la lecture d'Audiveris et on signale les mesures douteuses."""
    partition = converter.parse(mxl_path)
    parts = list(partition.parts)
    haut = parts[0]
    mesures = list(haut.getElementsByClass(stream.Measure))

    a_verifier = []
    for num_portee, part in enumerate(parts, start=1):
        ms = list(part.getElementsByClass(stream.Measure))
        for i, m in enumerate(ms):
            attendu = m.barDuration.quarterLength
            duree = max((v.highestTime for v in m.voices), default=m.highestTime)
            if abs(duree - attendu) > 0.01 and not (i == 0 and duree < attendu):  # anacrouse tolérée
                a_verifier.append(f"Mesure {m.number}, portée {num_portee} : {float(duree):g} temps au lieu de {float(attendu):g}")

    doc = pymupdf.open(pdf_path)
    titre = (doc.metadata.get('title') or '').split(' - ')[0].strip() or \
        max(spans, key=lambda s: s['size'])['t'] if spans else Path(pdf_path).stem
    en_tete = list(dict.fromkeys(s['t'].strip() for s in spans if EN_TETE.match(s['t'].strip())))
    compositeur = next((t.split(':', 1)[1].strip() for t in en_tete if t.lower().startswith(('compositeur', 'musique'))), '')
    # tonalité de départ : armure de la 1re mesure (absente = aucune altération)
    armure = mesures[0].keySignature if mesures else None
    tonalite = armure.asKey('major') if armure else None

    def nouvelle(parts_, sous_titre):
        s = stream.Score()
        s.metadata = metadata.Metadata(title=titre, composer=compositeur)
        s.metadata.movementName = sous_titre
        for p in parts_:
            s.insert(0, p)
        return s

    piano = []
    for part in parts:
        p = copy.deepcopy(part)
        for mm in list(p.recurse().getElementsByClass('MetronomeMark')):
            mm.activeSite.remove(mm)  # le tempo se règle dans la page ; Verovio part alors de ♩ = 120
        p.insert(0, instrument.Piano())
        piano.append(p)
    melodie = melodie_de(haut, avec_accords=False)
    versions = {'piano': nouvelle(piano, 'Piano'),
                'melodie': nouvelle([melodie], 'Mélodie'),
                'guitare': nouvelle([melodie_de(haut, avec_accords=True)], 'Guitare (mélodie + accords)')}
    for k, sc in versions.items():
        sc.write('musicxml', fp=dossier / f'{k}.musicxml')

    hauteurs = [n.pitch for n in melodie.recurse().getElementsByClass(note.Note)]
    accords = [cs.figure for cs in haut.recurse().getElementsByClass(harmony.ChordSymbol)]
    nb_syllabes = sum(len(n.lyrics) for n in haut.recurse().notes)
    return dict(mode_lecture='generique', titre=titre, compositeur=compositeur, en_tete=en_tete,
                detail=f"{len(parts)} portées · {len(mesures)} mesures",
                versions=['piano', 'melodie', 'guitare'],
                tonique=tonalite.tonic.pitchClass if tonalite else 0, mode=tonalite.mode if tonalite else 'major',
                nb_mesures=len(mesures), nb_couplets=0,
                tessitures={'melodie': (min(hauteurs).nameWithOctave, max(hauteurs).nameWithOctave)} if hauteurs else {},
                accords=sorted(set(accords)), nb_accords=len(accords), nb_syllabes=nb_syllabes,
                corrections=[], a_verifier=a_verifier,
                etapes=['PDF', 'Audiveris (notes, rythmes, accords)', 'music21 (mélodie, guitare)',
                        'Verovio (affichage, transposition, écoute)'],
                resume=f"{len(mesures)} mesures reconnues sur {len(parts)} portées, {len(accords)} accords lus par "
                       f"Audiveris, {len(a_verifier)} mesures au rythme incohérent à vérifier. Paroles non reprises : "
                       f"la lecture fine du texte n'existe pour l'instant que pour les PDF LilyPond.")


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    print(json.dumps(extraire(*sys.argv[1:]), ensure_ascii=False, indent=1))
