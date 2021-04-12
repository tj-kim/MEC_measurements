import os
import sys
import time
import json
import sched
import math

import mock
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '../end-user/'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import utilities
import simulated_mobile_eu as simulation
import mobility_models as mobility
from .. import Constants

from conftest import MQTTMsg

@mock.patch('time.time')
def test_simple_roundtrip_moving(mock_time):
    mock_time.return_value = 0
    moving = mobility.SimpleRoundTripMoving(velocity=1, wait_time = 10,
                                              start_x=10, stop_x=100)
    moving.start_moving()
    mock_time.return_value = 10
    x, y = moving.get_new_position()
    assert y == 0
    assert x == 10
    mock_time.return_value = 20
    x, y = moving.get_new_position()
    assert y == 0
    assert x == 20
    mock_time.return_value = 110
    x, y = moving.get_new_position()
    assert x == 90
    mock_time.return_value = 210
    x, y = moving.get_new_position()
    assert x == 30
    x, y = moving.get_new_position()
    mock_time.return_value = 0
    # Test stationary user
    moving = mobility.SimpleRoundTripMoving(velocity=0, wait_time=0,
                                              start_x=10, stop_x=10)
    moving.start_moving()
    mock_time.return_value = 10
    x, y = moving.get_new_position()
    assert x == 10
    assert y == 0

@mock.patch('time.time')
def test_circle_trip_moving(mock_time):
    mock_time.return_value = 0
    v = 1.0
    r = 10.0
    moving = mobility.CircleTripMoving(velocity=v, wait_time=0,
        start_x = r, start_y = 0, radius = r)
    moving.start_moving()
    new_time = 20.0
    mock_time.return_value = new_time
    x, y = moving.get_new_position()
    angle = v*20/r
    new_x = r*math.cos(angle)
    new_y = r*math.sin(angle)
    assert x == new_x
    assert y == new_y

    mock_time.return_value = 2.0*math.pi*r/v
    x, y = moving.get_new_position()
    assert x == r
    assert abs(y) < 0.01


@pytest.fixture(scope='module')
def env():
    interface = utilities.get_default_interface()
    env = simulation.Environment(interface)
    return env

@pytest.mark.incremental
class TestEnv(object):
    def test_place_bts(self, env):
        bts = simulation.BTSInfo('edge01', '', '', 'docker1', 0, 0,
                                 '10.0.99.10')
        env.place_bts(bts)
        bts = simulation.BTSInfo('edge02', '', '', 'docker2', 50, 0,
                                 '10.0.99.11')
        env.place_bts(bts)
        bts = simulation.BTSInfo('edge03', '', '', 'docker3', 100, 0,
                                 '10.0.99.12')
        env.place_bts(bts)

    def test_get_rssi_list(self, env):
        ret = env.get_rssi_list(0,0)
        assert len(ret) == 3

    def test_handover(self, env):
        self.cnt = 0
        eu = mock.Mock()
        ret = env.handover(eu, 'edge01', '')
        assert ret == 0.5

@pytest.fixture(scope='module')
def dev():
    moving = mock.Mock()
    eu = mock.Mock()
    env = mock.Mock()
    test_dev = simulation.MobileDevice(moving, end_user='test',
                                  ap_ssid='edge01')
    test_dev.app = mock.Mock()
    test_dev.env = mock.Mock()
    return test_dev

@pytest.mark.incremental
class TestDevice(object):
    def test_get_current_bts(self, dev):
        ssid, bssid = dev.get_current_bts()
        assert ssid == 'edge01'
        assert bssid == ''

    def test_scan_rssi(self, dev):
        dev.moving.get_new_position = mock.Mock(return_value=(0, 0))
        dev.env.get_rssi_list = mock.Mock(return_value=[
            {'SSID': 'edge01', 'BSSID': '', 'level': -50},
            {'SSID': 'edge02', 'BSSID': '', 'level': -100},
            {'SSID': 'edge03', 'BSSID': '', 'level': -150}])
        ret = dev.scan_rssi()
        assert len(ret) == 2

    @mock.patch("time.time")
    def test_handover(self, mock_time, dev):
        mock_time.return_value = 0
        dev.env.handover = mock.Mock(return_value=0.5)
        cb = mock.Mock()
        dev.connect_to_bts('test', 'test', cb)
        assert dev.is_connected == False
        assert dev.reconnect_time == 0.5
        dev.update_eu()
        assert dev.is_connected == False
        mock_time.return_value = 1
        dev.update_eu()
        assert dev.is_connected == True
        assert dev.reconnect_time == 0
        cb.assert_called()

    def test_terminate(self, dev):
        dev.terminate()
        # The app should be stopped
        dev.app.stop.assert_called()

    def test_update_rate(self, dev):
        dev.env.rate_man = mock.Mock()
        dev.ssid = 'edge01'
        dev.bssid = ''
        dev.device_update_rate()
        #dev.env.rate_man.set_speed.assert_called()


