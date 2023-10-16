import logging
import os
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import tag, TestCase

from .servers import MockSFTPClient, MockSSHClient, MockSSHClientWithError
from ..sftp_client import logger, SFTPClient, SFTPClientError
from ..ssh_client import SSHClient, SSHClientError


@tag('connect')
class TestConnector(TestCase):
    databases = '__all__'

    def setUp(self):
        self.original_SSHClient = SSHClient

    def tearDown(self):
        global SSHClient
        SSHClient = self.original_SSHClient

    def test_localhost_trusted(self):
        global SSHClient
        SSHClient = MockSSHClient
        ssh_client = SSHClient(remote_host='localhost', trusted_host=True)
        ssh_client.connect()
        with ssh_client as c:
            self.assertTrue(c.connected)
        c.close()
        self.assertFalse(ssh_client.connected)

    def test_username(self):
        with patch('edc_sync_files.tests.test_connection.SSHClient',
                   new=MockSSHClientWithError):
            remote_host = '127.0.0.1'
            options = dict(remote_host=remote_host,
                           trusted_host=False,
                           username='bob',
                           timeout=1)

            trusted_host = True
            options.update(trusted_host=trusted_host)
            ssh_client = SSHClient(**options)
            try:
                with ssh_client.connect() as c:
                    c.close()
            except SSHClientError as e:
                self.assertEqual(str(e), 'Authentication failed.')
            else:
                self.fail('SSHClientError unexpectedly not raised')

            trusted_host = False
            options.update(trusted_host=trusted_host)
            ssh_client = SSHClient(**options)
            try:
                with ssh_client.connect() as c:
                    c.close()
            except SSHClientError as e:
                self.assertEqual(str(e),
                                 f'Server \'{remote_host}\' not found in known_hosts')
            else:
                self.fail('SSHClientError unexpectedly not raised')

    def test_timeout_nottrusted(self):
        with patch('edc_sync_files.tests.test_connection.SSHClient',
                   new=MockSSHClientWithError):
            remote_host = '127.0.0.1'
            ssh_client = SSHClient(remote_host=remote_host,
                                   trusted_host=False, timeout=1)
            try:
                with ssh_client.connect() as c:
                    c.close()
            except SSHClientError as e:
                self.assertEqual(
                    str(e), f'Server \'{remote_host}\' not found in known_hosts')
            else:
                self.fail('SSHClientError unexpectedly not raised')

    def test_timeout_trusted(self):
        ssh_client = SSHClient(remote_host='127.0.0.0',
                               trusted_host=True, timeout=1)
        try:
            with ssh_client.connect() as c:
                c.close()
        except SSHClientError as e:
            self.assertEqual(str(e.__cause__),
                             'No authentication methods available')
        else:
            self.fail('SSHClientError unexpectedly not raised')

    def test_timeout_not_trusted(self):
        with patch('edc_sync_files.tests.test_connection.SSHClient',
                   new=MockSSHClientWithError):
            ssh_client = SSHClient(remote_host='localhost',
                                   trusted_host=True,
                                   username='thing1',
                                   timeout=1)
            try:
                with ssh_client.connect() as c:
                    c.close()
            except SSHClientError as e:
                self.assertEqual(str(e), 'Authentication failed.')
            else:
                self.fail('SSHClientError unexpectedly not raised')

    def test_sftp_closes(self):
        with patch('edc_sync_files.tests.test_connection.SSHClient', new=MockSSHClient):
            ssh_client = SSHClient(remote_host='localhost',
                                   trusted_host=True, timeout=1)
        with ssh_client.connect() as ssh_conn:
            sftp_client = SFTPClient()
            with sftp_client.connect(ssh_conn=ssh_conn) as sftp_conn:
                sftp_conn.close()

    def test_sftp_put(self):
        with patch('edc_sync_files.tests.test_connection.SSHClient', new=MockSSHClient), \
                patch('edc_sync_files.tests.test_connection.SFTPClient',
                      new=MockSFTPClient):
            ssh_client = SSHClient(remote_host='localhost',
                                   trusted_host=True, timeout=1)
            _, src = tempfile.mkstemp()
            dst = tempfile.mktemp()

            with ssh_client.connect() as ssh_conn:
                sftp_client = SFTPClient()

                with sftp_client.connect(ssh_conn=ssh_conn) as sftp_conn:
                    sftp_conn.put(src, dst)

            # Assertions
            self.assertEqual(1, len(sftp_conn.put_args))  # put was called once
            self.assertEqual(src, sftp_conn.put_args[0][
                0])  # put was called with src as first argument
            self.assertEqual(dst, sftp_conn.put_args[0][1])

            with sftp_client.connect(ssh_conn=ssh_conn) as sftp_conn:
                sftp_conn.update_progress(1, 100)

            self.assertEqual(1,
                             len(sftp_conn.progress_updates))
            self.assertEqual(1, sftp_conn.progress_updates[0][
                0])
            self.assertEqual(100, sftp_conn.progress_updates[0][1])

    def test_sftp_put_src_ioerror(self):
        with patch('edc_sync_files.tests.test_connection.SSHClient', new=MockSSHClient):
            ssh_client = SSHClient(remote_host='localhost',
                                   trusted_host=True, timeout=1)
            src = tempfile.mktemp()
            dst = tempfile.mktemp()
            with ssh_client.connect() as ssh_conn:
                sftp_client = SFTPClient()
                with sftp_client.connect(ssh_conn=ssh_conn) as sftp_conn:
                    self.assertRaises(SFTPClientError, sftp_conn.put, src, dst)
            self.assertFalse(os.path.exists(dst))

    def test_sftp_put_dst_ioerror(self):
        with patch('edc_sync_files.tests.test_connection.SSHClient', new=MockSSHClient):
            ssh_client = SSHClient(remote_host='localhost',
                                   trusted_host=True, timeout=1)
            src = tempfile.mktemp()
            dst = f'/badfolder/{tempfile.mktemp()}'
            with ssh_client.connect() as ssh_conn:
                sftp_client = SFTPClient()
                with sftp_client.connect(ssh_conn=ssh_conn) as sftp_conn:
                    self.assertRaises(SFTPClientError, sftp_conn.put, src, dst)
            self.assertFalse(os.path.exists(dst))

    def test_sftp_progress(self):
        with patch('edc_sync_files.tests.test_connection.SSHClient', new=MockSSHClient):
            ssh_client = SSHClient(remote_host='localhost',
                                   trusted_host=True, timeout=1)
            with ssh_client.connect() as ssh_conn:
                sftp_client = SFTPClient(verbose=True)
                with sftp_client.connect(ssh_conn=ssh_conn) as sftp_conn:
                    sftp_conn.update_progress(1, 100)

    @tag('connect')
    def test_sftp_put_progress(self):
        with patch('edc_sync_files.tests.test_connection.SSHClient', new=MockSSHClient):
            ssh_client = SSHClient(remote_host='localhost', trusted_host=True, timeout=1)
            _, src = tempfile.mkstemp(text=True)
            with open(src, 'w') as fd:
                fd.write('erik' * 10000)
            src_filename = os.path.basename(src)
            src_path = os.path.dirname(src)
            dst_tmp_path = f'{tempfile.gettempdir()}/tmp'
            if not os.path.exists(dst_tmp_path):
                os.mkdir(dst_tmp_path)
            dst_path = f'{tempfile.gettempdir()}/dst'
            if not os.path.exists(dst_path):
                os.mkdir(dst_path)
            with ssh_client.connect() as ssh_conn:
                sftp_client = SFTPClient(
                    verbose=True,
                    dst_path=dst_path,
                    dst_tmp=dst_tmp_path,
                    dst_tmp_path=dst_tmp_path,
                    src_path=src_path)
                with sftp_client.connect(ssh_conn=ssh_conn) as sftp_conn:
                    with self.assertLogs(logger=logger, level=logging.INFO) as cm:
                        sftp_conn.copy(filename=src_filename)
            expected_source = os.path.join(src_path, src_filename)
            expected_destination = os.path.join(dst_tmp_path, src_filename)
            self.assertIn((expected_source, expected_destination,
                           sftp_client.update_progress, True),
                          ssh_conn.open_sftp().put_args)
            self.assertIsNotNone(cm.output)
