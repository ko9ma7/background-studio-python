# Third-party notices

This repository's own source code is MIT licensed. Runtime engines and models
retain their own licenses.

| Component | Role | License / condition |
|---|---|---|
| [rembg](https://github.com/danielgatis/rembg) | Default image segmentation adapter | MIT |
| [ONNX Runtime](https://onnxruntime.ai/) | CPU inference used by rembg | MIT |
| [U-2-Net](https://github.com/xuebinqin/U-2-Net) | Optional downloaded model family | Apache-2.0 source; verify each checkpoint's accompanying terms |
| [FFmpeg](https://ffmpeg.org/) | Video decode/encode | LGPL/GPL configuration varies by distribution |
| [SAM 3](https://github.com/facebookresearch/sam3) | Optional concept-mask adapter | Separate SAM License; not installed or redistributed by default |

The application downloads no SAM 3 code or model automatically. Users who add
that optional engine must review and accept Meta's current SAM License.

Projects studied but not copied into this source are listed in
[`docs/research-matrix.md`](docs/research-matrix.md).

