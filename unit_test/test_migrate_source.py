import mock
import pytest

from .. import migrate_source
from .. import Constants

@pytest.fixture(scope='module')
def source():
    s = migrate_source.MigrateSource()
    return s

@pytest.mark.incremental
class TestMigrateSource(object):
    USER='test'
    IP='10.0.99.10'
    SERVER_NAME='docker1'

    def test_handle_cmd_pre_measure(self, source):
        source.controller = mock.Mock()
        service = Constants.OPENFACE
        tmp_dir = '/{}/{}'.format('tmp', '{}{}'.format(service,
                                                       TestMigrateSource.USER))
        kwargs = {
            'service_name': service,
            'end_user': TestMigrateSource.USER,
            'ip' : TestMigrateSource.IP,
            'server_name' : TestMigrateSource.SERVER_NAME,
            'port' : 9900,
            'container_img' : Constants.OPENFACE_DOCKER_IMAGE,
            'container_port' : 9999,
            'method' : 'delta'}
        source.handle_cmd_pre_measure(kwargs)
        source.controller.docker_checkpoint.assert_called_with(
            '{}{}'.format(Constants.OPENFACE, TestMigrateSource.USER),
            'snapshot_pre1', tmp_dir)
        source.controller.docker_verify.assert_called()

    def test_handle_cmd_measure_dirty(self, source):
        source.controller = mock.Mock()
        source.source_cb = mock.Mock()
        service=Constants.OPENFACE
        tmp_dir = '/{}/{}'.format('tmp', '{}{}'.format(service,
                                                       TestMigrateSource.USER))
        kwargs = {
            'service_name': service,
            'end_user': TestMigrateSource.USER,
            'ip' : TestMigrateSource.IP,
            'server_name' : TestMigrateSource.SERVER_NAME,
            'port' : 9900,
            'container_img' : Constants.OPENFACE_DOCKER_IMAGE,
            'container_port' : 9999,
            'method' : 'delta'}
        source.handle_cmd_measure_dirty(kwargs)
        source.controller.docker_checkpoint.assert_called_with(
            '{}{}'.format(Constants.OPENFACE, TestMigrateSource.USER),
            'snapshot_pre2', tmp_dir)
        source.controller.compute_diff.assert_called_with(
            '{}/snapshot_pre1/'.format(tmp_dir),
            '{}/snapshot_pre2/'.format(tmp_dir),
            '{}/snapshot_delta_1_2/'.format(tmp_dir))
        source.controller.measure_img_size.assert_has_calls([
            mock.call('{}/snapshot_delta_1_2/'.format(tmp_dir)),
            mock.call('{}/snapshot_pre2/'.format(tmp_dir))])
        source.source_cb.source_dirty_rate_cb.assert_called()

    def test_handle_cmd_prepare(self, source):
        source.controller = mock.Mock()
        handle_pre = mock.Mock()
        source.controller.rsync.return_value = handle_pre
        source.controller.docker_checkpoint.return_value = (None, 0)
        service=Constants.OPENFACE
        tmp_dir = '/{}/{}'.format('tmp', '{}{}'.format(service,
                                                       TestMigrateSource.USER))
        kwargs = {
            'service_name': service,
            'end_user': TestMigrateSource.USER,
            'ip' : TestMigrateSource.IP,
            'server_name' : TestMigrateSource.SERVER_NAME,
            'port' : 9900,
            'container_img' : Constants.OPENFACE_DOCKER_IMAGE,
            'container_port' : 9999,
            'method' : 'delta'}
        source.handle_cmd_prepare(kwargs)
        snapshot_pre2 = '{}/snapshot_pre2/'.format(tmp_dir)
        snapshot_pre3 = '{}/snapshot_pre3/'.format(tmp_dir)
        source.controller.docker_checkpoint.assert_called_with(
            '{}{}'.format(Constants.OPENFACE, TestMigrateSource.USER),
            'snapshot_pre3', tmp_dir)
        source.controller.rsync.assert_has_calls([
            mock.call(snapshot_pre2, 'root', TestMigrateSource.IP, tmp_dir,
                      wait=False),
            mock.call(snapshot_pre3, 'root', TestMigrateSource.IP, tmp_dir,
                      include='*.tar.gz.img',
                      exclude='*.img', wait=False),
            mock.call('{}/snapshot_delta_2_3/'.format(tmp_dir), 'root',
                      TestMigrateSource.IP, tmp_dir)])
        source.controller.compute_diff(snapshot_pre2,
                                       snapshot_pre3,
                                       '{}/snapshot_delta_2_3/'.format(tmp_dir))

    def test_handle_cmd_migrate(self, source):
        source.controller = mock.Mock()
        source.sock = mock.Mock()
        source.controller.docker_checkpoint.return_value = (None, 0)
        service=Constants.OPENFACE
        tmp_dir = '/{}/{}'.format('tmp', '{}{}'.format(service,
                                                       TestMigrateSource.USER))
        snapshot = '{}/snapshot/'.format(tmp_dir)
        snapshot_pre2 = '{}/snapshot_pre2/'.format(tmp_dir)
        snapshot_pre3 = '{}/snapshot_pre3/'.format(tmp_dir)
        kwargs = {'service_name': service,
                  'end_user': TestMigrateSource.USER,
                  'ip' : TestMigrateSource.IP,
                  'server_name' : TestMigrateSource.SERVER_NAME,
                  'port' : 9900,
                  'container_img' : Constants.OPENFACE_DOCKER_IMAGE,
                  'container_port' : 9999,
                  'method' : 'delta'}
        source.handle_cmd_migrate(kwargs)
        source.controller.docker_checkpoint.assert_called_with(
            '{}{}'.format(Constants.OPENFACE, TestMigrateSource.USER), 'snapshot',
            tmp_dir, leave_running=False)
        source.controller.rsync.assert_has_calls([
            mock.call(snapshot, 'root', TestMigrateSource.IP, tmp_dir,
                      include='*.tar.gz.img',
                      exclude="*.img", wait=False),
            mock.call('{}/snapshot_delta/'.format(tmp_dir), 'root',
                      TestMigrateSource.IP, tmp_dir)])
        source.sock.sendto.assert_called()
        source.sock.close.assert_called()
