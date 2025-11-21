 Day10 — Grafana HTTPS 적용 + 로컬 CA 기반 인증서 운영 + Nginx Redirect 구축

# 1) 오늘의 목표
- Grafana 접속 경로를 HTTP → HTTPS로 전환하여 보안 통신 제공  
- 자체 CA(Local CA)를 생성하여 서명된 서버 인증서(grafana.crt) 발급  
- Docker Compose 기반 Grafana TLS 구성 완성  
- Windows 브라우저가 인증서를 신뢰하도록 로컬 루트 인증서 등록  
- HTTP(80) 요청을 자동으로 HTTPS(3000)으로 리다이렉션하는 Nginx reverse-redirect 서비스 구축  

# 2) 오늘의 활동 요약（상세版）

##  1. Local CA 생성 → Grafana 서버 인증서 발급
HTTPS 적용을 위해 다음 파일들을 직접 생성함:

| 파일 | 의미 |
|------|------|
| localCA.key | 로컬 CA 개인키 |
| localCA.crt | 로컬 CA 인증서(Windows에서 신뢰해야 함) |
| grafana.key | 서버 개인키 |
| grafana.csr | 서버 인증서 요청 |
| grafana.crt | CA가 서명한 서버 인증서 |
| san_ip.cnf | 192.168.159.100 SAN 포함 |

→ 브라우저가 localCA.crt를 신뢰하면 grafana.crt는 정상 인증서로 처리됨

---

##  2. Docker Compose의 Grafana HTTPS 설정
추가된 핵심 옵션:

```
GF_SERVER_PROTOCOL=https
GF_SERVER_CERT_FILE=/certs/grafana.crt
GF_SERVER_CERT_KEY=/certs/grafana.key
GF_SERVER_HTTP_PORT=3000
GF_SERVER_DOMAIN=192.168.159.100
GF_SERVER_ROOT_URL=https://192.168.159.100:3000
GF_SERVER_ENFORCE_DOMAIN=true
```

 **중요 포인트**
- Grafana 컨테이너 UID는 **472**, 따라서  
  `/secrets/certs`, `/grafana/data` 폴더 모두 `chown -R 472:472` 필요  
- GF_SERVER_ENFORCE_DOMAIN=true → Host/SAN 불일치 시 거부

---

## 3. Grafana 홈 폴더 권한 오류 해결
초기 오류:

```
GF_PATHS_DATA='/var/lib/grafana' is not writable
mkdir: can't create directory '/var/lib/grafana/plugins'
```

해결:

```
sudo chown -R 472:472 grafana/data grafana/dashboards
sudo chown -R 472:472 secrets/certs
```

→ TLS 및 DB, Plugins 정상 동작.

---

##  4. localCA를 Windows “신뢰할 수 있는 루트 인증 기관” 저장소에 등록

브라우저 경고의 원인:
- localCA.crt는 Windows가 모르는 CA → 비신뢰

설치 절차:
1. localCA.crt Windows로 복사  
2. 더블클릭 → "인증서 설치"  
3. "로컬 컴퓨터(Local Machine)"  
4. 저장소: **신뢰할 수 있는 루트 인증 기관**  
5. 완료 후 브라우저 재시작  

→ 이후 HTTPS 접속 시 경고 사라짐.

---

## 5. HTTP → HTTPS 자동 리다이렉트 (Nginx)

docker-compose.yml:

```
nginx-redirect:
  image: nginx:alpine
  ports: ["80:80"]
  command: >
    sh -c 'printf "server { listen 80; return 301 https://$$host:3000$$request_uri; }" > /etc/nginx/conf.d/default.conf
    && nginx -g "daemon off;"'
  depends_on: [grafana]
```

동작:
- http://192.168.159.100 → 자동으로  
  https://192.168.159.100:3000 로 이동

---

## 6. 최종 HTTPS 구성 검증

### ✔ HTTPS 확인
```
curl -vk https://192.168.159.100:3000
```

### ✔ HTTP → HTTPS 리다이렉트 확인
```
curl -I http://192.168.159.100
```

결과:
```
HTTP/1.1 301 Moved Permanently
Location: https://192.168.159.100:3000/
```

### 브라우저 인증서 상태
- 발급자: netauto-local-CA  
- CN: 192.168.159.100  
- SAN: IP 포함  
- 상태: 신뢰됨  

---

# 3) 오늘 배운 점·의의

## 보안 적용 관점
- 로컬 환경에서도 운영 환경 수준의 HTTPS 구축 경험  
- PKI 구조 이해도 상승  

## Docker + HTTPS 연계
- 컨테이너 권한/UID 문제 해결 능력 향상  
- TLS · 볼륨 퍼미션 · DB 권한 문제 모두 경험  

## 실전적 Nginx 리다이렉션
- HTTP 접근을 완전히 HTTPS로 강제  
- 실 운영 환경에서도 필수 기능  

---

# 4) 오늘의 최종 산출물

- `/secrets/certs/localCA.crt`
- `/secrets/certs/grafana.crt`
- `docker-compose.yml` (TLS + Redirect 완비)
- Windows Root CA 등록 완료
- Grafana·Prometheus·Alertmanager 전체 HTTPS 운영 준비 완료

---

# 5) 다음 단계
- Nginx + Let's Encrypt 자동 발급 구성  
- API(8000) HTTPS 적용  
- Prometheus/Alertmanager TLS 구성  
- 전체 인프라 TLS 일원화  
