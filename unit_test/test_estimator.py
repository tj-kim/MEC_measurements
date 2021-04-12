import pytest

from .. import estimator

def test_coeffs():
    assert len(estimator.handover_coeffs) == 3

def test_find_handover_points_hys0():
    hys = 0
    a = 1
    b = 0
    src = (0,2)
    dst = (4,0)
    points = estimator.find_handover_points(a, b, src, dst, hys=hys)
    assert len(points) == 1
    assert points[0][0] == 3
    assert points[0][1] == 3

def test_find_handover_points_hys_default():
    hys = 7.0
    a = 0
    b = 0
    src = (70,20)
    dst = (140,20)
    points = estimator.find_handover_points(a, b, src, dst, hys=hys)
    assert len(points) == 2

def test_find_remain_time():
    t = estimator.find_remain_time((0,0),(10, 10), (1,1))
    assert t == 10
    t = estimator.find_remain_time((0,0),(0, 10), (0,1))
    assert t == 10
    with pytest.raises(ValueError):
        t = estimator.find_remain_time((0,0),(10, 10), (0, 1))
        t = estimator.find_remain_time((0,0),(20, 10), (1, 1))

def test_estimate_new_position():
    p = estimator.estimate_new_position((0, 0), (1, 1), 10)
    assert p == (10, 10)
