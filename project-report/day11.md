# Day11 — Ansible 재실행 안정화 + Drift-Free 상태 검증 + pytest 전체 통합 성공

# 1) 오늘의 목표
- Ansible 기반 Day 0/Day 1 구성 자동화가 재실행 시에도 안정적으로 동작하는지 확인
- OSPF Neighbor 형성 실패 원인 분석 → 개선 후 정상화
- 템플릿 기반 FRR 구성과 실제 장비 설정 간의 Drift 여부를 완전 자동 검증
- pytest 기반 End-to-End Test(연결성·OSPF·라우팅·드리프트) 전체 성공
- 지속 가능한 NetDevOps 파이프라인 구조를 만들기 위한 마지막 검증

# 2) 오늘의 활동 요약

## 1. Ansible 첫 실행에서 OSPF Neighbor 실패 원인 분석
초기 site.yml 실행 시 오류:

```
OSPF neighbor check failed on clab-netauto-r1.
Full count=0 expect=1
```

원인
- 초기 컨테이너가 뜬 직후 OSPF adjacency가 Init 상태
- FRR 템플릿은 정상이나, 라우터 간 converge까지 시간이 약간 필요
- verify.yml을 별도 실행하면 이미 Neighbor가 Full로 올라와 성공

의미 있는 배움
- 멱등성(Idempotency) 외에도 타이밍 이슈를 고려한 플레이북 설계가 중요
- 실제 운영에서도 OSPF/BGP는 세션 형성까지 수 초 필요
- 검증 태스크에 retry/delay가 필요한 상황 파악

## 2. verify.yml 실행 후 OSPF 정상 형성
verify.yml 단독 실행 결과:

- All assertions passed
- Ping 완전 성공
- OSPF Route 표 정상

## 3. 재실행 시 멱등성(Idempotency) 검증
site.yml 다시 실행한 결과:

핵심 변화
- FRR 템플릿 적용은 변경 없음 → skipping 정상 작동
- sysctl, IP 설정 등은 이미 설정되었지만 raw 명령은 항상 changed 처리
- OSPF·라우팅 검증은 모두 성공

멱등성 분석
- 변경된 것이 없을 때는 skip 되는 구조가 완성됨
- 실제 네트워크 자동화에서 매우 중요: 재배포해도 네트워크가 흔들리지 않음

## 4. python/validate.py Drift Detection 정상 동작
결과:

```
No drift found across 2 host(s): clab-netauto-r1, clab-netauto-r2
exit code 0
```

## 5. pytest 기반 End-to-End 자동 테스트 전체 성공
```
6 passed in 1.37s
```

테스트 구성 요소:

| 테스트 항목 | 의미 |
|-------------|-------|
| test_vtysh_available | FRR CLI 정상 접근 |
| test_ping_h1_to_h2 | End-to-End 연결성 |
| test_ospf_neighbors_full | OSPF 세션 안정성 |
| test_r1_has_ospf_route_to_h2 | r1의 OSPF Route 확인 |
| test_r2_has_ospf_route_to_h1 | r2의 OSPF Route 확인 |
| test_no_drift_against_template | 의도된 구성과 실제 구성 비교 |

# 3) 오늘 배운 점

## NetDevOps 설계 원칙 충족
- 멱등성
- 드리프트 감지
- 테스트 퍼스트
- 관측 가능성
- CI/CD 연계 준비 완료

## 운영 환경 학습 효과
- 네트워크 상태는 즉시 수렴되지 않을 수 있다는 점 이해
- verify.yml 같은 건강 검사 스테이지의 필요성 체득
- 테스트 자동화가 네트워크 안정성에 미치는 영향 학습

# 4) 오늘의 최종 산출물
- Ansible site.yml (Idempotent)
- verify.yml (OSPF/Route 검사)
- Drift Detection: python/validate.py
- pytest 자동화: 6개의 E2E 테스트
- 운영 상태 정상화 로그

# 5) 다음 단계
- GitHub Actions에서 실제 Containerlab을 자동으로 띄우고 테스트하는 구조 설계
- netauto.yml 안에서 containerlab deploy → ansible → pytest → drift detection → artifact 업로드 자동화
- CI_LIGHT / Full validation 모드 분리
