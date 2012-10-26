#!/usr/bin/env python
# vim: set fileencoding=utf-8 :

import json
import re
import os
import sys


with open('settings.json') as i:
    settings = json.load(i)


def get_message_files():
    """Devuelve una lista con los nombres de archivo de los mensajes
    """
    dir_re = re.compile(settings['dir_re'])
    for dirpath, dirname, filenames in os.walk(settings['base_path']):
        if dir_re.search(dirpath):
            for filename in filenames:
                yield os.path.join(dirpath, filename)


def send_message(msg):
    """Envia por email el mensaje al destinatario Sinliarg
    """
    return True


def mark_message(filename):
    """Marca el archivo del mensaje como enviado moviendolo a otro directorio
    """
    return True


def __main__(argv=None):
    """Lee archivos desde un directorio
        Por cada archivo envia un email de sinli
        Despues de enviar el email mueve el archivo a otro directorio
    """
    if argv is None:
        argv = sys.argv

    for message_fn in get_message_files():
        try:
            logger.info('sending message')
            with open(message_fn) as message_data:
                send_message(message_data)
            logger.info('message sent')
        except Exception, e:
            logger.error(e)
        else:
            mark_message(message_fn)

    return 0


if __name__ == '__main__':
    sys.exit(__main__())
