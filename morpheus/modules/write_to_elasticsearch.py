import logging
from ssl import create_default_context

import mrc
import numpy as np
from morpheus.utils.module_ids import WRITE_TO_ELASTICSEARCH
from morpheus.utils.module_ids import MORPHEUS_MODULE_NAMESPACE
from elasticsearch import Elasticsearch
from elasticsearch.helpers import parallel_bulk
from morpheus.messages import MessageMeta
from morpheus.utils.module_utils import register_module
from mrc.core import operators as ops

logger = logging.getLogger("morpheus.{}".format(__name__))


@register_module(WRITE_TO_ELASTICSEARCH, MORPHEUS_MODULE_NAMESPACE)
def write_to_elasticsearch(builder: mrc.Builder):
    """
    This module reads input data stream, converts each row of data to a document format suitable for Elasticsearch,
    and writes the documents to the specified Elasticsearch index using the Elasticsearch bulk API.

    Parameters
    ----------
    builder : mrc.Builder
        An mrc Builder object.

    Notes
    -----
    Configurable Parameters:
        - index     (String): Elastic search index.
        - host      (String): Elastic search host.
        - port      (String): Elastic search port.
        - user      (String): Elastic search username.
        - password  (String): Elastic search password.
        - cacrt     (String): Elastic search ca certificate path.
        - scheme    (String): Elastic search schema.
    """

    config = builder.get_current_module_config()

    index = config.get("index", None)
    host = config.get("host", None)
    port = config.get("port", None)
    user = config.get("user", "")
    password = config.get("password", "")
    scheme = config.get("scheme", "http")
    cacrt = config.get("cacrt", "")

    hosts = [val.strip() for val in host.split(",")]

    kwargs = {"hosts": hosts, "http_auth": (user, password), "scheme": scheme, "port": port}

    if kwargs["scheme"] == "https":
        kwargs["ssl_context"] = create_default_context(cafile=cacrt)

    logger.debug(f"Creating Elasticsearch connection with configuration: {kwargs}")

    # Create ElasticSearch connection
    elasticsearch = Elasticsearch(**kwargs)

    logger.debug(f"Elasticsearch cluster info: {es.info}")
    logger.debug("Creating Elasticsearch connection... Done!")

    def isnan(val):
        return isinstance(val, float) and np.isnan(val)

    def node_fn(obs: mrc.Observable, sub: mrc.Subscriber):

        def on_data(message: MessageMeta):

            rows = message.df.to_pandas().to_dict('records')

            actions = []
            for row in rows:
                action = {"_index": index, "_source": {key: 0 if isnan(val) else val for key, val in row.items()}}
                actions.append(action)

            for okay, info in parallel_bulk(elasticsearch, actions=actions, raise_on_exception=False):
                if not okay:
                    logger.error("Error writing to ElasticSearch: %s", str(info))
                    sub.on_error(info)
            return message

        obs.pipe(ops.map(on_data)).subscribe(sub)

    node = builder.make_node(WRITE_TO_ELASTICSEARCH, mrc.core.operators.build(node_fn))

    # Register input and output port for a module.
    builder.register_module_input("input", node)
    builder.register_module_output("output", node)
