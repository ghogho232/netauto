CLAB=containerlab


.PHONY: up down hostcfg push backup validate test report drift


up:
cd lab && $(CLAB) deploy -t netauto.clab.yml


hostcfg:
docker exec netauto-h1 sh -lc "ip a add 10.0.1.100/24 dev eth1 || true; ip route replace default via 10.0.1.1"
docker exec netauto-h2 sh -lc "ip a add 10.0.2.100/24 dev eth1 || true; ip route replace default via 10.0.2.1"


push:
cd ansible && ansible-galaxy collection install community.docker --force
cd ansible && ansible-playbook -i inventory.ini playbooks/deploy.yml


backup:
cd ansible && ansible-playbook -i inventory.ini playbooks/backup.yml


validate:
cd ansible && ansible-playbook -i inventory.ini playbooks/validate.yml


report:
python python/collect_routes.py && python python/report.py


test:
pytest -q


drift: backup
python python/validate.py


down:
cd lab && $(CLAB) destroy -t netauto.clab.yml -c
