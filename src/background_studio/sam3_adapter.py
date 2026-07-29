from __future__ import annotations

from functools import cached_property

from PIL import Image


class Sam3Unavailable(RuntimeError):
    pass


class Sam3ImageAdapter:
    @cached_property
    def processor(self):
        try:
            from sam3.model.sam3_image_processor import Sam3Processor
            from sam3.model_builder import build_sam3_image_model
        except ImportError as exc:
            raise Sam3Unavailable(
                "SAM 3 is optional. Install facebookresearch/sam3 and accept its SAM License."
            ) from exc
        return Sam3Processor(build_sam3_image_model())

    def isolate(self, image: Image.Image, prompt: str, score_threshold: float = 0.5) -> Image.Image:
        if not prompt.strip():
            raise ValueError("prompt is required")
        if not 0 <= score_threshold <= 1:
            raise ValueError("score_threshold must be between 0 and 1")

        state = self.processor.set_image(image.convert("RGB"))
        output = self.processor.set_text_prompt(state=state, prompt=prompt.strip())
        masks = output["masks"]
        scores = output["scores"]
        selected = masks[scores >= score_threshold]
        if len(selected) == 0:
            return Image.new("L", image.size, 0)

        combined = selected.any(dim=0).squeeze().detach().cpu().numpy()
        mask = Image.fromarray((combined * 255).astype("uint8"), mode="L")
        return mask.resize(image.size, Image.Resampling.NEAREST)
