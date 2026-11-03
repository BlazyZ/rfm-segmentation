"""Download vendor assets and a portable, project-local MySQL distribution."""
from pathlib import Path
import concurrent.futures
import urllib.request
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]

def available(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=25) as r:
            return url if r.status == 200 else None
    except Exception:
        return None

def main():
    target = ROOT / 'rfm/static/vendor/echarts.min.js'
    if not target.exists():
        urllib.request.urlretrieve('https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js', target)
    print('ECharts ready', flush=True)
    urls = [f'https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-8.4.{n}-winx64.zip' for n in (9, 8, 7)]
    urls += ['https://cdn.mysql.com/archives/mysql-8.4/mysql-8.4.6-winx64.zip']
    with concurrent.futures.ThreadPoolExecutor() as pool:
        choices = list(pool.map(available, urls))
    url = next((x for x in choices if x), None)
    if not url:
        raise RuntimeError('No MySQL download is accessible')
    print('MySQL source:', url, flush=True)
    archive = ROOT / 'runtime/mysql.zip'
    urllib.request.urlretrieve(url, archive)
    print('Downloaded', archive.stat().st_size, flush=True)
    with zipfile.ZipFile(archive) as z:
        z.extractall(ROOT / 'runtime')
    print('Extracted MySQL', flush=True)

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
