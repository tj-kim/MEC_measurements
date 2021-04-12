
import csv
import argparse
import yaml
import numpy as np
from numpy import convolve
import matplotlib.pyplot as plt

START_TIME = 'startTime[ns]'
END_TIME = 'endTime[ns]'
SENT_SIZE = 'sentSize[B]'
RESULTS = 'results'
GENERAL = 'general'
TRANSFER_TIME = 'transferTime[ms]' # in s
PROCESS_TIME = 'processTime[ms]' # in s
INDEX = 'indexServer'
E2E_DELAY = 'E2Edelay[ms]'

def moving_average(values, window):
    weights = np.repeat(1.0, window)/window
    smas = np.convolve(values, weights, 'valid')
    return smas

def save_result(output_name, entries):
    with open(output_name, 'w') as output:
        fields = [INDEX, START_TIME, END_TIME, E2E_DELAY, TRANSFER_TIME,
            PROCESS_TIME, SENT_SIZE]
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for entry in entries:
           writer.writerow(entry)

def plot_delay(plot_name,  plot_title, entries, plot_ma):
    delays = []
    transfer_times = []
    processTimes = []
    indices = []
    for entry in entries:
        indices.append(entry.get(INDEX))
        start_time = entry.get(START_TIME)
        end_time = entry.get(END_TIME)
        delta = entry.get(E2E_DELAY)
        delays.append(delta)
        transfer_times.append(entry.get(TRANSFER_TIME))
        processTimes.append(entry[PROCESS_TIME])
    #print delays
    #x = np.arange(len(delays))
    x = indices
    plt.plot(x, delays)
    plt.plot(x, transfer_times)
    plt.plot(x, processTimes)
    if plot_ma:
        delaysMA = moving_average(delays, 3)
        plt.plot(x[len(x)-len(delaysMA):], delaysMA)
        plt.legend(['E2E delay', 'Moving Average E2E delay', 'Processing time'])
    else:
        plt.legend(['E2E delay', 'Transfer time', 'Processing time'])
    plt.ylabel('Time (ms)')
    plt.xlabel('Packet index')
    plt.title(plot_title)
    plt.savefig(plot_name)
    plot_name_eps = plot_name.split('.')[0] + '.eps'
    plt.savefig(plot_name_eps, format='eps', dpi=1000)
    plt.close()

def parse_file(input_file):
    f = open(input_file)
    lines = f.readlines()
    entries = []
    index = 0
    sent_size = 0
    delay = 0
    for line in lines:
        d = {}
        line = line.rstrip()
        try:
            line_json = yaml.safe_load(line)
            #print("line_json {}".format(line_json))
            start = line_json[START_TIME] # ns
            end = line_json[END_TIME] # ns
            sent_size = line_json[SENT_SIZE] # B
            results = line_json[RESULTS]
            general_info = results[GENERAL]
            index = general_info[INDEX]
            transfer_time = general_info[TRANSFER_TIME] #ms
            process = general_info[PROCESS_TIME] #ms
            new_delay = (end-start)/10.0**6    # ms
            if new_delay < 2000.0:
                delay = new_delay
            d[INDEX] = index
            d[START_TIME] = start          # ns
            d[END_TIME] = end              # ns
            d[E2E_DELAY] = delay           # ms
            d[TRANSFER_TIME] = transfer_time # ms
            d[PROCESS_TIME] = process      # ms
            d[SENT_SIZE] = sent_size       # bytes
            #print(d)
        except yaml.YAMLError:
            print("Error during parsing {}".format(line))
            start = long(line.split(":")[1].split(",")[0])
            d[INDEX] = index
            d[START_TIME] = start # ns
            d[END_TIME] = 0
            d[E2E_DELAY] = 0
            d[TRANSFER_TIME] = 0
            d[PROCESS_TIME] = 0
            d[SENT_SIZE] = sent_size # B
        if d[E2E_DELAY] < 500:
            entries.append(d)
    return entries

def main(args):
    entries = parse_file(args.file)
    save_result(args.save, entries)
    plot_delay(args.plot, args.title, entries, args.ma)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--file',
        help="File name and its path.",
        type=str,
        required=True
    )
    parser.add_argument(
        '--save',
        help="Save the results into a file",
        type=str,
        default="output.csv"
    )
    parser.add_argument(
        '--plot',
        help="Plot the result",
        default="output.png"
    )
    parser.add_argument(
        '--title',
        help="Title of the plot",
        default="End-to-end delay"
    )
    parser.add_argument(
        '--ma',
        help="Plot the moving average of E2E delays",
        action='store_true'
    )
    args = parser.parse_args()
    main(args)
