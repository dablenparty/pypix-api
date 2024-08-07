#####################################################################
#   FasTUS Logging Class
#   Author: Jordan Michaels
#   License: Unlicense / Public Domain
#            https://opensource.org/license/unlicense/
#   Contact: fastus@utdream.anonaddy.com
#   Description:
#       This module allows you to configure your logger.
#   Docs:
#       https://docs.python.org/3.8/howto/logging.html
#####################################################################

import logging

# local
from api.core import settings

def logger():
    logger = logging.getLogger(settings.env('LOG_NAME'))
    logger_filepath = f"{settings.env('LOG_DIR')}{settings.env('LOG_NAME')}.log"
    logger_formatter = logging.Formatter(settings.env('LOG_FORMAT'))
    if not getattr(logger, 'handler_set', None):
        # only need one handler, otherwise logs repeated for each init
        logger_handler = logging.handlers.RotatingFileHandler(
            logger_filepath, 'a',
            int(settings.env('LOG_SIZE')),
            int(settings.env('LOG_DAYS'))
        )
        logger_handler.setFormatter(logger_formatter)
        logger.addHandler(logger_handler)
        logger_log_level = settings.env('LOG_LEVEL')
        logger.handler_set = True

        # can't use 'match/case' until python 3.10
        if logger_log_level == 'INFO':
            logger.setLevel(logging.INFO)
        elif logger_log_level == 'WARNING':
            logger.setLevel(logging.WARNING)
        elif logger_log_level == 'ERROR':
            logger.setLevel(logging.ERROR)
        elif logger_log_level == 'CRITICAL':
            logger.setLevel(logging.CRITICAL)
        else:
            # default to debug
            logger.setLevel(logging.DEBUG)

    return logger
