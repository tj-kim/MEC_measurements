#!/usr/bin/env python

import csv
import time
import argparse
import re
import json
import glob
import numpy as np
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from discovery_edge import DiscoveryYaml

TIME_REGEX = '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}'
time_match = re.compile(TIME_REGEX)
time_tag = ' :time: '
size_tag = ' :size: '
KEYWORDS_PRE_COPY = [
    'pre-checkpoint',
    'pre-rsync',
    'prepare',
    'checkpoint',
    'rsync',
    'xdelta_source',
    'final_rsync',
    'premigration',
    'xdelta_dest',
    'restore',
    'migrate',
]

SIZE_KEYWORDS_PRE_COPY = [
    'pre-rsync',
    'rsync',
    'final_rsync',
]

KEYWORDS_NON_LIVE_MIGRATION = [
    'checkpoint',
    'rsync',
    'migrate',
    'premigration',
    'restore'
]

SIZE_KEYWORDS_NON_LIVE_MIGRATION = [
    'rsync',
]

KEYWORDS = {'non_live_migration': KEYWORDS_NON_LIVE_MIGRATION,
            'pre_copy': KEYWORDS_PRE_COPY}

SIZE_KEYWORDS = {'non_live_migration': SIZE_KEYWORDS_NON_LIVE_MIGRATION,
                'pre_copy': SIZE_KEYWORDS_PRE_COPY}

def convert_time(input_time):
    """
    Sample input: 2018-05-22 21:53:50,295
    """
    t = input_time.split(',')
    epoch = time.mktime(time.strptime(t[0], "%Y-%m-%d %H:%M:%S"))
    epoch += int(t[1])/1000.0
    return epoch

def get_time(line):
    log_time_match = re.match(time_match, line)
    if log_time_match is None:
        return None
    else:
        log_time = convert_time(log_time_match.group(0))
        return log_time

def get_elapsed_time(line):
    return get_value_with_tag(line, time_tag)

def get_transfered_size(line):
    return get_value_with_tag(line, size_tag)

def get_value_with_tag(line, name_tag):
    index = line.find(name_tag)
    if index == -1:
        return None
    substr = line[index+len(name_tag):].split('=')
    return (substr[0], float(substr[1]))

class MigrateInstance(object):
    UNKNOWN_LOG = 0
    MIGRATE_LOG = 1
    TIME_LOG = 2
    SIZE_LOG = 3

    def __init__(self, ip, files, services, method):
        self.method=method
        self.values = [0]*len(KEYWORDS[self.method])
        self.size_values = [0]*len(SIZE_KEYWORDS[self.method])
        self.from_ip = ip
        self.to_ip = ''
        self.time = 0
        self.last = 0
        self.index = 0
        self.index_size = 0
        self.service_name = ''
        self.services = services
        self.files = files
        self.is_finish = False

    def get_line_type(self, line):
        migrate_tag = 'send msg: migrate'
        if time_tag in line:
            return MigrateInstance.TIME_LOG
        elif size_tag in line:
            return MigrateInstance.SIZE_LOG
        elif migrate_tag in line:
            return MigrateInstance.MIGRATE_LOG
        else:
            return MigrateInstance.UNKNOWN_LOG

    def get_migrate_info(self, line):
        json_match = re.search('{.*}', line)
        if json_match is not None:
            obj = json.loads(json_match.group(0))
            self.to_ip = obj['ip']
            self.service_name = obj['service_name']

    def find_restore_line(self, start_time, file_name):
        with open(file_name, 'r') as fd:
            # TODO offset 5000 ms =5s for getting premigration time
            next(l for l in fd if get_time(l) > (start_time -5000))
            for line in fd:
                delay = get_elapsed_time(line)
                if delay is None:
                    continue
                #print("delay...{}".format(delay))
                if delay[0] == KEYWORDS[self.method][self.index]:
                    self.values[self.index] = delay[1]
                    self.index+=1
                    if delay[0] == 'restore':
                        break

    def get_line(self, line):
        t = self.get_line_type(line)
        if t == MigrateInstance.TIME_LOG:
            delay = get_elapsed_time(line)
            print("time {}".format(delay))
            if delay[0] == KEYWORDS[self.method][self.index]:
                if self.index == 0:
                    self.time = get_time(line)
                self.values[self.index] = delay[1]
                self.index += 1
        elif t == MigrateInstance.SIZE_LOG:
            size = get_transfered_size(line)
            print("size {}".format(size))
            if size[0] == SIZE_KEYWORDS[self.method][self.index_size]:
                self.size_values[self.index_size] = size[1] # byte unit
                self.index_size += 1
        elif t == MigrateInstance.MIGRATE_LOG:
            self.get_migrate_info(line)
            self.last = get_time(line)
            dest_name = self.services.get_server_name_from_ip(self.to_ip)
            f = next((i for i in self.files if dest_name in i), None)
            print("send tag {}, dest_name {}, dst file {}".
                format(line, dest_name, f))
            if f is not None:
                self.find_restore_line(self.last, f)
        if self.index == len(KEYWORDS[self.method]) and\
            self.index_size == len(SIZE_KEYWORDS[self.method]):
            self.is_finish = True

    def to_dict(self):
        d = {
            'time': self.time,
            'from_ip': self.from_ip,
            'to_ip': self.to_ip,
            'service_name': self.service_name
        }
        # save delay values
        for i in range(len(KEYWORDS[self.method])):
            d[KEYWORDS[self.method][i].replace('-', '_')] = self.values[i]
        # save size values
        for i in range(len(SIZE_KEYWORDS[self.method])):
            d['size_' + SIZE_KEYWORDS[self.method][i].replace('-', '_')] =\
                self.size_values[i]
        return d

