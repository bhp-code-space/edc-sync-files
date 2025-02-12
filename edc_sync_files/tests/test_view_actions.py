import os
import tempfile
from unittest.mock import patch

from django.apps import apps as django_apps
from django.conf import settings
from django.test import tag, TestCase
from edc_sync.models import OutgoingTransaction
from faker import Faker

from .models import TestModel
from .servers import MockSSHClient, MockSSHClientWithError
from ..action_handler import ActionHandler, ActionHandlerError
from ..constants import CONFIRM_BATCH, EXPORT_BATCH, PENDING_FILES, SEND_FILES
from ..models import ExportedTransactionFileHistory

fake = Faker()

app_config = django_apps.get_app_config('edc_sync_files')


@tag('actions')
class TestActionHandler(TestCase):
    multi_db = True
    databases = '__all__'

    def setUp(self):
        ExportedTransactionFileHistory.objects.using('client').all().delete()
        OutgoingTransaction.objects.using('client').all().delete()
        TestModel.objects.using('client').all().delete()
        TestModel.objects.using('client').create(f1=fake.name())
        TestModel.objects.using('client').create(f1=fake.name())

    def test_invalid_action(self):
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClient):
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                media_path=app_config.log_folder,
                media_dst=app_config.log_folder,
                media_tmp=app_config.tmp_folder,
                remote_host='localhost')
            action_handler = ActionHandler(**kwargs)
            self.assertRaises(
                ActionHandlerError, action_handler.action, label='blahblah')

    def test_export_batch(self):
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClient):
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                media_path=app_config.log_folder,
                media_dst=app_config.log_folder,
                media_tmp=app_config.tmp_folder,
                remote_host='localhost')
            action_handler = ActionHandler(**kwargs)
            action_handler.action(label=EXPORT_BATCH)
            self.assertFalse(action_handler.data.get('errmsg'))
            self.assertGreater(
                action_handler.history_model.objects.using('client').all().count(), 0)

    def test_export_batch_error(self):
        """Asserts raises error if export fails.
        """
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClient):
            bad_src_path = os.path.join(tempfile.gettempdir(), 'bad_src_path')
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                remote_host='localhost')
            action_handler = ActionHandler(**kwargs)
            action_handler.tx_exporter.path = bad_src_path
            self.assertRaises(
                ActionHandlerError,
                action_handler.action, label=EXPORT_BATCH)

    def test_send_files(self):
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClient):
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                media_path=app_config.log_folder,
                media_dst=app_config.log_folder,
                media_tmp=app_config.tmp_folder,
                remote_host='localhost')
            action_handler = ActionHandler(**kwargs)
            action_handler.action(label=EXPORT_BATCH)
            action_handler = ActionHandler(**kwargs)
            action_handler.action(label=SEND_FILES)
            self.assertFalse(action_handler.data.get('errmsg'))

    def test_send_files_error(self):
        """Asserts raises error if send fails.
        """
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClientWithError):
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                media_path=app_config.log_folder,
                media_dst=app_config.log_folder,
                media_tmp=app_config.tmp_folder,
                remote_host='localhost')
            action_handler = ActionHandler(**kwargs)
            action_handler.action(label=EXPORT_BATCH)
            action_handler = ActionHandler(trusted_host=False, **kwargs)
            self.assertRaises(ActionHandlerError,
                              action_handler.action, label=SEND_FILES)

    def test_send_files_invalid_user_error(self):
        """Asserts raises error if send fails on invalid user.
        """
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClientWithError):
            remote_host = '127.0.0.1'
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                media_path=app_config.log_folder,
                media_dst=app_config.log_folder,
                media_tmp=app_config.tmp_folder,
                remote_host=remote_host)
            action_handler = ActionHandler(**kwargs)
            action_handler.action(label=EXPORT_BATCH)
            action_handler = ActionHandler(
                trusted_host=False, username='bob', **kwargs)
            try:
                action_handler.action(label=SEND_FILES)
            except ActionHandlerError as e:
                self.assertIn(f'Server \'{remote_host}\' not found in known_hosts',
                              str(e.__cause__))
            else:
                self.fail('ActionHandlerError unexpectedly not raised')

    def test_send_and_archive_files(self):
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClient):
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                media_path=app_config.log_folder,
                media_dst=app_config.log_folder,
                media_tmp=app_config.tmp_folder,
                remote_host='localhost')
            action_handler = ActionHandler(**kwargs)
            action_handler.action(label=EXPORT_BATCH)
            action_handler = ActionHandler(**kwargs)
            action_handler.action(label=SEND_FILES)
            for filename in action_handler.data.get('last_sent_files'):
                self.assertFalse(os.path.exists(
                    os.path.join(app_config.outgoing_folder, filename)))
            for filename in action_handler.data.get('last_archived_files'):
                self.assertTrue(os.path.exists(
                    os.path.join(app_config.archive_folder, filename)))
            self.assertEqual(action_handler.data.get('pending_files'), [])

    def test_pending_files(self):
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClient):
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                media_path=app_config.log_folder,
                media_dst=app_config.log_folder,
                media_tmp=app_config.tmp_folder,
                remote_host='localhost')
            for _ in range(0, 3):
                action_handler = ActionHandler(**kwargs)
                action_handler.action(label=EXPORT_BATCH)
                TestModel.objects.using('client').create(f1=fake.name())
                TestModel.objects.using('client').create(f1=fake.name())
            action_handler = ActionHandler(**kwargs)
            action_handler.action(label=PENDING_FILES)
            self.assertEqual(len(action_handler.data.get('pending_files')), 3)

    def test_pending_count(self):
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClient):
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                remote_host='localhost')
            for _ in range(0, 3):
                action_handler = ActionHandler(**kwargs)
                action_handler.action(label=EXPORT_BATCH)
                TestModel.objects.using('client').create(f1=fake.name())
                TestModel.objects.using('client').create(f1=fake.name())
            action_handler = ActionHandler(**kwargs)
            self.assertGreater(len(action_handler.pending_filenames), 0)
            self.assertEqual(len(action_handler.pending_filenames), 3)

    def test_pending_empty_after_sends_all(self):
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClient):
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                media_path=app_config.log_folder,
                media_dst=app_config.log_folder,
                media_tmp=app_config.tmp_folder,
                remote_host='localhost')
            for _ in range(0, 3):
                action_handler = ActionHandler(**kwargs)
                action_handler.action(label=EXPORT_BATCH)
                TestModel.objects.using('client').create(f1=fake.name())
                TestModel.objects.using('client').create(f1=fake.name())
            action_handler = ActionHandler(**kwargs)
            self.assertEqual(len(action_handler.pending_filenames), 3)
            action_handler.action(label=SEND_FILES)
            self.assertEqual(len(action_handler.pending_filenames), 0)

    def test_confirm_not_sent_raises(self):
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClient):
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                media_path=app_config.log_folder,
                media_dst=app_config.log_folder,
                media_tmp=app_config.tmp_folder,
                remote_host='localhost')
            for _ in range(0, 3):
                action_handler = ActionHandler(**kwargs)
                action_handler.action(label=EXPORT_BATCH)
                TestModel.objects.using('client').create(f1=fake.name())
                TestModel.objects.using('client').create(f1=fake.name())
            action_handler = ActionHandler(**kwargs)
            self.assertRaises(ActionHandlerError,
                              action_handler.action, label=CONFIRM_BATCH)

    def test_confirm(self):
        with patch('edc_sync_files.transaction.transaction_file_sender.SSHClient',
                   new=MockSSHClient):
            kwargs = dict(
                using='client',
                src_path=app_config.outgoing_folder,
                dst_tmp=app_config.tmp_folder,
                media_tmp=app_config.tmp_folder,
                dst_path=app_config.incoming_folder,
                archive_path=app_config.archive_folder,
                media_path=app_config.log_folder,
                media_dst=app_config.log_folder,
                remote_host='localhost')
            for _ in range(0, 3):
                action_handler = ActionHandler(**kwargs)
                action_handler.action(label=EXPORT_BATCH)
                TestModel.objects.using('client').create(f1=fake.name())
                TestModel.objects.using('client').create(f1=fake.name())
            for _ in range(0, 3):
                action_handler = ActionHandler(**kwargs)
                action_handler.action(label=SEND_FILES)
            action_handler = ActionHandler(**kwargs)
            action_handler.action(label=CONFIRM_BATCH)
            self.assertIsNotNone(action_handler.data.get('confirmation_code'))
