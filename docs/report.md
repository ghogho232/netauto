## Netauto Health Summary (2025-10-19 08:08:51 UTC)

| Metric | Value |
|---|---|
| OSPF Neighbors (Full) | 2/2 |
| OSPF Routes (Total) | 6 |
| Pytest Passed/Failed | 6/0 |
| Pytest Skipped | 0 |
| Drift | ✅ No drift |
| Commit | `e30123c` |

### Node Breakdown
| Node | OSPF Full | OSPF Neigh (all) | OSPF Routes |
|------|-----------|------------------|-------------|
| clab-netauto-r1 | 1 | 1 | 3 |
| clab-netauto-r2 | 1 | 1 | 3 |
---
# Netauto Report

## clab-netauto-r1
### OSPF Neighbors
``````
Neighbor ID     Pri State           Up Time         Dead Time Address         Interface                        RXmtL RqstL DBsmL
172.20.20.3       1 Full/-          51m25s            35.472s 10.0.12.2       eth1:10.0.12.1                       0     0     0
``````
### Routes
``````
Codes: K - kernel route, C - connected, S - static, R - RIP,
       O - OSPF, I - IS-IS, B - BGP, E - EIGRP, N - NHRP,
       T - Table, v - VNC, V - VNC-Direct, A - Babel, F - PBR,
       f - OpenFabric,
       > - selected route, * - FIB route, q - queued, r - rejected, b - backup
       t - trapped, o - offload failure

K>* 0.0.0.0/0 [0/0] via 172.20.20.1, eth0, 00:53:38
O   10.0.1.0/24 [110/10] is directly connected, eth2, weight 1, 00:51:35
C>* 10.0.1.0/24 is directly connected, eth2, 00:52:17
O>* 10.0.2.0/24 [110/20] via 10.0.12.2, eth1, weight 1, 00:51:15
O   10.0.12.0/30 [110/10] is directly connected, eth1, weight 1, 00:51:35
C>* 10.0.12.0/30 is directly connected, eth1, 00:52:17
C>* 172.20.20.0/24 is directly connected, eth0, 00:53:38
``````

## clab-netauto-r2
### OSPF Neighbors
``````
Neighbor ID     Pri State           Up Time         Dead Time Address         Interface                        RXmtL RqstL DBsmL
172.20.20.2       1 Full/-          51m25s            34.561s 10.0.12.1       eth1:10.0.12.2                       0     0     0
``````
### Routes
``````
Codes: K - kernel route, C - connected, S - static, R - RIP,
       O - OSPF, I - IS-IS, B - BGP, E - EIGRP, N - NHRP,
       T - Table, v - VNC, V - VNC-Direct, A - Babel, F - PBR,
       f - OpenFabric,
       > - selected route, * - FIB route, q - queued, r - rejected, b - backup
       t - trapped, o - offload failure

K>* 0.0.0.0/0 [0/0] via 172.20.20.1, eth0, 00:53:39
O>* 10.0.1.0/24 [110/20] via 10.0.12.1, eth1, weight 1, 00:51:16
O   10.0.2.0/24 [110/10] is directly connected, eth2, weight 1, 00:51:36
C>* 10.0.2.0/24 is directly connected, eth2, 00:52:18
O   10.0.12.0/30 [110/10] is directly connected, eth1, weight 1, 00:51:36
C>* 10.0.12.0/30 is directly connected, eth1, 00:52:18
C>* 172.20.20.0/24 is directly connected, eth0, 00:53:39
``````
