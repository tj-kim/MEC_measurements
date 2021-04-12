import pytest
from common_function import *

@pytest.mark.skip(reason="The service has some problem")
def test_ram_intensive(discovery_yaml):
    end_user = 'testramuser'
    source_ssid= discovery_yaml.get_ap_names()[0]
    ap_bssid = discovery_yaml.get_ap_bssid(source_ssid)
    broker_ip = discovery_yaml.get_centre_ip()
    result, service = mqtt_discovery_service(broker_ip, source_ssid, ap_bssid,
                        end_user, SIMPLE_SERVICE)
    assert result is True
    service_ip = service['ip']
    service_port = int(service['port'])
    query_simple(service_ip, service_port)
    assert True
    leaving_notification(broker_ip, end_user)


