import time
import subprocess

import mock
import docker
import pytest

from .. import container_monitor as cm
from .. import utilities

user = subprocess.check_output(['whoami'])

def is_valid_user():
    return user == 'root\n'

def query_stat_side_effect(cmd, shell=True):
    print(cmd)
    return "3.64%    49.98MiB / 15.59GiB"

def query_size_side_effect(cmd, shell=True):
    print(cmd)
    assert cmd == \
    'docker images foo --format "{{.Size}}"'
    return "10.0MB"

def query_status_side_effect(**kwargs):
    foo_container = mock.Mock()
    foo_container.status = u'running'
    return [foo_container]

@pytest.fixture(scope='module')
def monitor_class():
    monitor = cm.ContainerMonitor()
    monitor.client = mock.Mock(autospec=True)
    yield monitor
    monitor.database.close_connection()

@mock.patch('subprocess.check_output')
def test_measure_basic_stat(output_mock, monitor_class):
    output_mock.side_effect = query_stat_side_effect
    monitor = monitor_class
    stats = monitor.measure_container_basic_stat('foo')
    assert stats[0] == 3.64
    assert stats[1] == 49.98*(1024**2/1000**2)

@mock.patch('subprocess.check_output')
def test_measure_size(output_mock, monitor_class):
    output_mock.side_effect = query_size_side_effect
    monitor = monitor_class
    stat = monitor.measure_container_size('foo', 'foo')
    assert stat == 10.0

def test_get_status(monitor_class):
    monitor = monitor_class
    monitor.client.containers.list.side_effect = query_status_side_effect
    status = monitor.container_status('foo')
    monitor.client.containers.list.assert_called_with(filters={'name':'foo'})
    assert status == 'running'

@mock.patch('time.sleep')
def test_listen_change_with_timeout(time_mock):
    a = 10
    b = 10
    def check_function():
        return a!=b

    end_cb = mock.Mock()
    utilities.listen_change_with_timeout(check_function, end_cb, 10)
    assert end_cb.is_called
    assert len(time_mock.call_args_list) == 10
    time_mock = mock.Mock()
    end_cbd = mock.Mock()
    def check_function2():
        return a==b
    utilities.listen_change_with_timeout(check_function, end_cb, 10)
    assert end_cb.is_called
    assert len(time_mock.call_args_list) == 0
