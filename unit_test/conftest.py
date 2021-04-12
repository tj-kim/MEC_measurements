import pytest
import subprocess
import collections

from .. import create_test_db

MQTTMsg = collections.namedtuple('MQTTMsg', ['topic', 'payload'])

def get_user():
    return subprocess.check_output(['whoami']).rstrip('\n')

def pytest_runtest_makereport(item, call):
    if "incremental" in item.keywords:
        if call.excinfo is not None:
            parent = item.parent
            parent._previousfailed = item

def pytest_runtest_setup(item):
    if "incremental" in item.keywords:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail("previous test failed (%s)" % previousfailed.name)

ServerInfo = collections.namedtuple('ServerInfo', ['ip', 'port'])

@pytest.fixture(scope='module')
def create_db():
    create_test_db.main()
    return None

@pytest.fixture(scope='module')
def select_server():
    TIME_OUT = 5
    server_list = [
        ServerInfo('10.0.99.2',9999), # Vagrant IP
        ServerInfo('192.168.0.111',9999), # SBAN IP
        ServerInfo('172.18.35.196',9999) # Centre
    ]
    try:
        devbox_ip = subprocess.check_output(['host', 'wnds-devbox'])
        devbox_ip = devbox_ip.rstrip('\n').split()[-1]
    except subprocess.CalledProcessError:
        devbox_ip = ''
    if devbox_ip != '':
        server_list.append(ServerInfo(devbox_ip, 9999))

    for server in server_list:
        try:
            subprocess.check_output(['nc', '-zv', server.ip, str(server.port),
                                     '-w', str(TIME_OUT)])
            return ServerInfo(*server)
        except subprocess.CalledProcessError:
            pass
    pytest.skip('Cannot connect any to MQTT server')
