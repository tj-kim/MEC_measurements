import pytest
from .. import discovery_edge

def pytest_addoption(parser):
    parser.addoption(
        "--file",
        help="Network information file in YAML format",
        default="real_edge_nodes.yml"
    )
    parser.addoption(
        "--dirty_rate",
        help="Rate of dirty memory for simulated ram intensive app.",
        default=1
    )

@pytest.fixture(scope="module")
def conf_file(request):
    return request.config.getoption("--file")

@pytest.fixture(scope="module")
def discovery_yaml(conf_file):
    service = discovery_edge.DiscoveryYaml(conf_file)
    return service

@pytest.fixture(scope="module")
def dirty_rate(request):
    return request.config.getoption('--dirty_rate')
