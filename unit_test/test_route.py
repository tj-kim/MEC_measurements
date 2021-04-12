import os
import sys

import mock
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '../end-user/'))

import route

def test_get_avail_table_id():
    route.get_table_ids()

@mock.patch("subprocess.Popen")
def test_get_avail_mark(mock_popen):
    mock_popen.communicate.return_value = (
    'MARK       all  --  anywhere             10.0.99.11           MARK set 0x14', '')
    assert route.get_avail_mark() == 100

EU_LIST = ['EU1', 'EU2']

@pytest.fixture(scope='module')
def route_man():
    r = route.RouteManager(EU_LIST)
    return r

@pytest.mark.incremental
class TestRouteManager(object):
    @mock.patch("route.get_table_ids")
    def test_allocate_tables(self, mock_table, route_man):
        mock_table.return_value = [0, 255]
        with mock.patch("route.open", mock.mock_open()) as mock_file:
            route_man.allocate_tables()
            mock_file.assert_has_calls(
                [mock.call().write("{}\t{}\n".format(100+i,u))
                 for i,u in enumerate(EU_LIST)])
            assert route_man.tables[0].table_id == 100

    @mock.patch("subprocess.check_output")
    def test_set_gw_ip(self, mock_popen, route_man):
        eu = EU_LIST[0]
        mock_popen.return_value = ''
        route_man.set_gw_ip(eu, '10.0.99.10')

    @mock.patch("subprocess.check_output")
    @mock.patch("route.get_avail_mark")
    def test_set_filter(self, mock_popen, mock_get_mark, route_man):
        eu = EU_LIST[0]
        mock_get_mark.return_value = 20
        mock_popen.return_value = ''
        route_man.set_filter(eu, '10.0.99.10', 9900)

    @mock.patch("subprocess.check_output")
    def test_release_table(self, mock_popen, route_man):
        mock_popen.return_value = ''
        route_man.release_tables()
    

