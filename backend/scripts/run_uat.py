"""Prepare a UAT-only child. No launch unless --launch; never stops services."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import socket
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file",required=True)
    p.add_argument("--kind",choices=["api","worker"],required=True)
    p.add_argument("--launch",action="store_true")
    args=p.parse_args(argv)
    os.environ["LTC_PROFILE"]="uat"
    os.environ["LTC_UAT_ENV_FILE"]=str(Path(args.env_file).resolve())
    from app.config import get_settings, Settings
    get_settings.cache_clear()
    settings=get_settings()
    if not args.launch:
        print("CHECK ONLY: configuration accepted; no service, database, or LINE operation executed")
        return 0
    from app.uat_preflight import check_database
    check_database(settings)
    if args.kind=="api":
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1",8151))==0:
                raise RuntimeError("UAT_PORT_8151_OCCUPIED_NO_RESTART_PERFORMED")
        if not (Path(__file__).resolve().parents[2]/"frontend/dist/index.html").is_file():
            raise RuntimeError("UAT_BUILD_ISOLATED_FRONTEND_FIRST")
        command=[sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8151","--proxy-headers","--forwarded-allow-ips","127.0.0.1","--no-access-log"]
    else:
        from sqlalchemy import create_engine,text
        engine=create_engine(settings.database_url,connect_args={"options":"-c default_transaction_read_only=on"})
        try:
            with engine.connect() as c:
                if c.execute(text("SELECT EXISTS(SELECT 1 FROM worker_heartbeats WHERE seen_at>now()-interval '90 seconds')")).scalar_one():
                    raise RuntimeError("UAT_EXISTING_WORKER_HEARTBEAT_NO_RESTART_PERFORMED")
        finally:
            engine.dispose()
        command=[sys.executable,"-m","app.worker"]
    # Only this future child receives the new environment. No changes to any
    # existing shell, Windows service, source .env, or running API/worker.
    env={k:v for k,v in os.environ.items() if k.lower() not in Settings.model_fields and not k.startswith("JIAAN_")}
    env.update({"LTC_PROFILE":"uat","LTC_UAT_ENV_FILE":os.environ["LTC_UAT_ENV_FILE"],"JIAAN_EMERGENCY_LINE_DISPATCH":"off","JIAAN_WEBPUSH_DISPATCH":"off"})
    os.chdir(Path(__file__).resolve().parents[1])
    os.execve(sys.executable,command,env)
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        code=str(exc) if isinstance(exc,RuntimeError) and str(exc).startswith("UAT_") else type(exc).__name__
        print("NOT_READY: "+code)
        raise SystemExit(2)
