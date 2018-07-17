#!/usr/bin/env python3
import logging
import configparser

from matrix_bot.core import MatrixBot

if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    config = configparser.ConfigParser()
    config.read('config.cfg')

    bot = MatrixBot(config)
    bot.run()
