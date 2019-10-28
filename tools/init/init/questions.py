"""questions.py

All of our subclasses of Question live here.

We might break this file up into multiple pieces at some point, but
for now, we're keeping things simple (if a big lengthy)

----------------------------------------------------------------------

Copyright 2019 Canonical Ltd

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

 http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""

import json
from time import sleep
from os import path

from init.shell import (check, call, check_output, shell, sql, nc_wait,
                        log_wait, restart, download)
from init.config import Env, log
from init.question import Question


_env = Env().get_env()


class ConfigError(Exception):
    """Suitable error to raise in case there is an issue with the snapctl
    config or environment vars.

    """


class ConfigQuestion(Question):
    """Question class that simply asks for and sets a config value.

    All we need to do is run 'snap-openstack setup' after we have saved
    off the value. The value to be set is specified by the name of the
    question class.

    """
    def after(self, answer):
        """Our value has been saved.

        Run 'snap-openstack setup' to write it out, and load any changes to
        microstack.rc.

        # TODO this is a bit messy and redundant. Come up with a clean
        way of loading and writing config after the run of
        ConfigQuestions have been asked.

        """
        check('snap-openstack', 'setup')

        mstackrc = '{SNAP_COMMON}/etc/microstack.rc'.format(**_env)
        with open(mstackrc, 'r') as rc_file:
            for line in rc_file.readlines():
                if not line.startswith('export'):
                    continue
                key, val = line[7:].split('=')
                _env[key.strip()] = val.strip()


class Dns(Question):
    """Possibly override default dns."""

    _type = 'string'
    _question = 'DNS to use'

    def yes(self, answer: str):
        """Override the default dhcp_agent.ini file."""

        file_path = '{SNAP_COMMON}/etc/neutron/dhcp_agent.ini'.format(**_env)

        with open(file_path, 'w') as f:
            f.write("""\
[DEFAULT]
interface_driver = openvswitch
dhcp_driver = neutron.agent.linux.dhcp.Dnsmasq
enable_isolated_metadata = True
dnsmasq_dns_servers = {answer}
""".format(answer=answer))

        # Neutron is not actually started at this point, so we don't
        # need to restart.
        # TODO: This isn't idempotent, because it will behave
        # differently if we re-run this script when neutron *is*
        # started. Need to figure that out.


class ExtGateway(ConfigQuestion):
    """Possibly override default ext gateway."""

    _type = 'string'
    _question = 'External Gateway'

    def yes(self, answer):
        # Preserve old behavior.
        # TODO: update this
        _env['extgateway'] = answer


class ExtCidr(ConfigQuestion):
    """Possibly override the cidr."""

    _type = 'string'
    _question = 'External Ip Range'

    def yes(self, answer):
        # Preserve old behavior.
        # TODO: update this
        _env['extcidr'] = answer


class OsPassword(ConfigQuestion):
    _type = 'string'
    _question = 'Openstack Admin Password'

    def yes(self, answer):
        # Preserve old behavior.
        # TODO: update this
        _env['ospassword'] = answer

    # TODO obfuscate the password!


class IpForwarding(Question):
    """Possibly setup IP forwarding."""

    _type = 'boolean'  # Auto for now, to maintain old behavior.
    _question = 'Do you wish to setup ip forwarding? (recommended)'

    def yes(self, answer: str) -> None:
        """Use sysctl to setup ip forwarding."""
        log.info('Setting up ipv4 forwarding...')

        check('sysctl', 'net.ipv4.ip_forward=1')


class ForceQemu(Question):
    _type = 'auto'

    def yes(self, answer: str) -> None:
        """Possibly force us to use qemu emulation rather than kvm."""

        cpuinfo = check_output('cat', '/proc/cpuinfo')
        if 'vmx' in cpuinfo or 'svm' in cpuinfo:
            # We have processor extensions installed. No need to Force
            # Qemu emulation.
            return

        _path = '{SNAP_COMMON}/etc/nova/nova.conf.d/hypervisor.conf'.format(
            **_env)

        with open(_path, 'w') as _file:
            _file.write("""\
