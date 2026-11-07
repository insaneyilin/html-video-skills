"""Detect and contain a Qwen3-12Hz unpadded-length regression in MLX Audio.

The observed 0.6.4 implementation mistakes valid codec ID zero for padding.
A small in-memory decoder probe detects this behavior. Only affected model
instances receive the workaround; installed packages are never rewritten.
"""


def configure_decoder(tokenizer, audit, policy="auto", chunk_frames=150):
    """Probe output lengths and preserve valid zero IDs when needed.

    Args:
        tokenizer: Loaded Qwen3-12Hz speech tokenizer.
        audit: List receiving probe and decode diagnostics.
        policy: "auto" probes the invariant; "native" preserves native behavior.
        chunk_frames: Decoder work size for bounded intermediate memory.

    Returns:
        Whether a local workaround was installed.

    Raises:
        ValueError: If policy or decoder assumptions do not match this adapter.
    """
    import mlx.core as mx

    if policy not in ["auto", "native"]:
        raise ValueError("decoder_policy must be auto or native")
    if policy == "native":
        audit.append({"probe": "skipped", "workaround": False})
        return False
    if chunk_frames < 1 or not hasattr(tokenizer, "decoder"):
        raise ValueError("Unsupported speech tokenizer")
    rate = int(tokenizer.decode_upsample_rate)
    codebooks = int(tokenizer.decoder.config.num_quantizers)
    probe = mx.ones((1, 2, codebooks), dtype=mx.int32)
    probe[0, 0, 0] = 0
    audio, lengths = tokenizer.decode(probe)
    mx.eval(audio, lengths)
    expected, actual, reported = 2 * rate, int(audio.shape[-1]), int(lengths[0])
    affected = actual == expected and reported == rate
    audit.append(
        {
            "probe": "valid-zero-code",
            "expected": expected,
            "decoded": actual,
            "reported": reported,
            "workaround": affected,
        }
    )
    if actual != expected or reported not in [expected, rate]:
        raise ValueError(
            "Unexpected tokenizer lengths; inspect this runtime before applying the workaround"
        )
    if not affected:
        return False

    def decode_unpadded(codes):
        """Decode a single unpadded sequence while keeping all generated samples.

        Args:
            codes: Tensor with shape [1, time, codebooks], without padding.

        Returns:
            Waveform and exact decoded sample length.

        Raises:
            ValueError: If input batching, padding or dimensions are unsupported.
        """
        if (
            codes.ndim != 3
            or codes.shape[0] != 1
            or codes.shape[2] != codebooks
            or codes.shape[1] == 0
        ):
            raise ValueError(
                "The workaround only accepts one unpadded generated sequence"
            )
        if bool(mx.any(codes < 0).item()):
            raise ValueError("Negative padding tokens are unsupported")
        transposed = mx.transpose(codes, (0, 2, 1))
        pieces = []
        for start in range(0, codes.shape[1], chunk_frames):
            context = min(25, start)
            stop = min(start + chunk_frames, codes.shape[1])
            piece = tokenizer.decoder(transposed[..., start - context : stop])[
                ..., context * rate :
            ]
            mx.eval(piece)
            pieces.append(piece)
        waveform = mx.concatenate(pieces, axis=-1).squeeze(1)
        mx.eval(waveform)
        if waveform.shape[-1] != codes.shape[1] * rate:
            raise ValueError("Decoder output length changed unexpectedly")
        omitted = int(mx.sum(codes[..., 0] == 0).item()) * rate
        audit.append(
            {
                "codec_frames": codes.shape[1],
                "preserved_samples": waveform.shape[-1],
                "previously_omitted_samples": omitted,
            }
        )
        return waveform, mx.array([waveform.shape[-1]])

    tokenizer.decode = decode_unpadded
    return True
