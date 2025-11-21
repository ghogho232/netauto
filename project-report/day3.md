# 

# Day 3 — 상태 수집 · 리포트 자동 생성 · 드리프트 감지

## 1) 오늘의 목표

- 라우터(OSPF 동작 중) 상태를 **자동 수집**하고, 사람이 읽기 좋은 **Markdown 리포트**를 만든다.
- **의도된 설정(템플릿 렌더)** 과 **실제 장비 설정(백업)** 을 비교해 **드리프트(불일치)** 를 자동 감지한다.
- 결과물을 리포지토리에 포함해 **관측 가능성(Observability)** 과 **재현성**을 강화한다.

---

## 2) 오늘의 활동 요약

- `collect_routes.py`로 `vtysh` 명령(`show ip route`, `show ip ospf neighbor`) 실행 결과를 수집 → `python/out/routes.json` 저장
- `report.py`로 JSON을 읽어 **장비별/섹션별 Markdown 리포트**(`docs/report.md`) 생성
- `backup.yml`로 실제 장비의 `/etc/frr/frr.conf`를 `backups/*.conf`로 백업
- `validate.py`로 **템플릿 렌더 결과 vs 백업본** 비교
    - 중첩 변수 치환을 위한 **2-패스 렌더**
    - `router ospf` **섹션만 비교**(선택)
    - **공백/개행 정규화**로 포매팅 차이 무시
    - 드리프트 발생 시 **diff 출력 + 아티팩트 저장**, 없으면 ✅ 메시지

---

## 3) 코드와 자세한 설명

### 3-1. 라우팅/OSPF 상태 수집: `python/collect_routes.py`

```python
import json, subprocess, pathlib

CONTAINERS = ["clab-netauto-r1", "clab-netauto-r2"]
OUT = pathlib.Path("python/out"); OUT.mkdir(parents=True, exist_ok=True)

def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, text=True, capture_output=True).stdout

data = {}
for c in CONTAINERS:
    routes = sh(f"docker exec {c} vtysh -c 'show ip route'")
    ospf   = sh(f"docker exec {c} vtysh -c 'show ip ospf neighbor'")
    data[c] = {"routes": routes, "ospf": ospf}

with open(OUT / "routes.json", "w") as f:
    json.dump(data, f, indent=2)

print("saved python/out/routes.json")

```

**설명**

- 대상 컨테이너 목록을 순회하며 `vtysh` 명령을 실행 → **원문 출력** 수집
- 결과를 `{"<node>": {"routes": "...","ospf":"..."}}` 형태로 JSON 저장
- 이후 리포트 생성/자동 검증의 **입력 데이터**로 활용

---

### 3-2. Markdown 리포트 생성: `python/report.py`

```python
import json, pathlib

SRC = pathlib.Path("python/out/routes.json")
DST = pathlib.Path("docs"); DST.mkdir(parents=True, exist_ok=True)
MD = DST / "report.md"

data = json.loads(SRC.read_text())

FENCE = "``````"  # 내부에 백틱이 있어도 안전하게 감싸기 위해 6개 사용
lines = ["# Netauto Report", ""]

for node, d in data.items():
    lines += [
        f"## {node}",
        "### OSPF Neighbors",
        FENCE,
        d["ospf"].strip(),
        FENCE,
        "### Routes",
        FENCE,
        d["routes"].strip(),
        FENCE,
        ""
    ]

MD.write_text("\n".join(lines))
print(f"wrote {MD}")

```

**설명**

- JSON을 읽어 **장비별 섹션**을 만들고, OSPF/Routes를 **코드블록**으로 삽입
- 코드블록 펜스를 백틱 6개로 사용(안전한 감싸기)
- 산출물: `docs/report.md`

---

### 3-3. 드리프트 감지: `python/validate.py`

