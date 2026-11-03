"""Restore a SQL backup to a temporary, newly-created database and compare it.
Only the temporary database created by this script is removed at the end.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import uuid
import pymysql
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]

def main():
    started=time.perf_counter()
    config=dotenv_values(ROOT/'.env');admin=dotenv_values(ROOT/'runtime/mysql-admin.env')
    backup=sorted((ROOT/'runtime/backups').glob('*.sql'))[-1]
    executable=sorted((ROOT/'runtime').glob('mysql-*-winx64'))[-1]/'bin/mysql.exe'
    restore_name='rfm_restore_verify_'+uuid.uuid4().hex[:12]
    created=False
    conn=pymysql.connect(host=config['MYSQL_HOST'],port=int(config['MYSQL_PORT']),user='root',password=admin['MYSQL_ROOT_PASSWORD'],autocommit=True,charset='utf8mb4')
    checks=[]
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE `{restore_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
            created=True
        child_env=os.environ.copy();child_env['MYSQL_PWD']=admin['MYSQL_ROOT_PASSWORD']
        with backup.open('rb') as f:
            subprocess.run(['mysql','--no-defaults','--host='+config['MYSQL_HOST'],'--port='+config['MYSQL_PORT'],
                            '--user=root','--default-character-set=utf8mb4',restore_name],executable=str(executable),
                           stdin=f,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=child_env,check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        with conn.cursor() as cur:
            for table,columns in [('analysis_batches','COUNT(*)'),('transaction_lines','COUNT(*),SUM(amount_cents)'),('customer_rfm','COUNT(*),SUM(f),SUM(m_cents),SUM(detail_count)'),('app_state','active_batch_id')]:
                cur.execute(f'SELECT {columns} FROM `{config["MYSQL_DATABASE"]}`.`{table}`')
                original=cur.fetchall()
                cur.execute(f'SELECT {columns} FROM `{restore_name}`.`{table}`')
                restored=cur.fetchall()
                if original!=restored:raise AssertionError(f'Restore mismatch: {table}: {original} != {restored}')
                checks.append({'table':table,'passed':True,'values':[[str(v) for v in row] for row in restored]})
                print('PASS backup restore',table,flush=True)
    finally:
        if created:
            with conn.cursor() as cur:cur.execute(f'DROP DATABASE `{restore_name}`')
        conn.close()
    result={'backup_file':str(backup.relative_to(ROOT)),'bytes':backup.stat().st_size,'elapsed_seconds':round(time.perf_counter()-started,3),
            'temporary_database_removed':True,'checks':checks,'scope':'SQL中的四张表恢复核对；原始与批次文件需独立备份。'}
    (ROOT/'docs/备份恢复验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
