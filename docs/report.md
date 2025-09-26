# Netauto Report

## clab-netauto-r1
### OSPF Neighbors
``````
Neighbor ID     Pri State           Up Time         Dead Time Address         Interface                        RXmtL RqstL DBsmL
172.20.20.4       1 Full/-          8m34s             35.411s 10.0.12.2       eth1:10.0.12.1                       0     0     0
``````
### Routes
``````
Codes: K - kernel route, C - connected, S - static, R - RIP,
       O - OSPF, I - IS-IS, B - BGP, E - EIGRP, N - NHRP,
       T - Table, v - VNC, V - VNC-Direct, A - Babel, F - PBR,
       f - OpenFabric,
       > - selected route, * - FIB route, q - queued, r - rejected, b - backup
       t - trapped, o - offload failure

K>* 0.0.0.0/0 [0/0] via 172.20.20.1, eth0, 00:09:00
O   10.0.1.0/24 [110/10] is directly connected, eth2, weight 1, 00:08:34
C>* 10.0.1.0/24 is directly connected, eth2, 00:08:46
O>* 10.0.2.0/24 [110/20] via 10.0.12.2, eth1, weight 1, 00:08:24
O   10.0.12.0/30 [110/10] is directly connected, eth1, weight 1, 00:08:34
C>* 10.0.12.0/30 is directly connected, eth1, 00:08:46
C>* 172.20.20.0/24 is directly connected, eth0, 00:09:00
``````

## clab-netauto-r2
### OSPF Neighbors
``````
Neighbor ID     Pri State           Up Time         Dead Time Address         Interface                        RXmtL RqstL DBsmL
172.20.20.3       1 Full/-          8m35s             34.735s 10.0.12.1       eth1:10.0.12.2                       0     0     0
``````
### Routes
``````
Codes: K - kernel route, C - connected, S - static, R - RIP,
       O - OSPF, I - IS-IS, B - BGP, E - EIGRP, N - NHRP,
       T - Table, v - VNC, V - VNC-Direct, A - Babel, F - PBR,
       f - OpenFabric,
       > - selected route, * - FIB route, q - queued, r - rejected, b - backup
       t - trapped, o - offload failure

K>* 0.0.0.0/0 [0/0] via 172.20.20.1, eth0, 00:09:01
O>* 10.0.1.0/24 [110/20] via 10.0.12.1, eth1, weight 1, 00:08:25
O   10.0.2.0/24 [110/10] is directly connected, eth2, weight 1, 00:08:35
C>* 10.0.2.0/24 is directly connected, eth2, 00:08:47
O   10.0.12.0/30 [110/10] is directly connected, eth1, weight 1, 00:08:35
C>* 10.0.12.0/30 is directly connected, eth1, 00:08:47
C>* 172.20.20.0/24 is directly connected, eth0, 00:09:01
``````
