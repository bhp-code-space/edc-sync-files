from edc_base.utils import get_utcnow

from ..ssh_client import SSHClient, SSHClientError
from ..sftp_client import SFTPClient, SFTPClientError
from .file_archiver import FileArchiver


class TransactionFileSenderError(Exception):
    pass


class TransactionFileSender:

    def __init__(self, remote_host=None, username=None, src_path=None, dst_tmp=None,
                 dst_path=None, archive_path=None, history_model=None, using=None,
                 update_history_model=None, media_path=None, media_tmp=None, media_dst=None, **kwargs):
        self.using = using
        self.media_path = media_path
        self.media_dst = media_dst
        self.media_tmp = media_tmp
        self.update_history_model = True if update_history_model is None else update_history_model
        self.file_archiver = FileArchiver(
            src_path=src_path, dst_path=archive_path)
        self.history_model = history_model
        self.ssh_client = SSHClient(
            username=username, remote_host=remote_host, **kwargs)
        self.sftp_client = SFTPClient(
            src_path=src_path, dst_tmp=dst_tmp, dst_path=dst_path, **kwargs)

    def send(self, filenames=None):
        """Sends the file to the remote host and archives the sent file locally.
        """
        try:
            with self.ssh_client.connect() as ssh_conn:
                with self.sftp_client.connect(ssh_conn) as sftp_conn:
                    for filename in filenames:
                        sftp_conn.copy(filename=filename)
                        self.archive(filename=filename)
                        if self.update_history_model:
                            self.update_history(filename=filename)
        except SSHClientError as e:
            raise TransactionFileSenderError(e) from e
        except SFTPClientError as e:
            raise TransactionFileSenderError(e) from e
        return filenames

    def send_media(self, filenames=None):
        sftp_client = SFTPClient(
            src_path=self.media_path, dst_tmp=self.media_tmp, dst_path=self.media_dst)
        try:
            with self.ssh_client.connect() as ssh_conn:
                with sftp_client.connect(ssh_conn) as sftp_conn:
                    for filename in filenames:
                        sftp_conn.copy(filename=filename)
                        self.update_media_log(filename)
        except SSHClientError as e:
            raise TransactionFileSenderError(e) from e
        except SFTPClientError as e:
            raise TransactionFileSenderError(e) from e
        return filenames

    def update_history(self, filename=None):
        try:
            obj = self.history_model.objects.using(
                self.using).get(filename=filename)
        except self.history_model.DoesNotExist as e:
            raise TransactionFileSenderError(
                f'History does not exist for file \'{filename}\'. Got {e}') from e
        else:
            obj.sent = True
            obj.sent_datetime = get_utcnow()
            obj.save()

    def update_media_log(self, filename):
        media_path = '%(path)s/%(filename)s' % {'path': self.media_path, 'filename': 'log.txt'}
        f = open(media_path, 'a')
        f.write(filename+'\n')
        f.close()

    def archive(self, filename):
        self.file_archiver.archive(filename=filename)
