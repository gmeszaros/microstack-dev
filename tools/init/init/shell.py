"""shell.py

Contains wrappers around subprocess and pymysql commands, specific to
our needs in the init script.

# TODO capture stdout (and output to log.DEBUG)

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

import subprocess
from time import sleep
from typing import Dict, List

import netaddr
import netifaces
import pymysql
import socket
import wget

from init.config import Env, log

_env = Env().get_env()


def _popen(*args: List[str], env: Dict = _env):
    """Run a shell command, piping STDOUT and STDERR to our logger.

    :param args: strings to be composed into the bash call.
    :param env: defaults to our Env singleton; can be overriden.

    """
    proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, bufsize=1,
                            universal_newlines=True, encoding='utf-8')
    for line in iter(proc.stdout.readline, ''):
        log.debug(line)

    proc.wait()
    return proc


def check(*args: List[str], env: Dict = _env) -> int:
    """Execute a shell command, raising an error on failed excution.

    :param args: strings to be composed into the bash call.
    :param env: defaults to our Env singleton; can be overriden.

    """
    proc = _popen(*args, env=env)
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, " ".join(args))
    return proc.returncode


def check_output(*args: List[str], env: Dict = _env) -> str:
    """Execute a shell command, returning the output of the command.

    :param args: strings to be composed into the bash call.
    :param env: defaults to our Env singleton; can be overriden.

    Include our env; pass in any extra keyword args.
    """
    return subprocess.check_output(args, env=env,
                                   universal_newlines=True).strip()


def call(*args: List[str], env: Dict = _env) -> bool:
    """Execute a shell command.

    Return True if the call executed successfully (returned 0), or
    False if it returned with an error code (return > 0)

    :param args: strings to be composed into the bash call.
    :param env: defaults to our Env singleton; can be overriden.
    """
    proc = _popen(*args, env=env)
    return not proc.returncode


def shell(cmd: str, env: Dict = _env) -> int:
    """Execute a command, using the actual bourne again shell.

    Use this in cases where it is difficult to compose a comma
    separate list that will get parsed into a succesful bash
    command. (E.g., your bash command contains an argument like ".*"
    ".*" ".*")

    :param cmd: the command to run.
    :param env: defaults to our Env singleton; can be overriden.

    """
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, bufsize=1,
                            universal_newlines=True, shell=True)
    for line in iter(proc.stdout.readline, ''):
        log.debug(line)
    proc.wait()
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    return proc.returncode


def sql(cmd: str) -> None:
    """Execute some SQL!

    Really simply wrapper around a pymysql connection, suitable for
    passing the limited CREATE and GRANT commands that we need to pass
    in our init script.

    :param cmd: sql to execute.

    """
    mysql_conf = '{SNAP_COMMON}/etc/mysql/my.cnf'.format(**_env)
    connection = pymysql.connect(read_default_file=mysql_conf)

    with connection.cursor() as cursor:
        cursor.execute(cmd)


def nc_wait(addr: str, port: str) -> None:
    """Wait for a service to be answering on a port."""
    print('Waiting for {}:{}'.format(addr, port))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while sock.connect_ex((addr, int(port))) != 0:
        sleep(1)


def log_wait(log: str, message: str) -> None:
    """Wait until a message appears in a log."""
    while True:
        with open(log, 'r') as log_file:
            for line in log_file.readlines():
                if message in line:
                    return
        sleep(1)


def restart(service: str) -> None:
    """Restart a microstack service.

    :param service: the service(s) to be restarted. Can contain wild cards.
                    e.g. *rabbit*

    """
    check(
        'systemctl',
        'restart',
        'snap.{SNAP_INSTANCE_NAME}.{SERVICE}'.format(**_env, SERVICE=service)
    )


def disable(service: str) -> None:
    """Disable and mask a service.

    :param service: the service(s) to be disabled. Can contain wild cards.
                    e.g. *rabbit*

    """
    check('systemctl', 'disable', 'snap.microstack.{}'.format(service))
    check('systemctl', 'mask', 'snap.microstack.{}'.format(service))


def download(url: str, output: str) -> None:
    """Download a file to a path"""
    wget.download(url, output)


def fetch_ip_address():
    try:
        interface = netifaces.gateways()['default'][netifaces.AF_INET][1]
        return netifaces.ifaddresses(interface)[netifaces.AF_INET][0]['addr']
    except (KeyError, IndexError):
        log.exception('Failed to get ip address!')
        return None


def default_network():
    """Get info about the default netowrk.

    """
    gateway, interface = netifaces.gateways()['default'][netifaces.AF_INET]
    netmask = netifaces.ifaddresses(interface)[netifaces.AF_INET][0]['netmask']
    ip_address = netifaces.ifaddresses(interface)[netifaces.AF_INET][0]['addr']
    bits = netaddr.IPAddress(netmask).netmask_bits()
    # TODO: better way to do this!
    cidr = gateway.split('.')
    cidr[-1] = '0/{}'.format(bits)
    cidr = '.'.join(cidr)

    return ip_address, gateway, cidr
