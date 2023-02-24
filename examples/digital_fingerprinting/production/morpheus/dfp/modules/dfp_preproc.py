# Copyright (c) 2023, NVIDIA CORPORATION.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

import dfp.modules.dfp_split_users  # noqa: F401
import mrc

import morpheus._lib.modules  # noqa: F401
import morpheus.loaders.file_to_df_loader  # noqa: F401
import morpheus.modules.file_batcher  # noqa: F401
import morpheus.modules.file_to_df  # noqa: F401
from morpheus.utils.module_ids import DATA_LOADER
from morpheus.utils.module_ids import FILE_BATCHER
from morpheus.utils.module_ids import MODULE_NAMESPACE
from morpheus.utils.module_utils import get_module_config
from morpheus.utils.module_utils import load_module
from morpheus.utils.module_utils import register_module

from ..utils.module_ids import DFP_PREPROC
from ..utils.module_ids import DFP_SPLIT_USERS

logger = logging.getLogger("morpheus.{}".format(__name__))


@register_module(DFP_PREPROC, MODULE_NAMESPACE)
def dfp_preproc(builder: mrc.Builder):
    """
    This module function allows for the consolidation of multiple dfp pipeline modules relevent to inference/training
    process into a single module.

    Parameters
    ----------
    builder : mrc.Builder
        Pipeline budler instance.
    """

    config = get_module_config(DFP_PREPROC, builder)

    file_batcher_conf = config.get(FILE_BATCHER, None)
    data_loader_conf = config.get(DATA_LOADER, None)
    dfp_split_users_conf = config.get(DFP_SPLIT_USERS, None)

    # Load modules
    file_batcher_module = load_module(file_batcher_conf, builder=builder)
    data_loader_module = load_module(data_loader_conf, builder=builder)
    dfp_split_users_module = load_module(dfp_split_users_conf, builder=builder)

    # Make an edge between the modules.
    builder.make_edge(file_batcher_module.output_port("output"), data_loader_module.input_port("input"))
    builder.make_edge(data_loader_module.output_port("output"), dfp_split_users_module.input_port("input"))

    # Register input and output port for a module.
    builder.register_module_input("input", file_batcher_module.input_port("input"))
    builder.register_module_output("output", dfp_split_users_module.output_port("output"))
