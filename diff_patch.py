#!/usr/bin/python
from subprocess import call, Popen, PIPE
from joblib import Parallel, delayed, cpu_count, parallel_backend
import shutil
import os
import logging
import argparse

def bsdiff_(old, new, patch, filename, verbose):
    out = call(['bsdiff', old + filename, new + filename,\
            patch + filename])
    logging.debug("bsdiff {} {} {}. Output: {}".format(old + filename,\
                new + filename, patch + filename, out))

def bspatch_(old, new, patch, filename, verbose):
    out = call(['bspatch', old + filename, new+ filename,\
                patch + filename])
    logging.debug("bspatch {} {} {}. Output: {}".format(old + filename,\
                new + filename, patch + filename, out))

def xdelta_delta(old, new, patch, filename, verbose):
    oldfile = old + filename
    newfile = new + filename
    patchfile = patch + filename
    out = Popen(['xdelta', 'delta', oldfile, newfile, patchfile],
            stdout=PIPE, stderr=PIPE)
    ret_code = out.wait()
    ret = out.communicate()
    if ret_code == 2:
        shutil.copyfile(newfile, patchfile)
    logging.debug("xdelta delta {} {} {}. Output:{}".format(oldfile,\
                newfile, patchfile, ret))

def xdelta_patch(old, new, patch, filename, verbose):
    oldfile = old + filename
    newfile = new + filename
    patchfile = patch + filename
    out = Popen(['xdelta', 'patch', patchfile, oldfile, newfile],
            stdout=PIPE, stderr=PIPE)
    ret_code = out.wait()
    ret = out.communicate()
    if ret_code == 2:
        shutil.copyfile(patchfile, newfile)
    logging.debug("xdelta patch {} {} {}. Output: {}".format(patchfile,\
                oldfile, newfile, ret))

def create_bsdiff(old, new, patch, verbose):
    num_cores = cpu_count()
    Parallel(n_jobs=num_cores)(delayed(bsdiff_)(old, new, patch, i, verbose)\
                for i in os.listdir(old))

def create_bspatch(old, new, patch, verbose):
    num_cores = cpu_count()
    Parallel(n_jobs=num_cores)(delayed(bspatch_)(old, new, patch, i, verbose)\
                for i in os.listdir(old))

def create_xdelta_diff(old, new, patch, verbose, is_parallel=False):
    if is_parallel:
        num_cores = cpu_count()
    else:
        num_cores = 1
    with parallel_backend('threading', n_jobs=num_cores):
        Parallel()(
    #Parallel(n_jobs=num_cores)(
        delayed(xdelta_delta)(old, new, patch, i, verbose)\
                for i in os.listdir(new)
                    if (os.path.isfile(os.path.join(new, i)) and\
                        'tar.gz.img' not in i)
                )

def create_xdelta_patch(old, new, patch, verbose):
    num_cores = cpu_count()
    with parallel_backend('threading', n_jobs=num_cores):
        Parallel()(
    #Parallel(n_jobs=num_cores)(
        delayed(xdelta_patch)(old, new, patch, i, verbose)\
                for i in os.listdir(patch) if os.path.isfile(os.path.join(patch, i)))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--verbose',
        help='Verbose print debug',
        action='store_true')
    parser.add_argument(
        '--old',
        type=str,
        help='Old directory',
        required=True)
    parser.add_argument(
        '--new',
        type=str,
        help='New directory',
        required=True)
    parser.add_argument(
        '--patch',
        type=str,
        help='Patch directory',
        required=True)
    parser.add_argument(
        '--cmd',
        type=str,
        help='Command: [create_xdelta_diff, create_xdelta_patch]',
        required=True)
    args = parser.parse_args()
    if args.cmd == 'create_xdelta_diff':
        create_xdelta_diff(args.old, args.new, args.patch, args.verbose)
    elif args.cmd == 'create_xdelta_patch':
        create_xdelta_patch(args.old, args.new, args.patch, args.verbose)

