#!/usr/bin/env python
# vim: set fileencoding=utf-8 :

# export PYTHONPATH=$PYTHONPATH:/home/facundo/repo/sinliarg

import os
import sys
import unittest

# fixme: hay una forma menos fea de incluir en el path el directorio donde esta utils?
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))

import utils.ftp2email as ftp2email


class LoggingTester(object):

    def __init__(self):

        self.log_levels = ('debug', 'info', 'warning', 'error', 'critical')

        self.flush()

        # agregar un metodo por cada nivel de log
        # que acumula los mensajes en el diccionario
        map(lambda l: setattr(self, l, lambda x: self.messages[l].append(x)),
            self.log_levels)

    def flush(self):
        self.messages = dict((x, []) for x in self.log_levels)


ftp2email.logging = LoggingTester()


class FilesystemChannelTestCase(unittest.TestCase):
    "Test para el manejo de mensajes por archivos"

    @classmethod
    def setUpClass(cls):
        """Los archivos para tests estan en un directorio 'data'
            dentro del directorio donde está el test
        """
        cls.test_path = os.path.dirname(os.path.realpath(__file__))

    def setUp(self):
        self.ch = ftp2email.FilesystemChannel(os.path.join(self.test_path, 'data'),
                                                '/L0002349_[A-Z][0-9]{7}$')
        ftp2email.logging.flush()

    def test_get_message_files(self):
        "Verifica que se reconozcan correctamente los archivos con mensajes"

        espected_files = [os.path.join(self.test_path, x)
                            for x in ['data/L0002349_E0000001/vacio.xml',
                                      'data/L0002349_E0000001/REMFAA_L0002349_E0000001_517.xml',
                                      'data/L0002349_L0002349/vacio.xml',
                                      'data/L0002349_L0000001/vacio.xml']]

        self.assertListEqual(list(self.ch.load_messages()), espected_files)

    def test_get_message_data(self):
        "Verifica que se pueda cargar el contenido de un mensaje"
        msg_id = os.path.join(self.test_path, 'data/L0002349_E0000001/vacio.xml')
        self.assertEqual(self.ch.get_message_data(msg_id), '')

        msg_id = os.path.join(self.test_path,
                                'data/L0002349_E0000001/REMFAA_L0002349_E0000001_517.xml')
        self.assertEqual(self.ch.get_message_data(msg_id), open(msg_id).read())

    def test_mark_message(self):
        "Verifica que se mueva el archivo del mensaje para marcarlo como leido"

        real_move = ftp2email.shutil.move
        move_operations = []

        def fake_move(src, dst):
            move_operations.append((src, dst))
        ftp2email.shutil.move = fake_move

        self.ch.mark_message('/path/to/message.xml')
        msg_id = os.path.join(self.test_path, 'data/L0002349_E0000001/vacio.xml')
        self.ch.mark_message(msg_id)
        self.assertEqual(move_operations,
                            [(msg_id,
                              os.path.join(self.test_path, 'data/L0002349_E0000001/archived/vacio.xml'))])
        self.assertEqual(ftp2email.logging.messages['error'],
                            ['El archivo del mensaje no existe /path/to/message.xml'])
        self.assertEqual(ftp2email.logging.messages['info'],
                            ['Moviendo archivo de mensaje %s' % msg_id])

        ftp2email.shutil.move = real_move


def main():
    unittest.main()


if __name__ == '__main__':
    sys.exit(main())
