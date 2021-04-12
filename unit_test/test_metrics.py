import mock
from .. import setup_network_metrics as conf
from .. import discovery_edge
import subprocess

def test_find_metrics():
    assert conf.find_metrics('null', [{'name':'docker1'}]) == []
    assert conf.find_metrics('docker1', [
        {'name': 'docker1','metrics':[
            {'name':'docker2'}]}]) == [{'name':'docker2'}]

metric_docker1 = [
    {'name': 'docker2', 'bw': 100, 'delay': 10},
    {'name': 'docker3', 'bw': 100, 'delay': 10}
]

def mock_side_effect(arg):
    print(" ".join(arg))

@mock.patch('subprocess.check_output')
def test_setup_metrics_calltimes(mock_output, create_db):
    mock_output.side_effect = mock_side_effect
    dis = discovery_edge.DiscoverySql('unit_test/centraldb.db')
    conf.setup_metrics('vboxnet4', metric_docker1, dis)
    assert mock_output.call_count == 10
