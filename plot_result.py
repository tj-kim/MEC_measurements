import os
import sys
import argparse

import matplotlib
matplotlib.use('Agg')
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

sys.path.append(os.path.join(os.path.dirname(__file__), './end-user/'))
import Constants
import central_database
import simulated_mobile_eu_db as eu_database


service_names = [Constants.YOLO, Constants.OPENFACE, Constants.SIMPLE_SERVICE]

def plot_downtime():
    pass

def plot_migration(df, file_name):
    fix, ax = plt.subplots()
    fix.suptitle('Migration time')
    columns = ['service', 'pre_checkpoint', 'pre_rsync', 'checkpoint', 'xdelta_source',
               'final_rsync', 'xdelta_dest', 'restore']
    migration = df[columns].groupby('service').aggregate('mean')
    migration.plot.bar(stacked=True)
    plt.savefig('{}.eps'.format(file_name), format='eps', dpi=1000)
    plt.savefig('{}.png'.format(file_name), dpi=1000)
    plt.close()

def plot_cdf_e2e_delay(df, file_name, bins=1000):
    fig, ax = plt.subplots()
    fig.suptitle('CDF of E2E delay')
    ax.set_xlabel('Processing time (ms)')
    for title, group in df.groupby('service'):
        group['proc_delay'].plot.hist(cumulative=True, density=1,
                                      histtype='step', bins=bins, label=title)
    plt.savefig('{}.eps'.format(file_name), format='eps', dpi=1000)
    plt.savefig('{}.png'.format(file_name), dpi=1000)
    plt.close()

def get_service_name_from_user(service_id, name):
    return service_id[:-len(name)]

def filter_name(name):
    for s in service_names:
        len_s = len(s)
        if s == name[:len_s]:
            return pd.Series({'service': s, 'user': name[len_s:]})
    return pd.Series({'service': '', 'user':''})

def process_service_id(df, field_name='service_id'):
    df[['service', 'user']] = df[field_name].apply(filter_name)

def preprocess_centre_db(files):
    db = central_database.DBCentral(database=f)
    df_request = pd.read_sql_table('user_service', db.engine)
    process_service_id(df_request)
    df_migration = pd.read_sql_table('migrate_history', db.engine)
    df_migration['service_id'] = df_migration['service']
    process_service_id(df_migration)
    db.close()
    return df_request, df_migration

def main(server_files, eu_files):
    dbs = map(preprocess_centre_db, server_files)
    df_request = pd.concat([df[0] for db in dbs])
    df_migration = pd.concat([df[1] for db in dbs])
    plot_cdf_e2e_delay(df_request, 'e2e_cdf')
    plot_migration(df_migration, 'service_migration')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--server_files',
        help="Server database files",
        nargs='*')
    parser.add_argument(
        '--eu_files',
        help="EU database files",
        nargs='*')
    args = parser.parse_args()
    print(args)
    main(args.server_files, args.eu_files)
