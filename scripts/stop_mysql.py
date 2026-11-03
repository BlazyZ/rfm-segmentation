"""Gracefully stop only the project-owned MySQL instance."""
from pathlib import Path
import re
import pymysql
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]

def main():
    config=dotenv_values(ROOT/'.env')
    admin=dotenv_values(ROOT/'runtime/mysql-admin.env')
    expected=re.search(r'server-uuid=([a-f0-9-]+)',(ROOT/'runtime/mysql-data/auto.cnf').read_text(encoding='ascii')).group(1)
    with pymysql.connect(host=config['MYSQL_HOST'],port=int(config['MYSQL_PORT']),user='root',password=admin['MYSQL_ROOT_PASSWORD']) as conn, conn.cursor() as cur:
        cur.execute('SELECT @@server_uuid')
        if cur.fetchone()[0]!=expected:raise RuntimeError('Different MySQL instance; stop refused.')
        cur.execute('SHUTDOWN')
    print('Project MySQL stopped.')

if __name__=='__main__':main()
