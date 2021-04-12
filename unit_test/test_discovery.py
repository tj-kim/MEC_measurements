import pytest

from .. import discovery_edge

def test_discovery_abstract():
    nodes = discovery_edge.Discovery()
    with pytest.raises(NotImplementedError):
        nodes.get_server_ip('hello')

def test_discovery_yaml():
    nodes = discovery_edge.DiscoveryYaml('edge_nodes.yml')
    assert nodes.get_server_ip('docker1') == '10.0.99.10'
    assert nodes.get_ap_pass('edge01') == ''
    assert nodes.get_server_port('docker1') == 9889
    assert len(nodes.get_server_names()) >= 3
    assert len(nodes.get_ap_names()) >= 3
    model, number_bs, distance_bs = nodes.get_placement_bs_model()
    assert model == 'line'
    assert number_bs == 3
    assert distance_bs == 70.0
    m = nodes.get_metric('docker1', 'docker2')
    assert m.get('bw', 0) != 0
    assert m.get('delay', 0) != 0
    assert nodes.get_server_name_from_ip('10.0.99.10') == 'docker1'
    assert nodes.get_centre_ip() == '10.0.99.2'

    config_users = discovery_edge.DiscoveryYaml('eu_openface.yml')
    users = config_users.get_end_users()
    u = users[0]
    end_user = u['name']
    assert end_user == 'sim_eu_openface'
    service = u.get('service', None)
    assert service is not None


def test_discovery_sql(create_db):
    nodes = discovery_edge.DiscoverySql('unit_test/centraldb.db')
    assert nodes.get_server_ip('docker1') == '10.0.99.10'
    assert nodes.get_ap_pass('docker1') == ''
    assert len(nodes.get_server_names()) >= 3
    assert nodes.get_server_name_from_ip('10.0.99.10') == 'docker1'
    assert nodes.get_centre_ip() == '10.0.99.2'
