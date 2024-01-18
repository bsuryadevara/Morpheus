# Copyright (c) 2022-2023, NVIDIA CORPORATION.
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
from typing import Any
from typing import Dict
from typing import Optional

import mrc
import mrc.core.operators as ops
from pydantic import BaseModel
from pydantic import Field
from pydantic import ValidationError

from morpheus.messages import MessageMeta
from morpheus.utils.column_info import ColumnInfo
from morpheus.utils.column_info import DataFrameInputSchema
from morpheus.utils.column_info import RenameColumn
from morpheus.utils.module_utils import ModuleInterface
from morpheus.utils.module_utils import register_module
from morpheus.utils.nvt.schema_converters import create_and_attach_nvt_workflow
from morpheus.utils.schema_transforms import process_dataframe

logger = logging.getLogger(__name__)


class ColumnTransformConfig(BaseModel):
    dtype: str
    op_type: str
    from_: Optional[str] = Field(None, alias="from")


class SchemaTransformParamContract(BaseModel):
    schema_transform_config: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


@register_module("schema_transform", "morpheus_examples_llm")
def schema_transform(builder: mrc.Builder):
    """
    A module for applying simple DataFrame schema transform policies.

    This module reads the configuration to determine how to set data types for columns, select, or rename them in the dataframe.

    Parameters
    ----------
    builder : mrc.Builder
        The Morpheus pipeline builder object.

    Notes
    -------------
    The configuration should be passed to the module through the `module_config` attribute of the builder. It should
    contain a dictionary where each key is a column name, and the value is another dictionary with keys 'dtype' for
    data type, 'op_type' for operation type ('select' or 'rename'), and optionally 'from' for the original column
    name (if the column is to be renamed).

    Example Configuration
    ---------------------
    {
        "summary": {"dtype": "str", "op_type": "select"},
        "title": {"dtype": "str", "op_type": "select"},
        "content": {"from": "page_content", "dtype": "str", "op_type": "rename"},
        "source": {"from": "link", "dtype": "str", "op_type": "rename"}
    }
    """

    module_config = builder.get_current_module_config()

    # Validate the module configuration using the contract
    try:
        validated_config = SchemaTransformParamContract(**module_config)
    except ValidationError as e:
        error_messages = '; '.join([f"{error['loc'][0]}: {error['msg']}" for error in e.errors()])
        log_error_message = f"Invalid schema transform configuration: {error_messages}"
        logger.error(log_error_message)
        raise ValueError(log_error_message)

    schema_config = validated_config.schema_transform_config

    source_column_info = []

    for col_name, col_config in schema_config.items():
        op_type = col_config.get("op_type")
        if (op_type == "rename"):
            # Handling renamed columns
            source_column_info.append(
                RenameColumn(name=col_name, dtype=col_config["dtype"], input_name=col_config["from"]))
        elif (op_type == "select"):
            # Handling regular columns
            source_column_info.append(ColumnInfo(name=col_name, dtype=col_config["dtype"]))
        else:
            raise ValueError(f"Unknown op_type '{op_type}' for column '{col_name}'")

    source_schema = DataFrameInputSchema(column_info=source_column_info)
    source_schema = create_and_attach_nvt_workflow(input_schema=source_schema)

    def do_transform(message: MessageMeta):
        with message.mutable_dataframe() as mdf:
            _df = process_dataframe(mdf, source_schema)

        return MessageMeta(df=_df)

    node = builder.make_node("schema_transform", ops.map(do_transform))

    builder.register_module_input("input", node)
    builder.register_module_output("output", node)


SchemaTransformInterface = ModuleInterface("schema_transform", "morpheus_examples_llm", SchemaTransformParamContract)
