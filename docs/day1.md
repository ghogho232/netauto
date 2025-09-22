📌 수동 추가 절차

프로젝트 안에서 docs 디렉토리 만들기

cd ~/netauto
mkdir -p docs


day1.md 파일 생성

nano docs/day1.md


내용 붙여넣기
아래 내용을 편집기에 붙여넣으세요:

# Day 1 실습 정리: VMware Ubuntu + Containerlab + FRR(OSPF) 최소 토폴로지

## 1) 목표
- VMware Ubuntu VM에서 **Containerlab**으로 R1–R2–H1–H2 토폴로지 구성
- **FRRouting(OSPF)** 구동 및 **엔드투엔드(H1→H2) 통신 확인**
- 발생한 문제를 원인/영향/해결 관점으로 정리

---

## 2) 최종 토폴로지 & 파일 구조

### 토폴로지(논리)


H1(10.0.1.100/24) -- R1(10.0.1.1/24)
|
(10.0.12.0/30)
|
H2(10.0.2.100/24) -- R2(10.0.2.1/24)


### Containerlab 정의(`lab/netauto.clab.yml`)
```yaml
name: netauto
topology:
  nodes:
    r1:
      kind: linux
      image: frrouting/frr:latest
      binds:
        - ./configs/r1/frr.conf:/etc/frr/frr.conf
        - ./configs/r1/daemons:/etc/frr/daemons
    r2:
      kind: linux
      image: frrouting/frr:latest
      binds:
        - ./configs/r2/frr.conf:/etc/frr/frr.conf
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

FRR 데몬 파일(lab/configs/*/daemons)
zebra=yes      # 커널 라우팅 테이블과 상호작용 (반드시 필요)
ospfd=yes      # OSPFv2 데몬 활성화
bgpd=no
ospf6d=no
...            # 기타 데몬은 사용 안 함 → no

FRR 설정(lab/configs/r1/frr.conf, lab/configs/r2/frr.conf)

r1:

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


r2:

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

3) 실행 명령 핵심 로그
sudo containerlab deploy -t lab/netauto.clab.yml --reconfigure
sudo containerlab inspect -t lab/netauto.clab.yml

# 라우터 인터페이스
docker exec -it clab-netauto-r1 ip -br a
docker exec -it clab-netauto-r2 ip -br a

# 호스트 IP/기본경로 설정
docker exec -it clab-netauto-h1 sh -lc "ip a add 10.0.1.100/24 dev eth1; ip route replace default via 10.0.1.1"
docker exec -it clab-netauto-h2 sh -lc "ip a add 10.0.2.100/24 dev eth1; ip route replace default via 10.0.2.1"

# OSPF 이웃/경로
docker exec -it clab-netauto-r1 vtysh -c "show ip ospf neighbor"
docker exec -it clab-netauto-r2 vtysh -c "show ip route ospf"

# 최종 핑
docker exec -it clab-netauto-h1 ping -c 3 10.0.2.100

4) 확인해야 하는 내용 & 오늘 확인 결과

 containerlab inspect에 nodes 4개 + links 3개

 각 컨테이너에 eth1/eth2(라우터), eth1(호스트)

 r1 ↔ r2 OSPF 이웃 FULL

 라우팅 테이블 교환 성공

 엔드투엔드 ping 성공

5) 오류/시행착오 기록
Docker 소켓 권한 오류 → docker 그룹 추가 or sudo 실행
컨테이너 잔재로 배포 충돌 → destroy -c 후 재배포
컨테이너 이름 혼동 → clab- prefix 포함 확인
OSPF 데몬 미기동 → daemons 파일 권한/소유자 정리 후 restart
인터페이스 부재 → destroy -c 재배포로 해결
6) 아쉬운 점 / 개선 아이디어

호스트 IP 수동 설정 → Ansible로 자동화 필요

vtysh.conf 경고 → 파일 생성으로 제거 가능

검증 절차 분산 → 자동 리포트 생성 필요