def parse_file(input_name, ip, files, services, method):
    entries = []
    with open(input_name, 'r') as f:
        instance = MigrateInstance(ip, files, services, method)
        for line in f:
            instance.get_line(line)
            if instance.is_finish:
                entries.append(instance.to_dict())
                # Create new instance
                instance = MigrateInstance(ip, files, services, method)
    return entries

def save_result(output_name, entries, method):
    with open(output_name, 'w') as output:
        if method == 'non_live_migration':
            fields = ['time',
                  'from_ip',
                  'to_ip',
                  'service_name',
                  'checkpoint',
                  'rsync',
                  'migrate',
                  'premigration',
                  'restore',
                  'size_rsync']
        else: # method == 'pre_copy':
            fields = ['time',
                  'from_ip',
                  'to_ip',
                  'service_name',
                  'pre_checkpoint', # NOTE: change from dash to underscore to
                                    # prevent python error.
                  'pre_rsync',
                  'prepare',
                  'checkpoint',
                  'rsync',
                  'xdelta_source',
                  'final_rsync',
                  'migrate',
                  'premigration', # below are dest times, above are source times
                  'xdelta_dest',
                  'restore',
                  'size_pre_rsync',
                  'size_rsync',
                  'size_final_rsync']
        writer = csv.DictWriter(output, fieldnames=fields,
                                lineterminator="\n")
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry)

def plot_total_migration_time(entries, plot_name, method='pre_copy'):
    black_list = ['prepare', 'migrate']
    plot_title = 'Total migration time'
    plot_result(entries, plot_name, black_list, plot_title, method)

def plot_downtime_service(entries, plot_name, method='pre_copy'):
    black_list = ['pre-checkpoint', 'pre-rsync', 'prepare', 'migrate',
        'premigration']
    plot_name = plot_name.split('.png')[0] + '_downtime.png'
    plot_title = 'Total downtime service'
    plot_result(entries, plot_name, black_list, plot_title, method)

def plot_result(entries, plot_name, black_list, plot_title, method):
    plot_keywords=[k.replace('-', '_')
                   for k in KEYWORDS[method] if k not in black_list]
    print("plotting keywords: {} to file: {}".format(plot_keywords, plot_name))
    # Convert entries to numpy array
    app_dict = {}
    for i in entries:
        name = i.get('service_name', '')
        delays = np.array([ i[k] for k in plot_keywords ])
        try:
            app_dict[name].append(delays)
        except KeyError:
            app_dict[name] = [delays]
    # Take average
    apps = []
    apps_delay = []
    for K,V in app_dict.iteritems():
        #print("K= {}, V= {}".format(K,V))
        avg = np.mean(V, axis=0)
        apps.append(K)
        apps_delay.append(avg)
    #print(apps_delay)
    datasets = zip(*apps_delay)
    print("datasets = {} ".format(datasets))
    # Draw y axis
    p = []
    ind = np.arange(len(apps))
    last = np.array([0.0]*len(apps))
    for idx,keyword in enumerate(plot_keywords):
        bar = plt.bar(ind, datasets[idx], bottom=last)
        last += datasets[idx]
        p.append(bar)
    # Draw x axis
    plt.ylabel('Time (s)')
    #plt.xlabel('Application')
    plt.xticks(ind, tuple(apps))
    plt.title(plot_title)
    plt.legend(tuple(p), tuple(plot_keywords))
    plt.savefig(plot_name)
    plot_name_eps = plot_name.split('.')[0] + '.eps'
    plt.savefig(plot_name_eps, format='eps', dpi=1000)
    plt.close()

