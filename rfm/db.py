from contextlib import contextmanager
import os
from pathlib import Path
import pymysql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')

def connect(*, autocommit=True, cursorclass=pymysql.cursors.DictCursor):
    return pymysql.connect(host=os.getenv('MYSQL_HOST', '127.0.0.1'), port=int(os.getenv('MYSQL_PORT', '3307')),
        user=os.getenv('MYSQL_USER', 'rfm_app'), password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DATABASE', 'retail_rfm'), charset='utf8mb4', cursorclass=cursorclass,
        connect_timeout=5, read_timeout=300, write_timeout=300, autocommit=autocommit)

def query(sql, params=(), one=False):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone() if one else cur.fetchall()

def execute(sql, params=()):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount
