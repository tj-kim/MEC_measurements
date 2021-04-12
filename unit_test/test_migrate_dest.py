import mock
import pytest

from .. import migrate_dest
from .. import Constants

@pytest.fixture(scope='module')
def dest():
    with mock.patch('socket.socket') as mock_socket:
        d = migrate_dest.MigrateDest()
        return d

@pytest.mark.incremental
class TestMigrateDest(object):
    USER='test'
    IP='10.0.99.10'
    SERVER_NAME='docker1'

    def test_handle_prepare(self, dest):
        dest.controller = mock.Mock()
        service = Constants.OPENFACE
        tmp_dir = '/{}/{}'.format('tmp', '{}{}'.format(service,
                                                       TestMigrateDest.USER))
        snapshot_pre2 = '{}/snapshot_pre2/'.format(tmp_dir)
        snapshot_pre3 = '{}/snapshot_pre3/'.format(tmp_dir)
        dest.handle_cmd_prepare(('10.0.99.11', 9999),
            service_name=service,
            end_user=TestMigrateDest.USER,
            ip=TestMigrateDest.IP,
            server_name=TestMigrateDest.SERVER_NAME,
            port=9900,
            container_img=Constants.OPENFACE_DOCKER_IMAGE,
            container_port=9999,
            method='delta')
        dest.controller.restore_diff.assert_called_with(
            snapshot_pre2,
            snapshot_pre3,
            '{}/snapshot_delta_2_3/'.format(tmp_dir))

    def test_handle_migrate(self, dest):
        dest.controller = mock.Mock()
        dest.controller.docker_restore.return_value = ("", 0)
        dest.client = mock.Mock()
        service = Constants.OPENFACE
        tmp_dir = '/{}/{}'.format('tmp', '{}{}'.format(service,
                                                       TestMigrateDest.USER))
        snapshot_pre3 = '{}/snapshot_pre3/'.format(tmp_dir)
        snapshot = '{}/snapshot/'.format(tmp_dir)
        snapshot_delta = '{}/snapshot_delta/'.format(tmp_dir)
        dest.handle_cmd_migrate(('10.0.99.11', 9999),
            service_name=service,
            end_user=TestMigrateDest.USER,
            ip=TestMigrateDest.IP,
            server_name=TestMigrateDest.SERVER_NAME,
            port=9900,
            container_img=Constants.OPENFACE_DOCKER_IMAGE,
            container_port=9999,
            method='delta')
        dest.controller.restore_diff.assert_called_with(snapshot_pre3,
                                                        snapshot,
                                                        snapshot_delta)
        dest.controller.docker_restore(
            '{}{}'.format(service, TestMigrateDest.USER),
            snapshot, tmp_dir)

@mock.patch('socket.socket')
def test_process_line(mock_socket):
    d = migrate_dest.MigrateDest()
    d.handle_cmd_migrate = mock.Mock()
    d.handle_cmd_prepare = mock.Mock()
    kwargs = {
        'cmd':'measure',
        'service_name': Constants.OPENFACE,
        'end_user': 'test',
        'ip' : '10.0.99.10',
        'server_name' : 'docker1',
        'port' : 9900,
        'container_img' : Constants.OPENFACE_DOCKER_IMAGE,
        'container_port' : 9999,
        'method' : 'delta'}
    d.process_line('prepare {}'.format(kwargs), ('10.0.99.11',
                                                 Constants.BETWEEN_EDGES_PORT))
    d.process_line('migrate {}'.format(kwargs), ('10.0.99.11',
                                                 Constants.BETWEEN_EDGES_PORT))
    d.handle_cmd_migrate.assert_called()
    d.handle_cmd_prepare.assert_called()


