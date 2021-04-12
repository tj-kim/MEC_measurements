#!/usr/bin/python

import ast
import argparse
import numpy as np

DELAY = "delay"
START = "start"

def parse_delay_from_json(args):
    f = open(args.file)
    lines = f.readlines()
    starts = []
    delays =[]
    for line in lines:
        line = line.rstrip()
        #print line
        ast_line = ast.literal_eval(line)
        delay = ast_line[DELAY]
        delays.append(delay)
        start = ast_line[START]
        starts.append(start)
        if args.verbose:
            print("delay {}".format(delay))
    mean_delay = np.mean(delays)    
    print("average delay {} ns or {} ms".format(mean_delay, mean_delay/1000000))
    print delays
    if args.save:
        import csv
        with open(args.save_file, "w") as output:
            writer = csv.writer(output, lineterminator="\n")
            # Save in a format: [time, delay] in rows
            for i, val in enumerate(delays):
                writer.writerow([starts[i],  val])

    if args.plot:
        import matplotlib.pyplot as plt
        mean_delays = [mean_delay] * len(starts)
        plt.plot(starts, delays, starts, mean_delays, 'r--')
        plt.show()


            

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--file',
        type=str,
        help="Path to a parsing file.",
        default="delay_example.txt")
    parser.add_argument(
        '--param',
        type=str,
        help="Parameter will be parsed and analyzed.",
        default="delay")
    parser.add_argument(
        '--verbose',
        help="Print verbose message.",
        action='store_true')
    parser.add_argument(
        '--plot',
        help="Plot the result in a graph.",
        action='store_true')
    parser.add_argument(
        '--save',
        help="Save the analyzed results into a file.",
        action='store_true')
    parser.add_argument(
        '--save_file',
        type=str,
        help="Save the results into a file with a given name.",
        default='save_results_file.csv')

    global args 
    args = parser.parse_args()
    
    parse_delay_from_json(args)

if __name__ == '__main__':
    main()
