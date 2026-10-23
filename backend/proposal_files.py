"""Bounded document parsing and portable OOXML proposal export."""
import base64
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile


def read_document(filename, encoded):
    try:
        data = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError('File is not valid base64') from exc
    if len(data) > 3_000_000:
        raise ValueError('Documents must be smaller than 3 MB')
    extension = Path(filename).suffix.lower()
    if extension in {'.txt', '.md', '.eml'}:
        return data.decode('utf-8'), [{'location': 'text', 'start': 0}]
    if extension == '.docx':
        try:
            with ZipFile(BytesIO(data)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 15_000_000:
                    raise ValueError('Expanded document is too large')
                xml = archive.read('word/document.xml')
            if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                raise ValueError('XML entity declarations are not allowed')
            root = ET.fromstring(xml)
            paragraphs = [''.join(p.itertext()) for p in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')]
            text, locations = '', []
            for i, paragraph in enumerate(paragraphs):
                locations.append({'location': f'Paragraph {i + 1}', 'start': len(text)})
                text += paragraph + '\n'
            return text, locations
        except (BadZipFile, KeyError, ET.ParseError) as exc:
            raise ValueError('DOCX could not be read') from exc
    if extension == '.pdf':
        import pdfplumber
        try:
            with pdfplumber.open(BytesIO(data)) as pdf:
                if len(pdf.pages) > 25:
                    raise ValueError('Use a document with 25 pages or fewer')
                text, locations = '', []
                for i, page in enumerate(pdf.pages):
                    part = page.extract_text() or ''
                    if not part.strip():
                        raise ValueError(f'Page {i + 1} is unreadable; OCR is required and is not implemented')
                    locations.append({'location': f'Page {i + 1}', 'start': len(text)})
                    text += part + '\n'
                return text, locations
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('PDF could not be read; try a text-based document') from exc
    raise ValueError('Supported files: PDF, DOCX, TXT, MD and EML; macros are not supported')


def proposal_docx(document):
    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    def p(text, style='Normal'):
        return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
    body = p(document['title'], 'Title') + p('Prepared for ' + document['client'])
    body += p('This proposal addresses the reviewed requirements for the client opportunity. The sections below contain the answers approved for this package.')
    for req in document['requirements']:
        if req.get('status') == 'withdrawn':
            continue
        body += p(req['title'], 'Heading1')
        body += p(document['answers'].get(req['key'], {}).get('text', 'Not included'))
    body += '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:bottom="1134" w:left="1134" w:right="1134"/></w:sectPr>'
    styles = f'''<w:styles xmlns:w="{ns}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/><w:color w:val="000000"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="36"/><w:color w:val="000000"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr><w:keepNext/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/><w:color w:val="000000"/></w:rPr></w:style></w:styles>'''
    content = BytesIO()
    with ZipFile(content, 'w', ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml',f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>')
        z.writestr('word/styles.xml', styles)
        z.writestr('word/_rels/document.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    return content.getvalue()
