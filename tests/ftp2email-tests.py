#!/usr/bin/env python
# vim: set fileencoding=utf-8 :

# export PYTHONPATH=$PYTHONPATH:/home/facundo/repo/sinliarg

from email.parser import Parser as emailParser
import os
import poplib
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

    def test_filename(self):
        """Verifica el nombre de archivo del mensaje
        """
        # nombre generado a partir de los datos del mensaje
        self.assertEqual(self.message.filename,
                         'L0002349_E0000001_REMFAA_%s.xml' % hash(self.message.xml))

        # nombre asignado en la creación del objeto
        self.assertEqual(ftp2email.SinliargMessage(self.message.xml, filename='d.xml').filename,
                            'd.xml')


class FilesystemChannelTestCase(unittest.TestCase):
    """Test para el manejo de mensajes por archivos"""

    @classmethod
    def setUpClass(cls):
        """Los archivos para tests estan en un directorio 'data'
            dentro del directorio donde está el test
        """
        cls.test_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                        'data')

    def setUp(self):
        self.ch = ftp2email.FilesystemChannel(self.test_path,
                                                '/L0002349_[A-Z][0-9]{7}$')
        ftp2email.logging.flush()

    def test_load_messages(self):
        """Verifica que se reconozcan correctamente los archivos con mensajes
        """
        espected_files = [os.path.join(self.test_path, x)
                            for x in ['L0002349_E0000001/vacio.xml',
                                      'L0002349_E0000001/REMFAA_L0002349_E0000001_517.xml',
                                      'L0002349_L0002349/vacio.xml',
                                      'L0002349_L0000001/vacio.xml']]

        self.assertListEqual(list(self.ch.load_messages()), espected_files)

    @mock.patch('%s.ftp2email.SinliargMessage' % __name__)
    def test_get_message(self, message_mock):
        """Verifica que se pueda cargar el contenido de un mensaje
        """
        msg_id = os.path.join(self.test_path, 'L0002349_E0000001/vacio.xml')
        self.ch.get_message(msg_id)
        message_mock.assert_called_with('', filename='vacio.xml')

        msg_id = os.path.join(self.test_path,
                                'L0002349_E0000001/REMFAA_L0002349_E0000001_517.xml')
        self.ch.get_message(msg_id)
        message_mock.assert_called_with(open(msg_id).read(),
                                        filename='REMFAA_L0002349_E0000001_517.xml')

    @mock.patch('%s.ftp2email.shutil.move' % __name__)
    def test_mark_message(self, move_mock):
        """Verifica que se mueva el archivo del mensaje para marcarlo como leido
        """

        self.ch.mark_message('/path/to/message.xml')
        msg_id = os.path.join(self.test_path, 'L0002349_E0000001/vacio.xml')
        self.ch.mark_message(msg_id)

        move_mock.assert_called_with(msg_id,
                                     os.path.join(self.test_path,
                                            'L0002349_E0000001/archived/vacio.xml'))

        self.assertEqual(ftp2email.logging.messages['error'],
                            ['El archivo del mensaje no existe /path/to/message.xml'])
        self.assertEqual(ftp2email.logging.messages['info'],
                            ['Moviendo archivo de mensaje %s' % msg_id])

    def test_send_message(self):
        """Verifica que se guarde el mensaje en el sistema de archivos
        """
        msg = ftp2email.SinliargMessage("""<?xml version="1.0" encoding="utf-8"?>
                                        <REMFAA>
                                            <ARCHIVO>
                                                <DESCRIPCION>Factura/Remito 0001-00336393</DESCRIPCION>
                                                <FECHA>2012-09-18</FECHA>
                                                <VERSION>1.0</VERSION>
                                                <CODIGO>REMFAA</CODIGO>
                                            </ARCHIVO>
                                            <ORIGEN>
                                                <NOMBRE>Editorial 1</NOMBRE>
                                                <CUIT />
                                                <ID_SUCURSAL />
                                                <CODIGO_SINLI>E0000001</CODIGO_SINLI>
                                            </ORIGEN>
                                            <DESTINO>
                                                <NOMBRE>ILHSA</NOMBRE>
                                                <CUIT />
                                                <ID_SUCURSAL />
                                                <CODIGO_SINLI>L0002349</CODIGO_SINLI>
                                            </DESTINO>
                                         </REMFAA>""", filename='REMFAA_L0002349_E0000001.xml')

        with mock.patch('%s.ftp2email.open' % __name__, create=True) as open_mock:
            open_mock.return_value = mock.MagicMock(spec=file)
            self.ch.send_message(msg)

            dst_path = os.path.join(self.test_path, 'edit1',
                                    '_'.join([msg.src_code, msg.dst_code]),
                                    msg.sinli_type, msg.filename)

            open_mock.assert_called_once_with(dst_path, 'w')
            file_mock = open_mock.return_value
            file_mock.write.assert_called_once_with(msg.xml)
            file_mock.close.assert_called_once_with()


