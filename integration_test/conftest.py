import subprocess

import pytest
from .. import discovery_edge
from .. import utilities

def pytest_addoption(parser):
    parser.addoption(
        "--file",
        help="Network information file in YAML format",
        default="edge_nodes.yml"
    )

@pytest.fixture(scope="module")
def conf_file(request):
    return request.config.getoption("--file")

@pytest.fixture(scope="module")
def discovery_yaml(conf_file):
    service = discovery_edge.DiscoveryYaml(conf_file)
    return service

@pytest.fixture(scope="module")
def net_interface(discovery_yaml):
    """Get the name of the inface that associated to the centre server.
    """
    ip = discovery_yaml.get_centre_ip()
    return utilities.get_interface_for_ip(ip)

def get_user():
    return subprocess.check_output(['whoami']).rstrip('\n')
