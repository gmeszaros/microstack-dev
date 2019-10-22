#!/bin/sh

#requirement: match module version with the kernel
#uio_pci_generic
sudo microstack.dpdk-devbind --status | grep -B3 '00:19.0'
sudo modprobe uio_pci_generic
sudo microstack.dpdk-devbind --unbind 00:19.0
sudo microstack.dpdk-devbind --bind=uio_pci_generic 00:19.0
sudo microstack.dpdk-devbind --status | grep -B3 '00:19.0'

exit 0
#igb_uio:
# Oct 22 10:40:27 node08ob52 systemd[1]: Started Service for snap application microstack.ovs-vswitchd.
# Oct 22 10:40:45 node08ob52 ovs-vswitchd[20802]: ovs|00001|dpdk|ERR|EAL: Error reading from file descriptor 24: Input/output error
# Oct 22 10:40:45 node08ob52 ovs-vswitchd[20802]: ovs|00002|dpdk|ERR|EAL: Error reading from file descriptor 24: Input/output error
# Oct 22 10:40:45 node08ob52 ovs-vswitchd[20802]: ovs|00003|dpdk|ERR|EAL: Error reading from file descriptor 24: Input/output error
# Oct 22 10:40:45 node08ob52 ovs-vswitchd[20802]: ovs|00004|dpdk|ERR|EAL: Error reading from file descriptor 24: Input/output error
# Oct 22 10:40:48 node08ob52 ovs-vswitchd[20802]: ovs|00873|dpdk|ERR|Dropped 20837 log messages in last 0 seconds (most recently, 0 seconds ago) due to excessive rate
# Oct 22 10:40:48 node08ob52 ovs-vswitchd[20802]: ovs|00874|dpdk|ERR|EAL: Error reading from file descriptor 24: Input/output error
# Oct 22 10:40:48 node08ob52 ovs-vswitchd[20802]: ovs|00875|dpdk|ERR|Dropped 24292 log messages in last 0 seconds (most recently, 0 seconds ago) due to excessive rate
# Oct 22 10:40:48 node08ob52 ovs-vswitchd[20802]: ovs|00876|dpdk|ERR|EAL: Error reading from file descriptor 24: Input/output error
# Oct 22 10:40:48 node08ob52 ovs-vswitchd[20802]: ovs|00877|dpdk|ERR|Dropped 25760 log messages in last 0 seconds (most recently, 0 seconds ago) due to excessive rate
# Oct 22 10:40:48 node08ob52 ovs-vswitchd[20802]: ovs|00878|dpdk|ERR|EAL: Error reading from file descriptor 24: Input/output error
# Oct 22 10:40:48 node08ob52 ovs-vswitchd[20802]: ovs|00879|dpdk|ERR|Dropped 24396 log messages in last 0 seconds (most recently, 0 seconds ago) due to excessive rate
# Oct 22 10:40:48 node08ob52 ovs-vswitchd[20802]: ovs|00880|dpdk|ERR|EAL: Error reading from file descriptor 24: Input/output error
sudo microstack.dpdk-devbind --status | grep -B3 '00:19.0'
sudo modprobe igb_uio
sudo microstack.dpdk-devbind --unbind 00:19.0
sudo microstack.dpdk-devbind --bind=igb_uio 00:19.0
sudo microstack.dpdk-devbind --status | grep -B3 '00:19.0'

#vfio-pci
# Oct 22 10:39:37 node08ob52 ovs-vswitchd[19179]: ovs|00020|dpdk|ERR|EAL:   cannot set up DMA remapping, error 14 (Bad address)
# Oct 22 10:39:37 node08ob52 ovs-vswitchd[19179]: ovs|00021|dpdk|ERR|EAL:   0000:00:19.0 DMA remapping failed, error 14 (Bad address)
# Oct 22 10:39:37 node08ob52 ovs-vswitchd[19179]: ovs|00022|dpdk|ERR|EAL: Requested device 0000:00:19.0 cannot be used

sudo microstack.dpdk-devbind --status | grep -B3 '00:19.0'
sudo modprobe vfio-pci
sudo microstack.dpdk-devbind --unbind 00:19.0
sudo microstack.dpdk-devbind --bind=vfio-pci 00:19.0
sudo microstack.dpdk-devbind --status | grep -B3 '00:19.0'

