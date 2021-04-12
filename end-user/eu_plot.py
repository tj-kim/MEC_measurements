from __future__ import division

import argparse
import collections

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

import simulated_mobile_eu_db as db

RequestRecord = collections.namedtuple('RequestRecord',
                                       ['start', 'process_time', 'e2e_delay'])

def plot_request_per_interval(df, interval=5, timescale=10**6,
                              name='per_interval'):
    start_time = df['timestamp'].iloc[0]
    df['sec'] = df['timestamp'].map(
        lambda x: int((x-start_time)/interval/timescale))
    indexs = []
    values = []
    for title, group in df.groupby('sec'):
        indexs.append(title*interval)
        values.append(len(group))
    plt.plot(indexs, values)
    plt.ylabel("Request per {}s".format(interval))
    plt.xlabel("Time(s)")
    plt.savefig("{}.png".format(name), dpi=1000)
    plt.savefig("{}.eps".format(name), format='eps', dpi=1000)
    plt.close()

def plot_delay(df, name='delay'):
    ax = plt.gca()
    df.plot(kind='line', x='index', y='proc_delay', ax=ax)
    df.plot(kind='line', x='index', y='e2e_delay', ax=ax)
    plt.savefig("{}.png".format(name), dpi=1000)
    plt.savefig("{}.eps".format(name), format='eps', dpi=1000)
    plt.close()


def main(args):
    database = db.DBeu(database=args.file)
    df = pd.read_sql_table(db.UserRequest.__tablename__, database.engine)
    plot_request_per_interval(df)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--file',
        help="File name",
        type=str,
        required=True)
    parser.add_argument(
        '--csv',
        help='csv output',
        default=None)
    parser.add_argument(
        '--plot_type',
        help='plot_type',
        default='request_per_interval')
    parser.add_argument(
        '--title',
        help="Title of the plot",
        default=None)
    parser.add_argument(
        '--type',
        help="Input type: sql, csv, json",
        default='sql')
    args = parser.parse_args()
    main(args)

