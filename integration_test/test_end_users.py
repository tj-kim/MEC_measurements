import time

import pytest
from common_function import *
import os, sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../end-user'))
from simulated_mobile_eu import run_simulation
import Constants

from conftest import get_user

@pytest.mark.skipif(get_user() != 'root', reason="Permission denied!")
@pytest.mark.timeout(300)
def test_migration_with_sim_eu(discovery_yaml, net_interface):
    config_file = os.path.join(os.path.dirname(__file__),
                               '../edge_nodes.yml')
    config_eu_file = os.path.join(os.path.dirname(__file__),
                                  '../eu_openface.yml')
    run_simulation(config_file, config_eu_file, net_interface,
                   'unit_test_eu.log', log_level='DEBUG', sim_time=120)
    assert True

@pytest.mark.skip(reason=" Test case is obsoleted ")
@pytest.mark.parametrize('service_name', [
    (OPENFACE),
    (YOLO)
])
def test_02_new_migration(service_name, discovery_yaml):
    broker_ip = discovery_yaml.get_centre_ip()
    test_end_user = 'test02enduser'
    source_ap = discovery_yaml.get_ap_names()[0]
    ap_bssid = discovery_yaml.get_ap_bssid(source_ap)
    dest_ap = discovery_yaml.get_ap_names()[1]
    print("\n***start test_02_migration from {} to {} with service {}***\n".
        format(source_ap, dest_ap, service_name))
    result, service = mqtt_discovery_service(broker_ip, source_ap, ap_bssid,
        test_end_user, service_name)
    assert result is True
    service_ip = service['ip']
    service_port = service['port']
    print("!!!before migration query service {} to server {}:{}".format(
        service_name, service_ip, service_port))
    # Trigger pre_measure checkpoint
    query_service(source_ap, ap_bssid, test_end_user, service_name,
                  service_ip, service_port, timeout, debug)
    query_service(source_ap, ap_bssid, test_end_user, service_name,
                  service_ip, service_port, timeout, debug)
    query_service(source_ap, ap_bssid, test_end_user, service_name,
                  service_ip, service_port, timeout, debug)
    query_service(source_ap, ap_bssid, test_end_user, service_name,
                  service_ip, service_port, timeout, debug)
    time.sleep(20)
    service_ip, service_port = mqtt_report_monitor_rssi_info(broker_ip, source_ap,
        ap_bssid, dest_ap, test_end_user, service_name)
    print("!!!After migration query service {} to server {}:{}".format(
        service_name, service_ip, service_port))
    query_service(service_ip, service_port, timeout, debug)
    leaving_notification(broker_ip, test_end_user)

def test_03_stress_query_service(discovery_yaml):
    test_service_name = OPENFACE
    test_end_user = 'test03enduser'
    server_ap = discovery_yaml.get_ap_names()[0]
    ap_bssid = discovery_yaml.get_ap_bssid(server_ap)
    broker_ip = discovery_yaml.get_centre_ip()
    print("\n**start test_03 stress query to {} for user {} with service {}**\n".
        format(server_ap, test_end_user, test_service_name))
    result, service = mqtt_discovery_service(broker_ip, server_ap, ap_bssid,
        test_end_user, test_service_name)
    assert result is True
    service_ip = service['ip']
    service_port = service['port']
    query_service(server_ap, ap_bssid, test_end_user, test_service_name,
                  service_ip, service_port, timeout, debug)
    for i in range(3):
        print("discover again to server {} for user {} with service {}".
            format(server_ap, test_end_user, test_service_name))
        result, service = mqtt_discovery_service(broker_ip, server_ap, ap_bssid,
            test_end_user, test_service_name)
        assert result is True
        service_ip = service['ip']
        service_port = service['port']
        query_service(server_ap, ap_bssid, test_end_user, test_service_name,
                  service_ip, service_port, timeout, debug)
    leaving_notification(broker_ip, test_end_user)

