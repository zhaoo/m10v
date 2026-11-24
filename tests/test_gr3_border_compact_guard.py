"""Run the actual native border callback/queue checks with only guard at Oz."""
from tests.test_gr3_border_runtime import BorderRuntimeArmTests as _Runtime
class CompactBorderGuardArmTests(_Runtime):
    guard_flags=('-Oz',)
