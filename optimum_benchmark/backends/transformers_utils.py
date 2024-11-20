from contextlib import contextmanager
from typing import Any, Dict, Optional, Union

import torch
import transformers
from transformers import (
    AutoConfig,
    AutoFeatureExtractor,
    AutoImageProcessor,
    AutoProcessor,
    AutoTokenizer,
    FeatureExtractionMixin,
    GenerationConfig,
    ImageProcessingMixin,
    PretrainedConfig,
    ProcessorMixin,
    SpecialTokensMixin,
)

from ..import_utils import is_torch_available

TASKS_TO_MODEL_LOADERS = {
    # text processing
    "feature-extraction": "AutoModel",
    "fill-mask": "AutoModelForMaskedLM",
    "multiple-choice": "AutoModelForMultipleChoice",
    "question-answering": "AutoModelForQuestionAnswering",
    "token-classification": "AutoModelForTokenClassification",
    "text-classification": "AutoModelForSequenceClassification",
    # audio processing
    "audio-xvector": "AutoModelForAudioXVector",
    "text-to-audio": "AutoModelForTextToSpectrogram",
    "audio-classification": "AutoModelForAudioClassification",
    "audio-frame-classification": "AutoModelForAudioFrameClassification",
    # image processing
    "mask-generation": "AutoModel",
    "image-to-image": "AutoModelForImageToImage",
    "masked-im": "AutoModelForMaskedImageModeling",
    "object-detection": "AutoModelForObjectDetection",
    "depth-estimation": "AutoModelForDepthEstimation",
    "image-segmentation": "AutoModelForImageSegmentation",
    "image-classification": "AutoModelForImageClassification",
    "semantic-segmentation": "AutoModelForSemanticSegmentation",
    "zero-shot-object-detection": "AutoModelForZeroShotObjectDetection",
    "zero-shot-image-classification": "AutoModelForZeroShotImageClassification",
    # text generation
    "image-to-text": "AutoModelForVision2Seq",
    "text-generation": "AutoModelForCausalLM",
    "text2text-generation": "AutoModelForSeq2SeqLM",
    "image-text-to-text": "AutoModelForImageTextToText",
    "visual-question-answering": "AutoModelForVisualQuestionAnswering",
    "automatic-speech-recognition": ("AutoModelForSpeechSeq2Seq", "AutoModelForCTC"),
}


if is_torch_available():
    TASKS_TO_MODEL_TYPES_TO_MODEL_CLASSES = {}
    for task_name, model_loaders in TASKS_TO_MODEL_LOADERS.items():
        TASKS_TO_MODEL_TYPES_TO_MODEL_CLASSES[task_name] = {}

        if isinstance(model_loaders, str):
            model_loaders = (model_loaders,)

        for model_loader_name in model_loaders:
            model_loader_class = getattr(transformers, model_loader_name)
            TASKS_TO_MODEL_TYPES_TO_MODEL_CLASSES[task_name].update(model_loader_class._model_mapping._model_mapping)
else:
    TASKS_TO_MODEL_TYPES_TO_MODEL_CLASSES = {}

PretrainedProcessor = Union["FeatureExtractionMixin", "ImageProcessingMixin", "SpecialTokensMixin", "ProcessorMixin"]


def get_transformers_pretrained_config(model: str, **kwargs) -> "PretrainedConfig":
    # sometimes contains information about the model's input shapes that are not available in the config
    return AutoConfig.from_pretrained(model, **kwargs)


def get_transformers_generation_config(model: str, **kwargs) -> Optional["GenerationConfig"]:
    try:
        # sometimes contains information about the model's input shapes that are not available in the config
        return GenerationConfig.from_pretrained(model, **kwargs)
    except Exception:
        return GenerationConfig()


def get_transformers_pretrained_processor(model: str, **kwargs) -> Optional["PretrainedProcessor"]:
    try:
        # sometimes contains information about the model's input shapes that are not available in the config
        return AutoProcessor.from_pretrained(model, **kwargs)
    except Exception:
        try:
            return AutoFeatureExtractor.from_pretrained(model, **kwargs)
        except Exception:
            try:
                return AutoImageProcessor.from_pretrained(model, **kwargs)
            except Exception:
                try:
                    return AutoTokenizer.from_pretrained(model, **kwargs)
                except Exception:
                    return None


def get_flat_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    flat_dict = {}
    for k, v in d.items():
        if isinstance(v, dict):
            flat_dict.update(get_flat_dict(v))
        else:
            flat_dict[k] = v
    return flat_dict


def get_flat_artifact_dict(artifact: Union[PretrainedConfig, PretrainedProcessor]) -> Dict[str, Any]:
    if isinstance(artifact, ProcessorMixin):
        artifact_dict = {}

        for attribute in artifact.attributes:
            artifact_dict.update(get_flat_artifact_dict(attribute))
    else:
        if hasattr(artifact, "to_dict"):
            artifact_dict = {k: v for k, v in artifact.to_dict().items() if v is not None}
        else:
            try:
                artifact_dict = {k: getattr(artifact, k) for k in dir(artifact) if getattr(artifact, k) is not None}
            except Exception:
                pass

    artifact_dict = get_flat_dict(artifact_dict)

    return artifact_dict


