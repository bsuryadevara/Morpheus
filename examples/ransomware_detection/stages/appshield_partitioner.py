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

import typing
from morpheus.messages.message_meta import AppShieldMessageMeta

import mrc

from mrc.core import operators as ops
import pandas as pd
import json
from morpheus.cli.register_stage import register_stage
from morpheus.config import Config
from morpheus.config import PipelineModes
from morpheus.messages import MessageMeta
from morpheus.pipeline.multi_message_stage import MultiMessageStage
from morpheus.pipeline.stream_pair import StreamPair


@register_stage("appshield-partitioner", modes=[PipelineModes.FIL])
class AppshieldPartitionerStage(MultiMessageStage):
    """
    This class extends MultiMessageStage to deal with scenario specific features from Appshiled plugins data.

    Parameters
    ----------
    c : morpheus.config.Config
        Pipeline configuration instance
    interested_plugins : typing.List[str]
        Only intrested plugins files will be read from Appshield snapshots
    feature_columns : typing.List[str]
        List of features needed to be extracted.
    file_extns : typing.List[str]
        File extensions.
    n_workers: int, default = 2
        Number of dask workers.
    threads_per_worker: int, default = 2
        Number of threads for each dask worker.
    """

    def __init__(self,
                 c: Config,
                 interested_plugins: typing.List[str],
                 cols_include: typing.List[str],
                 plugins_schema: typing.Dict[str, any]):
        super().__init__(c)

        self._interested_plugins = interested_plugins
        self._cols_include = cols_include
        self._plugins_schema = plugins_schema

    @property
    def name(self) -> str:
        return "appshield-partitioner"

    def accepted_types(self) -> typing.Tuple:
        """
        Returns accepted input types for this stage.
        """
        return (MessageMeta, )

    def supports_cpp_node(self):
        return False

    @staticmethod
    def fill_interested_cols(plugin_df: pd.DataFrame, cols_include: typing.List[str]):

        cols_exists = plugin_df.columns
        for col in cols_include:
            if col not in cols_exists:
                plugin_df[col] = None
        plugin_df = plugin_df[cols_include]

        return plugin_df

    def _build_single(self, builder: mrc.Builder, input_stream: StreamPair) -> StreamPair:

        stream = input_stream[0]

        def node_fn(input: mrc.Observable, output: mrc.Subscriber):

            def filter_by_plugin(x: MessageMeta):
                df = x.df

                df["plugin"] = df['raw'].str.extract('("type_name":"([^"]+)")')[1]

                df_per_plugin = {}
                for intrested_plugin in self._interested_plugins:
                    plugin = self._plugins_schema[intrested_plugin]["name"]
                    plugin_df = df[df.plugin == plugin]
                    if not plugin_df.empty:
                        df_per_plugin[intrested_plugin] = plugin_df

                return df_per_plugin

            def extract_data(df_per_plugin: typing.Dict[str, pd.DataFrame]):

                plugin_dfs = []

                for plugin in df_per_plugin.keys():
                    plugin_df = df_per_plugin[plugin]
                    cols_rename_dict = self._plugins_schema[plugin]["column_mapping"]
                    plugin_df['raw'] = plugin_df.raw.str.replace('\\', '-')
                    plugin_df = plugin_df['raw'].apply(json.loads).apply(pd.Series)
                    plugin_df = plugin_df.rename(columns=cols_rename_dict)
                    plugin_df = AppshieldPartitionerStage.fill_interested_cols(plugin_df=plugin_df,
                                                                               cols_include=self._cols_include)
                    plugin_dfs.append(plugin_df)

                return plugin_dfs

            def batch_source_split(x: typing.List[pd.DataFrame]) -> typing.Dict[str, pd.DataFrame]:

                combined_df = pd.concat(x)

                # Get the sources in this DF
                unique_sources = combined_df["source"].unique()

                source_dfs = {}

                if len(unique_sources) > 1:
                    for source_name in unique_sources:
                        source_dfs[source_name] = combined_df[combined_df["source"] == source_name]
                else:
                    source_dfs[unique_sources[0]] = combined_df

                return source_dfs

            def build_metadata(x: typing.Dict[str, pd.DataFrame]):

                metas = []

                for source, df in x.items():

                    # Now make a AppShieldMessageMeta with the source name
                    meta = AppShieldMessageMeta(df, source)
                    metas.append(meta)

                return metas

            input.pipe(ops.map(filter_by_plugin),
                       ops.map(extract_data),
                       ops.map(batch_source_split),
                       ops.map(build_metadata),
                       ops.flatten()).subscribe(output)

        node = builder.make_node_full(self.unique_name, node_fn)
        builder.make_edge(stream, node)
        stream = node

        return stream, AppShieldMessageMeta
