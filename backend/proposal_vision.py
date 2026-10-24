"""Page images remain available for human verification of model transcriptions."""
import base64
import hashlib
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps
from .models import Nebius
from .proposal_schema import VisualPage
from .store import Conflict


def decode(encoded):
    try:
        data = base64.b64decode(encoded,validate=True)
    except ValueError as exc:
        raise ValueError('File is not valid base64') from exc
    if not data or len(data)>3000000:
        raise ValueError('Use a document between 1 byte and 3 MB')
    return data


def page_image(filename, data, page=1):
    if Path(filename).suffix.lower() == '.pdf':
        import pdfplumber
        try:
            with pdfplumber.open(BytesIO(data)) as pdf:
                if not 1 <= len(pdf.pages) <= 6:
                    raise ValueError('Visual import supports 1 to 6 pages; split larger PDFs')
                if not 1 <= page <= len(pdf.pages):
                    raise ValueError('Page is outside this document')
                target = pdf.pages[page-1]
                # Bound raster allocation before rendering unusual PDF page dimensions.
                scale = min(2,1600/max(target.width,target.height))
                image = target.to_image(resolution=72*scale).original
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('Could not render this PDF page') from exc
    else:
        if page != 1 or Path(filename).suffix.lower() not in {'.png','.jpg','.jpeg'}:
            raise ValueError('Visual import accepts PDF, PNG and JPEG')
        try:
            image = Image.open(BytesIO(data))
            if image.width*image.height>20000000 or getattr(image,'n_frames',1)!=1:
                raise ValueError('Use a single image below 20 megapixels')
            if image.format not in {'PNG','JPEG'}:
                raise ValueError('Choose a PNG or JPEG image')
            image=ImageOps.exif_transpose(image)
            image.load()
        except (Image.DecompressionBombError, OSError) as exc:
            raise ValueError('Image is invalid or too large') from exc
    image = image.convert('RGB')
    image.thumbnail((1600,1600))
    output=BytesIO();image.save(output,format='PNG')
    return output.getvalue()


def import_visual(config, filename, encoded):
    data=decode(encoded)
    count=1
    if Path(filename).suffix.lower()=='.pdf':
        import pdfplumber
        try:
            with pdfplumber.open(BytesIO(data)) as pdf:
                count=len(pdf.pages)
        except Exception as exc:
            raise ValueError('Could not read this PDF') from exc
        if not 1<=count<=6:
            raise ValueError('Visual import supports 1 to 6 pages; split larger PDFs')
    model=config.get('vision_model')
    if not model:
        raise ValueError('Configure vision_model before visual import')
    text,locations,pages='',[],[]
    for page in range(1,count+1):
        png=page_image(filename,data,page)
        raw,usage=Nebius(config).complete('visual_transcribe.txt',{'page':page},model=model,thinking=False,
            images=['data:image/png;base64,'+base64.b64encode(png).decode()],max_tokens=6000)
        result=VisualPage.model_validate(raw)
        if not result.text.strip():
            raise ValueError(f'Page {page} produced no readable transcription')
        locations.append({'location':f'Page {page} (visual transcription)','start':len(text)})
        text+=result.text+'\n'
        pages.append({'page':page,'uncertain_passages':result.uncertain_passages,'analysis':usage})
    if len(text)>80000:
        raise ValueError('Transcription exceeds 80000 characters; split this document')
    return text,locations,{'method':'nebius_vision','model':model,'review_required':True,'pages':pages,
                           'original_sha256':hashlib.sha256(data).hexdigest()}


def confirm(service,pid,sid,body):
    if not body.text.strip():
        raise ValueError('Transcription must contain readable text')
    def mutate(d):
        source=next((s for s in d['sources'] if s['id']==sid),None)
        if not source or not (source.get('ingestion') or {}).get('review_required'):
            raise ValueError('Choose a visual source awaiting transcription review')
        if source.get('analyzed') or source.get('transcription_reviewed'):
            raise Conflict('This transcription was already reviewed; import a corrected source instead')
        source['machine_transcription']=source['text']
        # Corrected text can alter page boundaries, so do not retain inaccurate offsets.
        if body.text != source['text']:
            source['locations']=[{'location':'Human-corrected transcription; compare original pages','start':0}]
        source['text']=body.text
        source['hash']=hashlib.sha256(body.text.encode()).hexdigest()
        source['transcription_reviewed']=True
        return {'source_id':sid,'corrected':body.text!=source['machine_transcription']}
    return service.change(pid,body.expected_revision,'visual_transcription_confirmed',mutate)
