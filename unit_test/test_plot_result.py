import pytest

import pandas as pd

from .. import plot_result

@pytest.fixture(scope='module')
def data_request():
    df = pd.DataFrame(data={
        'service_id': ['yolosim_eu' for i in range(5)],
        'user_id': ['sim_eu' for i in range(5)]
    })
    return df

@pytest.fixture(scope='module')
def data_migration():
    df = pd.DataFrame(data={
        'service': ['yolosim_eu', 'yolosim_eu'],
        'pre_checkpoint': [1, 1],
        'pre_rsync': [1, 1],
        'checkpoint': [1, 1],
        'xdelta_source': [1, 1],
        'final_rsync': [1, 1],
        'xdelta_dest': [1, 1],
        'restore': [1, 1]
    })
    return df

@pytest.mark.incremental
class TestCentrePlot(object):
    def test_process_service_id(self, data_request, data_migration):
        plot_result.process_service_id(data_request)
        assert data_request['service'].apply(lambda x: x=='yolo').all()
        data_migration['service_id'] = data_migration['service']
        plot_result.process_service_id(data_migration)
        assert data_migration['service'].apply(lambda x: x=='yolo').all()


@pytest.mark.incremental
class TestEUPlot(object):
    def test_foo(self):
        pass
