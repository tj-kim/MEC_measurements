import os
import logging
import subprocess

import shutil
import docker

from diff_patch import create_xdelta_diff, create_xdelta_patch

class MigrateController(object):
    def __init__(self):
        self.client = docker.from_env()
        self.ssh_handle = None

    def handle_cmd(self, process, cmd_str, wait):
        if not wait:
            logging.info('{}'.format(cmd_str))
            return process
        ret_code = process.wait()
        res = process.communicate()
        logging.info('{} return {}'.format(cmd_str, ret_code))
        if res[1] != '':
            logging.error("Error: {}".format(res[1]))
        logging.info('Output: {}'.format(res[0]))
        return res[0], ret_code

    def docker_verify(self, service):
        containers = self.client.containers.list(all=True,
                           filters={'name': service.get_container_name()})
        if len(containers) == 0:
            logging.error("Cannot found the container, create it first!")
            raise RuntimeError('Container not found!')
        # Check if the continer is running
        container = containers[0]
        if container.status != 'running':
            logging.error("container exited!")
            raise RuntimeError('Container exited!')

    def docker_remove_container(self, name):
        containers = self.client.containers.list(all=True,
                                    filters={'name': name})
        if len(containers) == 0:
            logging.info("Container {} not found".format(name))
        for container in containers:
            container.remove(force=True)

    def docker_create_container(self, img, name, container_port, host_port):
        containers = self.client.containers.list(all=True,
            filters={'name':name})
        if len(containers) > 0:
            # remove before create
            container = containers[0]
            container.remove(force=True)
        cmd = ['docker', 'create', '--name', name, '-p',
               '{}:{}'.format(host_port, container_port), img]
        out = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return self.handle_cmd(out, ' '.join(cmd), True)

    def docker_pull_image(self, img, wait=True):
        cmd = ['docker', 'pull', img]
        out = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return self.handle_cmd(out, ' '.join(cmd), wait)

    def docker_checkpoint(self, container_name, snapshot_name, folder,
                          leave_running=True, wait=True):
        """If wait is True, the function waits until the command is terminated
        and returns stdout. Otherwise, it returns a Popen object
        """
        shutil.rmtree('{}/{}'.format(folder.rstrip('/'), snapshot_name),
                      ignore_errors=True)
        cmd = ['docker', 'checkpoint', 'create',
               '--checkpoint-dir={}'.format(folder)]
        if leave_running:
            cmd.append('--leave-running')
        cmd.append(container_name)
        cmd.append(snapshot_name)
        out = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        return self.handle_cmd(out, ' '.join(cmd), wait)

    def docker_start(self, container_name, wait=True):
        cmd = ['docker', 'start', container_name]
        out = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        return self.handle_cmd(out, ' '.join(cmd), wait)

    def docker_restore(self, container_name, snapshot_name, folder, wait=True):
        cmd = ['docker', 'start', '--checkpoint={}'.format(snapshot_name),
               '--checkpoint-dir={}'.format(folder), container_name]
        out = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        return self.handle_cmd(out, ' '.join(cmd), wait)

    def measure_img_size(self, folder, exclude=''):
        cmd = ['du', '-sb']
        if exclude != '':
            cmd.append('--exclude')
            cmd.append(exclude)
        cmd.append(folder)
        return subprocess.check_output(cmd).split()[0]

    def open_ssh_session(self, dest_user, dest_ip):
        cmd = ['ssh', '{}@{}'.format(dest_user, dest_ip), '-N']
        out = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        logging.info("Start ssh master connection")
        self.ssh_handle = out

    def close_ssh_session(self):
        if self.ssh_handle is not None:
            ret = self.ssh_handle.poll()
            if ret is not None:
                logging.warn("SSH connection is interrupted")
                logging.error("SSH return: {}".format(self.ssh_handle.communicate()))
            else:
                self.ssh_handle.terminate()
                self.ssh_handle = None
        else:
            logging.error("Cannot find SSH connection")

    def rsync(self, source, dest_user, dest_ip, dest_folder, include='',
              exclude='', wait=True):
        if exclude != '':
            cmd = ['rsync', '-az', '--include={}'.format(include) ,
                '--exclude={}'.format(exclude),
                   source.rstrip('/'), '{}@{}:{}/'.format(dest_user, dest_ip,
                                                          dest_folder)]
        else:
            cmd = ['rsync', '-az', source.rstrip('/'),
                   '{}@{}:{}/'.format(dest_user, dest_ip, dest_folder)]
        out = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        return self.handle_cmd(out, ' '.join(cmd), wait)

    def compute_diff(self, old, new, patch, is_parallel=False):
        logging.debug("Compute diff {} {} {}".format(old, new, patch))
        # create patch folder = new - old
        shutil.rmtree(patch, ignore_errors=True)
        os.mkdir(patch)
        if not os.path.exists(old):
            logging.error("Cannot found old folder {}".format(old))
            return 1
        elif not os.path.exists(new):
            logging.error("Cannot found new folder {}".format(new))
            return 1
        else:
            create_xdelta_diff(old, new, patch, True, is_parallel)
            return 0

    def restore_diff(self, old, new, patch):
        if not os.path.exists(new):
            os.mkdir(new)
        if not os.path.exists(old):
            logging.error("Cannot found old folder {}".format(old))
            return 1
        elif not os.path.exists(patch):
            logging.error("Cannot found patch folder {}".format(patch))
            return 1
        else:
            # reconstruct folder new = old + patch
            create_xdelta_patch(old, new, patch, True)
