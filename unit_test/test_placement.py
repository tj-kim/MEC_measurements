
import mock
import pytest
from .. import placement

def test_linear_placement():
    number_bs = 3
    distance_bs = 70.0
    linear = placement.LinearPlacement(number_bs = number_bs,
        distance_bs = distance_bs)
    coords = linear.get_position_bs()
    assert coords[1] == (70, 0)

def test_circle_placement():
    number_bs = 3
    distance_bs = 70.0
    circle = placement.CirclePlacement(number_bs = number_bs,
        distance_bs = distance_bs)
    r = circle.get_radius()
    assert r - 40.41 < 0.01
    coords = circle.get_position_bs()
    assert abs(coords[1][1] - 35.0) < 0.01
    assert abs(coords[2][1] + 35.0) < 0.01
