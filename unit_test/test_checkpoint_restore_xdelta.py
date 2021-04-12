import pytest
import glob
import docker
import shutil
import os
import time
from subprocess import check_output, call

from conftest import get_user
from .. import Constants
from .. utilities import find_open_port, get_container_for_service
from .. diff_patch import create_xdelta_diff, create_xdelta_patch
from .. migrate_controller import MigrateController

@pytest.mark.skipif(get_user() != 'root', reason="Permission deined!")
def test_create_container():
    controller = MigrateController()
    service_name = Constants.YOLO
    # Test create container
    container_img, container_port = get_container_for_service(service_name)
    host_port =  find_open_port()
    container_name = service_name + 'unit_test'
    container_id = controller.docker_create_container(container_img,
        container_name, container_port, host_port)
    destroy(container_name)
    assert True

@pytest.mark.skipif(get_user() != 'root', reason="Permission deined!")
def test_checkpoint_restore_migrate_controller():
    controller = MigrateController()
    service_name = Constants.YOLO
    container_name = create_container(service_name)
    checkpoint_folder = '/tmp/{}'.format(container_name)
    shutil.rmtree(checkpoint_folder, ignore_errors=True)
    time.sleep(1)
    start = time.time()
    controller.docker_checkpoint(container_name, 'snapshot_pre1',
        checkpoint_folder)
    print("time for first checkpoint {}".format(time.time() - start))
    time.sleep(1)
    start = time.time()
    controller.docker_checkpoint(container_name, 'snapshot_pre2',
        checkpoint_folder)
    print("time for second checkpoint {}".format(time.time() - start))
    time.sleep(1)
    snapshot_pre1 = '{}/{}/'.format(checkpoint_folder, 'snapshot_pre1')
    snapshot_pre2 = '{}/{}/'.format(checkpoint_folder, 'snapshot_pre2')
    restore_snapshot_pre2 = '{}/{}/'.format(checkpoint_folder,
        'restore_snapshot_pre2')
    snapshot = '{}/{}/'.format(checkpoint_folder, 'snapshot')
    snapshot_dest = '{}/{}/'.format(checkpoint_folder, 'snapshot_dest')
    snapshot_delta_1_2 = '{}/{}/'.format(checkpoint_folder, 'snapshot_delta_1_2')
    snapshot_delta = '{}/{}/'.format(checkpoint_folder, 'snapshot_delta')
    start = time.time()
    controller.compute_diff(snapshot_pre1, snapshot_pre2, snapshot_delta_1_2)
    print("time for create xdelta diff_1_2 {}".format(time.time() - start))
    # Test reconstruct and check without *.tar.gz.img files
    start = time.time()
    controller.restore_diff(snapshot_pre1, restore_snapshot_pre2,
        snapshot_delta_1_2)
    print("time for restore xdelta patch_1_2 {}".format(time.time() - start))
    check_output(['diff', '--exclude=*.tar.gz.img', '--exclude=criu.work',
        snapshot_pre2, restore_snapshot_pre2])
    # final checkpoint
    start = time.time()
    controller.docker_checkpoint(container_name, 'snapshot', checkpoint_folder,
                                 leave_running=False)
    print("time for final checkpoint {}".format(time.time() - start))
    start = time.time()
    controller.compute_diff(snapshot_pre2, snapshot, snapshot_delta)
    print("time for create xdelta diff_delta {}".format(time.time() - start))
    check_output(['rsync', '-az', '--exclude=*.img', snapshot, snapshot_dest])
    # Reconstruct final checkpoint
    start = time.time()
    controller.restore_diff(snapshot_pre2, snapshot_dest, snapshot_delta)
    print("time for restore xdelta patch_dest {}".format(time.time() - start))
    check_output(['diff', '--exclude=*.tar.gz.img', snapshot, snapshot_dest])
    time.sleep(3) # TODO: this delay significantly affects to the restore time
    # Restore the container
    start = time.time()
    #restore('snapshot_dest', container_name, service_name)
    controller.docker_restore(container_name, 'snapshot_dest', checkpoint_folder)
    print("time for restore container {}".format(time.time() - start))
    assert True
    time.sleep(1)
    destroy(container_name)
    time.sleep(1)
    shutil.rmtree(checkpoint_folder, ignore_errors=True)

