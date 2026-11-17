"""Kit de téléchargement : fiche ODT et PDF mis en page comme la fiche à l'écran, plus les médias."""
import hashlib
import io
import mimetypes
import re
from itertools import count
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED

from PIL import Image, ImageDraw, ImageFont
from werkzeug.exceptions import HTTPException, NotFound

from . import files

PRIMARY = '#ed8b00'
MUTED = '#7a7167'
LINE = '#efe6da'
STATUTS = {1: 'Validée', 2: 'À valider', 3: 'Brouillon'}

# Couleurs des blocs, reprises de la fiche (id de bloc -> accent)
ACCENTS = {
    'description': PRIMARY, 'objectifs': '#1f8a70', 'pre_anim': '#3a6fc4',
    'post_anim': '#8a4fc0', 'public_specifique': MUTED, 'materiel': '#b07a1a',
    'variante': '#3a6fc4',
}
SEQUENCE_COLORS = {'intro': '#1f8a70', 'developpement': '#8a4fc0', 'conclu': '#c4366b'}


def mix(color, ratio, base=(255, 255, 255)):
    """Équivalent de color-mix(in srgb, color ratio, white)."""
    channels = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(c * ratio + b * (1 - ratio)):02x}' for c, b in zip(channels, base))


def sequence_color(label):
    name = (label or '').lower()
    name = name.replace('é', 'e').replace('è', 'e')
    for prefix, color in SEQUENCE_COLORS.items():
        if name.startswith(prefix):
            return color
    return PRIMARY


