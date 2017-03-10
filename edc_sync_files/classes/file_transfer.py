import socket
import os.path
import shutil
from os.path import join
import collections

from hurry.filesize import size
from os import listdir

from django.apps import apps as django_apps

from edc_base.utils import get_utcnow

from .transaction_messages import transaction_messages
from ..models import History
from ..constants import REMOTE
from .mixins import SSHConnectMixin


class FileConnector(SSHConnectMixin):
    """Connects to the file system given (host & password) or (ssh key pair.).
       1. Copies files from source folder to destination folder in file system.
       2. Copies files from file system to remote file system.
    """

    def __init__(self, host=None, password=None, source_folder=None,
                 destination_folder=None, archive_folder=None):
        self.trusted_host = True
        edc_sync_file_app = django_apps.get_app_config('edc_sync_files')
        self.progress_status = None
        self.host = host or edc_sync_file_app.host
        self.password = password or edc_sync_file_app.password
        self.user = edc_sync_file_app.user
        self.source_folder = source_folder or edc_sync_file_app.source_folder
        self.destination_folder = destination_folder or edc_sync_file_app.destination_folder
        self.archive_folder = archive_folder or edc_sync_file_app.archive_folder

    def connected(self):
        ssh = None
        client = self.connect(REMOTE)
        if client:
            ssh = client.open_sftp()
        connected = True if ssh else False
        if connected:
            ssh.close()
        return connected

    def progress(self, sent_bytes, total_bytes):
        self.progress_status = (sent_bytes / total_bytes) * 100
        print("Progress ", self.progress_status, "%")

    def copy(self, filename):
        """ Copy file from  source folder to destination folder in the
            current filesystem or to remote file system."""
        client = self.connect(REMOTE)
        host_sftp = client.open_sftp()
        destination_file_origin = os.path.join(self.destination_folder, filename)
        destination_file_tmp = '{}.{}'.format(
            os.path.join(self.destination_folder, filename), 'tmp')
        sent = True
        source_filename = os.path.join(self.source_folder, filename)
        try:
            sent_file = host_sftp.put(
                source_filename,
                destination_file_tmp,
                callback=self.progress, confirm=True)
            transaction_messages.add_message(
                'success', 'File {} sent to the'
                ' server successfully.'.format(source_filename))
            host_sftp.rename(
                destination_file_tmp,
                destination_file_origin)
            host_sftp.utime(destination_file_origin, None)  # Activate on modified for watchdog to detect a file.
            transaction_messages.add_message(
                'success', 'Renamed {} to {} successfully in the server.'.format
                (destination_file_tmp, source_filename))
        except IOError as e:
            sent = False
            transaction_messages.add_message(
                'error', 'IOError Got {} . Sending {}'.format(e, destination_file_origin))
            return False
        received_file = host_sftp.lstat(destination_file_origin)
        if received_file.st_size == sent_file.st_size:
            pass
        print(received_file.st_size, "received file", sent_file.st_size, "sent file")
        #  create a record on successful transfer
        if sent:
            self.update_history(filename, sent=sent)
            transaction_messages.add_message(
                'success', 'History record created for {}.'.format(source_filename))
        return sent

    def archive(self, filename):
        """ Move file from source_folder to archive folder """
        archived = True
        try:
            source_filename = join(self.source_folder, filename)
            destination_filename = join(self.archive_folder, filename)
            shutil.move(source_filename, destination_filename)
            transaction_messages.add_message(
                'success', 'Archived successfully {}.'.format(source_filename))
        except FileNotFoundError as e:
            archived = False
            transaction_messages.add_message(
                'error', 'FileNotFoundError Got {}'.format(str(e)))
        return archived

    def update_history(self, filename, sent=False):
        history = History.objects.get(filename=filename)
        history.sent = sent
        history.sent_datetime = get_utcnow()
        history.save()
        return history

    @property
    def hostname(self):
        device = self.connect(REMOTE)
        _, stdout, _ = device.exec_command('hostname')
        hostname = stdout.read()
        if isinstance(hostname, bytes):
            hostname = hostname.decode('utf-8')
        device.close()
        return hostname

    @property
    def localhost_hostname(self):
        return socket.gethostname()


class FileTransfer(object):
    """Transfer a list of files to the remote host or within host.
    """

    def __init__(self, file_connector=None):
        self.file_connector = file_connector or FileConnector()
        self.ordered_files = collections.OrderedDict()

    @property
    def files(self):
        files = listdir(self.file_connector.source_folder)
        try:
            files.remove('.DS_Store')
        except ValueError:
            pass
        return files

    @property
    def files_dict(self):
        file_attrs = []
        recorded_files = History.objects.filter(
            filename__in=self.files, sent=False).order_by('created')
        for history in recorded_files:
            source_filename = os.path.join(
                self.file_connector.source_folder, history.filename)
            file_attr = os.stat(source_filename)
            data = dict({
                'filename': history.filename,
                'filesize': size(file_attr.st_size),
            })
            file_attrs.append(data)
        return file_attrs

    def copy_files(self, filename=None):
        """ Copies the files from source folder to destination folder. """
        copied = False
        if filename:  # Use by client by machine
            for f in self.files_dict:
                if f.get('filename') == filename:
                    copied = self.file_connector.copy(f.get('filename'))
        else:  # Use by community server to send files to community server
            for f in self.files_dict:
                filename = f.get('filename')
                copied = self.file_connector.copy(filename)
                if copied:
                    self.archive(filename)
                    # reset
                    copied = False
        return copied

    def archive(self, filename):
        return self.file_connector.archive(filename)

    def approve_sent_file(self, filename, approval_code):
        try:
            sent_file_history = History.objects.get(filename=filename)
            sent_file_history.approval_code = approval_code
            sent_file_history.save()
        except History.DoesNotExist:
            pass