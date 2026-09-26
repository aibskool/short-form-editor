import unittest
from unittest.mock import patch

from hyperframes_cli import no_telemetry_env, run


class LocalRendererPrivacyTests(unittest.TestCase):
    def test_every_renderer_command_sets_supported_opt_out(self):
        with patch("hyperframes_cli.subprocess.run") as called:
            run(["check", "/tmp/composition"])
        env = called.call_args.kwargs["env"]
        self.assertEqual(env["HYPERFRAMES_NO_TELEMETRY"], "1")
        self.assertEqual(env["DO_NOT_TRACK"], "1")
        self.assertEqual(called.call_args.args[0][1:], ["check", "/tmp/composition"])


if __name__ == "__main__":
    unittest.main()
