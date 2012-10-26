#!/usr/bin/env python
# vim: set fileencoding=utf-8 :

import csv
import errno
import json
import logging
import os
import re
import shutil
import sys

with open('settings.json') as i:
    settings = json.load(i)


class MessageChannel(object):
    "Canal que permite enviar y recibir mensajes"

    def load_messages(self):
        "Devuelve una lista con los ids de los mensajes encontrados"
        raise NotImplementedError

    def get_message_data(self, msg_id):
        "Devuelve el contenido del mensaje con id msg_id"
        raise NotImplementedError

    def send_message(self, msg_data):
        ":msg_data: datos del mensaje a enviar"
        raise NotImplementedError


class FilesystemChannel(MessageChannel):
    "Canal de intercambio de mensajes por sistema de archivos"

    def __init__(self, base_path, dir_re):
        """
            :base_path: directorio base donde se guardan los mensajes
            :dir_re: expresion regular usada para reconocer
                     los directorios que contienen mensajes
        """
        self.base_path = os.path.abspath(base_path)
        self.dir_re = re.compile(dir_re)

    def get_message_data(self, msg_id):
        """Devuelve el contenido del mensaje msg_id
            :msg_id: el id del mensaje es el path al archivo con su contenido
        """
        with open(msg_id) as i:
            return i.read()

    def load_messages(self):
        """Devuelve una lista con los nombres de archivo de los mensajes
        """
        for dirpath, dirname, filenames in os.walk(self.base_path):
            if self.dir_re.search(dirpath):
                for filename in filenames:
                    yield os.path.join(dirpath, filename)

    def mark_message(self, msg_id):
        """Marca un mensaje como procesado/leido
            Mueve el archivo con el mensaje a un directorio 'leidos'
            :msg_id: path al archivo que contiene el mensaje
        """
        if not os.path.isfile(msg_id):
            logging.error('El archivo del mensaje no existe %s'
                            % msg_id)
            return

        base_dir, filename = os.path.split(msg_id)
        archived_path = os.path.join(base_dir, 'archived')
        try:
            logging.info('Moviendo archivo de mensaje %s' % msg_id)
            shutil.move(msg_id, os.path.join(archived_path, filename))
        except IOError, e:                  # si no existia el directorio intenta crearlo
            if e.errno == errno.ENOENT:
                try:
                    logging.error('Creando directorio para mensajes archivados en %s'
                                    % archived_path)
                    os.makedirs(archived_path)
                except OSError, e:          # si da error porque ya existe lo ignora
                    if e.exception.errno != errno.EEXIST:
                        raise
                shutil.move(msg_id, os.path.join(archived_path, filename))
            else:
                raise


class EmailChannel(MessageChannel):
    "Canal de intercambio de mensajes por email"

    def __init__(self, smtp_url=None, eaddress_file=None):
        self.smtp_url = smtp_url
        self.eaddress_file = eaddress_file

    def send_message(self, msg_data):
        """Envia por email el mensaje al destinatario Sinliarg por email
        """
        if not hasattr(self, 'sinli_emails'):
            self.load_sinli_codes()

    def load_sinli_codes(self):
        "Lee las direcciones de email para cada codigo sinli de un archivo csv"

        with open(self.eaddress_file) as i:
            self.sinli_emails = dict(csv.reader(i))
        return True


def __main__(argv=None):
    """Lee archivos desde un directorio
        Por cada archivo envia un email de sinli
        Despues de enviar el email mueve el archivo a otro directorio
    """
    if argv is None:
        argv = sys.argv

    srcChannel = FilesystemChannel(settings['base_path'], settings['dir_re'])
    dstChannel = EmailChannel(smtp_url=settings['smtp_url'], eaddress_file=settings['eaddress_file'])
    for msg_id in srcChannel.load_messages():
        try:
            msg_data = srcChannel.get_message_data(msg_id)
        except Exception, e:
            logging.error('Error obteniendo datos del mensaje\n%s' % e)

        try:
            dstChannel.send_message(msg_data)
        except Exception, e:
            logging.error('Error enviando mensaje\n%s' % e)
        else:
            srcChannel.mark_message(msg_id)

    return 0


if __name__ == '__main__':
    sys.exit(__main__())