def safe_name(value, fallback):
    """Nom de fichier lisible : on garde le titre, on retire seulement les caractères interdits."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', ' ', str(value or '')).strip(' .')
    name = re.sub(r'\s+', ' ', name)
    return name[:120].strip(' .') or fallback


class RichConverter(HTMLParser):
    """HTML nettoyé (issu de Markdown ou de l'éditeur) vers paragraphes ODF."""
    INLINE = {'strong': 'B', 'b': 'B', 'em': 'I', 'i': 'I', 'u': 'U', 'code': 'C', 's': 'S', 'del': 'S'}

    def __init__(self, para_style='Corps'):
        super().__init__(convert_charrefs=True)
        self.base = para_style
        self.out = []
        self.styles = []      # pile de styles de caractères
        self.lists = []       # pile ('ul'|'ol')
        self.open_p = False
        self.pending_href = []
        self.item_counter = []
        self.quote = 0

    def para_style(self):
        if self.quote:
            return 'Citation'
        return self.base

    def start_paragraph(self, style=None):
        self.end_paragraph()
        self.out.append(f'<text:p text:style-name="{style or self.para_style()}">')
        self.open_p = True

    def end_paragraph(self):
        if self.open_p:
            self.out.append('</text:p>')
            self.open_p = False

    def span_open(self):
        if self.styles:
            self.out.append(f'<text:span text:style-name="T{"".join(sorted(set(self.styles)))}">')

    def span_close(self):
        if self.styles:
            self.out.append('</text:span>')

    def handle_starttag(self, tag, attrs):
        if tag in ('p', 'div'):
            if not self.lists:
                self.start_paragraph()
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.start_paragraph('SousTitre')
        elif tag == 'br':
            if not self.open_p:
                self.start_paragraph()
            self.out.append('<text:line-break/>')
        elif tag in ('ul', 'ol'):
            self.end_paragraph()
            self.lists.append(tag)
            self.item_counter.append(0)
        elif tag == 'li':
            self.end_paragraph()
            self.item_counter[-1] += 1 if self.item_counter else 0
            depth = len(self.lists)
            marker = f'{self.item_counter[-1]}.' if self.lists and self.lists[-1] == 'ol' else '•'
            self.out.append(f'<text:p text:style-name="Puce{min(depth, 3)}">')
            self.out.append(f'{marker}<text:s text:c="2"/>')
            self.open_p = True
        elif tag == 'blockquote':
            self.end_paragraph()
            self.quote += 1
        elif tag == 'hr':
            self.end_paragraph()
        elif tag == 'a':
            href = dict(attrs).get('href')
            self.pending_href.append(href)
            if href and not self.open_p:
                self.start_paragraph()
            if href:
                self.out.append(f'<text:a xlink:type="simple" xlink:href={quoteattr(href)}>')
        elif tag in self.INLINE:
            self.span_close() if self.open_p else None
            self.styles.append(self.INLINE[tag])
            if self.open_p:
                self.span_open()

    def handle_endtag(self, tag):
        if tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.end_paragraph()
        elif tag in ('ul', 'ol'):
            self.end_paragraph()
            if self.lists:
                self.lists.pop()
                self.item_counter.pop()
        elif tag == 'li':
            self.end_paragraph()
        elif tag == 'blockquote':
            self.end_paragraph()
            self.quote = max(0, self.quote - 1)
        elif tag == 'a':
            if self.pending_href and self.pending_href.pop():
                self.out.append('</text:a>')
        elif tag in self.INLINE and self.styles:
            if self.open_p:
                self.span_close()
            self.styles.pop()
            if self.open_p:
                self.span_open()

    def handle_data(self, data):
        if not data.strip() and not self.open_p:
            return
        if not self.open_p:
            self.start_paragraph()
            self.span_open()
        if self.out and self.out[-1].endswith('<text:s text:c="2"/>') or self.out and self.out[-1].startswith('<text:p'):
            data = data.lstrip()
        text = escape(data.replace('\n', ' '))
        text = re.sub(r' {2,}', lambda m: ' <text:s text:c="%d"/>' % (len(m.group()) - 1), text)
        if self.styles and not self.out[-1].startswith('<text:span'):
            self.span_open()
        self.out.append(text)

    def result(self):
        self.end_paragraph()
        return ''.join(self.out)


def rich(text, style='Corps'):
    """Texte Markdown/HTML de la fiche converti en paragraphes ODF."""
    value = str(text or '').strip()
    if not value:
        return ''
    converter = RichConverter(style)
    converter.feed(files.render(value))
    converter.close()
    return converter.result()


BLOCK_IDS = count(1)


def block(label, text, accent):
    """Bloc coloré à bordure et fond teinté, comme les <fieldset> de la fiche."""
    body = rich(text)
    if not body:
        return ''
    key = accent[1:]
    return (f'<table:table table:name="Bloc{next(BLOCK_IDS)}" table:style-name="TB{key}">'
            '<table:table-column table:style-name="Pleine"/>'
            f'<table:table-row><table:table-cell table:style-name="CB{key}" office:value-type="string">'
            f'<text:p text:style-name="Legende{key}">{escape(label.upper())}</text:p>{body}'
            '</table:table-cell></table:table-row></table:table><text:p text:style-name="Espace"/>')


def block_styles(accents):
    styles = []
    for accent in sorted(set(accents)):
        key = accent[1:]
        styles.append(
            f'<style:style style:name="TB{key}" style:family="table"><style:table-properties style:width="17.4cm" '
            'table:align="margins" fo:margin-top="0cm" fo:margin-bottom="0.1cm"/></style:style>'
            f'<style:style style:name="CB{key}" style:family="table-cell"><style:table-cell-properties '
            f'fo:padding="0.2cm" fo:padding-left="0.35cm" fo:background-color="{mix(accent, 0.07)}" '
            f'fo:border="0.5pt solid {mix(accent, 0.45)}" fo:border-left="3pt solid {accent}"/></style:style>'
            f'<style:style style:name="Legende{key}" style:family="paragraph" style:parent-style-name="Corps">'
            '<style:paragraph-properties fo:margin-top="0cm" fo:margin-bottom="0.15cm" fo:keep-with-next="always"/>'
            f'<style:text-properties fo:font-size="9.5pt" fo:font-weight="bold" fo:letter-spacing="0.05cm" '
            f'fo:color="{mix(accent, 0.75, (0, 0, 0))}"/></style:style>')
    return ''.join(styles)


STATIC_STYLES = f'''
<style:style style:name="Pleine" style:family="table-column"><style:table-column-properties style:column-width="17.4cm"/></style:style>
<style:style style:name="Corps" style:family="paragraph"><style:paragraph-properties fo:margin-top="0cm" fo:margin-bottom="0.12cm" fo:line-height="125%"/><style:text-properties fo:font-size="10.5pt" fo:color="#26221e"/></style:style>
<style:style style:name="Espace" style:family="paragraph"><style:paragraph-properties fo:margin="0cm"/><style:text-properties fo:font-size="5pt"/></style:style>
<style:style style:name="EspaceGrand" style:family="paragraph"><style:paragraph-properties fo:margin="0cm"/><style:text-properties fo:font-size="14pt"/></style:style>
<style:style style:name="Titre" style:family="paragraph"><style:paragraph-properties fo:margin-top="0cm" fo:margin-bottom="0.15cm" fo:border-bottom="1.5pt solid {PRIMARY}" fo:padding-bottom="0.15cm" fo:keep-with-next="always"/><style:text-properties fo:font-size="22pt" fo:font-weight="bold" fo:color="#26221e"/></style:style>
<style:style style:name="Meta" style:family="paragraph"><style:paragraph-properties fo:margin-top="0.1cm" fo:margin-bottom="0.35cm"/><style:text-properties fo:font-size="9.5pt" fo:color="{MUTED}"/></style:style>
<style:style style:name="Badge" style:family="text"><style:text-properties fo:font-weight="bold" fo:color="#ffffff" fo:background-color="{PRIMARY}"/></style:style>
<style:style style:name="Titre2" style:family="paragraph"><style:paragraph-properties fo:margin-top="0.5cm" fo:margin-bottom="0.25cm" fo:keep-with-next="always"/><style:text-properties fo:font-size="15pt" fo:font-weight="bold" fo:color="{PRIMARY}"/></style:style>
<style:style style:name="SousTitre" style:family="paragraph" style:parent-style-name="Corps"><style:paragraph-properties fo:margin-top="0.15cm" fo:keep-with-next="always"/><style:text-properties fo:font-weight="bold"/></style:style>
<style:style style:name="Citation" style:family="paragraph" style:parent-style-name="Corps"><style:paragraph-properties fo:margin-left="0.6cm" fo:border-left="2pt solid {LINE}" fo:padding-left="0.2cm"/><style:text-properties fo:font-style="italic" fo:color="{MUTED}"/></style:style>
<style:style style:name="Puce1" style:family="paragraph" style:parent-style-name="Corps"><style:paragraph-properties fo:margin-left="0.9cm" fo:text-indent="-0.5cm" fo:margin-bottom="0.05cm"><style:tab-stops><style:tab-stop style:position="0cm"/></style:tab-stops></style:paragraph-properties></style:style>
<style:style style:name="Puce2" style:family="paragraph" style:parent-style-name="Puce1"><style:paragraph-properties fo:margin-left="1.5cm"><style:tab-stops><style:tab-stop style:position="0cm"/></style:tab-stops></style:paragraph-properties></style:style>
<style:style style:name="Puce3" style:family="paragraph" style:parent-style-name="Puce1"><style:paragraph-properties fo:margin-left="2.1cm"><style:tab-stops><style:tab-stop style:position="0cm"/></style:tab-stops></style:paragraph-properties></style:style>
<style:style style:name="Etiquette" style:family="paragraph"><style:paragraph-properties fo:margin-top="0.2cm" fo:margin-bottom="0.1cm" fo:keep-with-next="always"/><style:text-properties fo:font-size="8.5pt" fo:font-weight="bold" fo:letter-spacing="0.04cm" fo:color="{MUTED}"/></style:style>
<style:style style:name="Tags" style:family="paragraph"><style:paragraph-properties fo:margin-bottom="0.1cm"/><style:text-properties fo:font-size="10pt"/></style:style>
<style:style style:name="FaitLabel" style:family="paragraph"><style:paragraph-properties fo:margin="0cm"/><style:text-properties fo:font-size="8pt" fo:color="{MUTED}" fo:letter-spacing="0.03cm"/></style:style>
<style:style style:name="FaitValeur" style:family="paragraph"><style:paragraph-properties fo:margin="0cm"/><style:text-properties fo:font-size="11pt" fo:font-weight="bold"/></style:style>
<style:style style:name="CMedia" style:family="table-cell"><style:table-cell-properties fo:padding="0.15cm" fo:border="none"/></style:style>
<style:style style:name="VignetteImage" style:family="paragraph"><style:paragraph-properties fo:margin="0cm" fo:keep-with-next="always"/></style:style>
<style:style style:name="VignetteLegende" style:family="paragraph"><style:paragraph-properties fo:margin="0cm"/><style:text-properties fo:font-size="8.5pt" fo:color="#26221e"/></style:style>
<style:style style:name="Medias" style:family="paragraph" style:parent-style-name="Puce1"/>
<style:style style:name="Image" style:family="graphic"><style:graphic-properties style:vertical-pos="middle" style:vertical-rel="text" style:horizontal-pos="from-left" style:horizontal-rel="paragraph" fo:margin-right="0.1cm"/></style:style>
<style:style style:name="TFaits" style:family="table"><style:table-properties style:width="17.4cm" table:align="margins" fo:margin-bottom="0.2cm"/></style:style>
<style:style style:name="CFaits" style:family="table-cell"><style:table-cell-properties fo:padding="0.25cm" fo:background-color="#fffaf3" fo:border="0.5pt solid {LINE}"/></style:style>
<style:style style:name="Chip" style:family="text"><style:text-properties fo:font-size="9pt" fo:color="#b25f00" fo:background-color="#fff4e3"/></style:style>
<style:style style:name="ChipDuree" style:family="text"><style:text-properties fo:font-size="9pt" fo:font-weight="bold" fo:color="#b25f00" fo:background-color="#ffe6c4"/></style:style>
<style:style style:name="Puces" style:family="paragraph"><style:paragraph-properties fo:margin-bottom="0.2cm"/></style:style>
'''


def text_styles():
    """Styles de caractères pour toutes les combinaisons utiles (gras, italique, souligné, code, barré)."""
    from itertools import combinations
    letters = 'BCISU'
    out = []
    for size in range(1, len(letters) + 1):
        for combo in combinations(sorted(letters), size):
            name = ''.join(combo)
            props = []
            if 'B' in combo:
                props.append('fo:font-weight="bold"')
            if 'I' in combo:
                props.append('fo:font-style="italic"')
            if 'U' in combo:
                props.append('style:text-underline-style="solid" style:text-underline-width="auto" '
                             'style:text-underline-color="font-color"')
            if 'S' in combo:
                props.append('style:text-line-through-style="solid"')
            if 'C' in combo:
                props.append('style:font-name="Liberation Mono"')
            out.append(f'<style:style style:name="T{name}" style:family="text"><style:text-properties '
                       f'{" ".join(props)}/></style:style>')
    return ''.join(out)


class Pictures:
    """Images embarquées dans l'ODT (dédupliquées)."""

    def __init__(self):
        self.entries = {}   # chemin de l'archive -> (octets, type MIME)

    def frame(self, path, size='0.55cm'):
        name = f'Pictures/p{hashlib.sha1(path.name.encode()).hexdigest()[:12]}.png'
        try:
            self.entries.setdefault(name, (path.read_bytes(), 'image/png'))
        except OSError:
            return ''
        return self._frame(name, size, size)

    def thumbnail(self, data, width_cm=4.0):
        """Vignette JPEG (octets) recadrée au format 4:3 exact : toutes ont la même hauteur."""
        with Image.open(io.BytesIO(data)) as picture:
            picture = picture.convert('RGB')
            width, height = picture.size
            if height * 4 > width * 3:      # trop haute : on garde le haut (début des documents)
                picture = picture.crop((0, 0, width, round(width * 3 / 4)))
            elif height * 4 < width * 3:    # trop large : on garde le centre
                target = round(height * 4 / 3)
                offset = (width - target) // 2
                picture = picture.crop((offset, 0, offset + target, height))
            picture = picture.resize((480, 360), Image.LANCZOS)
            width, height = picture.size
            buffer = io.BytesIO()
            picture.save(buffer, 'JPEG', quality=80)
        name = f'Pictures/v{hashlib.sha1(buffer.getvalue()).hexdigest()[:12]}.jpg'
        self.entries.setdefault(name, (buffer.getvalue(), 'image/jpeg'))
        return self._frame(name, f'{width_cm}cm', f'{width_cm * height / width:.2f}cm')

    @staticmethod
    def _frame(name, width, height):
        return (f'<draw:frame draw:style-name="Image" text:anchor-type="as-char" svg:width="{width}" svg:height="{height}">'
                f'<draw:image xlink:href="{name}" xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/>'
                '</draw:frame>')


def chips(values, duration):
    parts = [f'<text:span text:style-name="Chip"> {escape(v)} </text:span>' for v in values if v]
    if duration:
        parts.append(f'<text:span text:style-name="ChipDuree"> {escape(duration)} </text:span>')
    return '<text:s/>'.join(parts)


def facts_table(facts):
    if not facts:
        return ''
    cells = ''.join(
        '<table:table-cell table:style-name="CFaits" office:value-type="string">'
        f'<text:p text:style-name="FaitLabel">{escape(label.upper())}</text:p>'
        f'<text:p text:style-name="FaitValeur">{escape(value)}</text:p></table:table-cell>'
        for label, value in facts)
    columns = ''.join('<table:table-column/>' for _ in facts)
    return (f'<table:table table:name="Faits" table:style-name="TFaits">{columns}'
            f'<table:table-row>{cells}</table:table-row></table:table><text:p text:style-name="Espace"/>')


def tag_groups_xml(groups, pictures):
    out = []
    separator = '<text:s text:c="4"/>'
    for label, tags in groups:
        if not tags:
            continue
        items = []
        for tag in tags:
            image = ''
            try:
                image = pictures.frame(files.pictogram_path(tag))
            except HTTPException:
                pass
            items.append(f'{image}{escape(tag.label or "")}')
        out.append(f'<text:p text:style-name="Etiquette">{escape(label.upper())}</text:p>'
                   f'<text:p text:style-name="Tags">{separator.join(items)}</text:p>')
    return ''.join(out)


MEDIA_COLUMNS = 4


def media_list(entries, pictures):
    """Grille de vignettes légendées ; `entries` = [(titre, octets de vignette ou None)]."""
    if not entries:
        return ''
    rows = []
    for start in range(0, len(entries), MEDIA_COLUMNS):
        cells = []
        for label, thumb in entries[start:start + MEDIA_COLUMNS]:
            image = ''
            if thumb:
                try:
                    image = f'<text:p text:style-name="VignetteImage">{pictures.thumbnail(thumb)}</text:p>'
                except Exception:
                    image = ''
            cells.append('<table:table-cell table:style-name="CMedia" office:value-type="string">'
                         f'{image}<text:p text:style-name="VignetteLegende">{escape(label)}</text:p></table:table-cell>')
        cells += ['<table:table-cell table:style-name="CMedia" office:value-type="string"><text:p/></table:table-cell>'
                  ] * (MEDIA_COLUMNS - len(cells))
        rows.append(f'<table:table-row>{"".join(cells)}</table:table-row>')
    columns = '<table:table-column/>' * MEDIA_COLUMNS
    return ('<text:p text:style-name="Etiquette">MÉDIAS</text:p>'
            f'<table:table table:name="Medias{next(BLOCK_IDS)}" table:style-name="TFaits">{columns}{"".join(rows)}</table:table>'
            '<text:p text:style-name="Espace"/>')


def build_odt(fiche, pictures):
    """`fiche` : dict décrit par `animation_fiche` / `material_fiche`."""
    body = [f'<text:p text:style-name="Titre">{escape(fiche["titre"])}</text:p>']
    if fiche.get('meta'):
        body.append(f'<text:p text:style-name="Meta">{escape(fiche["meta"])}</text:p>')
    body.append(facts_table(fiche.get('facts', [])))
    groups_xml = tag_groups_xml(fiche.get('tag_groups', []), pictures)
    body.append(groups_xml)
    if groups_xml:
        body.append('<text:p text:style-name="EspaceGrand"/>')
    accents = set(ACCENTS.values())
    for key, label, text in fiche.get('blocks', []):
        body.append(block(label, text, ACCENTS.get(key, PRIMARY)))
    sequences = fiche.get('sequences', [])
    if sequences:
        body.append('<text:p text:style-name="Titre2">Les séquences</text:p>')
    for index, seq in enumerate(sequences, 1):
        color = seq['color']
        accents.add(color)
        number = f'<text:span text:style-name="Num{color[1:]}"> {index} </text:span>'
        body.append(f'<text:p text:style-name="SeqTitre{color[1:]}">{number} {escape(seq["titre"])}</text:p>')
        body.append(f'<text:p text:style-name="Puces">{chips(seq["chips"], seq["duree"])}</text:p>')
        for key, label, text in seq['blocks']:
            body.append(block(label, text, ACCENTS.get(key, PRIMARY)))
        body.append(media_list(seq['medias'], pictures))
    body.append(media_list(fiche.get('medias', []), pictures))
    colors = {seq['color'] for seq in sequences}
    seq_styles = ''.join(
        f'<style:style style:name="SeqTitre{c[1:]}" style:family="paragraph"><style:paragraph-properties '
        f'fo:margin-top="0.45cm" fo:margin-bottom="0.15cm" fo:keep-with-next="always" fo:border-bottom="0.75pt solid {mix(c, 0.4)}" '
        f'fo:padding-bottom="0.08cm"/><style:text-properties fo:font-size="13pt" fo:font-weight="bold" fo:color="{c}"/></style:style>'
        f'<style:style style:name="Num{c[1:]}" style:family="text"><style:text-properties fo:color="#ffffff" '
        f'fo:background-color="{c}" fo:font-weight="bold"/></style:style>' for c in colors)
    static = STATIC_STYLES.replace('\n', '')
    namespaces = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                  'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
                  'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
                  'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
                  'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
                  'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
                  'xmlns:xlink="http://www.w3.org/1999/xlink" '
                  'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
                  'xmlns:dc="http://purl.org/dc/elements/1.1/"')
    content = ('<?xml version="1.0" encoding="UTF-8"?>'
               f'<office:document-content {namespaces} office:version="1.2">'
               f'<office:automatic-styles>{static}{block_styles(accents)}{text_styles()}{seq_styles}</office:automatic-styles>'
               f'<office:body><office:text>{"".join(body)}</office:text></office:body></office:document-content>')
    styles = ('<?xml version="1.0" encoding="UTF-8"?>'
              f'<office:document-styles {namespaces} office:version="1.2">'
              '<office:styles><style:default-style style:family="paragraph"><style:text-properties '
              'fo:font-family="\'Liberation Sans\', Arial, sans-serif" fo:font-size="10.5pt" fo:language="fr" fo:country="FR"/>'
              '</style:default-style></office:styles>'
              '<office:automatic-styles><style:page-layout style:name="pm1"><style:page-layout-properties '
              'fo:page-width="21cm" fo:page-height="29.7cm" fo:margin-top="1.6cm" fo:margin-bottom="1.6cm" '
              'fo:margin-left="1.8cm" fo:margin-right="1.8cm"/></style:page-layout></office:automatic-styles>'
              '<office:master-styles><style:master-page style:name="Standard" style:page-layout-name="pm1"/>'
              '</office:master-styles></office:document-styles>')
    manifest_entries = ''.join(
        f'<manifest:file-entry manifest:full-path="{name}" manifest:media-type="{mime}"/>'
        for name, (_, mime) in pictures.entries.items())
    manifest = ('<?xml version="1.0" encoding="UTF-8"?><manifest:manifest '
                'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">'
                '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>'
                '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
                '<manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>'
                f'{manifest_entries}</manifest:manifest>')
    output = io.BytesIO()
    with ZipFile(output, 'w') as archive:
        archive.writestr('mimetype', 'application/vnd.oasis.opendocument.text', compress_type=ZIP_STORED)
        archive.writestr('content.xml', content, compress_type=ZIP_DEFLATED)
        archive.writestr('styles.xml', styles, compress_type=ZIP_DEFLATED)
        for name, (data, _) in pictures.entries.items():
            archive.writestr(name, data, compress_type=ZIP_DEFLATED)
        archive.writestr('META-INF/manifest.xml', manifest, compress_type=ZIP_DEFLATED)
    return output.getvalue()


