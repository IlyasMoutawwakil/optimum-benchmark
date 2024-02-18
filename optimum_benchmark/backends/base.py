import gc
import random
from abc import ABC
from logging import getLogger
from collections import OrderedDict
from typing import Optional, ClassVar, Generic, Dict, Any

from .config import BackendConfigT
from ..task_utils import get_automodel_class_for_task
from .diffusers_utils import extract_diffusers_shapes_from_config, get_diffusers_pretrained_config
from .timm_utils import extract_timm_shapes_from_config, get_timm_pretrained_config, get_timm_pre_processor
from .transformers_utils import (
    extract_transformers_shapes_from_artifacts,
    get_transformers_generation_config,
    get_transformers_pretrained_config,
    get_transformers_pre_processor,
    PretrainedProcessor,
)

import numpy as np
from transformers import GenerationConfig, PretrainedConfig, PreTrainedModel, TrainerState

LOGGER = getLogger("backend")


class Backend(Generic[BackendConfigT], ABC):
    NAME: ClassVar[str]

    model_type: str
    model_shapes: Dict[str, int]

    pretrained_model: PreTrainedModel
    pretrained_config: Optional[PretrainedConfig]
    generation_config: Optional[GenerationConfig]
    pre_processor: Optional[PretrainedProcessor]

    def __init__(self, config: BackendConfigT):
        LOGGER.info(f"َAllocating {self.NAME} backend")
        self.config = config
        self.seed()

        if self.config.library == "diffusers":
            self.pretrained_config = get_diffusers_pretrained_config(self.config.model, **self.config.hub_kwargs)
            self.model_shapes = extract_diffusers_shapes_from_config(self.config.model, **self.config.hub_kwargs)
            self.model_type = self.config.task
            self.generation_config = None
            self.pre_processor = None

        elif self.config.library == "timm":
            self.pre_processor = get_timm_pre_processor(self.config.model)
            self.pretrained_config = get_timm_pretrained_config(self.config.model)
            self.model_shapes = extract_timm_shapes_from_config(config=self.pretrained_config)
            self.model_type = self.pretrained_config.architecture
            self.generation_config = None

        else:
            self.pre_processor = get_transformers_pre_processor(self.config.model, **self.config.hub_kwargs)
            self.generation_config = get_transformers_generation_config(self.config.model, **self.config.hub_kwargs)
            self.pretrained_config = get_transformers_pretrained_config(self.config.model, **self.config.hub_kwargs)
            self.model_shapes = extract_transformers_shapes_from_artifacts(self.pretrained_config, self.pre_processor)
            self.model_type = self.pretrained_config.model_type

        self.automodel_class = get_automodel_class_for_task(
            model_type=self.model_type,
            library=self.config.library,
            task=self.config.task,
            framework="pt",
        )

    def seed(self) -> None:
        LOGGER.info(f"\t+ Setting random seed to {self.config.seed}")
        random.seed(self.config.seed)
        np.random.seed(self.config.seed)

    def prepare_for_inference(self, **kwargs) -> None:
        """
        This method is used to prepare the model for inference.
        It can be used to compile the model with certain input/output shapes, for example.
        """
        pass

    def prepare_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        This method is used to prepare the inputs before passing them to the model.
        It can be used to move the inputs to the correct device, for example.
        """
        return inputs

    def forward(self, inputs: Dict[str, Any], kwargs: Dict[str, Any]) -> OrderedDict:
        """
        This method is used to perform the forward pass of the model.
        """
        raise NotImplementedError("Backend must implement forward method")

    def generate(self, inputs: Dict[str, Any], kwargs: Dict[str, Any]) -> OrderedDict:
        """
        This method is used to perform the generation pass of the model.
        """
        raise NotImplementedError("Backend must implement generate method")

    def call(self, inputs: Dict[str, Any], kwargs: Dict[str, Any]) -> OrderedDict:
        """
        This method is used to call a whole pipeline.
        """
        raise NotImplementedError("Backend must implement call method")

    def train(self, **kwargs) -> TrainerState:
        """
        This method is used to train the model.
        """
        raise NotImplementedError("Backend must implement train method")

    def delete_pretrained_model(self) -> None:
        if hasattr(self, "pretrained_model"):
            del self.pretrained_model

    def clean(self) -> None:
        LOGGER.info(f"Cleaning {self.NAME} backend")
        self.delete_pretrained_model()
        gc.collect()
