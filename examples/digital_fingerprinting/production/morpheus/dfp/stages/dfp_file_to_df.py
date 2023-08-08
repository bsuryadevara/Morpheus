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
"""Stage for converting fsspec file objects to a DataFrame."""

import logging
import typing

import mrc
import pandas as pd
from mrc.core import operators as ops

from morpheus.common import FileTypes
from morpheus.config import Config
from morpheus.pipeline.preallocator_mixin import PreallocatorMixin
from morpheus.pipeline.single_port_stage import SinglePortStage
from morpheus.pipeline.stream_pair import StreamPair
from morpheus.utils.column_info import DataFrameInputSchema
from morpheus.utils.controllers.file_to_df_controller import FileToDFController

logger = logging.getLogger(f"morpheus.{__name__}")


class DFPFileToDataFrameStage(PreallocatorMixin, SinglePortStage):
    """
    Stage for converting fsspec file objects to a DataFrame, pre-processing the DataFrame according to `schema`, and
    caching fetched file objects. The file objects are fetched in parallel using `morpheus.utils.downloader.Downloader`,
    which supports multiple download methods indicated by the `MORPHEUS_FILE_DOWNLOAD_TYPE` environment variable.

    Refer to `morpheus.utils.downloader.Downloader` for more information on the supported download methods.

    Parameters
    ----------
    c : `morpheus.config.Config`
        Pipeline configuration instance.
    schema : `morpheus.utils.column_info.DataFrameInputSchema`
        Input schema for the DataFrame.
    filter_null : bool, optional
        Whether to filter null values from the DataFrame.
    file_type : `morpheus.common.FileTypes`, optional
        File type of the input files. If `FileTypes.Auto`, the file type will be inferred from the file extension.
    parser_kwargs : dict, optional
        Keyword arguments to pass to the DataFrame parser.
    cache_dir : str, optional
        Directory to use for caching.
    """

    def __init__(self,
                 c: Config,
                 schema: DataFrameInputSchema,
                 filter_null: bool = True,
                 file_type: FileTypes = FileTypes.Auto,
                 parser_kwargs: dict = None,
                 cache_dir: str = "./.cache/dfp"):
        super().__init__(c)

        timestamp_column_name = c.ae.timestamp_column_name
        self._controller = FileToDFController(schema=schema,
                                              filter_null=filter_null,
                                              file_type=file_type,
                                              parser_kwargs=parser_kwargs,
                                              cache_dir=cache_dir,
                                              timestamp_column_name=timestamp_column_name)

    @property
    def name(self) -> str:
        """Stage name."""
        return "dfp-s3-to-df"

    def supports_cpp_node(self):
        """Whether this stage supports a C++ node."""
        return False

    def accepted_types(self) -> typing.Tuple:
        """Accepted input types."""
        return (typing.Any, )

    def _build_single(self, builder: mrc.Builder, input_stream: StreamPair) -> StreamPair:
        stream = builder.make_node(self.unique_name,
                                   ops.map(self._controller.convert_to_dataframe),
                                   ops.on_completed(self._controller.close))
        builder.make_edge(input_stream[0], stream)

        return stream, pd.DataFrame