def odt_to_pdf(odt_bytes, timeout=120):
    """PDF du même document via LibreOffice ; None si la conversion est impossible."""
    try:
        with tempfile.TemporaryDirectory(prefix='kit_') as tmp:
            root = Path(tmp)
            source = root / 'fiche.odt'
            source.write_bytes(odt_bytes)
            return files.office_to_pdf(source, root, timeout).read_bytes()
    except HTTPException:
        return None


# --- Description des fiches -------------------------------------------------

def animation_fiche(item):
    """Données de la fiche animation dans le même ordre et avec les mêmes libellés que l'écran."""
    duration = item.fk_duree.label if item.fk_duree else ''
    minutes = sum(seq.duree_minutes for seq in item.sequences if isinstance(seq.duree_minutes, int))
    sequences_label = str(len(item.sequences))
    if minutes:
        sequences_label += f' ({format_minutes(minutes)})'
    groups = []
    for reference in ('ref.thematiques', 'ref.saison', 'ref.public', 'ref.lieux'):
        tags = [tag for tag in item.tags if tag.reference == reference]
        groups.append((group_label(reference), tags))
    sequences = []
    for seq in item.sequences:
        type_label = seq.fk_type_seq.label if getattr(seq, 'fk_type_seq', None) else ''
        sequences.append({
            'titre': seq.titre,
            'color': sequence_color(type_label),
            'chips': [type_label, seq.fk_approche.label if seq.fk_approche else '',
                      seq.fk_modalite.label if seq.fk_modalite else ''],
            'duree': format_minutes(seq.duree_minutes),
            'blocks': [('description', 'Déroulement', seq.description),
                       ('objectifs', 'Objectifs', seq.objectifs),
                       ('materiel', 'Matériel complémentaire', seq.materiel_div)],
            'materiel': list(seq.materiel),
            'medias': [],
        })
    return {
        'titre': item.titre,
        'meta': ' · '.join(part for part in (STATUTS.get(item.statut, ''), item.auteurs,
                                             f'modifiée le {item.date_modif}' if item.date_modif else '') if part),
        'facts': [(label, value) for label, value in (('Durée', duration), ('Lieu', item.lieu or ''),
                                                      ('Séquences', sequences_label)) if value],
        'tag_groups': groups,
        'blocks': [('description', 'Description', item.description), ('objectifs', 'Objectifs', item.objectifs),
                   ('pre_anim', 'Avant l’animation', item.pre_anim), ('post_anim', 'Après l’animation', item.post_anim),
                   ('public_specifique', 'Public spécifique', item.public_specifique)],
        'sequences': sequences,
    }


