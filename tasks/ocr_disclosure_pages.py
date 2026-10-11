"""OCR source PDF pages for review; never import OCR output as verified facts."""
import argparse
import hashlib
import json
from pathlib import Path
import pymupdf
from rapidocr_onnxruntime import RapidOCR


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True)
    parser.add_argument('--pages',type=int,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
    with pymupdf.open(args.pdf) as pdf:
        for number in args.pages:
            if not 1 <= number <= len(pdf):raise ValueError('Page outside PDF')
            target=args.output/f'page-{number}.json'
            if target.exists():continue
            png=pdf[number-1].get_pixmap(matrix=pymupdf.Matrix(2,2)).tobytes('png')
            (args.output/f'page-{number}.png').write_bytes(png)
            rows,times=engine(png)
            payload=dict(source=str(args.pdf.resolve()),page=number,
                pdf_sha256=hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
                rows=rows or [],independently_verified=False)
            target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'Page {number}: {len(rows or [])} OCR boxes',flush=True)


if __name__=='__main__':main()
