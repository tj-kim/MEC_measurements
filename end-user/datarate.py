import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import logging
import subprocess

from utilities import check_output_w_warning

# This id must be a unique number
# TODO: Auto detect root id
root = 'fafa:'

class SpeedManager(object):
    """
    Set speed of simulated users using `tc`.

    Args:
        route (RouteManager): The :class:`RouteManager` instance
        dev (str): device name
        rate (int): the default data rate in Mbps, default 150Mbps
        dry_run (bool): This option is used for debugging purposes.
            It shows all commands should be excecuted.
    """

    def __init__(self, route, dev, rate=150, dry_run=False, warn=True):
        self.route = route
        self.dev = dev
        self.rate = rate
        self.current_speeds = {}
        if dry_run:
            self.run_command = self._dummy
        elif warn:
            self.run_command = check_output_w_warning
        else:
            self.run_command = subprocess.check_output

    def _dummy(self, *args):
        return ""

    def allocate_speeds(self):
        """Initialize speed settings:
        - Allocating a new qdisc root
        - Allocating a rule for each user

        Raises:
            RunTimeError: If the function is called be for allocating
                route tables.
            subprocess.CalledProcessError: if the there is any error \
                when setup the rules.
        """
        dev = self.dev
        if not self.route.is_allocated:
            raise RuntimeError("You must allocates route tables before"
                               " run this function")
        """Example:
            tc qdisc add dev eth0 root handle fafa: htb default 1
        """
        # Add root node
        try:
            cmd = ['tc', 'qdisc', 'add', 'dev', dev, 'root', 'handle',
               root, 'htb', 'default', '1']
            out = self.run_command(cmd)
            logging.debug("Cmd: {} output: {}".\
                          format(" ".join(cmd), out))
        except subprocess.CalledProcessError as e:
            if e.returncode == 2:
                # Node exists, remove it and try again
                cmd_rm = ['tc', 'qdisc', 'del', 'dev', dev, 'root',
                          'handle', root]
                out = self.run_command(cmd_rm)
                logging.debug("Cmd: {} output: {}".\
                              format(" ".join(cmd_rm), out))
                out = self.run_command(cmd)
                logging.debug("Cmd: {} output: {}".\
                              format(" ".join(cmd), out))
        # Create handlers
        """Example:
            tc class add dev eth0 parent fafa: classid fafa:1 \
                         htb rate 150Mbit
        """
        for idx, table in enumerate(self.route.tables):
            user_id = '{}{}'.format(root, idx)
            # Add HTB class for the user
            cmd = ['tc', 'class', 'add', 'dev', dev, 'parent', root,
                   'classid', user_id, 'htb', 'rate',
                   '{}Mbit'.format(self.rate)]
            out = self.run_command(cmd)
            logging.debug("Cmd: {} output: {}".\
                          format(" ".join(cmd), out))

    def clear_all(self):
        """Clear all settings."""
        # Removing the root node
        cmd = ['tc', 'qdisc', 'del', 'dev', self.dev, 'root', 'handle',
               root]
        out = self.run_command(cmd)
        logging.debug("Cmd: {} output: {}".\
                      format(" ".join(cmd), out))

    def set_speed(self, user, speed):
        """Set the speed of the user to a new speed

        Args:
            user (str): the user's name
            speed (int): the new speed in Mbps
        Raises:
            StopIteration: If the user is not in the route tables
            RuntimeError: If the script cannot setup a new filter for
              the user or cannot replace the old class.
        Returns:
            The status number: -1 = failed, 1 = unchanged, 0=success
        """
        # Find the user. Iterating over the user list is not a good
        # solution; but, since the number of user usually small, the
        # approach is still acceptable.
        idx, table = next(((idx, table)
                           for idx,table in enumerate(self.route.tables)
                           if table.name == user))
        user_id = '{}{}'.format(root, idx)
        dev = self.dev
        # Try to replace the old filter
        """
        Example:
           tc filter add dev eth0 protocol ip parent fafa: prio 2 \
                         handle 100 fw flowid fafa:1
        """
        try:
            if table.mark is None:
                # Ignore this request
                return -1
            current_speed = self.current_speeds.get(user, None)
            if speed == current_speed:
                # The new speed is the same with the old speed
                return 1
            if not table.have_filter:
                # Add a new filter
                cmd = ['tc', 'filter', 'add', 'dev', dev, 'protocol', 'ip',
                       'parent', root, 'prio', '2', 'handle',
                       '{}'.format(table.mark), 'fw', 'flowid', user_id]
                out = self.run_command(cmd)
                logging.debug("Cmd: {} output: {}".\
                              format(" ".join(cmd), out))
                table.have_filter = True
            # Change the speed
            """
            Example:
               tc class replace dev eth0 parent fafa: classid fafa:1 \
                                htb rate 10Mbit
            """
            cmd = ['tc', 'class', 'replace', 'dev', dev, 'parent',
                   root, 'classid', user_id, 'htb', 'rate',
                   '{}Mbit'.format(speed)]
            out = self.run_command(cmd)
            logging.debug("Cmd: {} output: {}".\
                      format(" ".join(cmd), out))
            self.current_speeds[user] = speed
            return 0
        except subprocess.CalledProcessError:
            if not table.have_filter:
                raise RuntimeError("Cannot setup a new filter with "
                                   "mark {} for flow {}.".\
                                   format(table.mark, user_id))
            else:
                raise RuntimeError("Cannot replace the tc class with "
                                   "id {}, new rate: {}, old rate: {}"\
                                   .format(user_id, speed, current_speed))
            return -1