GROUP_LABELS = {'ref.thematiques': 'Thématiques', 'ref.saison': 'Saison', 'ref.public': 'Public', 'ref.lieux': 'Lieux'}


def group_label(reference):
    return GROUP_LABELS.get(reference, reference)


def material_fiche(item):
    facts = [(label, getattr(item, name).label) for label, name in
             (('Type', 'fk_type_mat'), ('Difficulté', 'difficulte'), ('Catégorie', 'fk_type_mat_outil'))
             if getattr(item, name, None) is not None and getattr(item, name).label]
    return {
        'titre': item.nom,
        'meta': f'modifié le {item.date_modif}' if item.date_modif else '',
        'facts': facts,
        'tag_groups': [('Thématiques', list(item.thematiques))],
        'blocks': [('description', 'Description / Consigne', item.description),
                   ('variante', 'Variante', item.variante), ('materiel', 'Matériel', item.materiel)],
        'sequences': [],
        'materiel': [item],
    }


def format_minutes(minutes):
    if not isinstance(minutes, int) or minutes <= 0:
        return ''
    if minutes < 60:
        return f'{minutes} min'
    return f'{minutes // 60} h {minutes % 60:02d}' if minutes % 60 else f'{minutes // 60} h'


def unique_name(name, taken):
    stem, dot, extension = name.rpartition('.')
    if not dot:
        stem, extension = name, ''
    candidate, counter = name, 2
    while candidate.lower() in taken:
        candidate = f'{stem} ({counter})' + (f'.{extension}' if extension else '')
        counter += 1
    taken.add(candidate.lower())
    return candidate


