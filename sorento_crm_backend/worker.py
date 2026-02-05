#!/usr/bin/env python
"""RQ worker script for processing import jobs."""
import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rq import Worker, Queue, Connection
from app.services.queue_service import redis_conn
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    with Connection(redis_conn):
        worker = Worker(['imports'])
        logger.info("Starting RQ worker for 'imports' queue...")
        worker.work()
