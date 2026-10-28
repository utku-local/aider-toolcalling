"""Tests for --seed: the seed reaches every completion request, and no seed leaves requests unchanged.
The seed is merged into the model's extra_params, which send_completion copies into the request kwargs.
A request without --seed must not carry a seed key, so servers keep their own default behaviour.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aider.args import get_parser
from aider.model_seed import with_seed
from aider.models import Model

MODEL_NAME = "openai/test-model"


class ModelSeedTest(unittest.TestCase):
    def test_with_seed(self) -> None:
        self.assertIsNone(with_seed(None, None))
        self.assertEqual(with_seed({"max_tokens": 9}, None), {"max_tokens": 9})
        self.assertEqual(with_seed({"max_tokens": 9}, 7), {"max_tokens": 9, "seed": 7})
        original = {"top_p": 1}
        with_seed(original, 3)
        self.assertEqual(original, {"top_p": 1})

    def test_seed_reaches_the_request(self) -> None:
        model = Model(MODEL_NAME)
        for seed, expected in ((None, False), (42, True)):
            model.extra_params = with_seed(None, seed)
            with patch("aider.models.litellm.completion", return_value=SimpleNamespace(choices=[])) as call:
                model.send_completion([{"role": "user", "content": "hi"}], None, False)
            self.assertEqual("seed" in call.call_args.kwargs, expected)
            if expected:
                self.assertEqual(call.call_args.kwargs["seed"], 42)

    def test_flag(self) -> None:
        parser = get_parser([], None)
        self.assertIsNone(parser.parse_args([]).seed)
        self.assertEqual(parser.parse_args(["--seed", "5"]).seed, 5)


if __name__ == "__main__":
    unittest.main()
