import mock
import pytest
import subprocess

from .. import Constants
from .. import migrate_controller
from .. utilities import find_open_port, get_container_for_service
from conftest import get_user

@pytest.fixture(scope='module')
def controller():
    c = migrate_controller.MigrateController()
    return c

@pytest.fixture(scope='module')
def real_controller():
    c = migrate_controller.MigrateController()
    return c

@pytest.mark.skipif(get_user()!='root', reason="Permission denied!")
@pytest.mark.incremental
class TestRealMigrateController(object):
    CONTAINER_NAME = 'openface_unit_test'

    def test_create_container(self, real_controller):
        container_img, container_port = get_container_for_service(
            Constants.OPENFACE)
        real_controller.docker_create_container(
            container_img,
            TestRealMigrateController.CONTAINER_NAME,
            container_port,find_open_port(9900, 9999))

    def test_remove_container(self, real_controller):
        real_controller.docker_remove_container(
            TestRealMigrateController.CONTAINER_NAME)


@mock.patch('subprocess.Popen')
def test_docker_checkpoint(mock_popen, controller):
    out = mock.Mock()
    mock_popen.return_value = out
    out.wait.return_value = 0
    out.communicate.return_value = ('output', 'error')
    controller.docker_checkpoint('foo', 'bar', 'snapshot')
    assert mock_popen.called
    assert out.wait.called
    assert out.communicate.called

@mock.patch('subprocess.Popen')
def test_docker_checkpoint_non_blocking(mock_popen, controller):
    out = mock.Mock()
    mock_popen.return_value = out
    controller.docker_checkpoint('foo', 'bar', 'snapshot', wait=False)
    assert out.wait.called == False

@mock.patch('subprocess.Popen')
def test_docker_restore(mock_popen, controller):
    out = mock.Mock()
    mock_popen.return_value = out
    out.wait.return_value = 0
    out.communicate.return_value = ('output', 'error')
    controller.docker_restore('foo', 'snapshot', '/tmp')
    mock_popen.assert_called_with(['docker', 'start', '--checkpoint=snapshot',
                                   '--checkpoint-dir=/tmp', 'foo'],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)

@mock.patch('subprocess.check_output')
def test_measure_img_size(mock_check_output, controller):
    mock_check_output.return_value= "12345       foo"
    ret = controller.measure_img_size('foo', exclude='foo')
    assert ret == '12345'

@mock.patch('subprocess.Popen')
def test_rsync(mock_popen, controller):
    out = mock.Mock()
    mock_popen.return_value = out
    out.wait.return_value = 0
    out.communicate.return_value = ('output', 'error')
    controller.rsync('foo/', 'test', 'localhost', 'foo', include='*.tar.gz.img',
        exclude='*.img')
    mock_popen.assert_called_with( ["rsync", "-az", "--include=*.tar.gz.img",
                                    "--exclude=*.img", "foo",
                                    "test@localhost:foo/"],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)

@mock.patch('subprocess.Popen')
def test_rsync_no_exclude(mock_popen, controller):
    out = mock.Mock()
    mock_popen.return_value = out
    out.wait.return_value = 0
    out.communicate.return_value = ('output', 'error')
    controller.rsync('foo/', 'test', 'localhost', 'foo')
    mock_popen.assert_called_with( ["rsync", "-az", "foo", "test@localhost:foo/"],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)

def test_compute_diff(controller):
    # TODO Test compute diff
    pass

def test_restore_diff(controller):
    # TODO Test restore diff
    pass
