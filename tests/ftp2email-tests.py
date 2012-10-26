#!/usr/bin/env python
# vim: set fileencoding=utf-8 :

# export PYTHONPATH=$PYTHONPATH:/home/facundo/repo/sinliarg

import os
import sys
import unittest

# fixme: hay una forma menos fea de incluir en el path el directorio donde esta utils?
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))

import utils.ftp2email as ftp2email


class Ftp2emailTestCase(unittest.TestCase):
    "Test para el envio de mensajes sinli por email desde archivos"

    @classmethod
    def setUpClass(cls):
        """Los archivos para tests estan en un directorio 'data'
            dentro del directorio donde está el test
        """
        cls.script_path = os.path.dirname(os.path.realpath(__file__))
        ftp2email.settings['base_path'] = os.path.join(cls.script_path, 'data')

    def setUp(self):
        pass

    def test_get_message_files(self):
        "Verifica que se reconozcan correctamente los archivos con mensajes"

        espected_files = [os.path.join(self.script_path, x)
                            for x in ['data/L0002349_E0000001/vacio.xml',
                                      'data/L0002349_E0000001/REMFAA_L0002349_E0000001_517.xml',
                                      'data/L0002349_L0002349/vacio.xml',
                                      'data/L0002349_L0000001/vacio.xml']]
        self.assertListEqual(list(ftp2email.get_message_files()), espected_files)



def main():
    unittest.main()


if __name__ == '__main__':
    sys.exit(main())
