"""Start and initialize a project-local MySQL. Never reset an existing data directory."""
from pathlib import Path
import os
import re
import secrets
import subprocess
import time
import sys
import pymysql
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]

def main():
    runtime = ROOT / 'runtime'
    homes = sorted(runtime.glob('mysql-*-winx64'))
    if not homes:
        raise RuntimeError('请先运行 python scripts/fetch_assets.py 下载MySQL。')
    mysql_home = homes[-1]
    datadir = runtime / 'mysql-data'
    env_path = ROOT / '.env'
    if not env_path.exists():
        env_path.write_text('MYSQL_HOST=127.0.0.1\nMYSQL_PORT=3307\nMYSQL_DATABASE=retail_rfm\nMYSQL_USER=rfm_app\n'
                            f'MYSQL_PASSWORD={secrets.token_urlsafe(24)}\nAPP_HOST=127.0.0.1\nAPP_PORT=5000\nMAX_UPLOAD_MB=300\n', encoding='utf-8')
    config = dotenv_values(env_path)
    port = int(config['MYSQL_PORT'])
    if config['MYSQL_HOST'] != '127.0.0.1':
        raise RuntimeError('此脚本仅用于项目内127.0.0.1实例，外部数据库请使用schema.sql初始化。')
    for key in ('MYSQL_DATABASE', 'MYSQL_USER'):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,47}', config[key]):
            raise ValueError(f'{key}须为英文字母开头的字母数字下划线。')
    admin_path = runtime / 'mysql-admin.env'
    if not admin_path.exists():
        if datadir.exists():
            raise RuntimeError('已有数据目录但缺少管理员配置，拒绝重置；请检查runtime/mysql-admin.env。')
        admin_path.write_text('MYSQL_ROOT_PASSWORD=' + secrets.token_urlsafe(32) + '\n', encoding='utf-8')
    admin_password = dotenv_values(admin_path)['MYSQL_ROOT_PASSWORD']
    executable = str(mysql_home / 'bin/mysqld.exe')
    if not datadir.exists():
        print('正在初始化项目MySQL数据目录……', flush=True)
        subprocess.run(['mysqld', '--no-defaults', '--initialize-insecure', '--basedir=.', '--datadir=../mysql-data'], executable=executable, cwd=mysql_home, check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    def connect(password):
        return pymysql.connect(host='127.0.0.1', port=port, user='root', password=password, connect_timeout=2, autocommit=True, charset='utf8mb4')
    db = None
    try:
        db = connect(admin_password)
    except pymysql.err.OperationalError as exc:
        if exc.args[0] == 1045:
            db = connect('')
        else:
            log = open(runtime / 'mysql-console.log', 'ab')
            # MySQL's Windows argument parser can truncate a Unicode argv[0]. Use an ASCII
            # argv[0] and relative paths while executable= still selects the exact binary.
            proc = subprocess.Popen(['mysqld', '--no-defaults', '--basedir=.', '--datadir=../mysql-data',
                f'--port={port}', '--bind-address=127.0.0.1', '--mysqlx=OFF', '--character-set-server=utf8mb4',
                '--max-allowed-packet=64M', '--innodb-buffer-pool-size=256M', '--log-error=../mysql-error.log'],
                executable=executable, cwd=mysql_home, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            log.close()
            for _ in range(60):
                try:
                    db = connect(admin_password)
                    break
                except pymysql.err.OperationalError as error:
                    if error.args[0] == 1045:
                        db = connect('')
                        break
                    if proc.poll() is not None:
                        raise RuntimeError('MySQL启动失败，查看runtime/mysql-error.log；可能端口被占用。') from error
                    time.sleep(.5)
    if db is None:
        raise RuntimeError('MySQL30秒内未就绪，查看runtime/mysql-error.log。')
    with db, db.cursor() as cur:
        # @@datadir may be returned with lossy Unicode by MySQL on Windows.
        # Compare the instance UUID with our own auto.cnf instead of trusting that string.
        cur.execute('SELECT @@server_uuid')
        actual_uuid = cur.fetchone()[0]
        uuid_match = re.search(r'server-uuid=([a-f0-9-]+)', (datadir / 'auto.cnf').read_text(encoding='ascii'))
        if not uuid_match or actual_uuid != uuid_match.group(1):
            raise RuntimeError('端口由其他MySQL实例占用，拒绝修改；请改.env中的端口。')
        cur.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (admin_password,))
        cur.execute(f'CREATE DATABASE IF NOT EXISTS `{config["MYSQL_DATABASE"]}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
        cur.execute('CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s', (config['MYSQL_USER'], '127.0.0.1', config['MYSQL_PASSWORD']))
        cur.execute('ALTER USER %s@%s IDENTIFIED BY %s', (config['MYSQL_USER'], '127.0.0.1', config['MYSQL_PASSWORD']))
        cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON `{config["MYSQL_DATABASE"]}`.* TO %s@%s', (config['MYSQL_USER'], '127.0.0.1'))
        cur.execute(f'USE `{config["MYSQL_DATABASE"]}`')
        for statement in (ROOT / 'schema.sql').read_text(encoding='utf-8').split(';'):
            if statement.strip():
                cur.execute(statement)
    print(f'MySQL已就绪：127.0.0.1:{port} / {config["MYSQL_DATABASE"]}；密码保存在.env，不公开输出。', flush=True)

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
