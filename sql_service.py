import os
import subprocess
import sqlite3
from utilities import get_hostname
import logging
from subprocess import check_output

class Sqlite3Service(object):
    def __init__(self, **kwargs):
        self.database = kwargs.get('database', 'database')
        self.table = kwargs.get('table', 'table')
        print("Database {} - table {}".format(self.database, self.table))
        self.conn = sqlite3.connect(self.database)
        self.cursor = self.conn.cursor()

    def execute_edit_cmd(self, cmd):
        #logging.debug(cmd)
        self.cursor.execute(cmd)
        self.conn.commit()

    def execute_read_cmd(self, cmd):
        #logging.debug(cmd)
        self.cursor.execute(cmd)
        data = self.cursor.fetchall()
        return data

    def create_table(self, columns):
        cmd = "CREATE TABLE {} ({})".format(self.table, columns)
        self.execute_edit_cmd(cmd)

    def insert_data(self, values):
        cmd = "INSERT INTO {} VALUES ({})".format(self.table, values)
        self.execute_edit_cmd(cmd)

    def read_column_data(self, column):
        cmd = "SELECT {} FROM {}".format(column, self.table)
        return self.execute_read_cmd(cmd)

    def read_column_cond_data(self, column, condition):
        cmd = "SELECT {} FROM {} WHERE {}".format(column, self.table, condition)
        return self.execute_read_cmd(cmd)

    def read_conditional_data(self, condition):
        """ condition should be explitcitly defined, e.g.:
        timestamp > '2018-07-06 21:20:24.550771'
        """
        cmd = "SELECT * FROM {} WHERE {}".format(self.table, condition)
        return self.execute_read_cmd(cmd)

    def read_all_data(self):
        cmd = "SELECT * FROM {}".format(self.table)
        return self.execute_read_cmd(cmd)

    def close_connection(self):
        self.conn.close()


class Sqlite3NetworkMonitor(Sqlite3Service):
    def __init__(self, **kwargs):
        database = kwargs.get('database', '{}network.db'.format(get_hostname()))
        table = 'networkMonitor'
        super(Sqlite3NetworkMonitor, self).__init__(database=database, table=table)

    def create(self):
        if os.path.isfile(self.database):
            check_output(['savelog', '-ntl', self.database])
        self.conn = sqlite3.connect(self.database)
        self.cursor = self.conn.cursor()
        columns = 'timestamp text, source_dest text, latency real, bandwidth real'
        self.create_table(columns)

    def insert_net_metrics(self, ts, source_ip, dest_ip, latency, bandwidth):
        write_sql = "'{0}', '{1}_{2}', {3}, {4}".format(ts, source_ip, dest_ip,
            latency, bandwidth)
        self.insert_data(write_sql)

    def get_last_bw(self, source_ip, dest_ip):
        bw, = self.read_column_cond_data("bandwidth",
            '"source_dest"="{}_{}" ORDER BY timestamp DESC LIMIT 1'.
            format(source_ip, dest_ip))[0]
        return bw

    def get_last_delay(self, source_ip, dest_ip):
        latency, = self.read_column_cond_data("latency",
            '"source_dest"="{}_{}" ORDER BY timestamp DESC LIMIT 1'.
            format(source_ip, dest_ip))[0]
        return latency

    def get_last_delay_bw(self, source_ip, dest_ip):
        return self.read_column_cond_data("latency, bandwidth",
            '"source_dest"="{}_{}" ORDER BY timestamp DESC LIMIT 1'.
            format(source_ip, dest_ip))[0]

class Sqlite3ContainerMonitor(Sqlite3Service):
    def __init__(self, **kwargs):
        database = kwargs.get('database', '{}container.db'.format(get_hostname()))
        table = 'containerMonitor'
        super(Sqlite3ContainerMonitor, self).__init__(database=database,
                                                      table=table)

    def create(self):
        if os.path.isfile(self.database):
            subprocess.check_output(['savelog', '-ntl', self.database])
        self.conn = sqlite3.connect(self.database)
        self.cursor = self.conn.cursor()
        columns = ', '.join(['timestamp text',
                             'container_name',
                             'status',
                             'cpu',
                             'memory',
                             'size'])
        self.create_table(columns)

    def insert_container_metrics(self, ts, name, status, cpu, memory, size):
        write_sql = "'{0}', '{1}', '{2}', {3}, {4}, {5}".format(ts, name,
                                                                status, cpu,
                                                                memory, size)
        self.insert_data(write_sql)

class Sqlite3ServerMonitor(Sqlite3Service):
    def __init__(self, **kwargs):
        database = kwargs.get('database', '{}server.db'.format(get_hostname()))
        table = 'serverMonitor'
        super(Sqlite3ServerMonitor, self).__init__(database=database,
                                                      table=table)

    def create(self):
        if os.path.isfile(self.database):
            subprocess.check_output(['savelog', 'ntl', self.database])
        self.conn = sqlite3.connect(self.database)
        self.cursor = self.conn.cursor()
        columns = ', '.join(['timestamp text',
                             'max_cpu',
                             'n_cores',
                             'ram_total',
                             'ram_avail',
                             'disk_total',
                             'disk_avail'])
        self.create_table(columns)

    def insert_server_metrics(self, ts, max_cpu, n_cores, ram_total, ram_avail,
                              disk_total, disk_avail):
        write_sql = "'{0}', {1}, {2}, {3}, {4}, {5}, {6}".format(ts, max_cpu,
                                                                 n_cores, ram_total,
                                                                 ram_avail,
                                                                 disk_total,
                                                                 disk_avail)
        self.insert_data(write_sql)
