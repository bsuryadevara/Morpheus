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

import click
import yaml

from morpheus.config import Config
from morpheus.config import CppConfig
from morpheus.config import PipelineModes
from morpheus.pipeline.linear_pipeline import LinearPipeline
from morpheus.stages.general.monitor_stage import MonitorStage
from morpheus.stages.inference.triton_inference_stage import TritonInferenceStage
from morpheus.stages.input.kafka_source_stage import KafkaSourceStage
from morpheus.stages.output.write_to_kafka_stage import WriteToKafkaStage
from morpheus.stages.postprocess.add_scores_stage import AddScoresStage
from morpheus.stages.postprocess.serialize_stage import SerializeStage
from morpheus.utils.logger import configure_logging
from stages.create_features import CreateFeaturesRWStage
from stages.preprocessing import PreprocessingRWStage
from stages.appshield_partitioner import AppshieldPartitionerStage


@click.command()
@click.option('--debug', default=False)
@click.option('--use_cpp', default=False)
@click.option(
    "--num_threads",
    default=os.cpu_count(),
    type=click.IntRange(min=1),
    help="Number of internal pipeline threads to use.",
)
@click.option(
    "--n_dask_workers",
    default=6,
    type=click.IntRange(min=1),
    help="Number of dask workers.",
)
@click.option(
    "--threads_per_dask_worker",
    default=2,
    type=click.IntRange(min=1),
    help="Number of threads per each dask worker.",
)
@click.option(
    "--model_max_batch_size",
    default=1024,
    type=click.IntRange(min=1),
    help="Max batch size to use for the model.",
)
@click.option(
    "--pipeline_batch_size",
    default=10000,
    type=click.IntRange(min=1),
    help="Max batch size to use for the model.",
)
@click.option(
    "--conf_file",
    type=click.STRING,
    default="./config/ransomware_detection_streaming.yaml",
    help="Ransomware detection configuration filepath.",
)
@click.option(
    "--model_name",
    default="ransomw-model-short-rf",
    help="The name of the model that is deployed on Tritonserver.",
)
@click.option("--server_url", required=True, help="Tritonserver url.")
@click.option(
    "--sliding_window",
    default=3,
    type=click.IntRange(min=3),
    help="Sliding window to be used for model input request.",
)
@click.option('--input_topic', type=click.STRING, required=True, help=("Input Kafka topic"))
@click.option('--bootstrap_servers', type=click.STRING, default="localhost:9092", help=("bootstrap servers uri"))
@click.option(
    "--output_topic",
    type=click.STRING,
    help="Output Kafka topic",
)
def run_pipeline(debug,
                 use_cpp,
                 num_threads,
                 n_dask_workers,
                 threads_per_dask_worker,
                 model_max_batch_size,
                 pipeline_batch_size,
                 conf_file,
                 model_name,
                 server_url,
                 sliding_window,
                 input_topic,
                 bootstrap_servers,
                 output_topic):

    if debug:
        configure_logging(log_level=logging.DEBUG)
    else:
        configure_logging(log_level=logging.INFO)

    snapshot_fea_length = 99

    CppConfig.set_should_use_cpp(use_cpp)

    # Its necessary to get the global config object and configure it for FIL mode.
    config = Config()
    config.mode = PipelineModes.FIL

    # Below properties are specified by the command line.
    config.num_threads = num_threads
    config.model_max_batch_size = model_max_batch_size
    config.pipeline_batch_size = pipeline_batch_size
    config.feature_length = snapshot_fea_length * sliding_window
    config.class_labels = ["pred", "score"]

    # Create a linear pipeline object
    pipeline = LinearPipeline(config)

    # Load ransomware detection configuration.
    rwd_conf = load_yaml(conf_file)

    # Only intrested plugins files will be read from Appshield snapshots.
    interested_plugins = rwd_conf["intrested_plugins"]

    # Columns from the above intrested plugins.
    plugins_schema = rwd_conf['plugins_schema']

    # Columns from the above intrested plugins.
    cols_interested_plugins = rwd_conf['raw_columns']

    # Feature columns used by the model.
    feature_columns = rwd_conf['model_features']

    # File extensions.
    file_extns = rwd_conf['file_extensions']

    # Set source stage.
    # This stage reads raw data from the required plugins and merge all the plugins data into a single dataframe
    # for a given source.
    pipeline.set_source(KafkaSourceStage(config, bootstrap_servers=bootstrap_servers, input_topic=input_topic))

    # Add a monitor stage.
    # This stage logs the metrics (msg/sec) from the above stage.
    pipeline.add_stage(MonitorStage(config, description="FromKafka rate"))

    pipeline.add_stage(AppshieldPartitionerStage(config, interested_plugins, cols_interested_plugins, plugins_schema))

    pipeline.add_stage(MonitorStage(config, description="AppShield Partitioner rate"))

    # Add a create features stage.
    # This stage generates model feature values from the raw data.
    pipeline.add_stage(
        CreateFeaturesRWStage(config,
                              interested_plugins,
                              feature_columns,
                              file_extns,
                              n_workers=n_dask_workers,
                              threads_per_worker=threads_per_dask_worker))

    # Add a monitor stage.
    # This stage logs the metrics (msg/sec) from the above stage.
    pipeline.add_stage(MonitorStage(config, description="CreateFeatures rate"))

    # Add preprocessing stage.
    # This stage generates snapshot sequences using sliding window for each pid_process.
    pipeline.add_stage(PreprocessingRWStage(config, feature_columns=feature_columns[:-1],
                                            sliding_window=sliding_window))

    # Add a monitor stage
    # This stage logs the metrics (msg/sec) from the above stage.
    pipeline.add_stage(MonitorStage(config, description="PreProcessing rate"))

    # Add a inference stage.
    # This stage sends inference requests to the Tritonserver and captures the response.
    pipeline.add_stage(
        TritonInferenceStage(
            config,
            model_name=model_name,
            server_url=server_url,
            force_convert_inputs=True,
        ))

    # Add a monitor stage.
    # This stage logs the metrics (msg/sec) from the above stage.
    pipeline.add_stage(MonitorStage(config, description="Inference rate"))

    # Add a add scores stage.
    # This stage adds probability scores to each message.
    pipeline.add_stage(AddScoresStage(config, labels=["score"]))

    # Add a monitor stage.
    # This stage logs the metrics (msg/sec) from the above stage.
    pipeline.add_stage(MonitorStage(config, description="AddScore rate"))

    # Add a serialize stage.
    # This stage includes & excludes columns from messages.
    pipeline.add_stage(SerializeStage(config, exclude=[r'^ID$', r'^_ts_', r'source_pid_process']))

    # Add a monitor stage.
    # This stage logs the metrics (msg/sec) from the above stage.
    pipeline.add_stage(MonitorStage(config, description="Serialize rate"))

    # Add a write file stage.
    # This stage writes all messages to a kafka topic.
    pipeline.add_stage(WriteToKafkaStage(config, bootstrap_servers=bootstrap_servers, output_topic=output_topic))

    # Add a monitor stage.
    # This stage logs the metrics (msg/sec) from the above stage.
    pipeline.add_stage(MonitorStage(config, description="ToKafka rate"))

    # Run the pipeline.
    pipeline.run()


def load_yaml(filepath: str) -> typing.Dict[object, object]:
    """
    This function loads yaml configuration to a dictionary

    Parameters
        ----------
        filepath : str
            A file's path

        Returns
        -------
        typing.Dict[object, object]
            Configuration as a dictionary
    """
    with open(filepath, 'r', encoding='utf8') as f:
        conf_dct = yaml.safe_load(f)
        f.close()

    return conf_dct


# Execution starts here
if __name__ == "__main__":
    run_pipeline()
