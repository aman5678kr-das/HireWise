from pathlib import Path
import json, urllib.request, zipfile, concurrent.futures
root=Path('work/runtimes'); root.mkdir(parents=True,exist_ok=True)
def fetch(label,url,dest):
 dest=Path(dest); dest.parent.mkdir(parents=True,exist_ok=True)
 req=urllib.request.Request(url,headers={'User-Agent':'HirewiseLocalDev/1.0'})
 with urllib.request.urlopen(req,timeout=60) as src, dest.open('wb') as out:
  total=int(src.headers.get('Content-Length') or 0); done=0
  while True:
   b=src.read(1024*1024)
   if not b: break
   out.write(b); done+=len(b)
   if done%(32*1024*1024)<1024*1024: print(label,round(done/1024/1024),'MB /',round(total/1024/1024),'MB',flush=True)
 print(label,'download complete',flush=True); return dest
def node():
 with urllib.request.urlopen('https://nodejs.org/dist/index.json',timeout=30) as r: versions=json.load(r)
 version=next(x['version'] for x in versions if x['version'].startswith('v22.') and x['lts'])
 z=fetch('Node',f'https://nodejs.org/dist/{version}/node-{version}-win-x64.zip',root/'node.zip')
 out=root/'node'; out.mkdir(exist_ok=True)
 with zipfile.ZipFile(z) as f:
  for name in f.namelist():
   if '/node.exe' in name or '/npm' in name or '/npx' in name or name.endswith('/node_modules/npm/') or '/node_modules/npm/' in name: f.extract(name,out)
 exe=next(out.rglob('node.exe')); (root/'node.path').write_text(str(exe.resolve()),encoding='utf-8')
 print('Node installed at',exe,flush=True)
def postgres():
 z=fetch('PostgreSQL','https://get.enterprisedb.com/postgresql/postgresql-16.4-1-windows-x64-binaries.zip',root/'postgresql.zip')
 out=root/'postgres'; out.mkdir(exist_ok=True)
 with zipfile.ZipFile(z) as f:
  names=[n for n in f.namelist() if n.startswith('pgsql/') and (n.startswith('pgsql/bin/') or n.startswith('pgsql/lib/') or n.startswith('pgsql/share/'))]
  f.extractall(out,names)
 print('PostgreSQL extracted',flush=True)
with concurrent.futures.ThreadPoolExecutor(2) as ex: list(ex.map(lambda fn: fn(),[node,postgres]))
