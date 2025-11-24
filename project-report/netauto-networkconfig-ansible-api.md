# Netauto - 네트워크 구성, Ansible, API(Unicorn) 

## 목차

- [1. 개요](#1-개요)
- [2. 전체 아키텍처 개요](#2-전체-아키텍처-개요)
- [3. 네트워크 토폴로지 구성](#3-네트워크-토폴로지-구성)
  - [3.1 Containerlab 토폴로지 파일 (`netauto.clab.yml`)](#31-containerlab-토폴로지-파일-netautoclabyml)
  - [3.2 주소 설계 및 링크 구성](#32-주소-설계-및-링크-구성)
  - [3.3 FRRouting(OSPF) 설정](#33-frroutingospf-설정)
  - [3.4 통신 시나리오](#34-통신-시나리오)
- [4. Ansible 구성](#4-ansible-구성)
  - [4.1 디렉터리 구조](#41-디렉터리-구조)
  - [4.2 인벤토리·그룹 변수·호스트 변수](#42-인벤토리그룹-변수호스트-변수)
  - [4.3 주요 플레이북 설명](#43-주요-플레이북-설명)
    - [4.3.1 `configure_routers_kernel.yml`](#431-configure_routers_kernelyml)
    - [4.3.2 `configure_hosts.yml`](#432-configure_hostsyml)
    - [4.3.3 `deploy_frr.yml`](#433-deploy_frryml)
    - [4.3.4 `verify.yml`](#434-verifyyml)
    - [4.3.5 `deploy_all.yml`](#435-deploy_allyml-및-보조-플레이북)
  - [4.4 FRR 템플릿 기반 설정 배포](#44-frr-템플릿-기반-설정-배포)
  - [4.5 Ansible 설계상의 특징 및 의도](#45-ansible-설계상의-특징-및-의도)
- [5. netauto-api (FastAPI / “Unicorn”) 구성](#5-netauto-api-fastapi--unicorn-구성)
  - [5.1 설계 개요](#51-설계-개요)
  - [5.2 `health.py` - 헬스 체크 API](#52-healthpy---헬스-체크-api)
    - [5.2.1 입력 데이터 소스](#521-입력-데이터-소스)
    - [5.2.2 `parse_routes()` - 라우팅 상태 파싱](#522-parse_routes---라우팅-상태-파싱)
    - [5.2.3 `parse_junit()` - 테스트 결과 파싱](#523-parse_junit---테스트-결과-파싱)
    - [5.2.4 `/health` 응답 스키마와 상태 판정 로직](#524-health-응답-스키마와-상태-판정-로직)
  - [5.3 `metrics.py` - Prometheus 호환 메트릭 엔드포인트](#53-metricspy---prometheus-호환-메트릭-엔드포인트)
    - [5.3.1 코드 구조 및 의존성](#531-코드-구조-및-의존성)
    - [5.3.2 `_read_commit()` - Git 커밋 정보 추출](#532-_read_commit---git-커밋-정보-추출)
    - [5.3.3 `render_metrics()` - 텍스트 포맷 메트릭 생성](#533-render_metrics---텍스트-포맷-메트릭-생성)
    - [5.3.4 `/metrics` 엔드포인트 및 Snapshot 모드](#534-metrics-엔드포인트-및-snapshot-모드)
  - [5.4 netauto-api가 전체 파이프라인에서 맡는 역할](#54-netauto-api가-전체-파이프라인에서-맡는-역할)
- [6. 설계 상의 특징, 장점, 한계](#6-설계-상의-특징-장점-한계)
  - [6.1 설계 상의 특징](#61-설계-상의-특징)
  - [6.2 장점](#62-장점)
  - [6.3 한계 및 개선 아이디어](#63-한계-및-개선-방안)
- [7. 결론](#7-결론)

---

## 1. 개요

이 문서는 Netauto 프로젝트에서 사용한 **네트워크 구성(Containerlab 기반 토폴로지)**,  
**Ansible을 이용한 구성 관리 및 검증** 그리고 **FastAPI 기반 netauto-api(Unicorn)** 의 내부 구조를  
하나의 흐름으로 정리했다

1. **네트워크 토폴로지** (R1/R2/H1/H2, OSPF, IP 설계)
2. **Ansible에 의한 구성, 검증 자동화**
3. **netauto-api(FastAPI)로 상태를 집계, 노출**

이를 통해 Netauto가  **구성 관리 + 상태 수집 + API 기반 헬스 체크** 까지 포함한
작은 규모의 **NetDevOps 파이프라인**임을 보여준다.

---

## 2. 전체 아키텍처 개요

Netauto의 전체 구조를 큰 틀에서 보면 다음과 같은 계층으로 나눌 수 있다

1. **데이터 평면 / 제어 평면 (네트워크 계층)**  
   - Containerlab로 구성된 `r1`, `r2`, `h1`, `h2`  
   - FRRouting(FRR) 기반 OSPF 동작  
   - 링크 및 IP 설계는 최소하지만 실제 라우팅과 OSPF 동작을 재현할 수 있도록 구성

2. **구성 관리 계층 (Ansible)**  
   - 라우터, 호스트의 IP 및 라우팅 설정 OSPF 설정을 반복 가능하게 배포  
   - 템플릿(Jinja2) 기반 FRR 설정 생성 (`frr.conf.j2`)  
   - 검증용 플레이북(`verify.yml`)을 통해 OSPF Neighbor 및 End-to-End ping까지 자동 체크

3. **상태 집계 및 API 계층 (netauto-api)**  
   - Python/FastAPI 기반의 헬스 체크 서버  
   - `routes.json`, `junit.xml`, `report.md` 등의 산출물을 파싱  
   - `/health`에서 JSON 형태의 종합 상태, `/metrics`에서 Prometheus 텍스트 포맷 메트릭 제공

이 세 계층은 다음과 같은 흐름으로 연결된다

- Containerlab으로 **토폴로지를 띄움**
- Ansible로 **구성을 넣고 테스트**  
- 그 결과를 netauto-api가 **헬스 체크 API 및 메트릭으로 변환**

---

## 3. 네트워크 토폴로지 구성

### 3.1 Containerlab 토폴로지 파일 (`netauto.clab.yml`)


```yaml
name: netauto
topology:
  nodes:
    r1:
      kind: linux
      image: frrouting/frr:latest
      binds:
        - ./configs/r1/daemons:/etc/frr/daemons
    r2:
      kind: linux
      image: frrouting/frr:latest
      binds:
        - ./configs/r2/daemons:/etc/frr/daemons
    h1:
      kind: linux
      image: ghcr.io/hellt/network-multitool:latest
    h2:
      kind: linux
      image: ghcr.io/hellt/network-multitool:latest
  links:
    - endpoints: ["r1:eth1","r2:eth1"]   # R1-R2
    - endpoints: ["h1:eth1","r1:eth2"]   # H1-R1
    - endpoints: ["h2:eth1","r2:eth2"]   # H2-R2
```

#### 주요 포인트

- **노드 구성**
  - `r1`, `r2`: FRRouting 컨테이너 (OSPF 라우터 역할)
  - `h1`, `h2`: `network-multitool` 이미지(테스트 호스트 역할)
- **링크 구성**
  - `r1:eth1` - `r2:eth1`: 라우터 간 백본 링크
  - `h1:eth1` - `r1:eth2`: H1이 R1에 붙는 액세스 링크
  - `h2:eth1` - `r2:eth2`: H2가 R2에 붙는 액세스 링크

Containerlab를 통해 `clab-netauto` 라는 랩이 생성되며
각 컨테이너 이름은 `clab-netauto-r1`, `clab-netauto-h1` 처럼 자동으로 prefix가 붙는다

---

### 3.2 주소 설계 및 링크 구성

각 인터페이스의 IP 설계는 FRR 설정 또는 Ansible 변수를 통해 다음과 같이 구성된다

- **라우터 간 백본 링크 (`r1:eth1` <--> `r2:eth1`)**
  - 네트워크: `10.0.12.0/30`
  - `r1:eth1` -> `10.0.12.1/30`
  - `r2:eth1` -> `10.0.12.2/30`

- **H1 액세스 링크 (`h1:eth1` <--> `r1:eth2`)**
  - 네트워크: `10.0.1.0/24`
  - `r1:eth2` -> `10.0.1.1/24`
  - `h1` -> `10.0.1.100/24` (default gw: `10.0.1.1`)

- **H2 액세스 링크 (`h2:eth1` <--> `r2:eth2`)**
  - 네트워크: `10.0.2.0/24`
  - `r2:eth2` -> `10.0.2.1/24`
  - `h2` -> `10.0.2.100/24` (default gw: `10.0.2.1`)

이 설계를 바탕으로 최종적으로

- `h1 (10.0.1.100)` <--> `h2 (10.0.2.100)` 사이가  
- `r1 <--> r2` OSPF 라우팅을 통해 **End-to-End 통신 가능**한 구조가 됨

---

### 3.3 FRRouting(OSPF) 설정

라우터별 FRR 설정은 `lab/configs/r1/frr.conf`, `lab/configs/r2/frr.conf` 로 정의하고
Ansible 템플릿(`frr.conf.j2`)에 의해 재생성될 수 있음

#### R1 - `lab/configs/r1/frr.conf`

```plaintext
hostname r1
!
interface eth1
 ip address 10.0.12.1/30
interface eth2
 ip address 10.0.1.1/24
!
router ospf
 network 10.0.12.0/30 area 0
 network 10.0.1.0/24 area 0
!
line vty
```

#### R2 - `lab/configs/r2/frr.conf`

```plaintext
hostname r2
!
interface eth1
 ip address 10.0.12.2/30
interface eth2
 ip address 10.0.2.1/24
!
router ospf
 network 10.0.12.0/30 area 0
 network 10.0.2.0/24 area 0
!
line vty
```

#### OSPF 설계 요약

- **단일 Area 0** 구성
- R1, R2는 `10.0.12.0/30` 을 통해 OSPF Neighbor를 맺음
- 각 라우터는 자신이 직접 연결된 LAN(10.0.1.0/24 또는 10.0.2.0/24)을 OSPF로 광고
- 결과
  - R1은 10.0.2.0/24 라우트를 OSPF로 학습
  - R2는 10.0.1.0/24 라우트를 OSPF로 학습
  - 이를 통해 H1 <--> H2 통신이 가능해진다

---

### 3.4 통신 시나리오

구성이 정상적으로 완료되면 다음과 같은 시나리오가 작동한다

1. H1에서 H2로의 ping
   - 소스: `10.0.1.100` (H1)
   - 목적지: `10.0.2.100` (H2)
   - 경로: H1 -> R1 -> (OSPF 백본) -> R2 -> H2

2. 라우터 관점에서의 OSPF 상태
   - `vtysh -c "show ip ospf neighbor"` 실행 시 양쪽 모두 Full Neighbor 1개
   - `vtysh -c "show ip route ospf"` 에서 상대 측 LAN prefix 확인 가능

이러한 검증 작업은 Ansible 플레이북(`verify.yml`)에 의해 자동화됨

---

## 4. Ansible 구성

### 4.1 디렉터리 구조

Netauto의 Ansible 디렉터리 구조

```text
ansible/
  deploy_all.yml
  deploy_all_backup.yml
  group_vars/
    routers.yml
  host_vars/
    clab-netauto-r1.yml
    clab-netauto-r2.yml
    clab-netauto-h1.yml
    clab-netauto-h2.yml
  inventory.ini
  playbooks/
    backup.yml
    break_fix.yml
    configure_hosts.yml
    configure_routers_kernel.yml
    deploy_frr.yml
    verify.yml
  templates/
    frr.conf.j2
  site.yml
```

#### 역할 요약

- **`inventory.ini`**  
  - `routers`, `h1`, `h2` 등 호스트 그룹 정의
- **`group_vars/routers.yml`**  
  - 모든 라우터에 공통으로 적용될 변수(예: `ospf_area`, `transit_net`) 정의
- **`host_vars/*.yml`**  
  - 각 호스트별 세부 변수 (LAN, transit, hostname, host_ip 등) 정의
- **`playbooks/*.yml`**  
  - 실제 작업 단위(라우터 커널 설정, FRR 배포, 호스트 설정, 검증 등)
- **`templates/frr.conf.j2`**  
  - FRR 설정 템플릿(Jinja2)
- **`site.yml` / `deploy_all.yml`**  
  - 여러 플레이북을 순서대로 실행하기 위한 엔트리포인트 역할

---

### 4.2 인벤토리·그룹 변수·호스트 변수

#### `group_vars/routers.yml`

```yaml
ospf_area: 0
transit_net: 10.0.12.0/30
```

- 모든 라우터가 공통으로 사용하는 OSPF Area와 transit 네트워크 정보
- 템플릿(`frr.conf.j2`)에서 OSPF 설정에 활용 가능

#### `host_vars/clab-netauto-h1.yml`

```yaml
host_ip: 10.0.1.100/24
host_gw: 10.0.1.1
```

#### `host_vars/clab-netauto-h2.yml`

```yaml
host_ip: 10.0.2.100/24
host_gw: 10.0.2.1
```

- 호스트(H1, H2)의 IP/게이트웨이 설정
- `configure_hosts.yml` 플레이북에서 사용

#### `host_vars/clab-netauto-r1.yml`

```yaml
hostname: r1
lan_if: eth2
transit_if: eth1
lan_net: 10.0.1.0/24
transit_net: 10.0.12.0/30
ospf_area: 0
ospf_networks:
  - 10.0.1.0/24
  - 10.0.12.0/30
```

#### `host_vars/clab-netauto-r2.yml`

```yaml
hostname: r2
lan_if: eth2
transit_if: eth1
lan_net: 10.0.2.0/24
transit_net: 10.0.12.0/30
ospf_area: 0
ospf_networks:
  - 10.0.2.0/24
  - 10.0.12.0/30
```

- 각 라우터의 **인터페이스 역할(LAN/Transit)**, **네트워크**, **OSPF Area**, **Advertise할 네트워크 목록** 등을 정의
- FRR 템플릿 및 kernel 설정용 플레이북에서 활용 가능

---

### 4.3 주요 플레이북 설명

#### 4.3.1 `configure_routers_kernel.yml`

```yaml
- name: Configure kernel IPs and sysctl on routers
  hosts: routers
  gather_facts: no
  tasks:
    - name: Set IPs from vars
      shell: |
        {% if eth1_ip is defined %} ip addr replace {{ eth1_ip }} dev eth1; {% endif %}
        {% if eth2_ip is defined %} ip addr replace {{ eth2_ip }} dev eth2; {% endif %}
        sysctl -w net.ipv4.ip_forward=1
    - command: ip -br a
      register: ifs
    - debug: var=ifs.stdout_lines

- name: Apply FRR config (no restart)
  hosts: routers
  gather_facts: no
  tasks:
    - command: vtysh -b
```

#### 주요 포인트

1. **라우터 커널 인터페이스에 IP 설정**
   - `eth1_ip`, `eth2_ip` 변수에 따라 인터페이스에 `ip addr replace` 수행
   - Python이 없는 환경에서도 동작하도록 `shell`/`command` 모듈 중심으로 작성
2. **IPv4 포워딩 활성화**
   - `sysctl -w net.ipv4.ip_forward=1`
3. **FRR 설정 적용**
   - `vtysh -b` 명령으로 기존 `frr.conf` 를 다시 읽게 함

이를 통해 FRR 데몬을 재시작하지 않고도  
**커널 IP/라우팅 설정 + FRR 설정 재적용**이 가능하다

---

#### 4.3.2 `configure_hosts.yml`

```yaml
- name: Configure IP and default route on hosts
  hosts: h1,h2
  gather_facts: no
  tasks:
    - name: Flush any existing addresses on eth1 (no python/raw)
      raw: ip addr flush dev eth1 || true

    - name: Set IP on eth1 (no python/raw)
      raw: ip addr replace {{ host_ip }} dev eth1

    - name: Set default route via router (no python/raw)
      raw: ip route replace default via {{ host_gw }}
```

##### 역할

- **Host(H1/H2)의 IP 및 기본 라우트 설정**
  - `host_ip`, `host_gw` 는 호스트별 `host_vars` 에서 로드
- `raw` 모듈을 사용하여 Python이 없는 컨테이너 환경에서도 동작
- 기존 주소/라우트와 관계없이 항상 동일 상태로 맞추는 **idempotent한 네트워크 초기화** 구현

---

#### 4.3.3 `deploy_frr.yml`

```yaml
- name: Deploy FRR configs to routers
  hosts: routers
  gather_facts: false
  tasks:
    - name: Render frr.conf from template
      template:
        src: ../templates/frr.conf.j2
        dest: /etc/frr/frr.conf
        owner: frr
        group: frr
        mode: "0640"
      register: frr_tmpl

    - name: Ensure vtysh.conf exists (to silence warnings)
      copy:
        dest: /etc/frr/vtysh.conf
        content: ""
        owner: frr
        group: frr
        mode: "0640"

    - name: Apply config (vtysh -b) only when changed
      command: vtysh -b
      when: frr_tmpl.changed
      register: vtysh_apply
      changed_when: frr_tmpl.changed

    - name: Show vtysh output (debug)
      debug:
        var: vtysh_apply.stdout_lines
      when: frr_tmpl.changed
```

##### 역할

- `frr.conf.j2` 템플릿을 각 라우터의 `host_vars`/`group_vars` 를 기반으로 렌더링
- 변경 사항이 있을 경우에만 `vtysh -b` 를 실행하여 **불필요한 재적용을 방지**
- `vtysh.conf` 가 없을 때 발생하는 경고를 막기 위한 최소 파일 생성 포함

이 플레이북 덕분에 FRR 설정이 **명시적인 템플릿**으로 관리되며  
코드 리뷰, 버전 관리가 간단함

---

#### 4.3.4 `verify.yml`

```yaml
- name: Verify OSPF neighbors and routes
  hosts: routers
  gather_facts: no
  vars:
    expect_neighbors: 1
  tasks:
    - name: Wait for OSPF to converge (pause)
      pause:
        seconds: 10

    - name: Show OSPF neighbors
      command: vtysh -c "show ip ospf neighbor"
      register: neigh
      changed_when: false

    - name: Count Full neighbors (as int)
      set_fact:
        full_count: "{{ (neigh.stdout | regex_findall('Full') | length) | int }}"

    - name: Fail if neighbor Full count < expect
      assert:
        that:
          - full_count | int >= expect_neighbors | int
        fail_msg: |
          OSPF neighbor check failed on {{ inventory_hostname }}.
          Full count={{ full_count }} expect={{ expect_neighbors }}
          Output:
          {{ neigh.stdout }}

    - name: Show OSPF routes
      command: vtysh -c "show ip route ospf"
      register: routes
      changed_when: false

    - name: Print routes (debug)
      debug:
        var: routes.stdout_lines

- name: End-to-end ping from h1 to h2
  hosts: clab-netauto-h1
  gather_facts: no
  tasks:
    - name: Ping h2 address (raw, no python needed)
      raw: ping -c 3 10.0.2.100
      register: ping_out
      changed_when: false
      retries: 5
      delay: 3
      until: ping_out.rc == 0

    - name: Show ping result
      debug:
        var: ping_out.stdout_lines
```

##### 역할

1. **라우터 OSPF Neighbor 검증**
   - `show ip ospf neighbor` 출력에서 `"Full"` 문자열 개수를 세어 기대치 이상인지 확인
   - 기대 Neighbor 수(`expect_neighbors`)는 기본 1
   - 조건 불만족 시 `assert` 에 의해 플레이 실패 -> CI에서 바로 감지 가능

2. **OSPF 라우트 테이블 확인**
   - `show ip route ospf` 출력 로그를 남김
   - CI 실패 시 디버깅에 활용 가능

3. **End-to-End ping 검증**
   - H1에서 H2(10.0.2.100)으로 3회 ping
   - retry/timeout 로직 포함: OSPF 수렴 딜레이 등을 고려

이 플레이북은 사실상 **수동으로 확인해야 할 것들을 코드화**해 놓은 것으로  
Netauto의 **네트워크 헬스 체크**의 첫 단계라고 볼 수 있음

---

#### 4.3.5 `deploy_all.yml` 및 보조 플레이북

```yaml
- name: Configure kernel IPs and sysctl on routers (no python)
  hosts: routers
  gather_facts: no
  tasks:
    - name: Set IPs (r1/r2 분기)
      shell: |
        if [ "{{ inventory_hostname }}" = "clab-netauto-r1" ]; then
          ip addr replace 10.0.12.1/30 dev eth1
          ip addr replace 10.0.1.1/24 dev eth2
        else
          ip addr replace 10.0.12.2/30 dev eth1
          ip addr replace 10.0.2.1/24 dev eth2
        fi
    - name: Enable IPv4 forwarding
      command: sysctl -w net.ipv4.ip_forward=1
```

- 초기 버전/단순 버전에서 사용되는 커널 IP 설정 플레이북으로,
  - 후에 `configure_routers_kernel.yml` 처럼 변수 기반 구조로 리팩토링할 수 있는 대상
- `deploy_all_backup.yml`, `backup.yml`, `break_fix.yml` 등은
  - 실험 과정에서의 백업/복구, 의도적으로 장애 상황을 만들어 테스트하는 용도로 활용

---

### 4.4 FRR 템플릿 기반 설정 배포

`templates/frr.conf.j2` 는 라우터 공통/개별 변수들을 이용해 FRR 설정을 생성하는 템플릿

```jinja2
hostname {{ hostname | default(inventory_hostname) }}
!
interface {{ transit_if }}
 ip ospf network point-to-point
!
router ospf
{% set area = ospf_area | default(0) %}
{% for net in ospf_networks %}
 network {{ net }} area {{ area }}
{% endfor %}
!
line vty

```

이렇게 템플릿을 사용하면

- 라우터 추가/변경 시에도 host_vars만 수정하면 자동으로 새 설정 생성
- 라우터 간 설정 편차를 줄일 수 있음

---

### 4.5 Ansible 설계상의 특징 및 의도

1. **Python에 의존하지 않는 모듈 선택**
   - Containerlab의 FRR 이미지/테스트용 호스트는 Python이 없기 때문에
   - `raw`, `shell`, `command`, `pause`, `assert` 등 최소 모듈만 사용

2. **Idempotent (멱등성) 보장**
   - `ip addr replace`, `ip route replace`, 템플릿 기반 배포 등을 사용해  
     “여러 번 실행해도 동일 상태”가 되도록 구성

3. **검증(Verification)을 플레이북으로 명시**
   - 사람이 직접 **Neighbor Full 상태인지 확인**하는 대신  
   - `verify.yml` 안에 조건을 코드화하여 실패 시 CI에서 바로 감지 가능

4. **토폴로지/설계 전체를 코드로 표현**
   - Containerlab YAML + Ansible 템플릿/변수가 **네트워크 설계서** 역할을 함

---

## 5. netauto-api (FastAPI / Unicorn) 구성

### 5.1 설계 개요

netauto-api는 FastAPI를 기반으로 구현된 **경량 헬스 체크/메트릭 서버**이다

- 모듈 구조:
  - `python/api/health.py` - `/health` 엔드포인트 제공
  - `python/api/metrics.py` - `/metrics` 엔드포인트 제공
  - `python/utils/parsers.py` - JSON/JUnit/드리프트 상태 파서 모음 (외부 모듈)
- 역할:
  - 네트워크, 테스트, 드리프트 상태를 하나의 JSON 구조로 **집계**
  - Prometheus 텍스트 포맷으로 변환해 **수집 가능한 메트릭**으로 노출

이를 통해 네트워크 내부 상태와 테스트 결과를  
**HTTP API 하나로 외부 시스템에 전달**할 수 있게 된다

---

### 5.2 `health.py` - 헬스 체크 API

#### 5.2.1 입력 데이터 소스

```python
ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "python" / "out" / "routes.json"      # 라우팅 상태 수집 결과
JUNIT  = ROOT / "tests" / "artifacts" / "junit.xml"   # pytest 실행 결과
REPORT = ROOT / "docs" / "report.md"                  # Markdown 리포트
```

- `routes.json`:
  - `vtysh` 명령을 통해 수집한 OSPF/라우트 상태가 저장된 파일
  - 라우터별 `routes`, `ospf` 텍스트를 포함
- `junit.xml`:
  - pytest 실행 결과를 JUnit 형식으로 저장한 파일
- `report.md`:
  - 사람이 읽을 수 있는 형태로 정리한 네트워크 리포트

#### 5.2.2 `parse_routes()` - 라우팅 상태 파싱

```python
def parse_routes(data: dict) -> dict:
    total_routes = total_full = total_neigh = 0
    nodes = {}

    # 예: "O>* 10.0.2.0/24 ..." -> 10.0.2.0/24 추출
    ospf_line = re.compile(r'^\s*O[>\s\*]*\s+(\d+\.\d+\.\d+\.\d+/\d+)\b')

    for n, p in sorted((data or {}).items()):
        routes_text = (p or {}).get("routes", "") or ""
        ospf_text   = (p or {}).get("ospf", "") or ""

        # 'O'로 시작하는 라우트 라인만 추출해 중복 제거
        prefixes = set()
        for line in routes_text.splitlines():
            m = ospf_line.match(line)
            if m:
                prefixes.add(m.group(1))
        rcnt = len(prefixes)

        # OSPF Neighbor 중 Full 상태 라인 수 계산
        full = len(re.findall(r'\bFull\b', ospf_text))

        # Neighbor ID 헤더 제외한 실제 이웃 라인 수 계산
        neigh_lines = [l for l in ospf_text.splitlines() if l.strip() and "Neighbor ID" not in l]
        alln = len(neigh_lines)

        # 라우터별 요약 저장
        nodes[n] = {"routes": rcnt, "full": full, "neigh_all": alln}

        # 전체 합계 계산
        total_routes += rcnt
        total_full   += full
        total_neigh  += alln

    return {
        "nodes": nodes,
        "total_routes": total_routes,
        "total_full": total_full,
        "total_neigh": total_neigh
    }
```

#### 주요 로직

- 각 라우터의 `routes` 텍스트에서 **OSPF 라우트만 추출** (`O`로 시작하는 라인)
- 프리픽스를 set으로 모아 **중복 제거 후 개수 계산**
- `show ip ospf neighbor` 출력에서 `"Full"` 문자열 개수를 세어 Full Neighbor 수 계산
- 헤더를 제외한 라인 수로 전체 Neighbor 수(`neigh_all`) 계산
- 최종적으로:
  - `nodes` 딕셔너리에 라우터별 요약
  - `total_routes`, `total_full`, `total_neigh` 를 전체 합계로 반환

이 로직 덕분에 routes.json이 **텍스트 blob** 이더라도  
API 레이어에서는 **정제된 숫자 지표**를 얻을 수 있다.

---

#### 5.2.3 `parse_junit()` - 테스트 결과 파싱

```python
def parse_junit() -> dict:
    if not JUNIT.exists():
        return {"tests": 0, "passed": 0, "failed": 0, "skipped": 0}

    root = ET.fromstring(JUNIT.read_text(encoding="utf-8"))

    # 다양한 XML 루트(tag)에 대응 (testsuites, testsuite 등)
    if root.findall(".//testsuite"):
        suites = root.findall(".//testsuite")
    elif root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = list(root)
    else:
        suites = []

    tests = fail = err = skip = 0
    for s in suites:
        tests += int(s.attrib.get("tests", 0))
        fail  += int(s.attrib.get("failures", 0))
        err   += int(s.attrib.get("errors", 0))
        skip  += int(s.attrib.get("skipped", 0))

    passed = max(0, tests - fail - err - skip)
    return {"tests": tests, "passed": passed, "failed": fail + err, "skipped": skip}
```

#### 특징

- JUnit XML 구조가 `testsuite` / `testsuites` 등 다양할 수 있음을 고려
- `tests`, `failures`, `errors`, `skipped` 를 누적해 전체 테스트 통계를 계산
- `passed = tests - failures - errors - skipped` 로 계산

이를 통해, pytest 결과를 **단일 dictionary 구조**로 요약하여  
헬스 체크 및 메트릭 생성에 활용할 수 있다.

---

#### 5.2.4 `/health` 응답 스키마와 상태 판정 로직

```python
@app.get("/health")
def health():
    ...
    rsum = parse_routes(data)
    junit = parse_junit()
    report_present = REPORT.exists()

    # 상태 판정
    ok_neighbors = (rsum["total_neigh"] > 0 and rsum["total_full"] == rsum["total_neigh"])
    ok_tests     = (junit["tests"] > 0 and junit["failed"] == 0)
    status       = "ok" if ok_neighbors and ok_tests else "degraded"
    ...
    return {
        "status": status,
        "neighbors": {"full": rsum["total_full"], "total": rsum["total_neigh"]},
        "routes_total": rsum["total_routes"],
        "tests": junit,
        "report_present": report_present,
        "nodes": rsum["nodes"],
        "mtimes": mtimes
    }
```

#### 상태 판정 기준

1. **Neighbor 상태**
   - 최소 한 개 이상의 Neighbor가 존재하고(`total_neigh > 0`)
   - 모든 Neighbor가 Full 상태일 때(`total_full == total_neigh`) OK

2. **테스트 결과**
   - 적어도 한 개 이상의 테스트가 실행되었고(`tests > 0`)
   - 실패(`failed`)가 0일 때 OK

두 조건이 모두 만족하면 `status = "ok"`,  
그 외에는 `status = "degraded"` 로 판정한다.

#### 반환 JSON 구조

```json
{
  "status": "degraded",
  "neighbors": {"full": 2, "total": 2},
  "routes_total": 6,
  "tests": {"tests": 6, "passed": 5, "failed": 1, "skipped": 0},
  "report_present": true,
  "nodes": {
    "clab-netauto-r1": {"routes": 3, "full": 1, "neigh_all": 1},
    "clab-netauto-r2": {"routes": 3, "full": 1, "neigh_all": 1}
  }
}
```
- `status`: `"ok"` 또는 `"degraded"`
- `neighbors`:  
  - `full`: Full 상태 Neighbor 수 합계  
  - `total`: 전체 Neighbor 수 합계
- `routes_total`: 전체 OSPF 라우트 수
- `tests`: `parse_junit()` 결과 딕셔너리
- `report_present`: `docs/report.md` 존재 여부
- `nodes`: 라우터별 라우트/Neighbor 요약


이 JSON은 CI, 대시보드, 외부 도구 등에서  
**Netauto 환경의 건강 상태를 한 번에 판단**할 수 있게 해준다.

---

### 5.3 `metrics.py` - Prometheus 호환 메트릭 엔드포인트

#### 5.3.1 코드 구조 및 의존성

```python
from python.utils.parsers import (
    load_health_json,
    parse_junit,
    load_routes_json,
    load_drift_status,
)

router = APIRouter()
TOPOLOGY = "ospf-mini"
```

- `APIRouter`를 사용해 `health.py`의 FastAPI 인스턴스에 라우터로 포함
- `python/utils/parsers` 모듈에서 보조 파서들을 가져와 사용
- 토폴로지 이름(`TOPOLOGY`)은 레이블로 사용 가능

#### 5.3.2 `_read_commit()` - Git 커밋 정보 추출

```python
def _read_commit() -> str:
    head = Path(".git/HEAD")
    if not head.exists():
        return "unknown"
    ref = head.read_text(errors="ignore").strip()
    if ref.startswith("ref:"):
        ref_path = Path(".git") / ref.split(":", 1)[1].strip()
        return ref_path.read_text(errors="ignore").strip()[:12] if ref_path.exists() else "unknown"
    return ref[:12]
```

- `.git/HEAD` 를 읽어 현재 커밋 SHA를 가져오는 유틸리티
- 브랜치/Detached HEAD 양쪽을 처리
- 메트릭에 `commit` 라벨로 포함시켜 이 메트릭이 어떤 버전의 코드에서 나온 것인지 추적 가능하게 함

#### 5.3.3 `render_metrics()` - 텍스트 포맷 메트릭 생성

```python
def render_metrics() -> str:
    health = load_health_json()
    junit = parse_junit()
    routes = load_routes_json()
    drift = load_drift_status()
    ...
    lines = []
    lines.append("# HELP netauto_info Build info label carrier")
    lines.append("# TYPE netauto_info gauge")
    lines.append(f'netauto_info{{commit="{commit}",topo="{TOPOLOGY}"}} 1')
    ...
    lines.append("# HELP netauto_status Overall status (1=ok, 0=else)")
    lines.append("# TYPE netauto_status gauge")
    lines.append(f"netauto_status {1 if status == 'ok' else 0}")
    ...
    lines.append("# HELP netauto_neighbors OSPF neighbors by state")
    lines.append("# TYPE netauto_neighbors gauge")
    lines.append(f'netauto_neighbors{{state="full"}} {full}')
    lines.append(f'netauto_neighbors{{state="total"}} {total}')
    ...
```

주요 메트릭:

- `netauto_info{commit="...", topo="ospf-mini"} 1`
- `netauto_status` - `/health`의 status를 0/1로 변환
- `netauto_neighbors{state="full|total"}` - 네이버 수
- `netauto_routes_total` - 전체 라우트 수
- `netauto_tests_count{type="total|passed|failed|skipped"}` - 테스트 카운터
- `netauto_drift_config` - 드리프트 존재 여부(1/0)
- `netauto_node_routes{node="r1"}` - 노드별 라우트 수
- `netauto_node_neighbors{node="r1",state="full|total"}` - 노드별 Neighbor 수

마지막에 현재 UTC timestamp를 주석으로 남겨  
텍스트 스냅샷만 봐도 언제 생성된 메트릭인지 알 수 있게 함

#### 5.3.4 `/metrics` 엔드포인트 및 Snapshot 모드

```python
@router.get("/metrics")
def metrics():
    return Response(render_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")
```

- Prometheus의 default 텍스트 포맷에 맞추어 응답

```python
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true", help="write docs/metrics.txt")
    args = ap.parse_args()
    if args.snapshot:
        out = Path("docs/metrics.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_metrics(), encoding="utf-8")
        print(f"[ok] wrote {out}")
```

- CLI 모드에서 `--snapshot` 옵션을 주면 `docs/metrics.txt` 로 결과를 덤프
- CI나 로컬 디버깅 시 Prometheus 없이도 메트릭 출력 내용을 확인할 수 있다

---

### 5.4 netauto-api가 전체 파이프라인에서 맡는 역할

- **Ansible/pytest/스크립트**가 만들어낸 산출물(`routes.json`, `junit.xml`, 리포트)을
- **FastAPI(netauto-api)** 가 표준화된 **JSON·메트릭 인터페이스**로 변환하고
- 이후 관측/알람 시스템(예: Prometheus, Grafana, Alertmanager 등)이
  이를 처리하게 된다

netauto-api는 **네트워크 + 테스트 결과를 외부 시스템이 이해할 수 있는 형태로 노출하는 게이트웨이**라고 할 수 있다

---

### 5.5 산출물 예

### 1. report.md

# Netauto Report

## clab-netauto-r1
### OSPF Neighbors
``````
Neighbor ID     Pri State           Up Time         Dead Time Address         Interface                        RXmtL RqstL DBsmL
172.20.20.4       1 Full/-          6h14m36s          33.026s 10.0.12.2       eth1:10.0.12.1                       0     0     0
``````
### Routes
``````
Codes: K - kernel route, C - connected, S - static, R - RIP,
       O - OSPF, I - IS-IS, B - BGP, E - EIGRP, N - NHRP,
       T - Table, v - VNC, V - VNC-Direct, A - Babel, F - PBR,
       f - OpenFabric,
       > - selected route, * - FIB route, q - queued, r - rejected, b - backup
       t - trapped, o - offload failure

K>* 0.0.0.0/0 [0/0] via 172.20.20.1, eth0, 06:15:02
O   10.0.1.0/24 [110/10] is directly connected, eth2, weight 1, 06:14:36
C>* 10.0.1.0/24 is directly connected, eth2, 06:14:48
O>* 10.0.2.0/24 [110/20] via 10.0.12.2, eth1, weight 1, 06:14:26
O   10.0.12.0/30 [110/10] is directly connected, eth1, weight 1, 06:14:36
C>* 10.0.12.0/30 is directly connected, eth1, 06:14:48
C>* 172.20.20.0/24 is directly connected, eth0, 06:15:02
``````

## clab-netauto-r2
### OSPF Neighbors
``````
Neighbor ID     Pri State           Up Time         Dead Time Address         Interface                        RXmtL RqstL DBsmL
172.20.20.3       1 Full/-          6h14m36s          32.538s 10.0.12.1       eth1:10.0.12.2                       0     0     0
``````
### Routes
``````
Codes: K - kernel route, C - connected, S - static, R - RIP,
       O - OSPF, I - IS-IS, B - BGP, E - EIGRP, N - NHRP,
       T - Table, v - VNC, V - VNC-Direct, A - Babel, F - PBR,
       f - OpenFabric,
       > - selected route, * - FIB route, q - queued, r - rejected, b - backup
       t - trapped, o - offload failure

K>* 0.0.0.0/0 [0/0] via 172.20.20.1, eth0, 06:15:02
O>* 10.0.1.0/24 [110/20] via 10.0.12.1, eth1, weight 1, 06:14:26
O   10.0.2.0/24 [110/10] is directly connected, eth2, weight 1, 06:14:36
C>* 10.0.2.0/24 is directly connected, eth2, 06:14:48
O   10.0.12.0/30 [110/10] is directly connected, eth1, weight 1, 06:14:36
C>* 10.0.12.0/30 is directly connected, eth1, 06:14:48
C>* 172.20.20.0/24 is directly connected, eth0, 06:15:02
``````
---
### 2. junit.xml
```xml
<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" errors="0" failures="1" skipped="0" tests="6" time="2.384" timestamp="2025-10-30T16:47:39.570621+09:00" hostname="ganghyun"><testcase classname="tests.test_connectivity" name="test_vtysh_available" time="0.619" /><testcase classname="tests.test_connectivity" name="test_ping_h1_to_h2" time="0.177" /><testcase classname="tests.test_connectivity" name="test_ospf_neighbors_full" time="0.600" /><testcase classname="tests.test_connectivity" name="test_r1_has_ospf_route_to_h2" time="0.290" /><testcase classname="tests.test_connectivity" name="test_r2_has_ospf_route_to_h1" time="0.327" /><testcase classname="tests.test_connectivity" name="test_no_drift_against_template" time="0.300" /></testsuite></testsuites>
```


## 6. 설계 상의 특징, 장점, 한계

### 6.1 설계 상의 특징

- **Containerlab + Ansible + FastAPI** 라는 비교적 가벼운 스택 사용
- Python이 없는 컨테이너 환경을 고려한 `raw`/`shell` 중심의 Ansible 설계
- FRR 설정을 템플릿으로 관리하여 재사용성과 가독성 확보
- 네트워크 테스트 결과를 **JUnit + JSON** 으로 남겨
  - 개발/테스트 워크플로우에 자연스럽게 녹일 수 있도록 설계
- netauto-api를 통해 네트워크 헬스 상태를
  - 개발자/운영자 모두 접근하기 쉬운 HTTP 인터페이스로 제공

### 6.2 장점

1. **재현 가능성**  
   - 같은 리포지토리, 같은 Ansible 플레이북을 사용하면
   - 언제든 동일한 토폴로지와 구성 상태를 재현할 수 있음

2. **가시성(Visibility) 향상**  
   - OSPF Neighbor, 라우트, 테스트 결과가
   - `/health`, `/metrics` 를 통해 한 번에 확인 가능

3. **확장 용이성**  
   - 라우터/호스트를 추가하고 싶다면
     - Containerlab YAML에 노드/링크 추가
     - host_vars/group_vars에 변수 추가
     - 템플릿/플레이북을 약간 수정하는 것으로 대응 가능

4. **Dev/Net/SRE 관점의 공통 언어 제공**
   - 코드는 Python/Ansible/YAML 위주로
   - 네트워크 엔지니어뿐 아니라 개발자도 쉽게 이해 가능

### 6.3 한계 및 개선 방안

1. **단일 OSPF Area, 단일 토폴로지 제한**
   - 현재는 매우 단순한 2라우터 구조이므로
   - 다중 Area, BGP, MPLS 등으로 확장 시 추가 설계 필요

2. **보안/인증 미적용**
   - netauto-api는 인증 없이 사용됨
   - 실제 환경이라면 인증/권한 부여, TLS 적용 필요

3. **테스트 커버리지 제한**
   - 지금은 OSPF Neighbor/라우트/ping 정도에 초점
   - 지연(latency), 패킷 손실, 애플리케이션 레벨 테스트 등으로 확장 가능

---

## 7. 결론

이 문서는 Netauto 프로젝트의 **네트워크 토폴로지**, **Ansible 기반 구성 관리**, **netauto-api(FastAPI)를 이용한 상태 집계 및 노출 구조**를 정리했다

핵심은 다음과 같다

1. Containerlab + FRR을 이용해 **실제와 유사한 L3 토폴로지**를 구성
2. Ansible로 **구성/검증을 코드화**하여 재현성과 신뢰성을 확보
3. netauto-api로 **상태를 API/메트릭 형태로 표준화**해 외부 시스템과 연결

이 구조는 규모는 작지만
실제 현업에서 요구되는 **NetDevOps / Network Observability / Infra-as-Code** 개념을
랩 안에 잘 구축했다고 생각한다