@pytest.fixture(scope='module')
def app(select_server):
    dev = mock.Mock()
    dev.get_current_bts = mock.Mock(return_value=('edge01', ''))
    return simulation.MobileEUTestApp(end_user='test', device=dev,
                                      client_id='test_simulated_eu',
                                      clean_session=True,
                                      broker_ip=select_server.ip,
                                      broker_port=select_server.port,
                                      keepalive=60)

@pytest.mark.incremental
class TestApp(object):
    def test_parse_process_time(self, app):
        recv_json = {'list': [
            {
                'confidence': 0.73343179503559242,
                'object': 'Obama',
                'bb': ['653', '152', '782', '281']},
            {
                'confidence': 0.64899836762788954,
                'object': 'LeeHsienLoong',
                'bb': ['204', '135', '294', '224']}],
            'general': {
                'processTime[ms]': 448.7888813018799,
                'transferTime[ms]': 0.141143798828125,
                'indexServer': 38}}
        ret = app.parse_process_time(json.dumps(recv_json))
        assert ret == 448.7888813018799

    def test_discovery_service(self, app):
        app.publish = mock.Mock()
        app.discovery_service()
        app.publish.assert_called()

    def test_report_rssi(self, app):
        app.publish = mock.Mock()
        app.report_rssi([{'SSID': 'edge01', 'BSSID': '', 'level': -50}])
        app.publish.assert_called()

    def test_report_service(self, app):
        app.publish = mock.Mock()
        app.report_service(0, 10**9, 20000, 10)
        app.publish.assert_called()

    @mock.patch('socket.socket')
    def test_try_connect_to_service(self, mock_socket, app):
        sock = mock.Mock()
        app.service = mock.Mock()
        app.service.ip = '10.0.99.10'
        app.service.port = 9900
        mock_socket.return_value = sock
        app.try_connect_to_service(None)
        sock.connect_ex.return_value = 0
        app.try_connect_to_service(10)

    def test_process_allocated(self, app):
        client = None
        userdata = None
        app.try_connect_to_service = mock.Mock()
        assert app.state == simulation.EU_STATE.INIT
        msg = MQTTMsg('{}/{}'.format(Constants.ALLOCATED, app.end_user),
                      json.dumps({
                          'service_name': 'yolo',
                          'server_name': 'docker1',
                          'ip': '10.0.99.10',
                          'port': 9900
                      }))
        app.process_allocated(client, userdata, msg)
        assert app.state == simulation.EU_STATE.NORMAL
        app.try_connect_to_service.assert_called()

    def test_process_handover(self, app):
        client = None
        userdata = None
        msg = MQTTMsg('{}/{}'.format(Constants.HANDOVER, app.end_user),
                      json.dumps({
                          Constants.NEXT_SSID: 'edge02',
                          Constants.NEXT_BSSID: ''}))
        app.process_handover(client, userdata, msg)
        app.device.connect_to_bts.assert_called_with('edge02', '', app.handover_cb)

    def test_process_migrated(self, app):
        client = None
        userdata = None
        app.stream_sock = mock.Mock()
        msg = MQTTMsg('{}/{}'.format(Constants.MIGRATED, app.end_user),
                      json.dumps({
                          'service_name': 'yolo',
                          'server_name': 'docker2',
                          'ip': '10.0.99.11',
                          'port': 9900
                      }))
        app.process_migrated(client, userdata, msg)
        assert app.state == simulation.EU_STATE.NORMAL
