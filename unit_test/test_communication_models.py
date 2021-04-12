from .. import communication_models as cm

def test_rssi_2_distance():
    assert cm.distance(-30) == 1

def test_datarate_mode():
    assert cm.datarate_model(-100) == 0.00001

def test_handover_constant():
    # This function care only about `default` parameter.
    assert cm.handover_constant(None, None, None, default=0.5) == 0.5