[DEFAULT]
compute_driver = libvirt.LibvirtDriver

[workarounds]
disable_rootwrap = True

[libvirt]
virt_type = qemu
cpu_mode = host-model
""")

        # TODO: restart nova services when re-running this after init.


class VmSwappiness(Question):

    _type = 'boolean'
    _question = 'Do you wish to set vm swappiness to 1? (recommended)'

    def yes(self, answer: str) -> None:
        # TODO
        pass


class FileHandleLimits(Question):

    _type = 'boolean'
    _question = 'Do you wish to increase file handle limits? (recommended)'

    def yes(self, answer: str) -> None:
        # TODO
        pass


class RabbitMq(Question):
    """Wait for Rabbit to start, then setup permissions."""

    _type = 'boolean'

    def _wait(self) -> None:
        nc_wait(_env['extgateway'], '5672')
        log_file = '{SNAP_COMMON}/log/rabbitmq/startup_log'.format(**_env)
        log_wait(log_file, 'completed')

    def _configure(self) -> None:
        """Configure RabbitMQ

        (actions may have already been run, in which case we fail silently).
        """
        # Add Erlang HOME to env.
        env = dict(**_env)
        env['HOME'] = '{SNAP_COMMON}/lib/rabbitmq'.format(**_env)
        # Configure RabbitMQ
        call('rabbitmqctl', 'add_user', 'openstack', 'rabbitmq', env=env)
        shell('rabbitmqctl set_permissions openstack ".*" ".*" ".*"', env=env)

    def yes(self, answer: str) -> None:
        log.info('Waiting for RabbitMQ to start ...')
        self._wait()
        log.info('RabbitMQ started!')
        log.info('Configuring RabbitMQ ...')
        self._configure()
        log.info('RabbitMQ Configured!')


class DatabaseSetup(Question):
    """Setup keystone permissions, then setup all databases."""

    _type = 'boolean'

    def _wait(self) -> None:
        nc_wait(_env['extgateway'], '3306')
        log_wait('{SNAP_COMMON}/log/mysql/error.log'.format(**_env),
                 'mysqld: ready for connections.')

    def _create_dbs(self) -> None:
        for db in ('neutron', 'nova', 'nova_api', 'nova_cell0', 'cinder',
                   'glance', 'keystone'):
            sql("CREATE DATABASE IF NOT EXISTS {db};".format(db=db))
            sql(
                "GRANT ALL PRIVILEGES ON {db}.* TO {db}@{extgateway} \
                IDENTIFIED BY '{db}';".format(db=db, **_env))

    def _bootstrap(self) -> None:

        if call('openstack', 'user', 'show', 'admin'):
            return

        bootstrap_url = 'http://{extgateway}:5000/v3/'.format(**_env)

        check('snap-openstack', 'launch', 'keystone-manage', 'bootstrap',
              '--bootstrap-password', _env['ospassword'],
              '--bootstrap-admin-url', bootstrap_url,
              '--bootstrap-internal-url', bootstrap_url,
              '--bootstrap-public-url', bootstrap_url)

    def yes(self, answer: str) -> None:
        """Setup Databases.

        Create all the MySQL databases we require, then setup the
        fernet keys and create the service project.

        """
        log.info('Waiting for MySQL server to start ...')
        self._wait()
        log.info('Mysql server started! Creating databases ...')
        self._create_dbs()

        check('snapctl', 'set', 'database.ready=true')

        # Start keystone-uwsgi. We use snapctl, because systemd
        # doesn't yet know about the service.
        check('snapctl', 'start', 'microstack.nginx')
        check('snapctl', 'start', 'microstack.keystone-uwsgi')

        log.info('Configuring Keystone Fernet Keys ...')
        check('snap-openstack', 'launch', 'keystone-manage',
              'fernet_setup', '--keystone-user', 'root',
              '--keystone-group', 'root')
        check('snap-openstack', 'launch', 'keystone-manage', 'db_sync')

        restart('keystone-*')

        log.info('Bootstrapping Keystone ...')
        self._bootstrap()

        log.info('Creating service project ...')
        if not call('openstack', 'project', 'show', 'service'):
            check('openstack', 'project', 'create', '--domain',
                  'default', '--description', 'Service Project',
                  'service')

        log.info('Keystone configured!')


class NovaSetup(Question):
    """Create all relevant nova users and services."""

    _type = 'boolean'

    def _flavors(self) -> None:
        """Create default flavors."""

        if not call('openstack', 'flavor', 'show', 'm1.tiny'):
            check('openstack', 'flavor', 'create', '--id', '1',
                  '--ram', '512', '--disk', '1', '--vcpus', '1', 'm1.tiny')
        if not call('openstack', 'flavor', 'show', 'm1.small'):
            check('openstack', 'flavor', 'create', '--id', '2',
                  '--ram', '2048', '--disk', '20', '--vcpus', '1', 'm1.small')
        if not call('openstack', 'flavor', 'show', 'm1.medium'):
            check('openstack', 'flavor', 'create', '--id', '3',
                  '--ram', '4096', '--disk', '20', '--vcpus', '2', 'm1.medium')
        if not call('openstack', 'flavor', 'show', 'm1.large'):
            check('openstack', 'flavor', 'create', '--id', '4',
                  '--ram', '8192', '--disk', '20', '--vcpus', '4', 'm1.large')
        if not call('openstack', 'flavor', 'show', 'm1.xlarge'):
            check('openstack', 'flavor', 'create', '--id', '5',
                  '--ram', '16384', '--disk', '20', '--vcpus', '8',
                  'm1.xlarge')

    def yes(self, answer: str) -> None:
        log.info('Configuring nova ...')

        if not call('openstack', 'user', 'show', 'nova'):
            check('openstack', 'user', 'create', '--domain',
                  'default', '--password', 'nova', 'nova')
            check('openstack', 'role', 'add', '--project',
                  'service', '--user', 'nova', 'admin')

        if not call('openstack', 'user', 'show', 'placement'):
            check('openstack', 'user', 'create', '--domain', 'default',
                  '--password', 'placement', 'placement')
            check('openstack', 'role', 'add', '--project', 'service',
                  '--user', 'placement', 'admin')

        if not call('openstack', 'service', 'show', 'compute'):
            check('openstack', 'service', 'create', '--name', 'nova',
                  '--description', '"Openstack Compute"', 'compute')
            for endpoint in ['public', 'internal', 'admin']:
                call('openstack', 'endpoint', 'create', '--region',
                     'microstack', 'compute', endpoint,
                     'http://{extgateway}:8774/v2.1'.format(**_env))

        if not call('openstack', 'service', 'show', 'placement'):
            check('openstack', 'service', 'create', '--name',
                  'placement', '--description', '"Placement API"',
                  'placement')

            for endpoint in ['public', 'internal', 'admin']:
                call('openstack', 'endpoint', 'create', '--region',
                     'microstack', 'placement', endpoint,
                     'http://{extgateway}:8778'.format(**_env))

        # Grant nova user access to cell0
        sql(
            "GRANT ALL PRIVILEGES ON nova_cell0.* TO 'nova'@'{extgateway}' \
            IDENTIFIED BY \'nova';".format(**_env))

        # Use snapctl to start nova services.  We need to call them
        # out manually, because systemd doesn't know about them yet.
        # TODO: parse the output of `snapctl services` to get this
        # list automagically.
        for service in [
                'microstack.nova-api',
                'microstack.nova-api-metadata',
                'microstack.nova-compute',
                'microstack.nova-conductor',
                'microstack.nova-scheduler',
                'microstack.nova-uwsgi',
        ]:
            check('snapctl', 'start', service)

        check('snap-openstack', 'launch', 'nova-manage', 'api_db', 'sync')

        if 'cell0' not in check_output('snap-openstack', 'launch',
                                       'nova-manage', 'cell_v2',
                                       'list_cells'):
            check('snap-openstack', 'launch', 'nova-manage',
                  'cell_v2', 'map_cell0')

        if 'cell1' not in check_output('snap-openstack', 'launch',
                                       'nova-manage', 'cell_v2', 'list_cells'):

            check('snap-openstack', 'launch', 'nova-manage', 'cell_v2',
                  'create_cell', '--name=cell1', '--verbose')

        check('snap-openstack', 'launch', 'nova-manage', 'db', 'sync')

        restart('nova-*')

        nc_wait(_env['extgateway'], '8774')

        sleep(5)  # TODO: log_wait

        log.info('Creating default flavors...')
        self._flavors()


class NeutronSetup(Question):
    """Create all relevant neutron services and users."""

    _type = 'boolean'

    def yes(self, answer: str) -> None:
        log.info('Configuring Neutron')

        if not call('openstack', 'user', 'show', 'neutron'):
            check('openstack', 'user', 'create', '--domain', 'default',
                  '--password', 'neutron', 'neutron')
            check('openstack', 'role', 'add', '--project', 'service',
                  '--user', 'neutron', 'admin')

        if not call('openstack', 'service', 'show', 'network'):
            check('openstack', 'service', 'create', '--name', 'neutron',
                  '--description', '"OpenStack Network"', 'network')
            for endpoint in ['public', 'internal', 'admin']:
                call('openstack', 'endpoint', 'create', '--region',
                     'microstack', 'network', endpoint,
                     'http://{extgateway}:9696'.format(**_env))

        for service in [
                'microstack.neutron-api',
                'microstack.neutron-dhcp-agent',
                'microstack.neutron-l3-agent',
                'microstack.neutron-metadata-agent',
                'microstack.neutron-openvswitch-agent',
        ]:
            check('snapctl', 'start', service)

        check('snap-openstack', 'launch', 'neutron-db-manage', 'upgrade',
              'head')

        restart('neutron-*')

        nc_wait(_env['extgateway'], '9696')

        sleep(5)  # TODO: log_wait

        if not call('openstack', 'network', 'show', 'test'):
            check('openstack', 'network', 'create', 'test')

        if not call('openstack', 'subnet', 'show', 'test-subnet'):
            check('openstack', 'subnet', 'create', '--network', 'test',
                  '--subnet-range', '192.168.222.0/24', 'test-subnet')

        if not call('openstack', 'network', 'show', 'external'):
            check('openstack', 'network', 'create', '--external',
                  '--provider-physical-network=physnet1',
                  '--provider-network-type=flat', 'external')
        if not call('openstack', 'subnet', 'show', 'external-subnet'):
            check('openstack', 'subnet', 'create', '--network', 'external',
                  '--subnet-range', _env['extcidr'], '--no-dhcp',
                  'external-subnet')

        if not call('openstack', 'router', 'show', 'test-router'):
            check('openstack', 'router', 'create', 'test-router')
            check('openstack', 'router', 'add', 'subnet', 'test-router',
                  'test-subnet')
            check('openstack', 'router', 'set', '--external-gateway',
                  'external', 'test-router')


class GlanceSetup(Question):
    """Setup glance, and download an initial Cirros image."""

    _type = 'boolean'

    def _fetch_cirros(self) -> None:

        if call('openstack', 'image', 'show', 'cirros'):
            return

        env = dict(**_env)
        env['VER'] = '0.4.0'
        env['IMG'] = 'cirros-{VER}-x86_64-disk.img'.format(**env)

        log.info('Fetching cirros image ...')

        cirros_path = '{SNAP_COMMON}/images/{IMG}'.format(**env)

        if not path.exists(cirros_path):
            check('mkdir', '-p', '{SNAP_COMMON}/images'.format(**env))
            download(
                'http://download.cirros-cloud.net/{VER}/{IMG}'.format(**env),
                '{SNAP_COMMON}/images/{IMG}'.format(**env))

        check('openstack', 'image', 'create', '--file',
              '{SNAP_COMMON}/images/{IMG}'.format(**env),
              '--public', '--container-format=bare',
              '--disk-format=qcow2', 'cirros')

    def yes(self, answer: str) -> None:

        log.info('Configuring Glance ...')

        if not call('openstack', 'user', 'show', 'glance'):
            check('openstack', 'user', 'create', '--domain', 'default',
                  '--password', 'glance', 'glance')
            check('openstack', 'role', 'add', '--project', 'service',
                  '--user', 'glance', 'admin')

        if not call('openstack', 'service', 'show', 'image'):
            check('openstack', 'service', 'create', '--name', 'glance',
                  '--description', '"OpenStack Image"', 'image')
            for endpoint in ['internal', 'admin', 'public']:
                check('openstack', 'endpoint', 'create', '--region',
                      'microstack', 'image', endpoint,
                      'http://{extgateway}:9292'.format(**_env))

        for service in [
                'microstack.glance-api',
                'microstack.registry',  # TODO rename this to glance-registery
        ]:
            check('snapctl', 'start', service)

        check('snap-openstack', 'launch', 'glance-manage', 'db_sync')

        restart('glance*')

        nc_wait(_env['extgateway'], '9292')

        sleep(5)  # TODO: log_wait

        self._fetch_cirros()


class KeyPair(Question):
    """Create a keypair for ssh access to instances.

    TODO: split the asking from executing of questions, as ask about
    this up front. (This needs to run at the end, but for user
    experience reasons, we really want to ask all the non auto
    questions at the beginning.)
    """
    _type = 'string'

    def yes(self, answer: str) -> None:

        if 'microstack' not in check_output('openstack', 'keypair', 'list'):
            log.info('Creating microstack keypair (~/.ssh/{})'.format(answer))
            check('mkdir', '-p', '{HOME}/.ssh'.format(**_env))
            check('chmod', '700', '{HOME}/.ssh'.format(**_env))
            id_ = check_output('openstack', 'keypair', 'create', 'microstack')
            id_path = '{HOME}/.ssh/{answer}'.format(
                HOME=_env['HOME'],
                answer=answer
            )

            with open(id_path, 'w') as file_:
                file_.write(id_)
            check('chmod', '600', id_path)
            # TODO: too many assumptions in the below. Make it portable!
            user = _env['HOME'].split("/")[2]
            check('chown', '{}:{}'.format(user, user), id_path)


class SecurityRules(Question):
    """Setup default security rules."""

    _type = 'boolean'

    def yes(self, answer: str) -> None:
        # Create security group rules
        log.info('Creating security group rules ...')
        group_id = check_output('openstack', 'security', 'group', 'list',
                                '--project', 'admin', '-f', 'value',
                                '-c', 'ID')
        rules = check_output('openstack', 'security', 'group', 'rule', 'list',
                             '--format', 'json')
        ping_rule = False
        ssh_rule = False

        for rule in json.loads(rules):
            if rule['Security Group'] == group_id:
                if rule['IP Protocol'] == 'icmp':
                    ping_rule = True
                if rule['IP Protocol'] == 'tcp':
                    ssh_rule = True

        if not ping_rule:
            check('openstack', 'security', 'group', 'rule', 'create',
                  group_id, '--proto', 'icmp')
        if not ssh_rule:
            check('openstack', 'security', 'group', 'rule', 'create',
                  group_id, '--proto', 'tcp', '--dst-port', '22')


class PostSetup(Question):
    """Sneak in any additional cleanup, then set the initialized state."""

    def yes(self, answer: str) -> None:

        log.info('restarting libvirt and virtlogd ...')
        # This fixes an issue w/ logging not getting set.
        # TODO: fix issue.
        restart('*virt*')

        # Start horizon
        check('snapctl', 'start', 'microstack.horizon-uwsgi')

        check('snapctl', 'set', 'initialized=true')
        log.info('Complete. Marked microstack as initialized!')
