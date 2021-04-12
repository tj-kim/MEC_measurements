import pytest
import random
from common_function import *

@pytest.fixture
def random_server(discovery_yaml):
    ap_ssid = random.choice(discovery_yaml.get_ap_names())
    ap_bssid = discovery_yaml.get_ap_bssid(ap_ssid)
    return ap_ssid, ap_bssid

@pytest.mark.parametrize('service_name', [
    (OPENFACE),
    (YOLO)
])
def test_discovery_service_unknown_bs(service_name, discovery_yaml):
    end_user = 'testdiscover'
    ssid = 'unknown'
    bssid = 'bs:un:ko:wn'
    print("\nStart test_discover to {} for user {} with service {}\n".
          format(ssid, end_user, service_name))
    broker_ip = discovery_yaml.get_centre_ip()
    timeout=10
    result, service = mqtt_discovery_service(broker_ip, ssid, bssid,
        end_user, service_name, timeout)
    assert result is False
    leaving_notification(broker_ip, end_user)


def test_report_wrong_monitor_service_msg(discovery_yaml):
    test_service_name = OPENFACE
    test_end_user = 'testenduser'
    source_ap = discovery_yaml.get_ap_names()[0]
    ap_bssid = discovery_yaml.get_ap_bssid(source_ap)
    broker_ip = discovery_yaml.get_centre_ip()
    print("\n**start test_corner case to {} for user {} with service {}**\n".
        format(source_ap, test_end_user, test_service_name))
    result, service = mqtt_discovery_service(broker_ip, source_ap, ap_bssid,
        test_end_user, test_service_name)
    assert result is True
    service_ip = service['ip']
    service_port = service['port']
    query_service(source_ap, ap_bssid, test_end_user, test_service_name,
                  service_ip, service_port, timeout, debug)
    # report wrong msg
    topic = '{}/{}'.format(Constants.MONITOR_SERVICE, test_end_user)
    mqttClient = MqttMigrationTrigger(
        client_id='testMqttMigration',
        clean_session=True,
        broker_ip=broker_ip,
        broker_port=BROKER_PORT,
        keepalive=60)
    migrated_topic = '{}/{}'.format(MIGRATED, test_end_user)
    topic = '{}/{}'.format(Constants.MONITOR_SERVICE, test_end_user)
    payload = 'Testing strange msg'
    mqttClient.publish(topic, payload)
    print("!!!Publish topic {} payload {}".format(topic, payload))
    # check centralized is OK again
    result, service = mqtt_discovery_service(broker_ip, source_ap, ap_bssid,
        test_end_user, test_service_name)
    assert result is True
    service_ip = service['ip']
    service_port = service['port']
    query_service(source_ap, ap_bssid, test_end_user, test_service_name,
                  service_ip, service_port, timeout, debug)
    leaving_notification(broker_ip, test_end_user)
