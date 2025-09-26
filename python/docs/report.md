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
