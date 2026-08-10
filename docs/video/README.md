# OCI IAM Plotter user-journey video

`oci-iam-plotter-user-journey.mp4` is a caption-led, credential-free product tour covering the end-to-end user journey and every principal workspace.

To render it again on macOS:

```bash
python3 docs/video/build_walkthrough.py
```

The editable walkthrough copy is saved as `narration.md`. The renderer uses Pillow and FFmpeg. It intentionally does not record the protected local workspace or include customer tenancy data.
