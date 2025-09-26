## 1) 오늘의 목표
- Containerlab 토폴로지를 Ansible로 **원클릭(단일 명령)** 배포/검증.
- 호스트(h1/h2)는 **Python 없이** `raw` 모드로 제어해 Alpine 미러/패키지 문제를 우회.
- FRR(OSPF) 구성은 템플릿(Jinja2)로 **선언형 관리**, `vtysh -b`로 무중단 반영.
- 검증 플레이북에서 **OSPF 이웃/경로/엔드투엔드 핑**을 자동 판정.

---

## 2) 오늘의 활동 요약
1. Containerlab로 r1–r2–h1–h2 토폴로지 구성/초기화 (destroy -c / deploy --reconfigure).
2. Ansible `deploy_all.yml` 한 번으로:
   - 라우터 커널 IP/포워딩 설정(파이썬 無, 셸 명령)
   - FRR 템플릿 배포 + vtysh -b 반영
   - 호스트 IP/GW를 `raw`로 설정
   - OSPF 이웃 수를 assert로 검증 + 핑 확인
3. Python 설치 실패(Alpine 미러) → 호스트 작업은 모두 `raw`로 전환하여 안정화.

---

## 3) 코드와 자세한 설명

### 3-1. Ansible 설정 파일
```ini
# ansible.cfg
[defaults]
inventory = ansible/inventory.ini      # 기본 인벤토리 경로
remote_tmp = /tmp/.ansible             # 원격 임시 디렉토리(권한 문제 피하기)
stdout_callback = yaml                 # 보기 편한 출력 형식
host_key_checking = False              # 컨테이너/임시 호스트에서 접근 간소화
핵심: 인벤토리/출력/임시디렉토리를 명시해 컨테이너 환경에서의 사소한 오류를 줄임.

3-2. 인벤토리 & 변수
ini
# ansible/inventory.ini
[r1]
clab-netauto-r1 ansible_connection=docker ansible_python_interpreter=/usr/bin/python3

[r2]
clab-netauto-r2 ansible_connection=docker ansible_python_interpreter=/usr/bin/python3

[h1]
clab-netauto-h1 ansible_connection=docker ansible_python_interpreter=/usr/bin/python3

[h2]
clab-netauto-h2 ansible_connection=docker ansible_python_interpreter=/usr/bin/python3

[routers:children]
r1
r2

[hosts:children]
h1
h2
ansible_connection=docker: SSH 없이 컨테이너 내부로 직접 실행.

ansible_python_interpreter: 라우터 컨테이너(FRR)는 Python이 있으므로 모듈 사용 OK.
(단, 호스트 h1/h2는 Python 설치가 불안정 → raw 모듈로만 사용)

yaml
# ansible/group_vars/routers.yml
ospf_area: 0
transit_net: 10.0.12.0/30
모든 라우터에 공통 적용되는 변수(예: OSPF area, 전송망 대역).

yaml
# ansible/host_vars/clab-netauto-r1.yml
hostname: r1
lan_if: eth2
transit_if: eth1
lan_net: 10.0.1.0/24
transit_net: 10.0.12.0/30
ospf_area: 0
ospf_networks:
  - "{{ lan_net }}"
  - "{{ transit_net }}"
yaml
# ansible/host_vars/clab-netauto-r2.yml
hostname: r2
lan_if: eth2
transit_if: eth1
lan_net: 10.0.2.0/24
transit_net: 10.0.12.0/30
ospf_area: 0
ospf_networks:
  - "{{ lan_net }}"
  - "{{ transit_net }}"
라우터별 인터페이스/망/OSPF 광고 네트워크를 선언.

템플릿에서 이 선언형 변수를 읽어 frr.conf 생성.

yaml
# ansible/host_vars/clab-netauto-h1.yml
host_ip: 10.0.1.100/24
host_gw: 10.0.1.1

# ansible/host_vars/clab-netauto-h2.yml
host_ip: 10.0.2.100/24
host_gw: 10.0.2.1
호스트 IP와 게이트웨이. raw 명령으로 커널에 직접 적용.

3-3. 메인 파이프라인 (원클릭)
yaml
# ansible/deploy_all.yml
- name: Configure kernel IPs and sysctl on routers (no python)
  hosts: routers
  gather_facts: no
  tasks:
    - name: Set IPs (r1/r2 분기)
      shell: |
        if [ "{{ inventory_hostname }}" = "clab-netauto-r1" ]; then
          ip addr replace 10.0.12.1/30 dev eth1
          ip addr replace 10.0.1.1/24  dev eth2
        else
          ip addr replace 10.0.12.2/30 dev eth1
          ip addr replace 10.0.2.1/24  dev eth2
        fi
        sysctl -w net.ipv4.ip_forward=1
    - command: ip -br a
      register: ifs
    - debug: var=ifs.stdout_lines

- import_playbook: playbooks/deploy_frr.yml     # vtysh.conf 생성 + frr.conf 템플릿 + vtysh -b
- import_playbook: playbooks/configure_hosts.yml # raw로 eth1 IP/GW 설정 (python 없이 동작)
- import_playbook: playbooks/verify.yml          # 이웃/OSPF 경로/엔드투엔드 ping
커널 IP 셋업: ip addr replace / ip route replace는 멱등성(idempotent) 보장.

라우터/호스트/검증 순서로 하위 플레이북을 체이닝.

3-4. FRR(OSPF) 배포 (템플릿)
yaml
# ansible/playbooks/deploy_frr.yml
- name: Deploy FRR configs to routers
  hosts: routers
  gather_facts: no
  tasks:
    - name: Render frr.conf from template
      template:
        src: ../templates/frr.conf.j2
        dest: /etc/frr/frr.conf
        owner: frr
        group: frr
        mode: "0640"

    - name: Ensure vtysh.conf exists (to silence warnings)
      copy:
        dest: /etc/frr/vtysh.conf
        content: ""
        owner: frr
        group: frr
        mode: "0640"

    - name: Apply config without restart (vtysh -b)
      command: vtysh -b
template: 변수 기반으로 frr.conf 생성.

vtysh -b: FRR 데몬 재시작 없이 런타임 반영(안정).
(컨테이너에서 restart는 종종 rc=137 같은 충돌을 유발)

jinja2
# ansible/templates/frr.conf.j2
hostname {{ hostname | default(inventory_hostname) }}
!
router ospf
{% set area = ospf_area | default(0) %}
{% for net in ospf_networks %}
 network {{ net }} area {{ area }}
{% endfor %}
!
line vty
ospf_networks 반복으로 광고할 네트워크를 선언형으로 관리.

토폴로지 변경 시 변수만 수정하면 템플릿은 그대로.

3-5. 호스트 IP/GW 구성 (Python 없이 raw)
yaml
# ansible/playbooks/configure_hosts.yml
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
왜 raw?

raw는 원격 Python 인터프리터가 불필요.

Alpine 미러 불안정으로 apk add python3 실패해도 문제 없이 동작.

네트워크 초기화 작업(커널 명령)엔 모듈보다 오히려 간결/안정.

3-6. 검증(Assert 기반)
yaml
# ansible/playbooks/verify.yml
- name: Verify OSPF neighbors and routes
  hosts: routers
  gather_facts: no
  vars:
    expect_neighbors: 1
  tasks:
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

    - name: Show ping result
      debug:
        var: ping_out.stdout_lines
타입 오류 방지: | length) | int 로 명시 캐스팅.

판정: 이웃이 Full 1개 이상이면 pass. 라우트/핑 결과는 사람 눈으로도 확인 가능.

3-7. Containerlab 토폴로지(참고)
yaml
# lab/netauto.clab.yml
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
    - endpoints: ["r1:eth1","r2:eth1"]   # R1-R2(전송망)
    - endpoints: ["h1:eth1","r1:eth2"]   # H1-R1(액세스)
    - endpoints: ["h2:eth1","r2:eth2"]   # H2-R2(액세스)
binds로 FRR daemons 파일을 컨테이너 /etc/frr/daemons에 마운트(ospfd 등 활성).

링크 선언이 인터페이스 이름까지 고정(eth1/eth2) → Ansible에서 그 이름을 그대로 사용.

4) 왜 raw로도 문제가 없나? (raw vs 일반 모듈)
raw

장점: 원격 Python 미필요, 셸 명령 그대로 실행 → 초기 부팅/최소 OS에도 동작.

단점: 모듈처럼 상태/변경 추적은 약함(멱등성 직접 보장 필요).

일반 모듈

장점: 상태기반(idempotent), 체크/핸들러 등 높은 추상화.

단점: 원격에 Python 필요, 환경 의존(Alpine 미러 불안정 시 설치 실패).

이번 과제 적합성:

호스트 IP/GW는 커널 상태만 바꾸면 됨 → ip addr/route replace는 항상 안전.

따라서 raw가 더 단순/견고. 라우터(FRR) 쪽은 Python이 있어 모듈/템플릿 혼용.

5) 어려웠던 점 → 어떻게 극복했나
Alpine 패키지 미러 불안정으로 apk add python3 실패
→ 호스트는 전면 raw 전환(Python 의존 제거).

FRR 재시작(rc=137)
→ vtysh -b 로 무중단 반영.

검증 템플릿 타입 에러/재귀
→ | length | int 캐스팅 통일, assert 조건 단순화.

6) 실행 런북
bash
# 1) 토폴로지 초기화/재배포
cd ~/netauto/lab
sudo containerlab destroy -t netauto.clab.yml -c
sudo containerlab deploy  -t netauto.clab.yml --reconfigure

# 2) 전체 파이프라인
cd ~/netauto
ansible-playbook -i ansible/inventory.ini ansible/deploy_all.yml

# 3) 수동 확인(참고)
ansible routers -m command -a 'vtysh -c "show ip ospf neighbor"'
ansible routers -m command -a 'vtysh -c "show ip route ospf"'
ansible clab-netauto-h1 -m raw -a 'ping -c 3 10.0.2.100'
7) 오늘 공부한 것
Ansible 연결 드라이버(docker)와 raw의 유용성.

FRR 구성 템플릿/vtysh -b 운영 패턴.

Containerlab 링크/인터페이스 이름과 네트워크 멱등 커맨드(replace류).

8) 보충하면 좋을 것
Break & Fix 확장(인터페이스 다운, OSPF 비용 변경, 네트워크 미광고 등).

N대 확장: host_vars만 추가하면 템플릿이 자동 순회하도록 루프/조건 개선.

CI: GitHub Actions로 ansible-lint, 토폴로지 dry-run, 템플릿 렌더 테스트.
