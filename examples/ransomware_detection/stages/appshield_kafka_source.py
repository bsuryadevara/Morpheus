# Copyright (c) 2021-2023, NVIDIA CORPORATION.
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

import pandas as pd

from morpheus.config import Config

from morpheus.messages import MessageMeta
from morpheus.stages.input.kafka_source_stage import AutoOffsetReset, KafkaSourceStage

logger = logging.getLogger(__name__)


class AppshieldKafkaSource(KafkaSourceStage):
    """
    Load apshield messages from a Kafka cluster.

    Parameters
    ----------
    c : `morpheus.config.Config`
        Pipeline configuration instance.
    bootstrap_servers : str
        Comma-separated list of bootstrap servers. If using Kafka created via `docker-compose`, this can be set to
        'auto' to automatically determine the cluster IPs and ports
    input_topic : str
        Input kafka topic.
    group_id : str
        Specifies the name of the consumer group a Kafka consumer belongs to.
    client_id : str, default = None
        An optional identifier of the consumer.
    poll_interval : str
        Seconds that elapse between polling Kafka for new messages. Follows the pandas interval format.
    disable_commit : bool, default = False
        Enabling this option will skip committing messages as they are pulled off the server. This is only useful for
        debugging, allowing the user to process the same messages multiple times.
    disable_pre_filtering : bool, default = False
        Enabling this option will skip pre-filtering of json messages. This is only useful when inputs are known to be
        valid json.
    auto_offset_reset : `AutoOffsetReset`, case_sensitive = False
        Sets the value for the configuration option 'auto.offset.reset'. See the kafka documentation for more
        information on the effects of each value."
    stop_after: int, default = 0
        Stops ingesting after emitting `stop_after` records (rows in the dataframe). Useful for testing. Disabled if `0`
    async_commits: bool, default = True
        Enable commits to be performed asynchronously. Ignored if `disable_commit` is `True`.
    """

    def __init__(self,
                 c: Config,
                 bootstrap_servers: str,
                 input_topic: str = "test_pcap",
                 group_id: str = "morpheus",
                 client_id: str = None,
                 poll_interval: str = "10millis",
                 disable_commit: bool = False,
                 disable_pre_filtering: bool = False,
                 auto_offset_reset: AutoOffsetReset = AutoOffsetReset.LATEST,
                 stop_after: int = 0,
                 async_commits: bool = True):
        super().__init__(c,
                         bootstrap_servers,
                         input_topic,
                         group_id,
                         client_id,
                         poll_interval,
                         disable_commit,
                         disable_pre_filtering,
                         auto_offset_reset,
                         stop_after,
                         async_commits)

    @property
    def name(self) -> str:
        return "from-appshield-kafka"

    def supports_cpp_node(self):
        return False

    def _process_batch(self, consumer, batch):
        message_meta = None
        if len(batch):
            messages = []

            for msg in batch:
                payload = msg.value()
                if payload is not None:
                    messages.append(payload.decode("utf-8"))

            try:
                message_df = pd.DataFrame()
                message_df["raw"] = messages

            except Exception as e:
                logger.error(f"Error parsing payload into a dataframe : {e}")
            finally:
                if (not self._disable_commit):
                    for msg in batch:
                        consumer.commit(message=msg, asynchronous=self._async_commits)

            if message_df is not None:
                num_records = len(message_df)
                message_meta = MessageMeta(message_df)
                self._records_emitted += num_records
                self._num_messages += 1

                if self._stop_after > 0 and self._records_emitted >= self._stop_after:
                    self._stop_requested = True

            batch.clear()

        return message_meta
