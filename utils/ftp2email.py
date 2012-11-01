#!/usr/bin/env python
# vim: set fileencoding=utf-8 :

import argparse
import cStringIO
import csv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.parser import Parser as emailParser
import errno
import json
import logging
import os
import poplib
import re
import shutil
import smtplib
import sys
import traceback
import xml.etree.cElementTree as cElementTree


class SinliargMessage(object):
    """Mensaje de sinliarg"""

    def __init__(self, msg_data, filename=None):
        """
            :msg_data: datos del mensaje en formato XML
            :filename: nombre del archivo que contiene el XML del mensaje
        """
        self.xml = msg_data
        xmltree = cElementTree.parse(cStringIO.StringIO(self.xml))
        self.dst_code = xmltree.findtext('DESTINO/CODIGO_SINLI')
        self.src_code = xmltree.findtext('ORIGEN/CODIGO_SINLI')
        self.description = xmltree.findtext('ARCHIVO/DESCRIPCION')
        self.sinli_type = xmltree.findtext('ARCHIVO/CODIGO')
        self.filename = filename or self.gen_file_name()

    def gen_file_name(self):
        """Genera un nombre para el archivo que guardaria los datos del mensaje
        """
        return '_'.join([self.src_code, self.dst_code, self.sinli_type,
                         str(hash(self.xml))]) + '.xml'


class MessageChannel(object):
    """Canal que permite enviar y recibir mensajes"""

    def load_messages(self):
        """Devuelve una lista con los ids de los mensajes encontrados
        """
        raise NotImplementedError

    def get_message(self, msg_id):
        """Devuelve el mensaje con id msg_id
        """
        raise NotImplementedError

    def send_message(self, sinli_msg):
        """:sinli_msg: mensaje sinliarg a enviar
        """
        raise NotImplementedError

    def close(self):
        """Libera los recursos usados para leer los mensajes
        """
        pass


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

    def __str__(self):
        return 'FilesystemChannel(%s)' % self.base_path

    def get_message(self, msg_id):
        """Devuelve el mensaje msg_id
            :msg_id: el id del mensaje es el path al archivo con su contenido
        """
        with open(msg_id) as i:
            return SinliargMessage(i.read(), filename=os.path.split(msg_id)[1])

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

    def send_message(self, message):
        """Guarda el mensaje en el sistema de archivos
            :message: mensaje de sinliarg
        """
        dst_dir = '_'.join([message.src_code, message.dst_code])
        dst_path = None
        for path, dirs, files in os.walk(self.base_path):
            if dst_dir in path:
                dst_path = path
                break

        if dst_path is None:
            raise Exception('No existe el directorio %s para guardar el mensaje'
                                % dst_dir)

        file_path = os.path.join(dst_path, message.sinli_type, message.filename)
        try:
            dst_file = open(file_path, 'w')
        except IOError, e:      # si no existia el directorio intenta crearlo
            logging.debug('Creando directorio %s' % os.path.join(dst_path, message.sinli_type))
            if e.errno == errno.ENOENT:
                os.makedirs(os.path.join(dst_path, message.sinli_type))
                dst_file = open(file_path, 'w')
            else:
                raise

        logging.info('Guardando archivo %s' % file_path)
        dst_file.write(message.xml)
        dst_file.close()
        return file_path


