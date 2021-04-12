import re
import numpy as np
import os
import csv
import pytest
from .. import log_parser

@pytest.fixture
def create_files():
    try:
        os.remove('foo.png')
    except OSError:
        pass
    try:
        os.remove('test.csv')
    except OSError:
        pass
    log_parser.main('samples/migrate-docker*.txt',
                    'edge_nodes.yml',
                    'test.csv', 'foo.png')
    return None

def test_error(create_files):
    assert os.path.exists('foo.png')
    assert os.path.exists('test.csv')

def test_convert_time():
    # Reference: https://www.epochconverter.com/
    time_str = '2018-06-25 20:19:01,000'
    assert 1529929141 == log_parser.convert_time(time_str)
    assert re.match(log_parser.time_match, time_str)

check_list = [
    'pre_checkpoint', 'pre_rsync', 'prepare', 'checkpoint', 'rsync',
    'xdelta_source', 'final_rsync', 'migrate', 'xdelta_dest', 'restore'
]

def is_invalid(d):
    for i in check_list:
        if d.get(i, 0) == 0:
            return False
    return True

def test_csv_correct_case(create_files):
    with open('test.csv', 'r') as fd:
        reader = csv.DictReader(fd)
        for row in reader:
            assert is_invalid(row)


