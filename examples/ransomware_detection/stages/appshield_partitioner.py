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

    def __init__(self,
                 c: Config,
                 interested_plugins: typing.List[str],
                 cols_include: typing.List[str],
                 plugins_schema: typing.Dict[str, any]):
        super().__init__(c)

        self._interested_plugins = interested_plugins
        self._cols_include = cols_include
        self._plugins_schema = plugins_schema
        self._data_dict = {}

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

    def _check_multiple_snapshots(self):
        multiple_snapshots = {}
        for source_name, source_dict in self._data_dict.items():
            if len(source_dict) > 1:
                for snapshot_name in source_dict.keys():
                    multiple_snapshots.setdefault(source_name, []).append(snapshot_name)
        return multiple_snapshots

    def _add_data(self, source_name, snapshot_name, plugin_name, df):
        if source_name not in self._data_dict:
            self._data_dict[source_name] = {}
        source = self._data_dict[source_name]

        if snapshot_name not in source:
            source[snapshot_name] = {}
        snapshot = source[snapshot_name]

        if plugin_name not in snapshot:
            snapshot[plugin_name] = df
        else:
            snapshot[plugin_name] = pd.concat([snapshot[plugin_name], df])

    def _get_source_dfs(self, multiple_snapshots):
        source_dfs = {}

        for source in multiple_snapshots.keys():
            plugin_dfs = []

            max_snapshot_id = max(multiple_snapshots[source])
            snapshot_ids = [x for x in multiple_snapshots[source] if x != max_snapshot_id]

            for snapshot_id in snapshot_ids:
                plugin_df_dict = self._data_dict[source][snapshot_id]

                for plugin_name in plugin_df_dict.keys():
                    plugin_df = AppshieldPartitionerStage.fill_interested_cols(plugin_df=plugin_df_dict[plugin_name],
                                                                               cols_include=self._cols_include)
                    plugin_dfs.append(plugin_df)

                # Add fully recieved snapshot to processing list and removing from in memory
                del self._data_dict[source][snapshot_id]

            if plugin_dfs:
                source_dfs[source] = pd.concat(plugin_dfs, ignore_index=True)

        return source_dfs

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
                df["source"] = df['raw'].str.extract('("source":"([^"]+)")')[1]
                df["snapshot_id"] = df['raw'].str.extract('("scan_id":([^"]+),)')[1].astype(int)

                unique_sources = df.source.unique()
                unique_snapshot_ids = df.snapshot_id.unique()

                for source in unique_sources:
                    for snapshot_id in unique_snapshot_ids:
                        for intrested_plugin in self._interested_plugins:
                            plugin = self._plugins_schema[intrested_plugin]["name"]
                            plugin_df = df[(df.plugin == plugin) & (df.source == source) &
                                           (df.snapshot_id == snapshot_id)]
                            if not plugin_df.empty:

                                cols_rename_dict = self._plugins_schema[intrested_plugin]["column_mapping"]

                                plugin_df['raw'] = plugin_df.raw.str.replace('\\', '-')
                                plugin_df = plugin_df['raw'].apply(json.loads).apply(pd.Series)
                                plugin_df = plugin_df.rename(columns=cols_rename_dict)
                                self._add_data(source, snapshot_id, intrested_plugin, plugin_df)

                multiple_snapshots = self._check_multiple_snapshots()

                source_dfs = self._get_source_dfs(multiple_snapshots)

                return source_dfs

            def build_metadata(x: typing.Dict[str, pd.DataFrame]):

                metas = []

                for source, df in x.items():

                    # Now make a AppShieldMessageMeta with the source name
                    meta = AppShieldMessageMeta(df, source)
                    metas.append(meta)

                return metas

            input.pipe(ops.map(filter_by_plugin), ops.map(build_metadata), ops.flatten()).subscribe(output)

        node = builder.make_node_full(self.unique_name, node_fn)
        builder.make_edge(stream, node)
        stream = node

        return stream, AppShieldMessageMeta
