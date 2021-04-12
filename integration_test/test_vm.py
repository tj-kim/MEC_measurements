import pytest
import os
import socket
import time
import subprocess
from ..mqtt_protocol import MqttClient
from ..Constants import BROKER_PORT

@pytest.fixture(scope="module")
def vagrant():
    # Init context
    os.chdir('integration_test')
    yield None
    os.chdir('..')

def test_ping_vm(discovery_yaml, vagrant):
    try:
        for server in discovery_yaml.get_server_names():
            ip = discovery_yaml.get_server_ip(server)
            subprocess.check_output(['ping', '-c', '1', ip])
        assert True
    except subprocess.CalledProcessError:
        pytest.fail("Cannot ping to server {}".format(ip))

def test_connect(discovery_yaml, vagrant):
    broker_ip = discovery_yaml.get_centre_ip()
    mqttClient = MqttClient(
        client_id='testMqtt',
        clean_session=True,
        broker_ip=broker_ip,
        broker_port=BROKER_PORT,
        keepalive=60)
    mqttClient.loop_start()
    try:
        mqttClient.publish('testTopic', 'hello')
        assert True
    except Exception as ex:
        pytest.fail('Cannot publish to broker {}, ex {}'.format(broker_ip, ex))
