#!/usr/bin/env python
# vim: set fileencoding=utf-8 :

# export PYTHONPATH=$PYTHONPATH:/home/facundo/repo/sinliarg

import os
import sys
import traceback
import unittest

import mock

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


class SinliargMessageTestCase(unittest.TestCase):
    """Test para los mensajes"""

    def setUp(self):
        xmldata = """<?xml version="1.0" encoding="utf-8"?>
                     <REMFAA>
                     <ARCHIVO>
                         <DESCRIPCION>Factura/Remito 0001-00336393</DESCRIPCION>
                         <FECHA>2012-09-18</FECHA>
                         <VERSION>1.0</VERSION>
                         <CODIGO>REMFAA</CODIGO>
                     </ARCHIVO>
                     <ORIGEN>
                         <NOMBRE>ILHSA</NOMBRE>
                         <CUIT />
                         <ID_SUCURSAL />
                         <CODIGO_SINLI>L0002349</CODIGO_SINLI>
                     </ORIGEN>
                     <DESTINO>
                         <NOMBRE>Editorial 1</NOMBRE>
                         <CUIT>30-00000000-1</CUIT>
                         <ID_SUCURSAL>1</ID_SUCURSAL>
                         <CODIGO_SINLI>E0000001</CODIGO_SINLI>
                     </DESTINO>
                     </REMFAA>"""
        self.message = ftp2email.SinliargMessage(xmldata)

    def test_dst_code(self):
        """Verifica el codigo sinli de destino del mensaje
        """
        self.assertEqual(self.message.dst_code, 'E0000001')

    def test_src_code(self):
        """Verifica el codigo sinli de origen del mensaje
        """
        self.assertEqual(self.message.src_code, 'L0002349')

    def test_descripcion(self):
        """Verifica la descripcion del mensaje
        """
        self.assertEqual(self.message.description, 'Factura/Remito 0001-00336393')


class FilesystemChannelTestCase(unittest.TestCase):
    """Test para el manejo de mensajes por archivos"""

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
        """Verifica que se reconozcan correctamente los archivos con mensajes
        """
        espected_files = [os.path.join(self.test_path, x)
                            for x in ['data/L0002349_E0000001/vacio.xml',
                                      'data/L0002349_E0000001/REMFAA_L0002349_E0000001_517.xml',
                                      'data/L0002349_L0002349/vacio.xml',
                                      'data/L0002349_L0000001/vacio.xml']]

        self.assertListEqual(list(self.ch.load_messages()), espected_files)

    @mock.patch('%s.ftp2email.SinliargMessage' % __name__)
    def test_get_message(self, message_mock):
        """Verifica que se pueda cargar el contenido de un mensaje
        """
        msg_id = os.path.join(self.test_path, 'data/L0002349_E0000001/vacio.xml')
        self.ch.get_message(msg_id)
        message_mock.assert_called_with('', filename='vacio.xml')

        msg_id = os.path.join(self.test_path,
                                'data/L0002349_E0000001/REMFAA_L0002349_E0000001_517.xml')
        self.ch.get_message(msg_id)
        message_mock.assert_called_with(open(msg_id).read(),
                                        filename='REMFAA_L0002349_E0000001_517.xml')

    @mock.patch('%s.ftp2email.shutil.move' % __name__)
    def test_mark_message(self, move_mock):
        """Verifica que se mueva el archivo del mensaje para marcarlo como leido
        """

        self.ch.mark_message('/path/to/message.xml')
        msg_id = os.path.join(self.test_path, 'data/L0002349_E0000001/vacio.xml')
        self.ch.mark_message(msg_id)

        move_mock.assert_called_with(msg_id,
                                     os.path.join(self.test_path,
                                            'data/L0002349_E0000001/archived/vacio.xml'))

        self.assertEqual(ftp2email.logging.messages['error'],
                            ['El archivo del mensaje no existe /path/to/message.xml'])
        self.assertEqual(ftp2email.logging.messages['info'],
                            ['Moviendo archivo de mensaje %s' % msg_id])


