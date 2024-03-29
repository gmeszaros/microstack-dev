# Microstack Demo

These are instructions for setting up the demo that originally ran at
the Denver Open Infrastructure Summit in April of 2019. We'll set up a
working kubernetes cloud on top of microstack, demonstrating how to
deploy a workload on top of our cloud.

## System Requirements

This Demo must be run on a machine with the following specs:

- 16GB or more of RAM
- ~ 100G of free hard disk space
- A quad core or better cpu
- Virtualization extensions enabled on the cpu
- Ubuntu 16.04 or higher.

Example machines:
- A laptop running Ubuntu 19.04, with 32GB of RAM, a 1TB hard drive,
  and a quad core i7 processor.
- A kvm instance running on the above laptop with 16GB of RAM, Ubuntu
  18.04 installed, a 120G hard drive, and 4 cpus.

## Machine Setup

First, you'll need to install some dependencies on your machine.

Obviously, we'll need to install microstack. We'll also install the
juju and kubectl snaps, which will give us tools to deploy and manage
kubernetes, respectively.

```
sudo snap install --classic --beta microstack
sudo snap install --classic juju
sudo snap install --classic kubectl
```

To make sure that you can use the snaps we've installed, add /snap/bin
to your path

```
export PATH=/snap/bin:$PATH
```

or

```
sudo vim /etc/environment
```

Add /snap/bin to the beginning of your path, and save the file, then:

```
source /etc/environment
```

### Performance Considerations

Openstack runs a lot of processes, and opens a lot of network
connections. You may want to tweak your system networking and
virtualization defaults to accommodate this:

```
echo fs.inotify.max_queued_events=1048576 | sudo tee -a /etc/sysctl.conf
echo fs.inotify.max_user_instances=1048576 | sudo tee -a /etc/sysctl.conf
echo fs.inotify.max_user_watches=1048576 | sudo tee -a /etc/sysctl.conf
echo vm.max_map_count=262144 | sudo tee -a /etc/sysctl.conf
echo vm.swappiness=1 | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Initialize MicroStack

At this point, you have all the OpenStack bits on disk, and the
services are running. But they still have to be configured to talk to
each other. Plus, you need a root password and other niceties. Run the
init script to set all of that up:

```
microstack.init --auto
```

(Note that you may leave --auto out at present. The init script will
be interactive in the very near future, however, and if you are
scripting, you'll want to leave that auto in!)

### Optional Microstack Config

By default, microstack will use Cloudflare's 1.1.1.1 as a DNS. If
you're in a network restricted environment, or simply want to use a
different DNS, you'll need to edit the config manually:

```
sudo vim /var/snap/microstack/common/etc/neutron/dhcp_agent.ini
```

Add the following text to `dhcp_agent.ini`:

```
[DEFAULT]
interface_driver = openvswitch
dhcp_driver = neutron.agent.linux.dhcp.Dnsmasq
enable_isolated_metadata = True
dnsmasq_dns_servers = <your dns>
```

You'll need to restart the microstack services if you've made this change:

```
sudo systemctl restart snap.microstack.*
```

### Verify Your Cloud

Create a test instance in your cloud.

`microstack.launch cirros --name test`

This will launch a machine using the built-in cirros image. Once the
machine is setup, verify that you can ping it, then tear it down.

```
ping 10.20.20.<N>
microstack.openstack server delete test
```

## Bootstrap Juju

### Fetch an Ubuntu Image

The cirros images is great for quickly testing out our cloud's
functionality, but for this demo, we'll want to add a more full
featured ubuntu image. Go ahead and download it from the cloud images
repository:


```
mkdir images
curl https://cloud-images.ubuntu.com/bionic/current/bionic-server-cloudimg-amd64.img --output images/bionic-server-cloudimg-amd64.img
```

Now, add the image to your cloud:

```
microstack.openstack image create --file images/bionic-server-cloudimg-amd64.img --public --container-format=bare --disk-format=qcow2 bionic
```

Take note of the image id. Add it to your shell environment as IMAGE
(you'll need it later):

`export IMAGE=<image id>`

### Tell juju how to find your cloud.

Run `juju add-cloud microstack`

Answer the questions as follows:

<table>
  <tr><td>cloud type:</td> <td><code>openstack</code></td></tr>
  <tr><td>endpoint:</td> <td><code>http://10.20.20.1:5000/v3</code></td></tr>
  <tr><td>cert path:</td> <td><code>none</code></td></tr>
  <tr><td>auth type:</td> <td><code>userpass</code></td></tr>
  <tr><td>region:</td> <td><code>microstack</code></td></tr>
  <tr><td>region endpoint:</td> <td><code>http://10.20.20.1:5000/v3</code></td></tr>
  <tr><td>add another region?:</td> <td><code>N</code></td></tr>
</table>

You'll need to load microstack credentials. You can temporarily drop
into the microstack snap's shell environment to make this easy.

```
snap run --shell microstack.init
juju autoload-credentials
exit
```

### Configure simplestreams

In order to function, juju needs to know how to find metadata for the
images in your microstack cloud. Here's how to set that up.

```
mkdir simplestreams
juju metadata generate-image -d ~/simplestreams -i $IMAGE -s bionic -r microstack -u http://10.20.20.1:5000/v3
```

(If you don't still have an `IMAGE` variable in your env, you can find
your image id by running `microstack.openstack image list`)


### Setup a juju controller flavor

```
microstack.openstack flavor create juju-controller --ram 2048 --disk 20 --vcpus 1
```

### Run Juju Bootstrap scripts

You're ready to bootstrap juju!

```
juju bootstrap --debug --config network=test --config external-network=external --config use-floating-ip=true --bootstrap-series=bionic --bootstrap-constraints instance-type=juju-controller --metadata-source $HOME/simplestreams/ microstack microstack
```

### Upload simplestreams data

You'll need to upload your simplestreams data to the juju controller.

```
tar cvzf simplestreams.tar.gz simplestreams
juju switch controller
juju scp simplestreams.tar.gz 0:
juju ssh 0 -- tar xvzf simplestreams.tar.gz
```

### Make a juju model

Drop the following text into a file called `model-config.yaml`:

```yaml
use-floating-ip: true
image-metadata-url: /home/ubuntu/simplestreams/images
network: test
external-network: external
```

Now add the model:

```
juju add-model k8s --config model-config.yaml
```

## Deploy kubernetes

### Create a bundle.yaml

Drop the following text into a file called bundle.yaml:

```yaml
description: A minimal two-machine Kubernetes cluster, appropriate for development.