class EmailChannelTestCase(unittest.TestCase):
    """Test para el manejo de mensajes por email"""

    @classmethod
    def setUpClass(cls):
        """Los archivos para tests estan en un directorio 'data'
            dentro del directorio donde está el test
        """
        cls.test_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                        'data')

    def setUp(self):
        eaddress_file = os.path.join(self.test_path, 'email_address.csv')
        smtp_settings = {'host': 'smtpserver', 'port': None,
                         'user': 'u', 'pass': 'p'}
        pop_settings = {'host': 'popserver', 'port': None,
                        'user': 'u', 'pass': 'p'}
        self.ch = ftp2email.EmailChannel(smtp_settings=smtp_settings,
                                         pop_settings=pop_settings,
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

    def test_send_message(self):
        """Verifica el envio del mensaje por email
        """
        data_file = os.path.join(self.test_path,
                                 'L0002349_E0000001/REMFAA_L0002349_E0000001_517.xml')
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

    @mock.patch('%s.ftp2email.poplib.POP3' % __name__, autospec=True)
    def test_get_pop_server(self, pop3_mock):
        """Verifica que se establezca la conexion con el servidor pop
        """
        pop_server = self.ch.get_pop_server()
        pop3_mock.assert_called_once_with('popserver', port=110)
        pop3_mock.return_value.user.assert_called_once_with('u')
        pop3_mock.return_value.pass_.assert_called_once_with('p')
        self.assertTrue(pop_server, poplib.POP3)

    def test_is_sinliarg(self):
        """Verifica que se reconozcan los emails de sinliarg
        """
        with open(os.path.join(self.test_path, 'email_sinliarg')) as i:
                email = emailParser().parse(i)
        self.assertTrue(self.ch.is_sinliarg(email))

        del email['subject']
        email['subject'] = 'ignorame'
        self.assertFalse(self.ch.is_sinliarg(email))

    @mock.patch('%s.ftp2email.poplib.POP3' % __name__, autospec=True)
    def test_load_messages(self, pop3_mock):
        """Verifica que se lean correctamente los mensajes desde el servidor pop
        """

        # sin emails sinliarg
        pop3srv = pop3_mock.return_value
        pop3srv.uidl.return_value = ('+OK', ['1 00000010506477be', '2 00000011506477be'],
                                        40)
        pop3srv.retr = mock.Mock(wraps=lambda uid: {'1': '', '2': ''}[uid])
        self.assertEqual(len(self.ch.load_messages()), 0)
        pop3srv.uidl.assert_called_once_with()
        pop3srv.retr.assert_has_calls([mock.call('1'), mock.call('2')])
        pop3srv.quit.assert_called_once_with()

        # con un email sinliarg
        with open(os.path.join(self.test_path, 'email_sinliarg')) as i:
            email_sinliarg = i.read().splitlines()
        pop3srv.retr = mock.Mock(wraps=lambda uid: {'1': ('+OK', email_sinliarg, 1),
                                                    '2': ''}[uid])
        self.assertEqual(len(self.ch.load_messages()), 1)

        # sin ningun email
        pop3srv.uidl.return_value = ('+OK', [], 0)
        pop3srv.retr.reset_mock()
        self.assertEqual(len(self.ch.load_messages()), 0)
        self.assertTrue(not pop3srv.retr.called)

    def test_get_message(self):
        """Verifica que devuelva el mensaje cargado
        """
        # cuando el mensaje no fue leido levanta una excepcion
        self.assertRaises(Exception, self.ch.get_message, '00000010506477be')

        # devuelve el mensaje
        with open(os.path.join(self.test_path, 'email_sinliarg')) as i:
                email = emailParser().parse(i)
        self.ch.messages = {'00000010506477be': email}

        m = self.ch.get_message('00000010506477be')
        self.assertTrue(isinstance(m, ftp2email.SinliargMessage))

    @mock.patch('%s.ftp2email.poplib.POP3' % __name__, autospec=True)
    def test_mark_message(self, pop3_mock):
        """Verifica que se marque el mensaje como leido
        """
        pop3srv = pop3_mock.return_value
        pop3srv.uidl.return_value = ('+OK', ['1 00000010506477be', '2 00000011506477be'],
                                        40)
        self.assertTrue(self.ch.mark_message('00000010506477be'))
        pop3srv.dele.assert_called_once_with('1')
        pop3srv.quit.assert_called_once_with()

        pop3srv.dele.reset_mock()
        self.assertTrue(self.ch.mark_message('00000011506477be'))
        pop3srv.dele.assert_called_once_with('2')

        pop3srv.dele.reset_mock()
        self.assertTrue(not self.ch.mark_message('99900011506477be'))
        self.assertTrue(not pop3srv.dele.called)


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
