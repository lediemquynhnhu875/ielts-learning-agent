"""Import Task 2 tables from an official PDF supplied by the user.
Install pypdf only for this script: python -m pip install pypdf.
Full Task 2 text is retained per criterion, without fabricating band chunks.
"""
import argparse, json
from pathlib import Path
from pypdf import PdfReader

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf', help='Local official Writing Band Descriptors PDF')
    parser.add_argument('--pages', default='7,8,9', help='1-based Task 2 table pages; inspect your PDF first')
    parser.add_argument('--version', default='May 2023')
    args = parser.parse_args()
    reader = PdfReader(args.pdf)
    pages = [int(x) for x in args.pages.split(',')]
    text = '\n\n'.join(reader.pages[p - 1].extract_text() or '' for p in pages)
    if 'Task Response' not in text or 'Lexical' not in text or len(text) < 3000:
        raise SystemExit('Không nhận diện đủ bảng Task 2. Kiểm tra --pages hoặc PDF.')
    data = {'source_url': 'https://ielts.org/cdn/ielts-guides/ielts-writing-band-descriptors.pdf', 'version': args.version, 'pages': pages, 'retrieval': 'full_task2_tables_per_criterion', 'chunks': {f'W2-{c}-FULL': {'criterion': c, 'text': f'Assess only criterion {c} using its column in these complete Task 2 tables:\n' + text} for c in ('TR','CC','LR','GRA')}}
    path = Path(__file__).resolve().parent / 'rubric.json'
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Đã ghi', path, '— cần kiểm tra thủ công nội dung và cột trước khi chấm thật.')

if __name__ == '__main__': main()
