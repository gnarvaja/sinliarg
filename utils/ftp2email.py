#!/usr/bin/env python
# vim: set fileencoding=utf-8 :

import cStringIO
import csv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import errno
import json
import logging
import os
import re
import shutil
import smtplib
import sys
import traceback
import xml.etree.cElementTree as cElementTree


class SinliargMessage(object):
    """Mensaje de sinliarg"""

    def __init__(self, msg_data):
        """
            :msg_data: datos del mensaje en formato XML
        """
        self.xml = msg_data
        xmltree = cElementTree.parse(cStringIO.StringIO(self.xml))
        self.dst_code = xmltree.findtext('DESTINO/CODIGO_SINLI')
        self.src_code = xmltree.findtext('ORIGEN/CODIGO_SINLI')
        self.description = xmltree.findtext('ARCHIVO/DESCRIPCION')
        self.sinli_type = xmltree.findtext('ARCHIVO/CODIGO')


class MessageChannel(object):
    """Canal que permite enviar y recibir mensajes"""

    def load_messages(self):
        """Devuelve una lista con los ids de los mensajes encontrados
        """
        raise NotImplementedError

    def get_message_data(self, msg_id):
        """Devuelve el contenido del mensaje con id msg_id
        """
        raise NotImplementedError

    def send_message(self, msg_data):
        """:msg_data: datos del mensaje a enviar
        """
        raise NotImplementedError


class FilesystemChannel(MessageChannel):
    """Canal de intercambio de mensajes por sistema de archivos"""

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
    """Canal de intercambio de mensajes por email"""

    def __init__(self, smtp_settings, msg_from='', eaddress_file=None):
        """
            :smtp_settings: dict de configuracio del servidor smtp
                            {'host': '', 'port': '', 'user': '', 'pass': ''}
            :msg_from: valor que identifica el origen de los emails enviados
            :eaddress_file: nombre del archivo con codigo sinli, direccion de email (csv)
        """
        self.smtp_settings = smtp_settings
        self.msg_from = msg_from
        self.eaddress_file = eaddress_file

    def send_message(self, sinli_message):
        """Envia el mensaje al destinatario Sinliarg por email
            :sinli_message: mensaje Sinliarg a enviar
        """
        # crear el email a enviar
        dest_addr = self.get_destination_address(sinli_message)
        new_email = MIMEMultipart()
        new_email['From'] = self.msg_from
        new_email['To'] = dest_addr
        new_email['Subject'] = self.gen_email_subject(sinli_message)
        new_email.attach(MIMEText(self.gen_email_body(sinli_message)))
        xml_attach = MIMEText(sinli_message.xml, 'xml', 'utf-8')
        xml_attach['Content-disposition'] = 'attachment; filename="%s"' \
                                                % self.gen_filename(sinli_message)
        new_email.attach(xml_attach)

        # conectar con el servidor y hacer en envio
        smtp_server = smtplib.SMTP(self.smtp_settings['host'],
                                   port=self.smtp_settings.get('port', None), timeout=5)
        if self.smtp_settings['user'] is not None:
            smtp_server.login(self.smtp_settings['user'],
                              self.smtp_settings['pass'])
        smtp_server.sendmail(self.msg_from, dest_addr, new_email.as_string())
        smtp_server.close()

    def load_sinli_codes(self):
        """Lee las direcciones de email para cada codigo sinli de un archivo csv
        """
        with open(self.eaddress_file) as i:
            self.sinli_emails = dict(csv.reader(i))
        return self.sinli_emails

    def get_destination_address(self, message):
        """Devolve la direccion de email a donde debe ser enviado el mensaje
            :message: mensaje Sinliarg del cual se busca la direccion destino
        """
        if not hasattr(self, 'sinli_emails'):
            self.load_sinli_codes()
        return self.sinli_emails[message.dst_code]

    def gen_email_subject(self, message):
        """Genera una linea para asunto del email a enviar con el mensaje
        """
        return 'SINLIARG: Tipo: %s, De: %s, Para: %s' \
                % (message.sinli_type, message.src_code, message.dst_code)

    def gen_email_body(self, message):
        """Genera el texto para el cuerpo del email a enviar con el mensaje
        """
        return message.description or 'Mensaje sinliarg adjunto'

    def gen_filename(self, message):
        """Genera un nombre de archivo para el contenido del mensaje
        """
        return '%s.xml' % '_'.join((message.sinli_type, message.src_code,
                                    message.dst_code, str(hash(message.xml))))


def __main__(argv=None):
    """Lee archivos desde un directorio
        Por cada archivo envia un email de sinli
        Despues de enviar el email mueve el archivo a otro directorio
    """
    if argv is None:
        argv = sys.argv

    if len(argv) > 1:
        settings_filename = argv[1]
    else:
        settings_filename = 'settings.json'

    try:
        with open(settings_filename) as i:
            settings = json.load(i)
    except Exception:
        print 'Error abriendo archivo de configuracion: %s\n\n' % settings_filename
        raise

    log_format = '%(asctime)s|%(levelname)s|%(message)s'
    if 'log_file' in settings:
        logging.basicConfig(filename=settings['log_file'], level=logging.DEBUG,
                            format=log_format)
    else:
        logging.basicConfig(level=logging.DEBUG, format=log_format)

    srcChannel = FilesystemChannel(settings['base_path'], settings['dir_re'])
    dstChannel = EmailChannel(smtp_settings=settings['smtp_settings'],
                              msg_from='testsinli@fierro-soft.com.ar',
                              eaddress_file=settings['eaddress_file'])

    logging.info('Envio de mensajes FTP->Email iniciado')
    for msg_id in srcChannel.load_messages():
        logging.info('Procesando mensaje id: %s' % msg_id)
        try:
            msg_data = srcChannel.get_message_data(msg_id)
            logging.debug('...leido correctamente')
        except Exception:
            logging.error('Error obteniendo datos del mensaje\n%s' % traceback.format_exc())

        try:
            logging.info('Enviando mensaje id: %s' % msg_id)
            dstChannel.send_message(SinliargMessage(msg_data))
            logging.debug('...enviado correctamente')
        except Exception:
            logging.error('Error enviando mensaje\n%s' % traceback.format_exc())
        else:
            srcChannel.mark_message(msg_id)
    logging.info('Envio de mensajes FTP->Email finalizado')

    return 0


if __name__ == '__main__':
    sys.exit(__main__())
