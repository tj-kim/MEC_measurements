import time
import random

import pytest

from common_function import *

@pytest.fixture
def random_server(discovery_yaml):
    ap_ssid = random.choice(discovery_yaml.get_ap_names())
    ap_bssid = discovery_yaml.get_ap_bssid(ap_ssid)
    return ap_ssid, ap_bssid

@pytest.mark.parametrize('service_name', [
    (OPENFACE),
    (YOLO),
    (SIMPLE_SERVICE)
])
def test_discovery_service_centre(service_name, random_server, discovery_yaml):
    end_user = 'testdiscover'
    print("\nStart test_discover to {} for user {} with service {}\n".
          format(random_server[0], end_user, service_name))
    broker_ip = discovery_yaml.get_centre_ip()
    result, service = mqtt_discovery_service(broker_ip, random_server[0],
        random_server[1], end_user, service_name)
    assert result is True
    leaving_notification(broker_ip, end_user)

# TODO: add back SIMPLE_SERVICE with return query with last 10 dowtimes.
@pytest.mark.parametrize('service_name', [
    (OPENFACE),
    (YOLO)
])
def test_discovery_query_service(service_name, discovery_yaml):
    test_end_user = 'testquery'
    source_ap = discovery_yaml.get_ap_names()[0]
    ap_bssid = discovery_yaml.get_ap_bssid(source_ap)
    broker_ip = discovery_yaml.get_centre_ip()
    print("\n***start test_01_query_service to {} for user {} with service {}***\n".
        format(source_ap, test_end_user, service_name))
    result, service = mqtt_discovery_service(broker_ip, source_ap, ap_bssid,
        test_end_user, service_name)
    assert result is True
    service_ip = service['ip']
    service_port = service['port']
    query_service(source_ap, ap_bssid, test_end_user, service_name,
                  service_ip, service_port, timeout, debug)
    leaving_notification(broker_ip, test_end_user)
