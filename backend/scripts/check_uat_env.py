"""UAT profile/static checks or opt-in read-only DB/LINE checks. No sends."""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.uat import PROTECTED_FIELDS, fingerprint, fail, canonical_origin

def make_baseline(env_path, health_path, origins, output):
    # Read production values only in memory; output one-way fingerprints only.
    values={k.lower():v for k,v in dotenv_values(env_path,interpolate=False).items()}
    if not values.get("internal_health_token") and health_path:
        values["internal_health_token"]=Path(health_path).read_text(encoding="utf-8").strip()
    if any(not values.get(key) for key in PROTECTED_FIELDS) or not values.get("data_dir"):
        fail("UAT_PRODUCTION_BASELINE_SOURCE_INCOMPLETE")
    password=make_url(values.get("database_url", "")).password
    if not password: fail("UAT_PRODUCTION_DATABASE_BASELINE_REQUIRED")
    origin_values=set(origins+[values.get("public_base_url","")])-{ "" }
    if not origin_values:
        fail("UAT_PRODUCTION_ORIGIN_BASELINE_REQUIRED")
    target=Path(output)
    if not target.is_absolute() or target.exists():
        fail("UAT_NEW_PRIVATE_BASELINE_PATH_REQUIRED")
    target.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps({"version":1,"database_password":fingerprint(password),"fields":{key:fingerprint(values[key]) for key in PROTECTED_FIELDS},"origins":[fingerprint(canonical_origin(x)) for x in origin_values],"data_dirs":[fingerprint(str(Path(values["data_dir"]).resolve()))]},indent=2)+"\n"
    with target.open("x",encoding="utf-8") as stream:
        stream.write(content)
    if os.name != "nt":
        target.chmod(0o600)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--check-db",action="store_true")
    parser.add_argument("--check-line",action="store_true")
    parser.add_argument("--make-baseline")
    parser.add_argument("--production-env")
    parser.add_argument("--production-health-token-file")
    parser.add_argument("--production-origin",action="append",default=[])
    args=parser.parse_args(argv)
    try:
        if args.make_baseline:
            if not args.production_env: fail("UAT_PRODUCTION_ENV_PATH_REQUIRED")
            make_baseline(args.production_env,args.production_health_token_file,args.production_origin,args.make_baseline)
            print("PASS: private fingerprint baseline generated; no raw credentials copied")
            return 0
        if not args.env_file: fail("UAT_ENV_FILE_REQUIRED")
        os.environ["LTC_PROFILE"]="uat"
        os.environ["LTC_UAT_ENV_FILE"]=str(Path(args.env_file).resolve())
        from app.config import get_settings
        get_settings.cache_clear()
        settings=get_settings()
        print("PASS: dedicated UAT settings/static isolation; deployment not verified")
        from app.uat_preflight import check_database, check_line
        if args.check_db:
            check_database(settings)
            print("PASS: read-only DB role/roster checks and other-database connection denial")
        if args.check_line:
            check_line(settings)
            print("PASS: read-only Messaging API webhook route; LIFF console/runtime still requires human verification")
        print("NOT VERIFIED: real login/binding, live UAT runtime, delivery, and the 25 human UAT results")
        return 0
    except Exception as exc:
        code=str(exc) if isinstance(exc,RuntimeError) and str(exc).startswith("UAT_") else type(exc).__name__
        print("NOT_READY: "+code)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
