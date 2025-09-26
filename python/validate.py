# ---------------------------------------------
# 네트워크 자동화 실습: "드리프트 감지" 스크립트
# (의도한 설정 vs 실제 백업 설정 비교)
# ---------------------------------------------

import re, subprocess, pathlib, sys
from jinja2 import Environment, StrictUndefined
import yaml

# ===== 설정 =====
COMPARE_ONLY_OSPF = True         # True: router ospf 블록만 비교 (불필요한 잡음 줄이기)
ALLOW_WHITESPACE_DIFF = True     # True: 공백/빈 줄 차이는 무시 (포맷팅 차이 제거)
BACKUP_GLOB = "*.conf"           # backups/*.conf 기준으로 비교할 호스트 자동 추출
# =================

# 프로젝트 루트 경로 계산 (현재 파일 → python/validate.py → 루트로 이동)
root = pathlib.Path(__file__).resolve().parents[1]

# 비교 결과(diff)를 저장할 디렉토리 (없으면 생성)
outdir = root / "python" / "out"
outdir.mkdir(parents=True, exist_ok=True)

# Jinja2 환경 설정
# - StrictUndefined: 정의되지 않은 변수가 있으면 오류 발생
# - trim_blocks/lstrip_blocks: 불필요한 개행과 들여쓰기 제거
env = Environment(
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)

# 템플릿(frr.conf.j2) 로드
tpl_path = root / "ansible" / "templates" / "frr.conf.j2"
tpl_src = tpl_path.read_text(encoding="utf-8")
tpl = env.from_string(tpl_src)

# group_vars 로드 (전체 라우터에 공통 적용되는 변수)
gvars_path = root / "ansible" / "group_vars" / "routers.yml"
gvars = {}
if gvars_path.exists():
    gvars = yaml.safe_load(gvars_path.read_text(encoding="utf-8")) or {}

# 비교할 대상 호스트 목록: backups/*.conf 파일 이름에서 자동 추출
backups_dir = root / "backups"
hosts = sorted(p.stem for p in backups_dir.glob(BACKUP_GLOB)) or [
    "clab-netauto-r1", "clab-netauto-r2"   # 기본값
]

def load_host_vars(host: str) -> dict:
    """
    특정 호스트(host_vars/*.yml)와 group_vars를 로드해서
    Jinja 템플릿에 넘길 컨텍스트(dict)를 만든다.
    """
    hv_file = root / "ansible" / "host_vars" / f"{host}.yml"
    hv = {}
    if hv_file.exists():
        hv = yaml.safe_load(hv_file.read_text(encoding="utf-8")) or {}

    # inventory_hostname 기본 제공 (템플릿에서 default 필터용)
    hv.setdefault("inventory_hostname", host)

    # group_vars + host_vars 병합 (host_vars가 우선)
    ctx = dict(gvars)
    ctx.update(hv)

    # ospf_networks 자동 생성 (lan_net, transit_net 기반)
    if "ospf_networks" not in ctx:
        nets = []
        if ctx.get("lan_net"): nets.append(ctx["lan_net"])
        if ctx.get("transit_net"): nets.append(ctx["transit_net"])
        if nets:
            ctx["ospf_networks"] = nets
    return ctx

# router ospf 블록만 추출하기 위한 정규식
OSPF_START = re.compile(r"^router ospf\b", re.M)
SECTION_END = re.compile(r"^\s*!\s*$", re.M)

def extract_ospf(text: str) -> str:
    """
    config 텍스트에서 'router ospf' 블록만 추출한다.
    (router ospf ~ 다음 ! 줄 직전까지)
    """
    m = OSPF_START.search(text)
    if not m:
        return ""
    start = m.start()
    m2 = SECTION_END.search(text, pos=start + 1)
    end = m2.start() if m2 else len(text)
    return text[start:end]

def normalize(text: str) -> str:
    """
    비교 전에 공백/개행을 정규화해서 포맷팅 차이 무시.
    - 각 줄 끝 공백 제거
    - 연속 빈 줄을 1개로 축소
    - 전체 앞뒤 공백 제거
    """
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{2,}", "\n", text, flags=re.M)
    return text.strip()

# ---------------------------------------------
# 메인 루프: 호스트별로 비교 수행
# ---------------------------------------------
fail = 0      # 차이 발생 횟수
checked = []  # 비교 성공한 호스트 리스트

for host in hosts:
    # 1) 변수 로드 (host_vars + group_vars)
    ctx = load_host_vars(host)

    # 2) 템플릿 렌더 (2-패스: nested Jinja 변수까지 치환)
    try:
        once = tpl.render(**ctx)                      # 1차 렌더
        rendered = env.from_string(once).render(**ctx)  # 2차 렌더
    except Exception as e:
        print(f"[ERROR] Jinja render failed for {host}: {e}")
        fail += 1
        continue

    # 3) 백업 파일 로드
    bfile = backups_dir / f"{host}.conf"
    if not bfile.exists():
        print(f"[ERROR] backup not found for {host}: {bfile}")
        fail += 1
        continue
    backup = bfile.read_text(encoding="utf-8")

    # 4) 비교 대상 선택 (전체 vs OSPF 섹션만)
    if COMPARE_ONLY_OSPF:
        rendered_cmp = extract_ospf(rendered)
        backup_cmp   = extract_ospf(backup)
        suffix = ".ospf"
    else:
        rendered_cmp = rendered
        backup_cmp   = backup
        suffix = ""

    # 5) 공백 정규화 (옵션)
    if ALLOW_WHITESPACE_DIFF:
        rendered_cmp = normalize(rendered_cmp)
        backup_cmp   = normalize(backup_cmp)

    # 6) 비교 수행
    if rendered_cmp != backup_cmp:
        # 차이 있을 때
        print(f"[DRIFT] {host} differs")
        # 비교 파일을 python/out에 저장해서 diff 확인 가능
        rfile = outdir / f"{host}{suffix}.rendered"
        bfile2 = outdir / f"{host}{suffix}.backup"
        rfile.write_text(rendered_cmp + "\n", encoding="utf-8")
        bfile2.write_text(backup_cmp + "\n", encoding="utf-8")
        # diff 결과를 터미널에 출력
        subprocess.run(["diff", "-u", str(bfile2), str(rfile)])
        fail += 1
    checked.append(host)

# ---------------------------------------------
# 최종 결과 출력
# ---------------------------------------------
if fail == 0:
    # 모든 호스트에서 드리프트 없음
    print(f"✅ No drift found across {len(checked)} host(s): {', '.join(checked)}")

# 종료 코드: 0=성공(드리프트 없음), 1=실패(드리프트 존재)
sys.exit(1 if fail else 0)