class EmailChannelTestCase(unittest.TestCase):
    """Test para el manejo de mensajes por email"""

    @classmethod
    def setUpClass(cls):
        """Los archivos para tests estan en un directorio 'data'
            dentro del directorio donde está el test
        """
        cls.test_path = os.path.dirname(os.path.realpath(__file__))

    def setUp(self):
        eaddress_file = os.path.join(self.test_path, 'data/email_address.csv')
        self.ch = ftp2email.EmailChannel(smtp_settings={'host': 'smtpserver',
                                                        'port': None,
                                                        'user': 'u',
                                                        'pass': 'p'},
                                         msg_from='test@example.com',
                                         eaddress_file=eaddress_file)
        ftp2email.logging.flush()

    def test_load_sinli_codes(self):
        """Verifica que se carguen correctamente los codigos y direcciones de email
        """
        emails = self.ch.load_sinli_codes()

        self.assertEqual(len(emails), 12)
        self.assertEqual(emails['L0001562'], 'sinli@cuspide.com')
        self.assertEqual(emails['L0001563'], 'sinliarg@libreriahernandez.com.ar')
        self.assertTrue('Z0000000' not in emails)
        self.assertListEqual(emails.values(), self.ch.sinli_emails.values())

    def test_get_destination_address(self):
        """Verifica que se obtenga correctamente la direcciond de email
            a donde se debe enviar el mensaje
        """
        xmldata = """<?xml version="1.0" encoding="utf-8"?>
                     <REMFAA>
                     <ARCHIVO>
                         <DESCRIPCION>Factura/Remito 0001-00336393</DESCRIPCION>
                         <FECHA>2012-09-18</FECHA>
                         <VERSION>1.0</VERSION>
                         <CODIGO>REMFAA</CODIGO>
                     </ARCHIVO>
                     <ORIGEN>
                         <NOMBRE>ILHSA</NOMBRE>
                         <CUIT />
                         <ID_SUCURSAL />
                         <CODIGO_SINLI>L0002349</CODIGO_SINLI>
                     </ORIGEN>
                     <DESTINO>
                         <NOMBRE>Editorial 1</NOMBRE>
                         <CUIT>30-00000000-1</CUIT>
                         <ID_SUCURSAL>1</ID_SUCURSAL>
                         <CODIGO_SINLI>E0000001</CODIGO_SINLI>
                     </DESTINO>
                     </REMFAA>"""

        self.assertEqual(self.ch.get_destination_address(ftp2email.SinliargMessage(xmldata)),
                         'fc@fierro-soft.com.ar')

    def test_gen_email_subject(self):
        """Verifica la generacion del asunto del email
        """
        xmldata = """<?xml version="1.0" encoding="utf-8"?>
                     <REMFAA>
                     <ARCHIVO>
                         <DESCRIPCION>Factura/Remito 0001-00336393</DESCRIPCION>
                         <FECHA>2012-09-18</FECHA>
                         <VERSION>1.0</VERSION>
                         <CODIGO>REMFAA</CODIGO>
                     </ARCHIVO>
                     <ORIGEN>
                         <NOMBRE>ILHSA</NOMBRE>
                         <CUIT />
                         <ID_SUCURSAL />
                         <CODIGO_SINLI>L0002349</CODIGO_SINLI>
                     </ORIGEN>
                     <DESTINO>
                         <NOMBRE>Editorial 1</NOMBRE>
                         <CUIT>30-00000000-1</CUIT>
                         <ID_SUCURSAL>1</ID_SUCURSAL>
                         <CODIGO_SINLI>E0000001</CODIGO_SINLI>
                     </DESTINO>
                     </REMFAA>"""

        self.assertEqual(self.ch.gen_email_subject(ftp2email.SinliargMessage(xmldata)),
                         'SINLIARG: Tipo: REMFAA, De: L0002349, Para: E0000001')

    def test_gen_email_body(self):
        """Verifica la generacion del cuerpo del email
        """
        xmldata = """<?xml version="1.0" encoding="utf-8"?>
                     <REMFAA>
                     <ARCHIVO>
                         <DESCRIPCION>Factura/Remito 0001-00336393</DESCRIPCION>
                         <FECHA>2012-09-18</FECHA>
                         <VERSION>1.0</VERSION>
                         <CODIGO>REMFAA</CODIGO>
                     </ARCHIVO>
                     <ORIGEN>
                         <NOMBRE>ILHSA</NOMBRE>
                         <CUIT />
                         <ID_SUCURSAL />
                         <CODIGO_SINLI>L0002349</CODIGO_SINLI>
                     </ORIGEN>
                     <DESTINO>
                         <NOMBRE>Editorial 1</NOMBRE>
                         <CUIT>30-00000000-1</CUIT>
                         <ID_SUCURSAL>1</ID_SUCURSAL>
                         <CODIGO_SINLI>E0000001</CODIGO_SINLI>
                     </DESTINO>
                     </REMFAA>"""

        self.assertEqual(self.ch.gen_email_body(ftp2email.SinliargMessage(xmldata)),
                            'Factura/Remito 0001-00336393')

    def test_gen_filename(self):
        """Verifica la generacion del nombre de archivo para el adjunto
        """
        xmldata = """<?xml version="1.0" encoding="utf-8"?>
                     <REMFAA>
                     <ARCHIVO>
                         <DESCRIPCION>Factura/Remito 0001-00336393</DESCRIPCION>
                         <FECHA>2012-09-18</FECHA>
                         <VERSION>1.0</VERSION>
                         <CODIGO>REMFAA</CODIGO>
                     </ARCHIVO>
                     <ORIGEN>
                         <NOMBRE>ILHSA</NOMBRE>
                         <CUIT />
                         <ID_SUCURSAL />
                         <CODIGO_SINLI>L0002349</CODIGO_SINLI>
                     </ORIGEN>
                     <DESTINO>
                         <NOMBRE>Editorial 1</NOMBRE>
                         <CUIT>30-00000000-1</CUIT>
                         <ID_SUCURSAL>1</ID_SUCURSAL>
                         <CODIGO_SINLI>E0000001</CODIGO_SINLI>
                     </DESTINO>
                     </REMFAA>"""

        self.assertEqual(self.ch.gen_filename(ftp2email.SinliargMessage(xmldata)),
                            'REMFAA_L0002349_E0000001_2717603300731787160.xml')

    def test_send_message(self):
        """Verifica el envio del mensaje por email
        """
        data_file = os.path.join(self.test_path,
                                 'data/L0002349_E0000001/REMFAA_L0002349_E0000001_517.xml')
        with open(data_file) as i:
            msg_data = i.read()

        with mock.patch('%s.ftp2email.smtplib.SMTP' % __name__) as smtp_mock:
            smtpserver_mock = mock.Mock(create=True)
            smtp_mock.return_value = smtpserver_mock
            try:
                self.ch.send_message(ftp2email.SinliargMessage(msg_data))
            except Exception:
                self.fail('Unexpected exception: %s' % traceback.format_exc())

            smtp_mock.assert_called_once_with('smtpserver', port=None, timeout=5)
            smtpserver_mock.login.assert_called_once_with('u', 'p')
            self.assertEqual(smtpserver_mock.sendmail.call_count, 1)
            self.assertEqual(smtpserver_mock.close.call_count, 1)