```python
# 의도 vs 실제 비교: OSPF 섹션만(옵션), 공백 정규화, 2-패스 렌더
import re, subprocess, pathlib, sys
from jinja2 import Environment, StrictUndefined
import yaml

COMPARE_ONLY_OSPF = True
ALLOW_WHITESPACE_DIFF = True
BACKUP_GLOB = "*.conf"

root = pathlib.Path(__file__).resolve().parents[1]
outdir = root / "python" / "out"; outdir.mkdir(parents=True, exist_ok=True)

env = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)

tpl_path = root / "ansible" / "templates" / "frr.conf.j2"
tpl_src = tpl_path.read_text(encoding="utf-8")
tpl = env.from_string(tpl_src)

gvars_path = root / "ansible" / "group_vars" / "routers.yml"
gvars = yaml.safe_load(gvars_path.read_text(encoding="utf-8")) if gvars_path.exists() else {}
gvars = gvars or {}

backups_dir = root / "backups"
hosts = sorted(p.stem for p in backups_dir.glob(BACKUP_GLOB)) or ["clab-netauto-r1","clab-netauto-r2"]

def load_host_vars(host: str) -> dict:
    hv_file = root / "ansible" / "host_vars" / f"{host}.yml"
    hv = yaml.safe_load(hv_file.read_text(encoding="utf-8")) if hv_file.exists() else {}
    hv = hv or {}
    hv.setdefault("inventory_hostname", host)
    ctx = dict(gvars); ctx.update(hv)
    if "ospf_networks" not in ctx:
        nets=[];
        if ctx.get("lan_net"): nets.append(ctx["lan_net"])
        if ctx.get("transit_net"): nets.append(ctx["transit_net"])
        if nets: ctx["ospf_networks"]=nets
    return ctx

OSPF_START = re.compile(r"^router ospf\b", re.M)
SECTION_END = re.compile(r"^\s*!\s*$", re.M)

def extract_ospf(text: str) -> str:
    m = OSPF_START.search(text)
    if not m: return ""
    start = m.start()
    m2 = SECTION_END.search(text, pos=start + 1)
    end = m2.start() if m2 else len(text)
    return text[start:end]

def normalize(text: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{2,}", "\n", text, flags=re.M)
    return text.strip()

fail = 0
checked = []

for host in hosts:
    ctx = load_host_vars(host)
    try:
        once = tpl.render(**ctx)                       # 1차 렌더 (중첩 문자열 남을 수 있음)
        rendered = env.from_string(once).render(**ctx) # 2차 렌더 (완전 치환)
    except Exception as e:
        print(f"[ERROR] Jinja render failed for {host}: {e}")
        fail += 1; continue

    bfile = backups_dir / f"{host}.conf"
    if not bfile.exists():
        print(f"[ERROR] backup not found for {host}: {bfile}")
        fail += 1; continue
    backup = bfile.read_text(encoding="utf-8")

    if COMPARE_ONLY_OSPF:
        rendered_cmp = extract_ospf(rendered); backup_cmp = extract_ospf(backup); suffix=".ospf"
    else:
        rendered_cmp = rendered; backup_cmp = backup; suffix=""

    if ALLOW_WHITESPACE_DIFF:
        rendered_cmp = normalize(rendered_cmp); backup_cmp = normalize(backup_cmp)

    if rendered_cmp != backup_cmp:
        print(f"[DRIFT] {host} differs")
        rfile = outdir / f"{host}{suffix}.rendered"
        bfile2 = outdir / f"{host}{suffix}.backup"
        rfile.write_text(rendered_cmp + "\n", encoding="utf-8")
        bfile2.write_text(backup_cmp + "\n", encoding="utf-8")
        subprocess.run(["diff", "-u", str(bfile2), str(rfile)])
        fail += 1
    checked.append(host)

if fail == 0:
    print(f"✅ No drift found across {len(checked)} host(s): {', '.join(checked)}")

sys.exit(1 if fail else 0)

```

**핵심 포인트**

