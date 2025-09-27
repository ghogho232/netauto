# --- Vars ---
CLAB        ?= containerlab
LAB         ?= lab/netauto.clab.yml
PFX         ?= clab-netauto          # 컨테이너 접두사
INV         ?= ansible/inventory/hosts.ini
PLAYDIR     ?= ansible
PY          ?= .venv/bin/python
PYTEST      ?= .venv/bin/pytest

.PHONY: up down hostcfg push backup validate report test smoke routing drift help

help:
	@echo "make up       - containerlab 배포(--reconfigure)"
	@echo "make hostcfg  - h1/h2 IP & default GW 설정"
	@echo "make push     - Ansible 배포(playbooks)"
	@echo "make backup   - 구성 백업"
	@echo "make validate - Ansible 기반 validate(playbook)"
	@echo "make report   - 라우팅/리포트 수집"
	@echo "make test     - pytest 전체"
	@echo "make smoke    - pytest smoke 마커"
	@echo "make routing  - pytest routing 마커"
	@echo "make drift    - 백업 후 드리프트 검증"
	@echo "make down     - containerlab 정리(-c)"

# --- Containerlab ---
up:
	sudo $(CLAB) deploy -t $(LAB) --reconfigure -v
	sudo $(CLAB) inspect -t $(LAB)

down:
	sudo $(CLAB) destroy -t $(LAB) -c

# --- Host network quick config (for h1/h2) ---
hostcfg:
	docker exec $(PFX)-h1 sh -lc "ip a add 10.0.1.100/24 dev eth1 || true; ip route replace default via 10.0.1.1"
	docker exec $(PFX)-h2 sh -lc "ip a add 10.0.2.100/24 dev eth1 || true; ip route replace default via 10.0.2.1"

# --- Ansible flows ---
push:
	cd $(PLAYDIR) && ansible-galaxy collection install community.docker --force
	cd $(PLAYDIR) && ansible-playbook -i $(INV) deploy_all.yml

backup:
	cd $(PLAYDIR) && ansible-playbook -i $(INV) backup.yml

validate:
	cd $(PLAYDIR) && ansible-playbook -i $(INV) validate.yml

# --- Python report/drift ---
report:
	$(PY) python/collect_routes.py && $(PY) python/report.py

drift: backup
	$(PY) python/validate.py

# --- Tests ---
test:
	NETAUTO_PREFIX=$(PFX) $(PYTEST) -q

smoke:
	NETAUTO_PREFIX=$(PFX) $(PYTEST) -q -m smoke

routing:
	NETAUTO_PREFIX=$(PFX) $(PYTEST) -q -m routing

