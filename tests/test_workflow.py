"""Regression checks for grouping, paths, complete codec output and quiet cuts."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/html-video-demo/scripts")
)
from common import init_project, inside, load_project, plan_groups, source_signature
from audio_utils import aligned_cues, assemble, quiet_cut


class WorkflowTests(unittest.TestCase):
    """Verify workflow invariants without loading model weights."""

    def test_init_never_overwrites(self):
        """Existing project content must survive attempted initialization."""
        with tempfile.TemporaryDirectory() as tmp:
            init_project(tmp)
            before = Path(tmp, "project.json").read_bytes()
            with self.assertRaises(ValueError):
                init_project(tmp)
            self.assertEqual(before, Path(tmp, "project.json").read_bytes())

    def test_groups_are_configurable_and_ordered(self):
        """Grouping follows content length and rejects reordered explicit groups."""
        with tempfile.TemporaryDirectory() as tmp:
            init_project(tmp)
            p = load_project(tmp)
            self.assertEqual(plan_groups(p), [["overview", "save"]])
            p["voice"]["max_group_chars"] = 55
            self.assertEqual(plan_groups(p), [["overview"], ["save"]])
            p["groups"] = [["save", "overview"]]
            with self.assertRaises(ValueError):
                plan_groups(p)

    def test_paths_cannot_escape(self):
        """Relative traversal and escaping symlinks are rejected."""
        with (
            tempfile.TemporaryDirectory() as tmp,
            tempfile.TemporaryDirectory() as elsewhere,
        ):
            with self.assertRaises(ValueError):
                inside(tmp, "../secret")
            Path(tmp, "escape").symlink_to(elsewhere, target_is_directory=True)
            with self.assertRaises(ValueError):
                inside(tmp, "escape/secret")

    def test_manifest_identity_changes(self):
        """Content edits invalidate intermediate timing identity."""
        with tempfile.TemporaryDirectory() as tmp:
            init_project(tmp)
            before = source_signature(tmp)
            p = load_project(tmp)
            p["title"] = "Another example"
            Path(tmp, "project.json").write_text(json.dumps(p))
            self.assertNotEqual(before, source_signature(tmp))

    def test_missing_aligned_words_are_rejected(self):
        """A forced-alignment result must cover the supplied transcript."""
        items = [SimpleNamespace(text="你好", start_time=0.1, end_time=0.8)]
        with self.assertRaises(ValueError):
            aligned_cues(["你好世界"], items, 2)

    def test_speech_cannot_be_a_cut(self):
        """Noisy intervals cannot silently become chapter boundaries."""
        with self.assertRaises(ValueError):
            quiet_cut(np.ones(3000, dtype=np.float32) * 0.2, 1000, 1, 2)

    def test_assembly_preserves_samples_and_tail(self):
        """Silent cuts retain all input samples and configured post-word holds."""
        sr = 1000
        audio = np.zeros(3000, dtype=np.float32)
        audio[200:800] = 0.2
        audio[2000:2600] = 0.3
        project = {
            "video": {"fps": 30},
            "alignment": {
                "pre_roll_seconds": 0.35,
                "end_hold_seconds": 1,
                "cut_rms_dbfs": -43,
            },
            "scenes": [
                {"id": "one", "narration": ["你好"]},
                {"id": "two", "narration": ["世界"]},
            ],
        }
        items = [
            SimpleNamespace(text="你好", start_time=0.2, end_time=0.8),
            SimpleNamespace(text="世界", start_time=2, end_time=2.6),
        ]
        cues, words = aligned_cues(["你好", "世界"], items, 3)
        scenes, chapters, audit = assemble(project, audio, sr, cues, words)
        self.assertTrue(audit["samples_preserved"])
        self.assertTrue(all(s["end_hold"] >= 1 for s in scenes))
        self.assertEqual(
            sum(np.count_nonzero(c) for c in chapters), np.count_nonzero(audio)
        )
        self.assertTrue(all(np.max(np.abs(c[-100:])) == 0 for c in chapters))


class DecoderTests(unittest.TestCase):
    """Test the valid-zero regression and native no-op behavior."""

    @classmethod
    def setUpClass(cls):
        """Load MLX only for the decoder-specific checks."""
        try:
            import mlx.core as mx
        except ImportError as error:
            raise unittest.SkipTest("MLX not installed") from error
        cls.mx = mx

    def tokenizer(self, affected):
        """Construct a tiny decoder with either old or corrected length reporting.

        Args:
            affected: Whether zero codec IDs reduce reported length.

        Returns:
            Minimal tokenizer implementing the adapter contract.
        """
        mx = self.mx

        class Decoder:
            config = SimpleNamespace(num_quantizers=2)

            def __call__(self, codes):
                return mx.ones((1, 1, codes.shape[-1] * 4)) * 0.1

        class Tokenizer:
            decode_upsample_rate = 4
            decoder = Decoder()

            def decode(self, codes):
                length = (
                    mx.sum(codes[..., 0] > 0) * 4 if affected else codes.shape[1] * 4
                )
                return mx.ones((1, codes.shape[1] * 4)) * 0.1, mx.array([length])

        return Tokenizer()

    def test_zero_codec_samples_are_preserved(self):
        """Valid zeros cannot shorten generated speech."""
        from qwen_decode import configure_decoder

        tokenizer, audit = self.tokenizer(True), []
        self.assertTrue(configure_decoder(tokenizer, audit))
        audio, lengths = tokenizer.decode(
            self.mx.array([[[0, 1], [3, 1], [0, 1], [4, 1]]])
        )
        self.assertEqual(audio.shape[-1], 16)
        self.assertEqual(int(lengths[0]), 16)
        self.assertEqual(audit[-1]["previously_omitted_samples"], 8)

    def test_fixed_native_decoder_is_untouched(self):
        """Future correct runtimes must not receive an unnecessary patch."""
        from qwen_decode import configure_decoder

        tokenizer = self.tokenizer(False)
        before = tokenizer.decode
        self.assertFalse(configure_decoder(tokenizer, []))
        self.assertEqual(before, tokenizer.decode)


if __name__ == "__main__":
    unittest.main()
