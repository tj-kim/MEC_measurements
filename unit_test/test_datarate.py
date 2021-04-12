import os
import sys
import subprocess

import mock
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '../end-user'))

import route
import datarate

N_OF_USERS = 5
DUMMY_IP = '127.0.0.1'
DUMMY_PORT = 9900
DUMMY_ID = 100

@pytest.fixture(scope='module')
def rate_man():
    mock_route = mock.Mock()
    mock_route.tables = [route.RouteEntry(mark=DUMMY_ID + i,
                                     name='user{}'.format(i),
                                     id=DUMMY_ID + i,
                                     dest_ip=DUMMY_IP,
                                     dest_port=DUMMY_PORT + i)
                    for i in range(N_OF_USERS)]
    r = datarate.SpeedManager(mock_route, 'eth0')
    return r

def existing_node_side_effect(args):
    output = ''
    cmd = ' '.join(args)
    raise subprocess.CalledProcessError(cmd=cmd, output=output,
                                        returncode=2)

@pytest.mark.incremental
class TestSpeedManager(object):
    def test_failed_allocation(self, rate_man):
        rate_man.route.is_allocated = False
        with pytest.raises(RuntimeError):
            rate_man.allocate_speeds()

    def test_allocation(self, rate_man):
        rate_man.run_command = mock.MagicMock(return_value='')
        rate_man.route.is_allocated = True
        rate_man.allocate_speeds()
        expected_calls = \
        ['tc qdisc add dev eth0 root handle fafa: htb default 1'] + \
        ['tc class add dev eth0 parent fafa: classid fafa:{} htb '
         'rate 150Mbit'.format(i) for i in range(N_OF_USERS)]
        rate_man.run_command.assert_has_calls([
            mock.call(c.split()) for c in expected_calls
        ])

    def test_allocation_with_existing_node(self, rate_man):
        rate_man.run_command = mock.MagicMock()
        rate_man.route.is_allocated = True
        # Raise an exception once.
        rate_man.run_command.side_effect = \
            [existing_node_side_effect, None, None] \
            + [None for i in range(N_OF_USERS)]
        expected_calls = \
        ['tc qdisc add dev eth0 root handle fafa: htb default 1',
         'tc qdisc del dev eth0 root handle fafa:'
         'tc qdisc del dev eth0 root handle fafa: htb default 1'] + \
        ['tc class add dev eth0 parent fafa: classid fafa:{} htb '
         'rate 150Mbit'.format(i) for i in range(N_OF_USERS)]
        rate_man.allocate_speeds()

    def test_set_speed_no_filter(self, rate_man):
        rate_man.run_command = mock.MagicMock(return_value='')
        user_index = 0
        rate_man.route.tables[user_index].have_filter = False
        new_speed = 10
        rate_man.set_speed(rate_man.route.tables[user_index].name,
                           new_speed)
        expected_calls = [
            'tc filter add dev eth0 protocol ip parent fafa: prio 2 '
            'handle {} fw flowid fafa:0'.format(DUMMY_ID),
            'tc class replace dev eth0 parent fafa: classid fafa:{} '
            'htb rate {}Mbit'.format(user_index, new_speed)
        ]
        rate_man.run_command.assert_has_calls([
            mock.call(c.split()) for c in expected_calls
            ])
        assert rate_man.route.tables[user_index].have_filter == True

    def test_set_speed_with_filter(self, rate_man):
        new_speed = 11
        user_index = 0
        rate_man.run_command = mock.MagicMock(return_value='')
        rate_man.set_speed(rate_man.route.tables[user_index].name,
                           new_speed)
        expected_call = \
            'tc class replace dev eth0 parent fafa: classid fafa:{} ' \
            'htb rate {}Mbit'.format(user_index, new_speed)
        rate_man.run_command.assert_called_with(expected_call.split())

    def test_clear_all(self, rate_man):
        rate_man.run_command = mock.MagicMock(return_value='')
        rate_man.clear_all()
        expected_call = \
            'tc qdisc del dev eth0 root handle fafa:'
        rate_man.run_command.assert_called_with(expected_call.split())
