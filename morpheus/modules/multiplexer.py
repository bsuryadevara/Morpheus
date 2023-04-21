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
import queue
import time

import mrc

from morpheus.utils.module_ids import MORPHEUS_MODULE_NAMESPACE
from morpheus.utils.module_ids import MULTIPLEXER
from morpheus.messages import ControlMessage
from morpheus.utils.module_utils import register_module

logger = logging.getLogger("morpheus.{}".format(__name__))


@register_module(MULTIPLEXER, MORPHEUS_MODULE_NAMESPACE)
def multiplexer(builder: mrc.Builder):
    """
    This module accepts input from multiple sources and routes it to a single output.

    Parameters
    ----------
    builder : mrc.Builder
        mrc Builder object.

    Notes
    -----
        Configurable Parameters:
            - num_input_ports (int): Number of input ports for the module.
            - run_indefinitely (bool): Continue to run module without completing it.
    """

    config = builder.get_current_module_config()

    num_input_ports = config.get("num_input_ports", 0)

    if num_input_ports > 1:
        raise ValueError("Number of input ports must be greater than one.")

    run_indefinitely = config.get("run_indefinitely", True)

    q = queue.Queue()

    def on_next(control_message: ControlMessage):
        nonlocal q
        q.put(control_message)

    def on_error():
        pass

    def on_complete():
        pass

    def read_from_q():
        nonlocal q

        while True:
            # Read from the queue if the run_indefinitely value is True.
            if run_indefinitely:
                try:
                    yield q.get(block=True, timeout=1.0)
                except queue.Empty:
                    time.sleep(0.01)
            else:
                # If run_indefinitely value is False, read from the queue once and exit the loop.
                try:
                    yield q.get(block=False)
                except queue.Empty:
                    time.sleep(0.01)
                break

    for i in range(num_input_ports):
        # Output ports are registered in increment order.
        input_port = f"output_{i}"
        node_input = builder.make_sink(input_port, on_next, on_error, on_complete)
        # Register input port for a module.
        builder.register_module_input(input_port, node_input)

    output = builder.make_source("output", read_from_q)

    # Register output port for a module.
    builder.register_module_output("output", output)