AUDIO_EXTENSIONS = {'.mp3', '.wma', '.wav', '.ogg', '.m4a', '.aac', '.flac'}


def audio_tile(extension):
    """Tuile violette avec note de musique, comme celle de la fiche à l'écran (4:3)."""
    scale, width, height = 4, 480, 360
    image = Image.new('RGB', (width * scale, height * scale), '#6b4fa0')
    draw = ImageDraw.Draw(image)
    unit = 5.5 * scale                      # l'icône de 24 unités occupe ~168 px
    left, top = (width * scale - 24 * unit) / 2, (height * scale - 24 * unit) / 2 - 18 * scale
    point = lambda x, y: (left + x * unit, top + y * unit)
    stroke = round(1.7 * unit)
    draw.line([point(9, 18), point(9, 5), point(21, 3), point(21, 16)], fill='white', width=stroke, joint='curve')
    for cx, cy in ((6, 18), (18, 16)):
        draw.ellipse([*point(cx - 3, cy - 3), *point(cx + 3, cy + 3)], outline='white', width=stroke)
    label = extension.lstrip('.').upper()
    if label:
        font = None
        for name in ('LiberationSans-Bold.ttf', 'DejaVuSans-Bold.ttf', 'Arial Bold.ttf'):
            try:
                font = ImageFont.truetype(name, 24 * scale)
                break
            except OSError:
                continue
        font = font or ImageFont.load_default(size=24 * scale)
        draw.text((width * scale / 2, 300 * scale), label, fill='white', font=font, anchor='mm')
    image = image.resize((width, height), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', quality=85)
    return buffer.getvalue()


def thumbnail_bytes(media, source):
    """Vignette du média ; tuile « note » pour les sons ; None si le format ne s'y prête pas."""
    if source.suffix.lower() in AUDIO_EXTENSIONS:
        return audio_tile(source.suffix)
    try:
        data = files.thumbnail_file(media).read_bytes()
    except Exception:
        return None
    if (mimetypes.guess_type(source.name)[0] or '').startswith('video/'):
        try:
            return with_play_badge(data)
        except Exception:
            return data
    return data


def with_play_badge(data):
    """Pastille « lecture » au centre, comme sur les vignettes vidéo de la fiche."""
    scale = 4
    with Image.open(io.BytesIO(data)) as source:
        base = source.convert('RGB')
    width, height = base.size
    layer = Image.new('RGBA', (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    radius = round(width * 0.13 * scale)
    cx, cy = width * scale / 2, height * scale / 2
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(0, 0, 0, 153),
                 outline=(255, 255, 255, 255), width=max(2, round(radius * 0.09)))
    half, length = radius * 0.41, radius * 0.68
    draw.polygon([(cx - length * 0.35, cy - half), (cx - length * 0.35, cy + half),
                  (cx + length * 0.65, cy)], fill=(255, 255, 255, 255))
    layer = layer.resize((width, height), Image.LANCZOS)
    base.paste(layer, (0, 0), layer)
    buffer = io.BytesIO()
    base.save(buffer, 'JPEG', quality=85)
    return buffer.getvalue()


def export_kit(fiche, with_pdf=True):
    """ZIP : fiche ODT, fiche PDF et médias nommés d'après leur titre."""
    pictures = Pictures()
    taken = set()
    archive_io = io.BytesIO()
    base = safe_name(fiche['titre'], 'fiche')
    with ZipFile(archive_io, 'w', compression=ZIP_DEFLATED) as archive:
        media_entries = []
        groups = [(seq['materiel'], seq['medias']) for seq in fiche['sequences']]
        if fiche.get('materiel'):
            fiche['medias'] = []
            groups.append((fiche['materiel'], fiche['medias']))
        for materiel, labels in groups:
            for media in {item.id: item for item in materiel}.values():
                name = safe_name(media.nom, f'media-{media.id}')
                label = name
                thumb = None
                if media.url:
                    try:
                        source = files.media_path(media)
                    except NotFound:
                        source = None
                    if source is not None:
                        filename = unique_name(name + source.suffix.lower(), taken)
                        media_entries.append((source, filename))
                        label = filename
                        thumb = thumbnail_bytes(media, source)
                labels.append((label, thumb))
        odt = build_odt(fiche, pictures)
        archive.writestr(unique_name(base + '.odt', taken), odt)
        if with_pdf:
            pdf = odt_to_pdf(odt)
            if pdf:
                archive.writestr(unique_name(base + '.pdf', taken), pdf)
        for source, filename in media_entries:
            archive.write(source, f'medias/{filename}')
    archive_io.seek(0)
    return archive_io
