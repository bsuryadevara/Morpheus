# SPDX-FileCopyrightText: Copyright (c) 2022-2023, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import typing

import mrc

import morpheus._lib.stages as _stages
from morpheus.cli.register_stage import register_stage
from morpheus.config import Config
from morpheus.config import PipelineModes
from morpheus.messages import ControlMessage
from morpheus.messages import MessageMeta
from morpheus.messages import MultiMessage
from morpheus.modules.preprocess.deserialize import DeserializeInterface
from morpheus.pipeline.multi_message_stage import MultiMessageStage
from morpheus.pipeline.stage_schema import StageSchema

logger = logging.getLogger(__name__)


@register_stage("deserialize",
                modes=[PipelineModes.FIL, PipelineModes.NLP, PipelineModes.OTHER],
                ignore_args=["message_type", "task_type", "task_payload"])
class DeserializeStage(MultiMessageStage):
    """
    Messages are logically partitioned based on the pipeline config's `pipeline_batch_size` parameter.

    This stage deserialize the output of `FileSourceStage`/`KafkaSourceStage` into a `MultiMessage`. This
    should be one of the first stages after the `Source` object.

    Parameters
    ----------
    c : `morpheus.config.Config`
        Pipeline configuration instance.

    """

    def __init__(self,
                 c: Config,
                 *,
                 ensure_sliceable_index: bool = True,
                 message_type: typing.Literal[MultiMessage, ControlMessage] = MultiMessage,
                 task_type: str = None,
                 task_payload: dict = None):
        super().__init__(c)

        self._batch_size = c.pipeline_batch_size
        self._ensure_sliceable_index = ensure_sliceable_index

        self._max_concurrent = c.num_threads

        # Mark these stages to log timestamps if requested
        self._should_log_timestamps = True

        self._message_type = message_type
        self._task_type = task_type
        self._task_payload = task_payload

        if (self._message_type == ControlMessage):

            if ((self._task_type is None) != (self._task_payload is None)):
                raise ValueError("Both `task_type` and `task_payload` must be specified if either is specified.")
        else:
            if (self._task_type is not None or self._task_payload is not None):
                raise ValueError("Cannot specify `task_type` or `task_payload` for non-control messages.")

        self._module_config = {
            "ensure_sliceable_index": self._ensure_sliceable_index,
            "message_type": "MultiMessage" if self._message_type == MultiMessage else "ControlMessage",
            "task_type": self._task_type,
            "task_payload": self._task_payload,
            "batch_size": self._batch_size,
            "max_concurrency": self._max_concurrent,
            "should_log_timestamp": self._should_log_timestamps
        }

    @property
    def name(self) -> str:
        return "deserialize"

    def accepted_types(self) -> typing.Tuple:
        """
        Returns accepted input types for this stage.

        """
        return (MessageMeta, )

    def supports_cpp_node(self):
        # Enable support by default
        return True

    def compute_schema(self, schema: StageSchema):
        schema.output_schema.set_type(self._message_type)

    def _build_single(self, builder: mrc.Builder, input_node: mrc.SegmentObject) -> mrc.SegmentObject:
        # TODO(Devin)
        if self._build_cpp_node:
            out_node = _stages.DeserializeStage(builder, self.unique_name, self._batch_size)
            builder.make_edge(input_node, out_node)
        else:
            module_instance = DeserializeInterface.get_definition(module_name=f"deserialize_{self.unique_name}",
                                                                  module_config=self._module_config)

            module = module_instance.load(builder)

            mod_in_node = module.input_port("input")
            out_node = module.output_port("output")

            builder.make_edge(input_node, mod_in_node)

        return out_node
