#!/usr/bin/python
import argparse
import collections
import logging
import pprint
import sys

import settings
import benchmarkfactory
from cluster.ceph import Ceph
from log_support import setup_loggers
from db import DB

logger = logging.getLogger("cbt")


def parse_args(args):
    parser = argparse.ArgumentParser(description='Continuously run ceph tests.')
    parser.add_argument(
        '-a', '--archive',
        required=True,
        help='Directory where the results should be archived.',
        )

    parser.add_argument(
        '-r', '--rebuild',
        required=False,
        action='store_true',
        default=False,
        help='Rebuild the results archive database.',
        )

    parser.add_argument(
        '-q', '--query',
        required=False,
        help='query the results archive using SQL.',
        )

    parser.add_argument(
        '-f', '--format',
        required=False,
        help='The query results format.',
        choices=['json', 'csv', 'raw'],
        default='csv',
        )

    parser.add_argument(
        '-c', '--conf',
        required=False,
        help='The ceph.conf file to use.',
        )

    parser.add_argument(
        'config_files',
        nargs='*',
        help='YAML config file(s).',
        )

    return parser.parse_args(args[1:])

def shutdown(message):
    sys.exit(message)

def rebuild():
    db = DB(True)
    db.close()
    return 0

def query(q):
    db = DB(False)
    db.query(q)
    db.close()
    return 0

def runtests(settings):
    if not settings.cluster:
        shutdown('No cluster settings found. Did you include a yaml file?')

    if not settings.benchmarks:
        shutdown('No benchmark settings found. Did you include a yaml file?')

    iteration = 0
    logger.debug("Settings.general:\n    %s",
                 pprint.pformat(settings.general).replace("\n", "\n    "))
    logger.debug("Settings.cluster:\n    %s",
                 pprint.pformat(settings.cluster).replace("\n", "\n    "))

    global_init = collections.OrderedDict()

    # FIXME: Create ClusterFactory and parametrically match benchmarks and clusters.
    cluster = Ceph(settings.cluster)

    # E_OK
    return_code = 0

    try:
        for iteration in range(settings.general.get("iterations", 0)):
            benchmarks = benchmarkfactory.get_all(cluster, iteration)
            for b in benchmarks:
                if b.exists():
                    continue

                # Tell the benchmark to initialize unless it's in the skip list.
                if b.getclass() not in global_init:
                    b.initialize()

                    # Skip future initializations unless rebuild requested.
                    if not settings.cluster.get('rebuild_every_test', False):
                        global_init[b.getclass()] = b

                try:
                    b.run()
                finally:
                    if b.getclass() not in global_init:
                        b.cleanup()
    except:
        return_code = 1  # FAIL
        logger.exception("During tests")
    finally:
        for k, b in global_init.items():
            try:
                b.cleanup()
            except:
                logger.exception("During %s cleanup", k)
                return_code = 1  # FAIL

    return return_code

def main(argv):
    setup_loggers()
    ctx = parse_args(argv)
    settings.initialize(ctx)
    if not settings.general:
        shutdown('No general settings found.')
    if settings.general.get('rebuild'):
        return rebuild()
    if settings.general.get('query'):
        return query(settings.general.get('query'));
    else:
        return runtests(settings)

if __name__ == '__main__':
    exit(main(sys.argv))
