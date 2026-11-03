"""Create a consistent SQL backup using mysqldump, without printing credentials."""
from pathlib import Path
from datetime import datetime
import os
import subprocess
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]

def main():
    config=dotenv_values(ROOT/'.env')
    homes=sorted((ROOT/'runtime').glob('mysql-*-winx64'))
    if not homes:raise RuntimeError('Project MySQL tools are missing.')
    target=ROOT/'runtime/backups'/('retail_rfm_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.sql')
    target.parent.mkdir(exist_ok=True)
    child_env=os.environ.copy()
    child_env['MYSQL_PWD']=config['MYSQL_PASSWORD']
    executable=homes[-1]/'bin/mysqldump.exe'
    args=['mysqldump','--no-defaults','--host='+config['MYSQL_HOST'],'--port='+config['MYSQL_PORT'],
          '--user='+config['MYSQL_USER'],'--default-character-set=utf8mb4','--single-transaction','--quick',
          '--no-tablespaces','--set-gtid-purged=OFF','--column-statistics=0','--skip-add-locks',config['MYSQL_DATABASE']]
    with target.open('wb') as f:
        subprocess.run(args,executable=str(executable),stdout=f,stderr=subprocess.PIPE,env=child_env,check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    print('Backup:',target,'bytes:',target.stat().st_size)
    return target

if __name__=='__main__':main()
