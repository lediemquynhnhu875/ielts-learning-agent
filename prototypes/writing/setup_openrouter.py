"""Local interactive configuration; no API call and no key logging."""
from getpass import getpass
from pathlib import Path
import re

def main():
    path = Path(__file__).resolve().parent / '.env'
    if path.exists() and input('.env đã tồn tại. Gõ REPLACE để thay: ').strip() != 'REPLACE': return
    print('Key: https://openrouter.ai/settings/keys')
    print('Model IDs: https://openrouter.ai/models — chọn model hỗ trợ JSON.')
    key = getpass('API key (nhập ẩn): ').strip()
    if not key or any(c.isspace() for c in key): raise SystemExit('API key không hợp lệ.')
    values = {'OPENROUTER_API_KEY':key,'OPENROUTER_BASE_URL':'https://openrouter.ai/api/v1'}
    for role in ('A','B','MODERATOR'):
        model = input(f'Model ID cho {role}: ').strip()
        if not re.fullmatch(r'[A-Za-z0-9_./:-]+', model) or '/' not in model: raise SystemExit('ID cần dạng provider/model. Chưa lưu.')
        values['WRITING_' + role + '_MODEL'] = model
    path.write_text('\n'.join(k+'='+v for k,v in values.items())+'\n',encoding='utf-8')
    print('Đã lưu .env local. Chưa gọi API. Nhập rubric rồi khởi động lại app.')

if __name__ == '__main__': main()
