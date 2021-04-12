import pytest
from .. import setup_network_metrics as conf
from .. import discovery_edge
from .. network_monitor import NetworkMonitor
import subprocess
import yaml
import socket
import logging
from .. utilities import find_my_ip
from conftest import get_user

def detect_subnet(ips):
    # Group octects of addresses
    segs = zip(*[i.split('.') for i in ips])
    octect = [ i[0] if i.count(i[0]) == len(i) else 'x' for i in segs]
    return '.'.join([i for i in octect if i != 'x'])

def test_detect_subnet():
    ips = ['10.0.99.10', '10.0.99.11', '10.0.99.12']
    assert detect_subnet(ips) == '10.0.99'
    ips = ['10.0.98.10', '10.0.97.11', '10.0.96.12']
    assert detect_subnet(ips) == '10.0'

def setup_metric(discovery_yaml):
    names = discovery_yaml.get_server_names()
    ips = [discovery_yaml.get_server_ip(name) for name in names]
    print(ips)
    subnet = detect_subnet(ips)
    # This test assume all nodes have the same subnet
    dev = subprocess.check_output(
        "ip route | awk '/^" + subnet +"/{print $3}'",
        shell=True).rstrip("\n")
    target = names[0]
    m = discovery_yaml.get_metrics(target)
    print('Metrics: {}'.format(m))
    conf.setup_metrics(dev, m, discovery_yaml)
    return ips, dev, m

@pytest.mark.skipif(get_user() != 'root', reason="Permission denied!")
def test_metric_setup(discovery_yaml):
    ips, dev, m = setup_metric(discovery_yaml)
    try:
        for i,ip in enumerate(ips):
            # Verify
            out = subprocess.check_output(
                "ping -c 3 "+ip+"| awk '/^rtt/{print $4}' | awk -F '/' '{print $1}'",
                shell=True)
            logging.info("Check ping to {}: {}".format(ip, out))
            delay = float(out.rstrip("\n"))
            print('Test with {}: {}ms'.format(ip, delay))
            server_name = discovery_yaml.get_server_name_from_ip(ip)
            server_metric = next((i for i in m if i.get('name') == server_name), None)
            if server_metric is not None:
                expect = server_metric.get('delay', 10000)
                assert expect + 2 >= delay >= expect
            else:
                assert 2 >= delay >= 0
        assert True
    except subprocess.CalledProcessError:
        pytest.fail('Cannot connect to server {}'.format(ips))
    finally:
        conf.delete_all_rules(dev)

def check_condition(measure, setting, tolerance = 0.1):
    # Check the measured value and the setting value are under tolerance
    delta = abs(measure - setting)
    if delta/setting < tolerance:
        return True
    else:
        return False

def real_machine_measure_network(discovery_yaml):
    """ This test is just for real machines.
    Actually we do not run this test in the test suites of integration test.

    """
    print("start test network monitor using netperf")
    netMon = NetworkMonitor()
    netMon.update_edge_nodes_info(discovery_yaml)
    ips, dev, m = setup_metric(discovery_yaml)
    my_ip = find_my_ip()
    for i,ip in enumerate(ips):
        if ip != my_ip:
            # Verify
            print("verify network between {} and {}".format(my_ip, ip))
            server_name = discovery_yaml.get_server_name_from_ip(ip)
            server_metric = next((i for i in m if i.get('name') == server_name), None)
            print("server_metric = {}".format(server_metric))
            delay = netMon.measure_latency(ip)
            bandwidth = netMon.measure_bandwidth(ip)
            print('Test with {} latency: {} microseconds, bandwidth {} mbps'.
                format(ip, delay, bandwidth))
            if server_metric is not None:
                expect_delay = int(server_metric.get('delay', 10000))*1000
                assert check_condition(delay, expect_delay)
                expect_bandwidth = server_metric.get('bw', 100)
                assert check_condition(bandwidth, expect_bandwidth)
            else:
                assert check_condition(delay, 50.0)
                assert check_condition(bandwidth, 100.0)
    assert True
    conf.delete_all_rules(dev)
