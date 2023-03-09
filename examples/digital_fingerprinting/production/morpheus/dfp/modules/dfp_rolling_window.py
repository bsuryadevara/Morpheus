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
import os
import typing
from contextlib import contextmanager

import mrc
import pandas as pd
from dfp.utils.cached_user_window import CachedUserWindow
from dfp.utils.logging_timer import log_time
from mrc.core import operators as ops

import cudf

from morpheus.messages import MessageControl
from morpheus.messages import MessageMeta
from morpheus.utils.module_ids import MORPHEUS_MODULE_NAMESPACE
from morpheus.utils.module_utils import register_module

from ..utils.module_ids import DFP_ROLLING_WINDOW

logger = logging.getLogger("morpheus.{}".format(__name__))


@register_module(DFP_ROLLING_WINDOW, MORPHEUS_MODULE_NAMESPACE)
def dfp_rolling_window(builder: mrc.Builder):
    """
    This module function establishes a rolling window to maintain history.

    Parameters
    ----------
    builder : mrc.Builder
        Pipeline builder instance.

    Notes
    ----------
    Configurable parameters:
        - aggregation_span: The span of time to aggregate over
        - cache_dir: Directory to cache the rolling window data
        - cache_to_disk: Whether to cache the rolling window data to disk
        - timestamp_column_name: Name of the timestamp column
        - trigger_on_min_history: Minimum number of rows to trigger the rolling window
        - trigger_on_min_increment: Minimum number of rows to trigger the rolling window
    """

    config = builder.get_current_module_config()

    timestamp_column_name = config.get("timestamp_column_name", "timestamp")

    min_history = config.get("trigger_on_min_history", 1)
    min_increment = config.get("trigger_on_min_increment", 0)
    aggregation_span = config.get("aggregation_span", "360d")

    cache_to_disk = config.get("cache_to_disk", False)
    cache_dir = config.get("cache_dir", None)
    if (cache_dir is not None):
        cache_dir = os.path.join(cache_dir, "rolling-user-data")

    user_cache_map: typing.Dict[str, CachedUserWindow] = {}

    @contextmanager
    def get_user_cache(user_id: str):
        # Determine cache location
        cache_location = os.path.join(cache_dir, f"{user_id}.pkl") if cache_to_disk else None

        user_cache = user_cache_map.get(user_id, None)

        if (user_cache is None):
            user_cache = CachedUserWindow(user_id=user_id,
                                          cache_location=cache_location,
                                          timestamp_column=timestamp_column_name)

            user_cache_map[user_id] = user_cache

        yield user_cache

    def try_build_window(message: MessageMeta, user_id: str) -> typing.Union[MessageMeta, None]:
        with get_user_cache(user_id) as user_cache:

            # incoming_df = message.get_df()
            with message.mutable_dataframe() as dfm:
                incoming_df = dfm.to_pandas()

            # TODO(Devin): note cuDF does not support tz aware datetimes (?)
            incoming_df[timestamp_column_name] = pd.to_datetime(incoming_df[timestamp_column_name], utc=True)

            if (not user_cache.append_dataframe(incoming_df=incoming_df)):
                # Then our incoming dataframe wasnt even covered by the window. Generate warning
                logger.warning(("Incoming data preceeded existing history. "
                                "Consider deleting the rolling window cache and restarting."))
                return None

            if (cache_to_disk and cache_dir is not None):
                logger.debug("Saved rolling window cache for %s == %d items", user_id, user_cache.total_count)
                user_cache.save()

            # Exit early if we don't have enough data
            if (user_cache.count < min_history):
                logger.debug("Not enough data to train")
                return None

            # We have enough data, but has enough time since the last training taken place?
            if (user_cache.total_count - user_cache.last_train_count < min_increment):
                logger.debug("Elapsed time since last train is too short")
                return None

            # Obtain a dataframe spanning the aggregation window
            df_window = user_cache.get_spanning_df(max_history=aggregation_span)

            # Hash the incoming data rows to find a match
            incoming_hash = pd.util.hash_pandas_object(incoming_df.iloc[[0, -1]], index=False)

            # Find the index of the first and last row
            match = df_window[df_window["_row_hash"] == incoming_hash.iloc[0]]

            if (len(match) == 0):
                raise RuntimeError("Invalid rolling window")

            first_row_idx = match.index[0].item()
            last_row_idx = df_window[df_window["_row_hash"] == incoming_hash.iloc[-1]].index[-1].item()

            found_count = (last_row_idx - first_row_idx) + 1

            if (found_count != len(incoming_df)):
                raise RuntimeError(("Overlapping rolling history detected. "
                                    "Rolling history can only be used with non-overlapping batches"))

            # TODO(Devin): Optimize
            return MessageMeta(cudf.from_pandas(df_window))

    def on_data(control_message: MessageControl):

        payload = control_message.payload()
        user_id = control_message.get_metadata("user_id")

        # TODO(Devin): Require data type to be set
        if (control_message.has_metadata("data_type")):
            data_type = control_message.get_metadata("data_type")
        else:
            data_type = "streaming"

        # If we're an explicit training or inference task, then we don't need to do any rolling window logic
        if (data_type == "payload"):
            return control_message
        elif (data_type == "streaming"):
            with log_time(logger.debug) as log_info:
                result = try_build_window(payload, user_id)  # Return a MessageMeta

                if (result is not None):
                    log_info.set_log(
                        ("Rolling window complete for %s in {duration:0.2f} ms. "
                         "Input: %s rows from %s to %s. Output: %s rows from %s to %s"),
                        user_id,
                        len(payload.df),
                        payload.df[timestamp_column_name].min(),
                        payload.df[timestamp_column_name].max(),
                        result.count,
                        result.df[timestamp_column_name].min(),
                        result.df[timestamp_column_name].max(),
                    )
                else:
                    # Result is None indicates that we don't have enough data to build payload for the event
                    # CM is discarded here
                    log_info.disable()
                    return None

            # TODO (bhargav) Check if we need to pass control_message config to data_prep module.
            # If no config is passed there won't be any tasks to perform in the DataPrep stage.
            # TODO(Devin): requires a bit more thought, should be safe to re-use the control message here, but
            #  I'm not 100 percent sure

            control_message.payload(result)
            # Don't need this? control_message.set_metadata("user_id", user_id)
            # Update data type to payload and forward
            control_message.set_metadata("data_type", "payload")

            return control_message
        else:
            raise RuntimeError("Unknown data type")

    def node_fn(obs: mrc.Observable, sub: mrc.Subscriber):
        obs.pipe(ops.map(on_data), ops.filter(lambda x: x is not None)).subscribe(sub)

    node = builder.make_node_full(DFP_ROLLING_WINDOW, node_fn)

    builder.register_module_input("input", node)
    builder.register_module_output("output", node)