class EmailChannel(MessageChannel):
    """Canal de intercambio de mensajes por email"""
    sinliMimeTypes = ['text/xml', 'application/xml']

    def __init__(self, smtp_settings, pop_settings, msg_from='', eaddress_file=None):
        """
            :smtp_settings: dict de configuracion del servidor smtp
                            {'host': '', 'port': '', 'user': '', 'pass': ''}
            :pop_settings: dict de configuracion del servidor pop
                            {'host': '', 'port': '', 'user': '', 'pass': ''}
            :msg_from: valor que identifica el origen de los emails enviados
            :eaddress_file: nombre del archivo con codigo sinli, direccion de email (csv)
        """
        self.smtp_settings = smtp_settings
        self.pop_settings = pop_settings
        self.msg_from = msg_from
        self.eaddress_file = eaddress_file

    def __str__(self):
        return 'EmailChannel(%s)' % self.msg_from

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
                                                % sinli_message.filename
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

    def get_pop_server(self):
        """Inicia una conexión con el servidor pop
        """
        logging.debug('Iniciando conexion con servidor pop3 %s:%s'
                        % (self.pop_settings['host'], self.pop_settings.get('port', None)))
        pop_server = poplib.POP3(self.pop_settings['host'],
                                 port=self.pop_settings.get('port', None) or 110)
        pop_server.user(self.pop_settings['user'])
        pop_server.pass_(self.pop_settings['pass'])
        return pop_server

    def is_sinliarg(self, email):
        """Determina si un email contiene un mensaje Sinliarg
        """
        return bool('sinliarg' in email.get('subject', '').lower()
                    and len([x for x in email.walk()
                            if x.get_content_type() in self.sinliMimeTypes]) == 1)

    def load_messages(self):
        """Busca los mensajes en el servidor pop
        """
        pop_server = self.get_pop_server()
        email_parser = emailParser()
        self.messages = {}

        for email_ids in pop_server.uidl()[1]:
            email_nro, email_uid = email_ids.split(' ')
            try:
                email_data = '\n'.join(pop_server.retr(email_nro)[1])
                email = email_parser.parsestr(email_data)
            except Exception:
                logging.error('Error leyendo email uid: %s\n%s' % (email_uid, traceback.format_exc()))
                continue
            logging.info('Leyendo email asunto: %s' % email.get('subject', None))
            if self.is_sinliarg(email):
                logging.debug('  email sinliarg reconocido')
                self.messages[email_uid] = email

        pop_server.quit()
        return self.messages.keys()

    def get_message(self, msg_id):
        """Devuelve el mensaje msg_id
            :msg_id: el id del mensaje es el path al archivo con su contenido
        """
        if msg_id not in self.messages:
            raise Exception('El mensaje id:%s no fue leido' % msg_id)

        email_part = [x for x in self.messages[msg_id].walk()
                        if x.get_content_type() in self.sinliMimeTypes][0]

        message_data = email_part.get_payload(decode=True)
        if not message_data.startswith('<?'):       # para leer mensajes con registro SINLI
            message_data = message_data[message_data.find('<?'):]

        return SinliargMessage(message_data, filename=email_part.get_filename())

    def mark_message(self, msg_id):
        """Marca un mensaje como procesado/leido
            Elimina el email del servidor pop
            :msg_id: uid del email
        """
        deleted = False
        pop_server = self.get_pop_server()
        for email_ids in pop_server.uidl()[1]:
            email_nro, email_uid = email_ids.split(' ')
            if email_uid == msg_id:
                logging.info('Eliminando email uid: %s del servidor POP' % msg_id)
                pop_server.dele(email_nro)
                deleted = True
                break
        pop_server.quit()
        if not deleted:
            logging.error('No se encontró el mensaje uid: %s' % msg_id)
        return deleted


def pipeChannels(src_channel, dst_channel):
    """Enviar los mensajes de un canal a otro
        :src_channel: canal de origen de los mensajes
        :dst_channel: canal de destino de los mensajes
    """
    logging.info('Envio de mensajes %s->%s iniciado' % (src_channel, dst_channel))
    for msg_id in src_channel.load_messages():
        logging.info('Procesando mensaje id: %s' % msg_id)
        try:
            sinli_message = src_channel.get_message(msg_id)
            logging.debug('...leido correctamente')
        except Exception:
            logging.error('Error obteniendo datos del mensaje\n%s' % traceback.format_exc())
            continue

        try:
            logging.info('Enviando mensaje id: %s' % msg_id)
            dst_channel.send_message(sinli_message)
            logging.debug('...enviado correctamente')
        except Exception:
            logging.error('Error enviando mensaje\n%s' % traceback.format_exc())
        else:
            src_channel.mark_message(msg_id)
    src_channel.close()
    logging.info('Envio de mensajes %s->%s finalizado' % (src_channel, dst_channel))


def __main__(argv=None):
    """Lee archivos desde un directorio
        Por cada archivo envia un email de sinli
        Despues de enviar el email mueve el archivo a otro directorio
    """

    arg_parser = argparse.ArgumentParser(description='Enviar mensajes sinliarg entre distintos canales')
    arg_parser.add_argument('-i', '--input', required=True,
                            choices=('files', 'emails'),
                            help='Canal de entrada (files|email)')
    arg_parser.add_argument('-o', '--output', required=True,
                            choices=('files', 'emails'),
                            help='Canal de salida (files|email)')
    arg_parser.add_argument('-s', '--settings', default='settings.json',
                            help='Archivo de configuración')
    args = arg_parser.parse_args(argv)

    try:
        with open(args.settings) as i:
            settings = json.load(i)
    except Exception:
        print 'Error abriendo archivo de configuracion: %s\n\n' % args.settings
        raise

    # configurar el log
    log_format = '%(asctime)s|%(levelname)s|%(message)s'
    log_level = getattr(logging, settings.get('log_level', 'DEBUG'), logging.DEBUG)
    if 'log_file' in settings:
        logging.basicConfig(filename=settings['log_file'], level=log_level,
                            format=log_format)
    else:
        logging.basicConfig(level=log_level, format=log_format)

    # intercambiar mensajes
    channels_map = {'files': lambda:
                        FilesystemChannel(settings['base_path'], settings['dir_re']),
                    'emails': lambda:
                        EmailChannel(smtp_settings=settings['smtp_settings'],
                                    pop_settings=settings['pop_settings'],
                                    msg_from=settings['sinli_email'],
                                    eaddress_file=settings['eaddress_file'])}

    input_channel = channels_map[args.input]()
    output_channel = channels_map[args.output]()
    pipeChannels(input_channel, output_channel)

    return 0


if __name__ == '__main__':
    sys.exit(__main__())
