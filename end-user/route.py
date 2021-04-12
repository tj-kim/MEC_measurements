import logging
import subprocess

RT_TABLES = '/etc/iproute2/rt_tables'

def get_table_ids():
    ids = []
    with open(RT_TABLES, 'r') as f:
        for l in filter(lambda x: x[0]!='#', f):
            parts = l.split()
            if len(parts) == 2:
                ids.append(int(parts[0]))
    return ids

def get_mark_table(table=''):
    """Finds all marks of a IP table.

    .. note::

        We use `wait` flag to prevent the conflict between concurent
        users. The command will back off 1 second if it cannot acquire
        the lock.

    """
    ids = []
    if table != '':
        iptables = subprocess.Popen(['iptables', '-t', table, '-L', '--wait'],
                                stdout=subprocess.PIPE)
    else:
        iptables = subprocess.Popen(['iptables', '-L', '--wait'],
                                stdout=subprocess.PIPE)
    grep = subprocess.Popen(['grep', 'MARK'], stdin=iptables.stdout,
                             stdout=subprocess.PIPE)
    ret = iptables.wait()
    ret = grep.wait()
    for l in grep.communicate()[0].split("\n"):
        parts = l.split()
        if len(parts) > 0:
            ids.append(int(parts[-1], base=16))
    return ids

def get_avail_mark(from_id=100, to_id=200):
    ids = []
    for i in ['', 'mangle', 'nat']:
        ids += get_mark_table(i)
    return next((i for i in range(from_id, to_id) if i not in ids), None)

def create_mark_filter(dest_ip, dest_port, mark):
    cmd = ['iptables', '-t', 'mangle', '-A', 'OUTPUT', '-d', dest_ip, '-p',
           'tcp', '--dport', '{}'.format(dest_port), '-j', 'MARK',
           '--set-mark', '{}'.format(mark), '--wait']
    out = subprocess.check_output(cmd)
    logging.debug('cmd: {} output: {}'.format(' '.join(cmd), out))

def delete_mark_filter(dest_ip, dest_port, mark):
    cmd = ['iptables', '-t', 'mangle', '-D', 'OUTPUT', '-d', dest_ip, '-p',
           'tcp', '--dport', '{}'.format(dest_port), '-j', 'MARK',
           '--set-mark', '{}'.format(mark), '--wait']
    out = subprocess.check_output(cmd)
    logging.debug('cmd: {} output: {}'.format(' '.join(cmd), out))

def delete_mark_rule(mark):
    cmd = ['ip', 'rule', 'del', 'fwmark', '{}'.format(mark)]
    out = subprocess.check_output(cmd)
    logging.debug('cmd: {} output: {}'.format(' '.join(cmd), out))

def create_mark_rule(mark, table):
    cmd = ['ip', 'rule', 'add', 'fwmark', '{}'.format(mark), 'table', table]
    out = subprocess.check_output(cmd)
    logging.debug('cmd: {} output: {}'.format(' '.join(cmd), out))

def delete_route_table(table_id):
    cmd = ['sed', '-i', '/^{}/d'.format(table_id), RT_TABLES]
    out = subprocess.check_output(cmd)
    logging.debug('cmd: {} output: {}'.format(' '.join(cmd), out))

def delete_route_default_rule(table):
    cmd=['ip', 'route', 'del', 'table', table, 'default']
    out = subprocess.check_output(cmd)
    logging.debug('cmd: {} output: {}'.format(' '.join(cmd), out))

def create_route_default_rule(table, gw):
    cmd=['ip', 'route', 'add', 'table', table, 'default', 'via', gw]
    out = subprocess.check_output(cmd)
    logging.debug('cmd: {} output: {}'.format(' '.join(cmd), out))

class RouteEntry(object):
    def __init__(self, **kwargs):
        self.mark = kwargs.get('mark', None)
        self.name = kwargs.get('name', '')
        self.table_id = kwargs.get('id', 0)
        self.dest_ip = kwargs.get('dest_ip', '')
        self.dest_port = kwargs.get('dest_port', '')
        self.have_filter = False # True if the tc filter is already set up.
        self.gw_ip = kwargs.get('gw', None)

class RouteManager(object):
    def __init__(self, users):
        self.tables = [ RouteEntry(name=u) for u in users]
        self.is_allocated = False

    def allocate_tables(self, from_id=100, to_id=200):
        ids = get_table_ids()
        with open(RT_TABLES, 'a') as f:
            for i in self.tables:
                new_id=next((i for i in range(from_id, to_id) if i not in ids),
                              None)
                f.write("{}\t{}\n".format(new_id, i.name))
                i.table_id = new_id
                ids.append(new_id)
            self.is_allocated = True

    def set_gw_ip(self, user, ip):
        table = next((i for i in self.tables if i.name==user))
        try:
            # Delete table
            delete_route_default_rule(table.name)
        except subprocess.CalledProcessError:
            logging.warn("Deleted existed rule")
        table.gw_ip = ip
        create_route_default_rule(table.name, table.gw_ip)

    def set_filter(self, user, dest_ip, dest_port, from_mark=100, to_mark=200):
        table = next((i for i in self.tables if i.name==user))
        if table.mark is not None:
            # Delete old filter
            delete_mark_filter(table.dest_ip, table.dest_port, table.mark)
            # Recreate filter with the new destination
            create_mark_filter(dest_ip, dest_port, table.mark)
        else:
            # Allocate a new mark
            mark = get_avail_mark(from_mark, to_mark)
            create_mark_filter(dest_ip, dest_port, mark)
            table.mark = mark
            # Add a new mark rule
            create_mark_rule(mark, table.name)
        table.dest_ip = dest_ip
        table.dest_port =dest_port

    def release_tables(self):
        """
        Clear all settings
        """
        for table in self.tables:
            if table.mark is not None:
                # Remove mark rule
                delete_mark_rule(table.mark)
                delete_mark_filter(table.dest_ip, table.dest_port, table.mark)
            # Delete route table
            delete_route_table(table.table_id)