class PipeChannelsTestCase(unittest.TestCase):
    """Test para la funcion que envia mensajes entre canales"""

    def test_pipeChannels(self):
        src_channel_mock = mock.Mock(create=True)
        src_channel_mock.load_messages.return_value = (1, 2, 3)
        src_channel_mock.get_message_data.return_value = """<?xml version="1.0" encoding="utf-8"?>
                                                           <REMFAA>
                                                             <ARCHIVO>
                                                               <DESCRIPCION>mensaje sinliarg</DESCRIPCION>
                                                               <CODIGO>REMFAA</CODIGO>
                                                             </ARCHIVO>
                                                             <ORIGEN>
                                                               <CODIGO_SINLI>L0000001</CODIGO_SINLI>
                                                             </ORIGEN>
                                                             <DESTINO>
                                                               <CODIGO_SINLI>E0000001</CODIGO_SINLI>
                                                             </DESTINO>
                                                           </REMFAA>"""
        dst_channel_mock = mock.Mock(create=True)

        ftp2email.pipeChannels(src_channel_mock, dst_channel_mock)
        self.assertEqual(src_channel_mock.load_messages.call_count, 1)
        self.assertEqual(src_channel_mock.get_message.call_count, 3)
        src_channel_mock.get_message.assert_has_calls([mock.call(x) for x in (1, 2, 3)])
        self.assertEqual(dst_channel_mock.send_message.call_count, 3)
        src_channel_mock.mark_message.assert_has_calls([mock.call(x) for x in (1, 2, 3)])

def main():
    unittest.main()


if __name__ == '__main__':
    sys.exit(main())