def extract_transformers_shapes_from_artifacts(
    config: Optional["PretrainedConfig"] = None,
    processor: Optional["PretrainedProcessor"] = None,
) -> Dict[str, Any]:
    flat_artifacts_dict = {}

    if config is not None:
        flat_artifacts_dict.update(get_flat_artifact_dict(config))

    if processor is not None:
        flat_artifacts_dict.update(get_flat_artifact_dict(processor))

    shapes = {}

    # text input
    if "vocab_size" in flat_artifacts_dict:
        shapes["vocab_size"] = flat_artifacts_dict["vocab_size"]

    if "type_vocab_size" in flat_artifacts_dict:
        shapes["type_vocab_size"] = flat_artifacts_dict["type_vocab_size"]

    if "max_position_embeddings" in flat_artifacts_dict:
        shapes["max_position_embeddings"] = flat_artifacts_dict["max_position_embeddings"]
    elif "n_positions" in flat_artifacts_dict:
        shapes["max_position_embeddings"] = flat_artifacts_dict["n_positions"]

    # image input
    if "num_channels" in flat_artifacts_dict:
        shapes["num_channels"] = flat_artifacts_dict.get("channels", None)

    if "image_size" in flat_artifacts_dict:
        image_size = flat_artifacts_dict["image_size"]
    elif "size" in flat_artifacts_dict:
        image_size = flat_artifacts_dict["size"]
    else:
        image_size = None

    if isinstance(image_size, (int, float)):
        shapes["height"] = image_size
        shapes["width"] = image_size
    elif isinstance(image_size, (list, tuple)):
        shapes["height"] = image_size[0]
        shapes["width"] = image_size[0]
    elif isinstance(image_size, dict) and len(image_size) == 2:
        shapes["height"] = list(image_size.values())[0]
        shapes["width"] = list(image_size.values())[1]
    elif isinstance(image_size, dict) and len(image_size) == 1:
        shapes["height"] = list(image_size.values())[0]
        shapes["width"] = list(image_size.values())[0]

    if "input_size" in flat_artifacts_dict:
        input_size = flat_artifacts_dict["input_size"]
        shapes["num_channels"] = input_size[0]
        shapes["height"] = input_size[1]
        shapes["width"] = input_size[2]

    # classification labels
    if "id2label" in flat_artifacts_dict:
        id2label = flat_artifacts_dict["id2label"]
        shapes["num_labels"] = len(id2label)
    elif "num_classes" in flat_artifacts_dict:
        shapes["num_labels"] = flat_artifacts_dict["num_classes"]

    # object detection labels
    if "num_queries" in flat_artifacts_dict:
        shapes["num_queries"] = flat_artifacts_dict["num_queries"]

    # image-text input
    if "image_token_id" in flat_artifacts_dict:
        shapes["image_token_id"] = flat_artifacts_dict["image_token_id"]
    if "in_chans" in flat_artifacts_dict:
        shapes["num_channels"] = flat_artifacts_dict["in_chans"]
    if "patch_size" in flat_artifacts_dict:
        shapes["patch_size"] = flat_artifacts_dict["patch_size"]
    if "temporal_patch_size" in flat_artifacts_dict:
        shapes["temporal_patch_size"] = flat_artifacts_dict["temporal_patch_size"]
    if "spatial_merge_size" in flat_artifacts_dict:
        shapes["spatial_merge_size"] = flat_artifacts_dict["spatial_merge_size"]

    return shapes


def get_transformers_automodel_loader_for_task(task: str):
    model_loader_name = TASKS_TO_MODEL_LOADERS[task]
    model_loader_class = getattr(transformers, model_loader_name)
    return model_loader_class


TORCH_INIT_FUNCTIONS = {
    "normal_": torch.nn.init.normal_,
    "uniform_": torch.nn.init.uniform_,
    "trunc_normal_": torch.nn.init.trunc_normal_,
    "xavier_normal_": torch.nn.init.xavier_normal_,
    "xavier_uniform_": torch.nn.init.xavier_uniform_,
    "kaiming_normal_": torch.nn.init.kaiming_normal_,
    "kaiming_uniform_": torch.nn.init.kaiming_uniform_,
    "normal": torch.nn.init.normal,
    "uniform": torch.nn.init.uniform,
    "xavier_normal": torch.nn.init.xavier_normal,
    "xavier_uniform": torch.nn.init.xavier_uniform,
    "kaiming_normal": torch.nn.init.kaiming_normal,
    "kaiming_uniform": torch.nn.init.kaiming_uniform,
}


def fast_random_tensor(tensor: torch.Tensor, *args: Any, **kwargs: Any) -> torch.Tensor:
    return torch.nn.init.uniform_(tensor)


@contextmanager
def fast_weights_init():
    # Replace the initialization functions
    for name, init_func in TORCH_INIT_FUNCTIONS.items():
        if name != "uniform_":  # avoid recursion
            setattr(torch.nn.init, name, fast_random_tensor)
    try:
        yield
    finally:
        # Restore the original initialization functions
        for name, init_func in TORCH_INIT_FUNCTIONS.items():
            if name != "uniform_":  # avoid recursion
                setattr(torch.nn.init, name, init_func)
