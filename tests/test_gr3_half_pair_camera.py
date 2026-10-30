"""Compatibility entrypoint for the owned native-IIP camera adapter tests.

The retired SD row-file harness is replaced by the r7 ownership harness;
CPU composition is retained only as a host reference in test_gr3_half_pair.
"""
from tests.test_gr3_half_pair_camera_iip import HalfPairCameraIIP as PairCameraTests
