import argparse
import json
import petname
import os
import subprocess
import time
import sys

from typing import List


def check(*args: List[str]) -> int:
    """Execute a shell command, raising an error on failed excution.

    :param args: strings to be composed into the bash call.

    """
    return subprocess.check_call(args, env=os.environ)


def check_output(*args: List[str]) -> str:
    """Execute a shell command, returning the output of the command.

    :param args: strings to be composed into the bash call.

    Include our env; pass in any extra keyword args.
    """
    return subprocess.check_output(args, universal_newlines=True,
                                   env=os.environ).strip()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('image',
                        help='The name of the openstack image to use.')
    parser.add_argument('-n', '--name', help='The name of the instance')
    parser.add_argument('-k', '--key', help='ssh key to use',
                        default='microstack')
    parser.add_argument('-f', '--flavor', help='Flavor to use.',
                        default='m1.tiny')
    parser.add_argument('-t', '--net-id', help='Network', default='test')
    parser.add_argument('-w', '--wait', action='store_true',
                        help='Wait for server to become active before exiting')
    parser.add_argument('-r', '--retry', action='store_true',
                        help='Retry failed launch attempts')

    args = parser.parse_args()
    return args


def create_server(name, args):

    ret = check_output('openstack', 'server', 'create',
                       '--flavor', args.flavor,
                       '--image', args.image,
                       '--nic', 'net-id={}'.format(args.net_id),
                       '--key-name', args.key,
                       name, '--format', 'json')
    ret = json.loads(ret)
    return ret['id']


def delete_server(server_id):
    check('openstack', 'server', 'delete', server_id)


def check_server(name, server_id, args):
    status = 'Unknown'

    retries = 0
    max_retries = 10

    waits = 0
    max_waits = 1000  # 100 seconds + ~1000 calls to `openstack server list`.

    while True:
        status_ = check_output('openstack', 'server', 'list',
                               '--format', 'json')
        status_ = json.loads(status_)
        for server in status_:
            if server['ID'] == server_id:
                status = server['Status']

        if not status:
            # Something went wrong ...
            break

        if not args.wait and not args.retry:
            # Just return BUILD or ACTIVE or Unknown.
            break

        if waits < 1:
            print("Waiting for server to build ...")

        if status == 'BUILD':
            if waits <= max_waits:
                waits += 1
                time.sleep(0.1)
                continue
            # Looks like we're stuck! Fall through to ERROR check
            # below.
            status = 'BUILD (stuck)'

        if status in ['ERROR', 'BUILD (stuck)']:
            if not args.retry or retries > max_retries:
                break

            print('Ran into an error launching server. Retrying ...')
            delete_server(server_id)
            server_id = create_server(name, args)
            waits = 0  # Reset waits
            retries += 1
            continue

        if status == 'ACTIVE':
            break

    return (status, server_id)


def launch(name, args):
    """Launch a server!"""

    print("Launching server ...")
    server_id = create_server(name, args)

    status, server_id = check_server(name, server_id, args)
    if status not in ['BUILD', 'ACTIVE']:
        print('Uh-oh. Something went wrong launching {}. Status is {}.'.format(
            name, status))
        sys.exit(1)

    print('Allocating floating ip ...')
    ip = check_output('openstack', 'floating', 'ip', 'create', '-f', 'value',
                      '-c', 'floating_ip_address', 'external')
    check('openstack', 'server', 'add', 'floating', 'ip', server_id, ip)

    print("""\
Server {} launched! (status is {})

Access it with `ssh -i \
$HOME/.ssh/id_microstack` <username>@{}""".format(name, status, ip))

    gate = check_output('snapctl', 'get', 'questions.ext-gateway')
    print('You can also visit the OpenStack dashboard at http://{}'.format(
        gate))


def main():
    args = parse_args()
    name = args.name or petname.generate()

    # Parse microstack.rc
    # TODO: we need a share lib that does this in a more robust way.
    mstackrc = '{SNAP_COMMON}/etc/microstack.rc'.format(**os.environ)
    with open(mstackrc, 'r') as rc_file:
        for line in rc_file.readlines():
            if not line.startswith('export'):
                continue
            key, val = line[7:].split('=')
            os.environ[key.strip()] = val.strip()

    return launch(name, args)


if __name__ == '__main__':
    main()