@pytest.mark.skipif(get_user() != 'root', reason="Permission denied!")
def test_checkpoint_restore_xdelta():
    service_name = Constants.YOLO
    container_name = create_container(service_name)
    checkpoint_folder = '/tmp/{}'.format(container_name)
    shutil.rmtree(checkpoint_folder, ignore_errors=True)
    create_checkpoint_leave_running(container_name)
    create_checkpoint(container_name)
    # Xdelta diff
    snapshot = '/tmp/{}/snapshot/'.format(container_name)
    snapshot_pre = '/tmp/{}/snapshot_pre/'.format(container_name)
    snapshot_delta = '/tmp/{}/snapshot_delta/'.format(container_name)
    snapshot_new = '/tmp/{}/snapshot_new/'.format(container_name)
    os.mkdir(snapshot_delta)
    start = time.time()
    """
    xdelta_cmd = ['python', 'diff_patch.py',
                  '--old', snapshot_pre,
                  '--new', snapshot,
                  '--patch', snapshot_delta,
                  '--cmd', 'create_xdelta_diff', '--verbose']
    out = check_output(xdelta_cmd)
    print("{} .output: {}".format(' '.join(xdelta_cmd), out))
    """
    create_xdelta_diff(snapshot_pre, snapshot, snapshot_delta, True)
    print(':time: xdelta_source {}'.format(time.time() - start))
    # Xdelta patch
    os.mkdir(snapshot_new)
    start = time.time()
    """
    xdelta_cmd = ['python', 'diff_patch.py',
                  '--old', snapshot_pre,
                  '--new', snapshot_new,
                  '--patch', snapshot_delta,
                  '--cmd', 'create_xdelta_patch', '--verbose']
    out = call(xdelta_cmd)
    print("{} .output: {}".format(' '.join(xdelta_cmd), out))
    """
    create_xdelta_patch(snapshot_pre, snapshot_new, snapshot_delta, True)
    print(':time: xdelta_dest {}'.format(time.time() - start))
    cp_files = glob.glob(snapshot+'*.tar.gz.img')
    for f in cp_files:
        shutil.copy(f, snapshot_new)
    shutil.copytree('/tmp/{}/snapshot/criu.work'.format(container_name),
        '/tmp/{}/snapshot_new/criu.work'.format(container_name))
    shutil.copy('/tmp/{}/snapshot/descriptors.json'.format(container_name),
        '/tmp/{}/snapshot_new/descriptors.json'.format(container_name))
    # Compare the diff result
    cmd = ['diff', snapshot, snapshot_new]
    out = call(cmd)
    print("old and new diff {}".format(out))
    assert out == 0
    time.sleep(2)
    start = time.time()
    restore('snapshot_new', container_name, service_name)
    print("time for restore container {}".format(time.time() - start))
    time.sleep(1)
    destroy(container_name)
    assert True


def destroy(container_name):
    print("check and remove container name {}".format(container_name))
    docker_client = docker.from_env()
    try:
        container = docker_client.containers.get(container_name)
        print("Detect the container {}.".format(container_name))
        container.remove(force=True)
    except docker.errors.NotFound:
        print("Not available docker container_name {}.\
            Try run a new one.".format(container_name))

def restore(snapshot_name, container_name, service_name):
    docker_client = docker.from_env()
    checkpoint_folder = '/tmp/{}'.format(container_name)
    exposed_port =  find_open_port()
    container_img, container_port = get_container_for_service(service_name)
    destroy(container_name)
    create_cmd = ["docker", "create", "--name", container_name,
            "-p", "{}:{}".format(exposed_port, container_port),
            container_img]
    result = check_output(create_cmd)
    print(" ".join(create_cmd) + result)
    start = time.time()
    cmd = ["docker", "start", "--checkpoint={}".format(snapshot_name),
           "--checkpoint-dir={}".format(checkpoint_folder), container_name]
    out = check_output(cmd)
    print('{}. output: {}'.format(' '.join(cmd), out))
    print(':time: restore {}'.format(time.time() - start))

def create_container(service_name):
    docker_client = docker.from_env()
    container_img, container_port = get_container_for_service(service_name)
    exposed_port =  find_open_port()
    container_name = service_name + 'unit_test'
    destroy(container_name)
    try:
        print("create new container {}".format(container_name))
        container = docker_client.containers.run(container_img,
            auto_remove=True,
            detach=True,
            name=container_name,
            ports={'{}/tcp'.format(container_port):exposed_port})
    except Exception:
        print("Cannot create and run a docker container {}".
            format(container_img))
    return container_name

def create_checkpoint_leave_running(container_name):
    folder = '/tmp/{}'.format(container_name)
    cmd = ["docker", "checkpoint", "create", "--checkpoint-dir={}".format(
            folder), '--leave-running', container_name, 'snapshot_pre']
    out = check_output(cmd)
    assert out.rstrip("\n\r") == 'snapshot_pre'
    print('{}. output: {}'.format(' '.join(cmd), out))
    print(os.listdir(folder + '/snapshot_pre'))

def create_checkpoint(container_name):
    folder = '/tmp/{}'.format(container_name)
    cmd = ["docker", "checkpoint", "create", "--checkpoint-dir={}".format(
           folder), container_name, 'snapshot']
    out = check_output(cmd)
    assert out.rstrip('\n\r') == 'snapshot'
    print('{}. output: {}'.format(' '.join(cmd), out))
    print(os.listdir(folder+'/snapshot'))
