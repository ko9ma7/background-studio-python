# Research and adoption matrix

Checked on 2026-07-29.

| Source | What it contributes | Decision |
|---|---|---|
| junyanz/CycleGAN | Unpaired image-to-image style translation | Documented as a future style-transfer stage; not a segmentation engine |
| facebookresearch/sam3 | Concept-prompted image segmentation and video tracking | Optional adapter only because of model size, GPU needs, and SAM License |
| danielgatis/rembg | Reusable ONNX sessions and image background removal | Default Python engine |
| nadermx/backgroundremover | FFmpeg frame pipeline and transparent video outputs | Video workflow reference; implementation here is independent |
| imgly/background-removal-js | In-browser private inference | Used only in the separate AGPL web repository |
| jasonmayes/Real-Time-Person-Removal | Real-time browser person segmentation pattern | Performance and webcam roadmap reference |
| royshil/obs-backgroundremoval | Real-time portrait video and OBS use cases | Streaming roadmap reference |
| facebookresearch/denoiser | Speech-noise removal, not visual background removal | Excluded from visual pipeline; possible separately licensed audio extension |
| AUTOMATIC1111/stable-diffusion-webui-rembg | Extension UI around rembg | UI workflow reference |
| plemeri/transparent-background | InSPyReNet edge-quality options | Optional future engine |
| xiyaowong/transparent.nvim | Neovim theme transparency | Out of scope |
| wladradchenko/wunjo.wladradchenko.ru | Multi-tool local media editing | Product workflow reference; no code copied |