series: bionic
machines:
  '0':
    constraints: instance-type=m1.small
    series: bionic
  '1':
    constraints: instance-type=m1.small
    series: bionic
  '2':
    constraints: instance-type=m1.small
    series: bionic

services:
  easyrsa:
    annotations:
      gui-x: '450'
      gui-y: '550'
    charm: cs:~containers/easyrsa
    num_units: 1
    to:
    - '2'
  etcd:
    annotations:
      gui-x: '800'
      gui-y: '550'
    charm: cs:~containers/etcd
    num_units: 1
    to:
    - '0'
  flannel:
    annotations:
      gui-x: '450'
      gui-y: '750'
    charm: cs:~containers/flannel
  kubernetes-master:
    annotations:
      gui-x: '800'
      gui-y: '850'
    charm: cs:~containers/kubernetes-master
    constraints: cores=2 mem=4G root-disk=16G
    expose: true
    num_units: 1
    options:
      channel: 1.10/stable
    to:
    - '0'
  kubernetes-worker:
    annotations:
      gui-x: '100'
      gui-y: '850'
    charm: cs:~containers/kubernetes-worker
    constraints: cores=4 mem=4G root-disk=16G
    expose: true
    num_units: 1
    options:
      channel: 1.10/stable
    to:
    - '1'

relations:
- - kubernetes-master:kube-api-endpoint
  - kubernetes-worker:kube-api-endpoint
- - kubernetes-master:kube-control
  - kubernetes-worker:kube-control
- - kubernetes-master:certificates
  - easyrsa:client
- - kubernetes-master:etcd
  - etcd:db
- - kubernetes-worker:certificates
  - easyrsa:client
- - etcd:certificates
  - easyrsa:client
- - flannel:etcd
  - etcd:db
- - flannel:cni
  - kubernetes-master:cni
- - flannel:cni
  - kubernetes-worker:cni
```

### Deploy the bundle

`juju deploy bundle.yaml`

Watch progress with:

`watch --color 'juju status --color'`

Once all the applications are green, you can proceed to using your new
k8s cloud!


## Using Kubernetes

### Setup your kubeconfig

```
mkdir ~/.kube
juju scp kubernetes-master/0:config ~/.kube/config
export KUBECONFIG=$HOME/.kube/config
```

### Verify that your Kubernetes Cloud is Accessible

`kubectl cluster-info`

### Run a project!

The canonical distribution of kubernetes has a microbot demo built
in. To run it, do the following:

```
juju config kubernetes-worker ingress=true
juju run-action kubernetes-worker/0 microbot replicas=2
juju show-action-output <id> # Where id is in the output of the above
```

The show action command should give you a url that looks something like:

microbot.10.20.20.4.xip.io

Try visiting that url in a browser, or simply fetching it with wget (you can also get the url by running `kubectl get ingress`):

```
wget http://microbot.10.20.20.4.xip.io
```

You can inspect your running app with

```
kubectl get pods
kubectl get services,endpoints
```

To clean up, run:

```
juju run-action kubernetes-worker/0 microbot delete=true
```

For more information, visit https://jujucharms.com/canonical-kubernetes/ or ask at https://discourse.jujucharms.com/.