def get_unit(data):
    """Get data
    return: 1 if keep the same unit
            2 if change the unit to KB
            3 if change the unit to MB
    """
    mindata = min(data)
    if mindata/1000 > 1000:
        return 3
    elif mindata/1000 > 1:
        return 2
    else:
        return 1

def plot_transfered_size(entries, plot_name, method='pre_copy'):
    plot_keywords = ['size_' + k.replace('-', '_') for k in SIZE_KEYWORDS[method]]
    # Convert entries to numpy array
    app_dict = {}
    for i in entries:
        name = i.get('service_name', '')
        sizes = np.array([ i[k] for k in plot_keywords ])
        try:
            app_dict[name].append(sizes)
        except KeyError:
            app_dict[name] = [sizes]
    # Take average
    apps = []
    apps_size = []
    std_size = []
    for K,V in app_dict.iteritems():
        #print("K= {}, V= {}".format(K,V))
        avg = np.mean(V, axis=0)
        std = np.std(V, axis=0)
        apps.append(K)
        apps_size.append(avg)
        std_size.append(std)
    apps_size = np.array(apps_size)
    datasets = apps_size.transpose()
    #print("datasets ", datasets)
    std_size = np.array(std_size)
    std_datasets = std_size.transpose()
    #print("std_data = ", std_datasets)
    # prepare x_label, y, std_y, and y_label,
    for i, data in enumerate(datasets):
        _y= data
        unit = get_unit(_y)
        _std_y = std_datasets[i]
        _y_label = 'Memory size (bytes)'
        if unit == 2: # KB
            _y = _y/10.0**3
            _std_y = _std_y/10.0**3
            _y_label = 'Memory size (KB)'
        elif unit == 3: # MB
            _y = _y/10.0**6
            _std_y = _std_y/10.0**6
            _y_label = 'Memory size (MB)'
        _title = 'Transfer memory {}'.format(plot_keywords[i])
        _plot_name = "{}_{}.png".format(
            plot_name.split('.png')[0], plot_keywords[i])
        plot_bar_std(apps, _y, _std_y, _y_label, _title, _plot_name)

def plot_bar_std(x_label, y, std_y, y_label, title, plot_name):
    print("plot bar std title {} to file {}".format(title, plot_name))
    fig, ax = plt.subplots()
    x_pos = np.arange(len(x_label))
    ax.bar(x_pos, y, yerr=std_y/2, align='center', alpha=0.5, ecolor='black', capsize=10)
    ax.set_ylabel(y_label)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(x_label)
    ax.set_title(title)
    ax.yaxis.grid(True)
    plt.tight_layout()
    plt.savefig(plot_name)
    plot_name_eps = plot_name.split('.')[0] + '.eps'
    plt.savefig(plot_name_eps, format='eps', dpi=1000)
    plt.close()


def main(pattern, conf, save, plot, method='pre_copy'):
    print("start with method {}".format(method))
    nodes = DiscoveryYaml(conf)
    files = glob.glob(pattern)
    print("files name: {}".format(files))
    if len(files) < 2:
        print("Error not enough information")
        return
    names = nodes.get_server_names()
    print("files name: {}. Hostnames:{}".format(files, names))
    entries = []
    for f in files:
        name = next((i for i in names if i in f), None)
        if name is not None:
            entries += parse_file(f, nodes.get_server_ip(name), files, nodes, method)
        else:
            print("You have to name the log file with $HOSTNAME in the name.")
    if len(entries) < 2:
        print("Error during parsing file. entries = {}".format(entries))
        return
    save_result(save, entries, method)
    if plot != '':
        plot_total_migration_time(entries, plot, method)
        plot_downtime_service(entries, plot, method)
        plot_transfered_size(entries, plot, method)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--pattern',
        help="File name pattern e.g: samples/migrate-docker*.txt",
        type=str,
        required=True
    )
    parser.add_argument(
        '--nodes',
        help="Nodes description",
        type=str,
        default='edge_nodes.yml'
    )
    parser.add_argument(
        '--save',
        help="Save the results into a file",
        type=str,
        default="output.csv"
    )
    parser.add_argument(
        '--method',
        help="Migration method: non_live_migration, pre_copy (default).",
        type=str,
        default="pre_copy"
    )
    parser.add_argument(
        '--plot',
        help="Plot the result",
        default=""
    )
    args = parser.parse_args()
    main(args.pattern, args.nodes, args.save, args.plot, args.method)