- **2-패스 렌더**: host_vars에 `{{ var }}` 같은 중첩 문자열이 있어도 완전 치환
- **OSPF 섹션만 비교(옵션)**: `router ospf` ~ 다음 `!` 직전만 비교해 **잡음 감소**
- **공백 정규화**: 빈 줄·줄끝 공백 차이 무시(의미 같은데 모양만 다른 경우 제외)
- **산출물/로그**: 드리프트 발생 시 `python/out/*.rendered/*.backup` 저장 + `diff -u` 출력

---

## 4) 어려웠던 점 → 어떻게 극복했나

- **문제 1: 드리프트 오탐(변수 미치환/포매팅 차이)**
    - 증상: 렌더 결과에 `{{ lan_net }}` 같은 Jinja 변수가 그대로 남거나, 빈 줄 차이만으로 diff 발생
    - 해결:
        - 템플릿 **2-패스 렌더**로 중첩 변수 완전 치환
        - **OSPF 섹션만 비교**해서 비핵심 차이 제거
        - **공백/개행 정규화**로 포매팅 차이 무시
- **문제 2: Ansible/YAML 자잘한 오류**
    - 예: YAML 들여쓰기/대시() 누락, raw 모듈/쉘 사용 시 따옴표
    - 해결: 에러 메시지 줄번호 확인 → 최소 재현 케이스로 축소 → 포맷 교정 후 재실행

---

## 5) 실행 런북 (Runbook)

> 전제: Containerlab 토폴로지 구동/OSPF 동작, Ansible 인벤토리/변수/템플릿 구성 완료
> 

```bash
# 0) (선택) 최신 설정 배포
ansible-playbook ansible/playbooks/deploy_frr.yml

# 1) 실제 장비 설정 백업
ansible-playbook ansible/playbooks/backup.yml
# → backups/clab-netauto-r1.conf, backups/clab-netauto-r2.conf 생성/갱신

# 2) 상태 수집(JSON)
python3 python/collect_routes.py
# → python/out/routes.json

# 3) 리포트 생성(Markdown)
python3 python/report.py
# → docs/report.md

# 4) 드리프트 감지
python3 python/validate.py
# → 드리프트 없으면:
# ✅ No drift found across 2 host(s): clab-netauto-r1, clab-netauto-r2
# → 드리프트 있으면 diff 출력 + python/out/*.backup / *.rendered 저장
```

**결과 해석 체크리스트**

- `docs/report.md`에서 각 라우터의 **Neighbor State: Full** 확인
- R1에 `O>* 10.0.2.0/24 via 10.0.12.2`, R2에 `O>* 10.0.1.0/24 via 10.0.12.1` 존재
- `validate.py`에서 ✅ 메시지(= 의도 == 실제) 또는 diff(= 불일치 구간) 확인

---

## 6) 오늘 공부한 것

- **관측 가능성(Observability) 자동화**: CLI 출력 → JSON → Markdown 변환 파이프라인
- **드리프트 개념**: SoT(템플릿/변수)와 실제 설정의 차이를 **자동 감지/보고**
- **Jinja/Ansible 실전 팁**: 변수 스코프, 중첩 치환(2-패스), 공백 제어(trim/lstrip)
- **검증 습관화**: 배포 후 → 수집 → 보고 → 드리프트 체크로 **증거 기반 운영**

---

## 7) 보충하면 좋을 것 (다음 단계 제안)

- **요약 메트릭**: 이웃 Full 수, OSPF 경로 수를 JSON `summary`로 기록 → 리포트 상단 표 추가
- **알림/헬스체크**: 기대치 미달 시 Slack/Webhook 알림, FastAPI `/health` 제공
- **BGP & 정책 확장**: `bgp.asn/neighbors/advertise` 변수화 → 템플릿/pytest 확장
- **CI 연동**: GitHub Actions로 템플릿 렌더·정적 검사·리포트/아티팩트 업로드
- **Make 타겟**: `make collect`, `make report`, `make drift` 등 원클릭 실행
