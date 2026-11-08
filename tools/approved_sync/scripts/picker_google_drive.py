"""Manual Google Picker grant. Default dry-run; never uploads or enables sync."""
import argparse,json,logging,os,re,secrets,time,webbrowser
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from google_drive_api import GoogleDriveBackup,authenticated_service

ORIGIN='http://127.0.0.1:17866'

def validated_selection(cfg,selection,service):
    if not isinstance(selection,dict) or set(selection)!={'parent','folder'} or not all(isinstance(value,str) for value in selection.values()):raise ValueError('TWO_FOLDER_SELECTIONS_REQUIRED')
    candidate=dict(cfg,driveParentFolderId=selection['parent'],driveFolderId=selection['folder'])
    GoogleDriveBackup(candidate,service=service,read_only=True)
    # This confirms API identity/permissions, not permission to start scheduled sync.
    candidate.update(driveEnabled=False,driveAccountCheckedByHuman=False,
                     pickerGrantVerified=True)
    return candidate

def render_page(api_key,project_number,token,nonce):
    data=json.dumps(dict(key=api_key,app=project_number,token=token,nonce=nonce)).replace('<','\\u003c')
    return '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<title>小照本機資料夾授權</title><h1>本人選取既有資料夾</h1>
<p>請先選 XiaoZhao，再選其下 ApprovedSource。此頁不會上傳檔案或啟用排程。</p>
<button id="parent" disabled>1 選 XiaoZhao</button>
<button id="folder" disabled>2 選 ApprovedSource</button>
<button id="save" disabled>3 核對並保存目的地（仍停用同步）</button><p id="status"></p>
<script src="https://apis.google.com/js/api.js"></script><script nonce="''' + nonce + '''">
const c=''' + data + ''';const selected={};
function pick(which){
 let view=new google.picker.DocsView(google.picker.ViewId.FOLDERS)
  .setIncludeFolders(true).setSelectFolderEnabled(true);
 if(which==='folder' && selected.parent)view.setParent(selected.parent);
 new google.picker.PickerBuilder().setAppId(c.app).setDeveloperKey(c.key)
 .setOAuthToken(c.token).setOrigin(location.origin).addView(view).setCallback(d=>{
   if(d.action===google.picker.Action.PICKED){selected[which]=d.docs[0].id;
    document.getElementById('status').textContent='已選取；最後仍由 API 核對帳號、名稱與上下層。';
    document.getElementById('folder').disabled=!selected.parent;
    document.getElementById('save').disabled=!(selected.parent&&selected.folder);}
 }).build().setVisible(true);
}
gapi.load('picker',()=>document.getElementById('parent').disabled=false);
document.getElementById('parent').onclick=()=>pick('parent');
document.getElementById('folder').onclick=()=>pick('folder');
document.getElementById('save').onclick=async()=>{
 document.getElementById('save').disabled=true;
 try{const r=await fetch('/'+c.nonce+'/selection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(selected)});
 document.getElementById('status').textContent=r.ok?'核對完成；請關閉頁面，同步仍停用。':'核對失敗；未保存，請關閉頁面檢查設定。';}
 catch(e){document.getElementById('status').textContent='失敗；不要重送，請回本機檢查。';}
};</script></html>'''

def serve_picker(config_path,*,service,credentials,timeout=300):
    config_path=Path(config_path).resolve()
    allowed=(Path(os.environ['LOCALAPPDATA'])/'XiaoZhaoSync/sync_targets.local.json').resolve()
    if config_path!=allowed:raise PermissionError('DEDICATED_PRIVATE_CONFIG_REQUIRED')
    original=config_path.read_bytes();cfg=json.loads(original.decode('utf-8-sig'))
    if cfg.get('driveEnabled') is not False:raise PermissionError('DISABLE_SYNC_BEFORE_PICKER')
    if not re.fullmatch(r'[0-9]{6,30}',str(cfg.get('pickerProjectNumber',''))):raise ValueError('PROJECT_NUMBER_REQUIRED')
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,100}',cfg.get('pickerApiKey','')):raise ValueError('PICKER_KEY_REQUIRED')
    nonce=secrets.token_urlsafe(32)
    page=render_page(cfg['pickerApiKey'],str(cfg['pickerProjectNumber']),credentials.token,nonce).encode()
    state={'done':False,'success':False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,body=b''):
            self.send_response(status);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','strict-origin')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'nonce-"+nonce+"' https://apis.google.com; frame-src https://docs.google.com https://drive.google.com; connect-src 'self' https://*.googleapis.com; style-src 'unsafe-inline'")
            self.end_headers();self.wfile.write(body)
        def valid_host(self):return self.headers.get('Host')=='127.0.0.1:17866'
        def do_GET(self):
            if not self.valid_host() or self.path!='/'+nonce:self.reply(404);return
            self.reply(200,page)
        def do_POST(self):
            if not self.valid_host() or self.path!='/'+nonce+'/selection' or self.headers.get('Origin')!=ORIGIN:
                self.reply(403);return
            if state['done']:self.reply(409);return
            state['done']=True
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=1024 or self.headers.get('Content-Type')!='application/json':raise ValueError('INVALID_BODY')
                selection=json.loads(self.rfile.read(size))
                candidate=validated_selection(cfg,selection,service)
                if config_path.read_bytes()!=original:raise RuntimeError('CONFIG_CHANGED')
                # Preserve the previous private config; exclusive names never overwrite evidence.
                backup=config_path.with_name('sync_targets.before-picker.'+nonce+'.private.json')
                with backup.open('xb') as f:f.write(original)
                tmp=config_path.with_name('sync_targets.picker.'+nonce+'.tmp')
                with tmp.open('x',encoding='utf-8') as f:json.dump(candidate,f,ensure_ascii=False,indent=2)
                os.replace(tmp,config_path)
                state['success']=True;self.reply(200,b'OK')
            except Exception:self.reply(400,b'BLOCKED')
    with HTTPServer(('127.0.0.1',17866),Handler) as server:
        server.timeout=1
        webbrowser.open(ORIGIN+'/'+nonce)
        end=time.monotonic()+timeout
        while not state['done'] and time.monotonic()<end:server.handle_request()
    if not state['success']:raise RuntimeError('PICKER_NOT_VERIFIED')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True)
    p.add_argument('--select-folders',action='store_true');a=p.parse_args()
    if not a.select_folders:
        print('CHECK ONLY: no browser, OAuth refresh, listener, upload or config change');return
    cfg=json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
    service,credentials=authenticated_service(cfg)
    serve_picker(a.config,service=service,credentials=credentials)
    print('PASS: user-selected folders verified; sync and schedule remain disabled')

if __name__=='__main__':
    logging.disable(logging.CRITICAL)
    try:main()
    except Exception as exc:
        print('PICKER_BLOCKED: '+type(exc).__name__);raise SystemExit(1)
