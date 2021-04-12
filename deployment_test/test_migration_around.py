import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '../end-user'))
from simulated_mobile_eu import run_simulation

def test_openface(discovery_yaml):
    config_file = os.path.join(os.path.dirname(__file__), '../real_edge_nodes.yml')
    config_eu_file = os.path.join(os.path.dirname(__file__), '../eu_openface.yml')
    run_simulation(config_file, config_eu_file, 'e2e_delay_openface.log', sim_time=460)
    assert True

def _test_yolo(discovery_yaml):
    config_file = os.path.join(os.path.dirname(__file__), '../real_edge_nodes.yml')
    config_eu_file = os.path.join(os.path.dirname(__file__), '../eu_yolo.yml')
    run_simulation(config_file, config_eu_file, 'e2e_delay_yolo.log', sim_time=460)
    assert True

def _test_openface_6eus(discovery_yaml):
    config_file = os.path.join(os.path.dirname(__file__), '../real_edge_nodes.yml')
    config_eu_file = os.path.join(os.path.dirname(__file__), '../eu_6us.yml')
    run_simulation(config_file, config_eu_file, 'e2e_delay_6eus.log', sim_time=460)
    assert True
